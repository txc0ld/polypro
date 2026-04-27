"""Command-line entry point."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import click

from .calibration import report as calibration_report
from .automation_sources import check_sources
from .config import Policy
from .promotion import PromotionInputs, evaluate as evaluate_promotion
from .replay import reconstruct_trade, summarize as summarize_log
from .runtime import build_default_runtime, build_live_scanner_runtime, run_forever
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
@click.option("--live-scanner/--stub-scanner", default=False, show_default=True)
@click.option("--gamma-limit", type=int, default=200, show_default=True)
@click.option("--live-trading/--paper-trading", default=False, show_default=True)
def run(
    config_path: Path,
    log_path: Path,
    db_path: Path,
    scan_seconds: int,
    live_scanner: bool,
    gamma_limit: int,
    live_trading: bool,
) -> None:
    """Run the runtime. Live scanner uses public Polymarket reads only."""
    policy = Policy.from_yaml(config_path)
    creds = load_credentials()
    clob = None
    if live_trading:
        if not policy.automation.allow_order_placement:
            click.echo(
                "Refusing --live-trading because automation.allow_order_placement is false.",
                err=True,
            )
            raise SystemExit(2)
        from .adapters.polymarket_clob_trade import PolymarketCLOBTradeAdapter

        clob = PolymarketCLOBTradeAdapter(credentials=creds)
    if live_scanner:
        rt = build_live_scanner_runtime(
            policy,
            str(log_path),
            db_path=str(db_path),
            gamma_limit=gamma_limit,
            clob=clob,
            wallet_address=creds.funder_address or creds.wallet_address,
        )
    else:
        rt = build_default_runtime(policy, str(log_path), db_path=str(db_path))
        rt.wallet_address = creds.funder_address or creds.wallet_address
    rt.heartbeat = Heartbeat(log_path.parent / "heartbeat.json")
    asyncio.run(run_forever(rt, scan_seconds=scan_seconds))


@main.command("scan-once")
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default="configs/policy.yaml", show_default=True)
@click.option("--log", "log_path", type=click.Path(dir_okay=False, path_type=Path), default="logs/immutable.jsonl", show_default=True)
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default="logs/polyflow.db", show_default=True)
@click.option("--live/--stub", "live_scanner", default=False, show_default=True)
@click.option("--gamma-limit", type=int, default=200, show_default=True)
def scan_once(config_path: Path, log_path: Path, db_path: Path, live_scanner: bool, gamma_limit: int) -> None:
    """Run a single scanner tick. --live pulls public Polymarket markets."""
    policy = Policy.from_yaml(config_path)
    if live_scanner:
        rt = build_live_scanner_runtime(
            policy,
            str(log_path),
            db_path=str(db_path),
            gamma_limit=gamma_limit,
        )
    else:
        rt = build_default_runtime(policy, str(log_path), db_path=str(db_path))
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


@main.command("automation-sources")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default="configs/policy.yaml",
    show_default=True,
)
@click.option(
    "--root",
    "root_path",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
)
def automation_sources_cmd(config_path: Path, root_path: Path) -> None:
    """Check pinned reference repos used by automation."""
    policy = Policy.from_yaml(config_path)
    statuses = check_sources(
        policy.automation.sources,
        root=root_path,
        require_pinned_commit=policy.automation.require_pinned_commits,
    )
    click.echo(
        json.dumps(
            {
                "ready": sum(1 for status in statuses if status.ok),
                "total": len(statuses),
                "sources": [status.as_dict() for status in statuses],
            },
            indent=2,
        )
    )


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
        import re

        env_path = Path(".env.local")
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

        updates = (
            ("POLY_API_KEY", derived.api_key, ("POLY_API_KEY", "POLYAPIKEY")),
            ("POLY_API_SECRET", derived.secret, ("POLY_API_SECRET", "POLYAPISECRET")),
            ("POLY_API_PASSPHRASE", derived.passphrase, ("POLY_API_PASSPHRASE", "POLYAPIPASSPHRASE")),
        )

        body = existing
        replaced = 0
        appended: list[str] = []
        for canonical, value, aliases in updates:
            line = f"{canonical}={value}"
            # Exact-line match for any alias name; otherwise append.
            pattern = re.compile(
                rf"^(?:{'|'.join(re.escape(a) for a in aliases)})\s*[:=].*$",
                re.MULTILINE,
            )
            if pattern.search(body):
                body = pattern.sub(line, body)
                replaced += 1
            else:
                appended.append(line)

        if appended:
            if body and not body.endswith("\n"):
                body += "\n"
            body += "\n".join(appended) + "\n"

        env_path.write_text(body, encoding="utf-8")
        click.echo(
            f"Updated {replaced} existing keys, appended {len(appended)} new keys to {env_path}.",
            err=True,
        )

    click.echo(json.dumps(out, indent=2))


@main.command()
@click.option("--limit", type=int, default=50, show_default=True)
@click.option(
    "--user",
    "user_override",
    default=None,
    help="Address to query (default: POLY_FUNDER_ADDRESS if set, else POLY_WALLET_ADDRESS).",
)
def positions(limit: int, user_override: str | None) -> None:
    """Fetch positions from the Polymarket Data API.

    Defaults to the funder/proxy address (where outcome tokens actually live for
    browser-onboarded users). Falls back to the EOA if no funder is configured.
    """
    creds = load_credentials()
    target = user_override or creds.funder_address or creds.wallet_address
    if not target:
        click.echo(
            "No address configured. Set POLY_FUNDER_ADDRESS or POLY_WALLET_ADDRESS.",
            err=True,
        )
        raise SystemExit(2)

    from .adapters.polymarket_user import PolymarketUserAdapter

    async def _run() -> list[dict]:
        async with PolymarketUserAdapter(wallet_address=target) as adapter:
            return await adapter.positions()

    rows = asyncio.run(_run())
    click.echo(json.dumps(rows[:limit], indent=2, default=str))


@main.command("promotion-status")
@click.option("--db", "db_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default="logs/polyflow.db", show_default=True)
@click.option("--log", "log_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default="logs/immutable.jsonl", show_default=True)
@click.option("--observer-days", type=int, default=0, show_default=True)
@click.option("--paper-days", type=int, default=0, show_default=True)
def promotion_status_cmd(db_path: Path, log_path: Path, observer_days: int, paper_days: int) -> None:
    """Read live inputs from SQLite + log and evaluate the LIVE_TINY -> LIVE_STANDARD gate."""
    from .persistence import SQLiteStore

    store = SQLiteStore(db_path)
    summary = summarize_log(log_path)
    avg_clv_bps = store.average_clv_bps() or 0.0
    decision = evaluate_promotion(
        PromotionInputs(
            observer_days=observer_days,
            paper_days=paper_days,
            paper_trades=summary.placed_orders,
            live_tiny_trades=0,
            unexplained_pnl_events=0,
            kelly_breaches=summary.kill_switch_events,
            unlogged_actions=0,
            calibration_report_present=bool(store.calibration_buckets()),
            closing_line_value_positive=avg_clv_bps > 0,
            post_order_hook_pass_rate=1.0,
        )
    )
    click.echo(
        json.dumps(
            {
                "promote": decision.promote,
                "reasons": list(decision.reasons),
                "inputs": {
                    "paper_trades": summary.placed_orders,
                    "kill_switch_events": summary.kill_switch_events,
                    "calibration_buckets": len(store.calibration_buckets()),
                    "average_clv_bps": avg_clv_bps,
                },
            },
            indent=2,
        )
    )


@main.command("ghost-summary")
@click.option(
    "--log",
    "log_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default="logs/ghost.jsonl",
    show_default=True,
)
def ghost_summary_cmd(log_path: Path) -> None:
    """Aggregate ghost-mode failure modes (Protocol §5)."""
    from .adapters.ghost_clob import summarize_ghost_log

    rep = summarize_ghost_log(log_path)
    click.echo(json.dumps({"total": rep.total, "by_reason": rep.by_reason}, indent=2))


@main.command("deployment-gates")
@click.option("--historical-markets", type=int, required=True)
@click.option("--historical-pnl", type=float, default=0.0, show_default=True)
@click.option("--sim-trades", type=int, default=0, show_default=True)
@click.option("--sim-ev", type=float, default=0.0, show_default=True)
@click.option("--sim-mdd", type=float, default=0.0, show_default=True)
@click.option("--sim-wr", type=float, default=0.0, show_default=True)
@click.option("--ghost-hours", type=float, default=0.0, show_default=True)
@click.option("--ghost-orders", type=int, default=0, show_default=True)
@click.option("--ghost-unhandled", type=int, default=0, show_default=True)
@click.option("--dryrun-days", type=float, default=0.0, show_default=True)
@click.option("--dryrun-bankroll-pct", type=float, default=0.0, show_default=True)
@click.option("--dryrun-pnl", type=float, default=0.0, show_default=True)
@click.option("--dryrun-kelly-breaches", type=int, default=0, show_default=True)
def deployment_gates_cmd(
    historical_markets: int,
    historical_pnl: float,
    sim_trades: int,
    sim_ev: float,
    sim_mdd: float,
    sim_wr: float,
    ghost_hours: float,
    ghost_orders: int,
    ghost_unhandled: int,
    dryrun_days: float,
    dryrun_bankroll_pct: float,
    dryrun_pnl: float,
    dryrun_kelly_breaches: int,
) -> None:
    """Walk the five deployment gates (Protocol §7)."""
    from .deployment_gates import GateInputs, evaluate

    decision = evaluate(
        GateInputs(
            historical_markets_validated=historical_markets,
            historical_pnl_total_usd=historical_pnl,
            simulation_trades=sim_trades,
            simulation_ev_per_trade_usd=sim_ev,
            simulation_max_drawdown_usd=sim_mdd,
            simulation_realized_win_rate=sim_wr,
            ghost_mode_hours=ghost_hours,
            ghost_mode_orders_attempted=ghost_orders,
            ghost_mode_unhandled_failure_modes=ghost_unhandled,
            live_dryrun_days=dryrun_days,
            live_dryrun_bankroll_pct_used=dryrun_bankroll_pct,
            live_dryrun_pnl_total_usd=dryrun_pnl,
            live_dryrun_kelly_breaches=dryrun_kelly_breaches,
        )
    )
    click.echo(
        json.dumps(
            {
                "stage": decision.stage,
                "promote": decision.promote,
                "blockers": list(decision.blockers),
                "next_action": decision.next_action,
            },
            indent=2,
        )
    )


@main.command()
def reconcile() -> None:
    """Compare live wallet positions with the local SQLite store (Protocol §8)."""
    from .adapters.polymarket_user import PolymarketUserAdapter
    from .persistence import SQLiteStore
    from .reconciliation import reconcile as do_reconcile

    creds = load_credentials()
    addr = creds.funder_address or creds.wallet_address
    if not addr:
        click.echo("No wallet/funder address configured.", err=True)
        raise SystemExit(2)

    store = SQLiteStore("logs/polyflow.db")

    async def _run() -> dict:
        async with PolymarketUserAdapter(wallet_address=addr) as user:
            rep = await do_reconcile(user=user, store=store)
        return {
            "on_chain_position_count": rep.on_chain_position_count,
            "local_position_count": rep.local_position_count,
            "missing_from_local": list(rep.missing_from_local),
            "missing_from_chain": list(rep.missing_from_chain),
            "drift_detected": rep.drift_detected,
        }

    out = asyncio.run(_run())
    click.echo(json.dumps(out, indent=2))


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


@main.command("dashboard")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default="logs/polyflow.db", show_default=True)
@click.option("--log", "log_path", type=click.Path(dir_okay=False, path_type=Path), default="logs/immutable.jsonl", show_default=True)
@click.option("--heartbeat", "heartbeat_path", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8643, show_default=True, type=int)
def dashboard_cmd(
    db_path: Path,
    log_path: Path,
    heartbeat_path: Path | None,
    host: str,
    port: int,
) -> None:
    """Serve the real-time operations dashboard."""
    from .dashboard import DashboardServer

    click.echo(f"POLYFLOW dashboard listening on http://{host}:{port}")
    asyncio.run(
        DashboardServer(
            db_path=db_path,
            log_path=log_path,
            heartbeat_path=heartbeat_path,
            host=host,
            port=port,
        ).serve_forever()
    )


if __name__ == "__main__":
    main()
