"""Command-line entry point."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import click

from .calibration import report as calibration_report
from .config import Policy
from .promotion import PromotionInputs, evaluate as evaluate_promotion
from .replay import reconstruct_trade, summarize as summarize_log
from .runtime import build_default_runtime, run_forever
from .secrets import credentials_summary, load_credentials
from .subagents.heartbeat import Heartbeat


@click.group()
def main() -> None:
    """POLYFLOW CLI."""


@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default="configs/policy.yaml", show_default=True)
@click.option("--log", "log_path", type=click.Path(dir_okay=False, path_type=Path), default="logs/immutable.jsonl", show_default=True)
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default="logs/polyflow.db", show_default=True)
@click.option("--scan-seconds", type=int, default=300, show_default=True)
def run(config_path: Path, log_path: Path, db_path: Path, scan_seconds: int) -> None:
    """Run the runtime against the given policy. Stub adapters by default."""
    policy = Policy.from_yaml(config_path)
    rt = build_default_runtime(policy, str(log_path), db_path=str(db_path))
    rt.heartbeat = Heartbeat(log_path.parent / "heartbeat.json")
    asyncio.run(run_forever(rt, scan_seconds=scan_seconds))


@main.command("scan-once")
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default="configs/policy.yaml", show_default=True)
@click.option("--log", "log_path", type=click.Path(dir_okay=False, path_type=Path), default="logs/immutable.jsonl", show_default=True)
def scan_once(config_path: Path, log_path: Path) -> None:
    """Run a single scanner tick. Useful for inspection and CI."""
    policy = Policy.from_yaml(config_path)
    rt = build_default_runtime(policy, str(log_path))
    approved = asyncio.run(rt.tick_scan())
    click.echo(json.dumps({"approved": approved, "watchlist_size": len(rt.watchlist)}, indent=2))


@main.command("show-policy")
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default="configs/policy.yaml", show_default=True)
def show_policy(config_path: Path) -> None:
    """Echo the parsed policy (with config hash) for inspection."""
    policy = Policy.from_yaml(config_path)
    click.echo(policy.model_dump_json(indent=2))


@main.command()
@click.option("--log", "log_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default="logs/immutable.jsonl", show_default=True)
def status(log_path: Path) -> None:
    """Tail the immutable log + heartbeat status."""
    hb = Heartbeat(log_path.parent / "heartbeat.json").last_seen()
    age = (
        (datetime.now(timezone.utc) - hb).total_seconds()
        if hb is not None
        else None
    )
    last_lines: list[dict] = []
    if log_path.exists():
        # Read the last 5 records without loading the whole file
        with log_path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(8192, size)
            f.seek(size - chunk, 0)
            tail = f.read().decode("utf-8", errors="replace").splitlines()
        for line in tail[-5:]:
            try:
                last_lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    click.echo(
        json.dumps(
            {
                "heartbeat_last_seen": hb.isoformat() if hb else None,
                "heartbeat_age_seconds": age,
                "recent_log": last_lines,
            },
            indent=2,
            default=str,
        )
    )


@main.command()
@click.option("--predictions", type=str, required=True, help="comma-separated predicted probabilities")
@click.option("--outcomes", type=str, required=True, help="comma-separated 0/1 realized outcomes")
def calibrate(predictions: str, outcomes: str) -> None:
    """Compute Brier / log-loss / bucket calibration for a predictions, outcomes pair."""
    p = [float(x) for x in predictions.split(",") if x]
    o = [int(x) for x in outcomes.split(",") if x]
    rep = calibration_report(p, o)
    click.echo(
        json.dumps(
            {
                "n": rep.n,
                "brier": rep.brier,
                "log_loss": rep.log_loss,
                "buckets": rep.buckets,
            },
            indent=2,
        )
    )


@main.command("promotion-check")
@click.option("--observer-days", type=int, required=True)
@click.option("--paper-days", type=int, required=True)
@click.option("--paper-trades", type=int, required=True)
@click.option("--live-tiny-trades", type=int, required=True)
@click.option("--unexplained-pnl", type=int, default=0, show_default=True)
@click.option("--kelly-breaches", type=int, default=0, show_default=True)
@click.option("--unlogged-actions", type=int, default=0, show_default=True)
@click.option("--has-calibration/--no-calibration", default=True, show_default=True)
@click.option("--clv-positive/--clv-not-positive", default=True, show_default=True)
@click.option("--hook-pass-rate", type=float, default=1.0, show_default=True)
def promotion_check(
    observer_days: int,
    paper_days: int,
    paper_trades: int,
    live_tiny_trades: int,
    unexplained_pnl: int,
    kelly_breaches: int,
    unlogged_actions: int,
    has_calibration: bool,
    clv_positive: bool,
    hook_pass_rate: float,
) -> None:
    """Check whether the LIVE_TINY -> LIVE_STANDARD promotion gates pass."""
    decision = evaluate_promotion(
        PromotionInputs(
            observer_days=observer_days,
            paper_days=paper_days,
            paper_trades=paper_trades,
            live_tiny_trades=live_tiny_trades,
            unexplained_pnl_events=unexplained_pnl,
            kelly_breaches=kelly_breaches,
            unlogged_actions=unlogged_actions,
            calibration_report_present=has_calibration,
            closing_line_value_positive=clv_positive,
            post_order_hook_pass_rate=hook_pass_rate,
        )
    )
    click.echo(json.dumps({"promote": decision.promote, "reasons": list(decision.reasons)}, indent=2))


@main.command("creds-check")
def creds_check() -> None:
    """Print a redacted summary of loaded credentials and what's still missing."""
    creds = load_credentials()
    click.echo(json.dumps(credentials_summary(creds), indent=2))


@main.command("derive-creds")
@click.option(
    "--write/--no-write",
    default=False,
    help="Append derived secret + passphrase to .env.local (never overwrites existing).",
)
def derive_creds(write: bool) -> None:
    """Sign the ClobAuth message with POLY_PRIVATE_KEY and call /auth/api-key.

    Returns redacted credentials. Pass --write to persist them into .env.local
    (existing keys are preserved; we never overwrite).
    """
    from .adapters.polymarket_clob_trade import derive_api_credentials

    creds = load_credentials()
    if not creds.private_key:
        click.echo(
            "POLY_PRIVATE_KEY is not set. Add it to .env.local before deriving credentials.",
            err=True,
        )
        raise SystemExit(2)

    async def _run() -> dict:
        derived = await derive_api_credentials(private_key=creds.private_key)
        return {
            "apiKey": f"{derived.api_key[:4]}...{derived.api_key[-4:]}",
            "secret": "<set>",
            "passphrase": "<set>",
            "_full": derived,
        }

    out = asyncio.run(_run())
    derived = out.pop("_full")

    if write:
        env_path = Path(".env.local")
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        lines: list[str] = []
        for key, value in (
            ("POLY_API_KEY", derived.api_key),
            ("POLY_API_SECRET", derived.secret),
            ("POLY_API_PASSPHRASE", derived.passphrase),
        ):
            if key in existing or key.replace("_", "") in existing:
                continue
            lines.append(f"{key}={value}")
        if lines:
            with env_path.open("a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write("\n".join(lines) + "\n")
            click.echo(f"Wrote {len(lines)} new keys to {env_path}.", err=True)

    click.echo(json.dumps(out, indent=2))


@main.command()
@click.option("--limit", type=int, default=50, show_default=True)
def positions(limit: int) -> None:
    """Fetch the live wallet's positions from the Polymarket Data API."""
    creds = load_credentials()
    if not creds.wallet_address:
        click.echo("No wallet address configured. Set POLY_WALLET_ADDRESS or POLYAPIADDRESS.", err=True)
        raise SystemExit(2)

    from .adapters.polymarket_user import PolymarketUserAdapter

    async def _run() -> list[dict]:
        async with PolymarketUserAdapter(wallet_address=creds.wallet_address) as adapter:
            return await adapter.positions()

    rows = asyncio.run(_run())
    click.echo(json.dumps(rows[:limit], indent=2, default=str))


@main.command("summarize-log")
@click.option("--log", "log_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default="logs/immutable.jsonl", show_default=True)
def summarize_log_cmd(log_path: Path) -> None:
    """Print actor / action / kill-switch / order counts from the immutable log."""
    s = summarize_log(log_path)
    click.echo(
        json.dumps(
            {
                "total_records": s.total_records,
                "kill_switch_events": s.kill_switch_events,
                "placed_orders": s.placed_orders,
                "rejected_orders": s.rejected_orders,
                "by_actor": s.by_actor,
                "by_action": s.by_action,
            },
            indent=2,
        )
    )


@main.command("replay-trade")
@click.option("--log", "log_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default="logs/immutable.jsonl", show_default=True)
@click.option("--signal-id", required=True)
def replay_trade_cmd(log_path: Path, signal_id: str) -> None:
    """Reconstruct every log record relevant to a single signal_id."""
    records = reconstruct_trade(log_path, signal_id=signal_id)
    out = [
        {"ts": r.ts, "actor": r.actor, "action": r.action,
         "market_id": r.market_id, "payload": r.payload}
        for r in records
    ]
    click.echo(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
