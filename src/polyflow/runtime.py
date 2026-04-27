"""POLYFLOW runtime — the 24/7 core loop (PRD §12.1).

Orchestrates: scan → probability → signal → risk → format → place →
post-order hook → log. Every step is gated; nothing is optional.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import structlog

from .adapters.clob import CLOBAdapter, PaperCLOBAdapter
from .adapters.gamma import GammaAdapter, StubGammaAdapter
from .adapters.anchors import FileAnchorAdapter
from .adapters.news import RSSNewsAdapter
from .adapters.polymarket_gamma import PolymarketGammaAdapter
from .config import Policy
from .incident import IncidentManager
from .logger import ImmutableLogger
from .market_scanner import classify, market_quality_score, quickfire_score, strategy_candidates
from .order_formatter import format_order
from .persistence import SQLiteStore
from .post_order_hook import evaluate_exposure
from .risk_governor import KillSwitch, evaluate
from .signals import decide_action, score_signal
from .subagents import SubagentScheduler, SubagentTask
from .subagents.heartbeat import Heartbeat
from .subagents.order_sync import OrderSync
from .subagents.reference_repo_monitor import ReferenceRepoMonitor
from .subagents.resolution_monitor import ResolutionMonitor
from .subagents.strategy_automation import StrategyAutomation, TradeActivityAnalyzer
from .types import (
    Mode,
    OrderType,
    ProbabilityEstimate,
    RiskState,
    Signal,
    Strategy,
)
from .watchlist import Watchlist

log = structlog.get_logger("polyflow.runtime")


@dataclass
class Runtime:
    policy: Policy
    gamma: GammaAdapter
    clob: CLOBAdapter
    logger: ImmutableLogger
    state: RiskState

    incidents: IncidentManager = field(default_factory=IncidentManager)
    watchlist: Watchlist = field(default_factory=Watchlist)
    store: SQLiteStore | None = None
    heartbeat: Heartbeat | None = None
    scheduler: SubagentScheduler = field(default_factory=SubagentScheduler)
    wallet_address: str | None = None

    async def tick_scan(self) -> list[str]:
        """One pass of the 5-minute scanner cadence. Returns approved market IDs."""
        markets = await self.gamma.list_active_markets()
        approved: list[str] = []

        for m in markets:
            # Compute quality if the adapter didn't supply one.
            if m.market_quality == 0.0:
                m = m.model_copy(update={"market_quality": market_quality_score(m)})
            decision = classify(m, self.policy.market_filters)

            self.logger.log(
                actor="market_scanner",
                action="classify",
                market_id=m.id,
                event_id=m.event_id,
                input_obj={
                    "market_id": m.id,
                    "category": m.category,
                    "question": m.question,
                    "liquidity_usd": m.liquidity_usd,
                    "volume_24h_usd": m.volume_24h_usd,
                    "spread_pct": m.spread_pct,
                    "depth_within_5c_usd": m.depth_within_5c_usd,
                },
                output_obj={
                    "approved": decision.approved,
                    "manual_only": decision.manual_only,
                    "reasons": list(decision.reasons),
                    "strategy_candidates": [s.value for s in strategy_candidates(m)],
                    "quickfire_eligible": decision.approved,
                    "quickfire_score": quickfire_score(m),
                },
                payload={
                    "approved": decision.approved,
                    "manual_only": decision.manual_only,
                    "reasons": list(decision.reasons),
                    "strategy_candidates": [s.value for s in strategy_candidates(m)],
                    "market_quality": m.market_quality,
                    "quickfire_eligible": decision.approved,
                    "quickfire_score": quickfire_score(m),
                },
            )

            if decision.approved:
                self.watchlist.upsert(m, quality=m.market_quality)
                if self.store is not None:
                    self.store.upsert_market(m, status="watching")
                approved.append(m.id)
            else:
                self.watchlist.evict(m.id, reasons=decision.reasons)
                if self.store is not None and decision.reasons:
                    self.store.set_market_status(m.id, "skipped")

        return approved

    async def evaluate_candidate(
        self,
        *,
        signal: Signal,
        estimate: ProbabilityEstimate,
        market,
        strategy: Strategy,
    ) -> dict:
        """Run a single candidate signal through the full gauntlet."""
        if not self.incidents.can_trade():
            self.logger.log(
                actor="runtime",
                action="incident_blocked",
                market_id=signal.market_id,
                payload={"state": self.incidents.state.value},
            )
            return {"placed": False, "reason": f"INCIDENT:{self.incidents.state.value}"}

        signal.score = score_signal(signal)
        signal.status = decide_action(signal.score)

        self.logger.log(
            actor="signal_arbiter",
            action="score",
            market_id=signal.market_id,
            event_id=signal.event_id,
            input_obj=signal.model_dump(),
            output_obj={"score": signal.score, "status": signal.status},
            payload={"signal_id": str(signal.signal_id), "score": signal.score, "status": signal.status},
        )
        if self.store is not None:
            self.store.insert_signal(signal)
            # Persist the underlying probability estimate so the resolution monitor
            # can pair it with the eventual outcome for calibration.
            self.store.insert_probability_estimate(
                estimate_id=str(estimate.id),
                market_id=estimate.market_id,
                token_id=estimate.token_id,
                outcome=estimate.outcome.value,
                market_price=estimate.market_price,
                model_probability=estimate.model_probability,
                uncertainty=estimate.uncertainty,
                edge_after_costs=estimate.edge_after_costs,
                source_confidence=estimate.source_confidence,
                resolution_risk=estimate.resolution_risk,
            )

        if signal.status in ("REJECT", "WATCH"):
            return {"placed": False, "reason": signal.status}

        decision = evaluate(
            policy=self.policy,
            estimate=estimate,
            market=market,
            side=signal.side,
            state=self.state,
        )
        self.logger.log(
            actor="risk_governor",
            action="evaluate",
            market_id=signal.market_id,
            input_obj=signal.model_dump(),
            output_obj=decision.model_dump(),
            payload=decision.model_dump(),
        )
        if not decision.approved:
            return {"placed": False, "reason": "RISK_REJECTED", "details": decision.reason_codes}

        if self.policy.mode is Mode.OBSERVE:
            return {"placed": False, "reason": "MODE_OBSERVE"}

        balance = await self.clob.get_token_balance(estimate.token_id)
        formatted = format_order(
            policy=self.policy,
            market=market,
            estimate=estimate,
            decision=decision,
            side=signal.side,
            strategy=strategy,
            order_type=OrderType.GTC,
            current_token_balance=balance,
            risk_ref=str(signal.signal_id),
            evidence_ref=signal.evidence_refs[0] if signal.evidence_refs else None,
        )
        self.logger.log(
            actor="clob_order_formatter",
            action="format",
            market_id=signal.market_id,
            input_obj={"signal_id": str(signal.signal_id)},
            output_obj=formatted.model_dump(),
            payload=formatted.model_dump(),
        )

        if not formatted.ready_to_submit or formatted.order_payload is None:
            return {"placed": False, "reason": "FORMATTER_REJECTED", "details": formatted.reason_codes}

        record = await self.clob.place_order(formatted.order_payload)
        self.logger.log(
            actor="clob_adapter",
            action="place_order",
            market_id=signal.market_id,
            input_obj=formatted.order_payload.model_dump(),
            output_obj=record,
            payload=record,
        )

        # Post-order hook — mandatory.
        positions = await self.clob.get_positions()
        try:
            guard = evaluate_exposure(
                policy=self.policy,
                state=self.state,
                positions=positions,
                open_order_ids_by_market={},
            )
            self.logger.log(
                actor="post_order_kelly_guard",
                action="evaluate",
                market_id=signal.market_id,
                output_obj={"ok": guard.ok, "breaches": list(guard.breaches)},
                payload={"ok": guard.ok, "breaches": list(guard.breaches)},
            )
        except KillSwitch as ks:
            self.incidents.trip_killed(
                code="POST_ORDER_KELLY_BREACH",
                detail=str(ks),
                actor="post_order_kelly_guard",
            )
            self.logger.log(
                actor="post_order_kelly_guard",
                action="kill_switch",
                market_id=signal.market_id,
                payload={"reason": str(ks)},
            )
            raise

        return {"placed": True, "exchange_order_id": record.get("exchange_order_id")}


def build_default_runtime(policy: Policy, log_path: str, *, db_path: str | None = None) -> Runtime:
    """Build a runtime with stub adapters — safe for OBSERVE / PAPER modes."""
    return Runtime(
        policy=policy,
        gamma=StubGammaAdapter(),
        clob=PaperCLOBAdapter(),
        logger=ImmutableLogger(log_path, code_version="dev", config_hash=policy.config_hash),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
        store=SQLiteStore(db_path) if db_path else None,
    )


def build_live_scanner_runtime(
    policy: Policy,
    log_path: str,
    *,
    db_path: str | None = None,
    gamma_limit: int = 200,
    gamma_pages: int = 1,
    clob: CLOBAdapter | None = None,
    wallet_address: str | None = None,
) -> Runtime:
    """Build a read-only live scanner runtime using public Polymarket feeds.

    ``gamma_pages > 1`` paginates the Gamma /markets call so the scanner
    sees thousands of markets per cycle (each page is up to 500 markets,
    sorted by 24h volume desc — page 1 is top-volume, deeper pages are
    fast-moving / lower-volume markets the top sort misses).
    """
    return Runtime(
        policy=policy,
        gamma=PolymarketGammaAdapter(
            enrich_order_books=True,
            max_order_book_enrich=gamma_limit,
            default_max_pages=gamma_pages,
        ),
        clob=clob or PaperCLOBAdapter(),
        logger=ImmutableLogger(log_path, code_version="dev", config_hash=policy.config_hash),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
        store=SQLiteStore(db_path) if db_path else None,
        wallet_address=wallet_address,
    )


async def run_forever(
    rt: Runtime,
    *,
    scan_seconds: int = 300,
    resolution_seconds: int = 900,
    order_sync_seconds: int = 30,
) -> None:
    """Minimal 24/7 loop. Subagent cadences run via the scheduler in production."""
    if rt.heartbeat is not None:
        rt.scheduler.register(SubagentTask(name="heartbeat", period_seconds=10.0, fn=rt.heartbeat.tick))
    if rt.policy.automation.enabled:
        reference_repo_monitor = ReferenceRepoMonitor(
            policy=rt.policy,
            logger=rt.logger,
            store=rt.store,
        )
        rt.scheduler.register(
            SubagentTask(
                name="reference_repo_monitor",
                period_seconds=float(rt.policy.subagents.reference_repo_monitor_seconds),
                fn=reference_repo_monitor.tick,
            )
        )
    rt.scheduler.register(
        SubagentTask(
            name="market_scanner",
            period_seconds=float(scan_seconds),
            fn=lambda: _safe_scan(rt),
        )
    )

    if rt.store is not None and rt.policy.automation.enabled:
        from pathlib import Path as _P
        from .adapters.btc_feed import BtcPriceFeed
        from .adapters.commodities import CommoditiesFeed
        from .adapters.macro_calendar import MacroCalendar
        from .adapters.odds_api import OddsAPIClient
        from .circuit_breakers import CircuitBreakers

        # Anchor adapter: prefer The Odds API when key is present; otherwise
        # fall back to the file-based anchor adapter for operator-curated data.
        odds_client = OddsAPIClient.from_env()
        if odds_client.configured:
            from .adapters.anchors import _OddsAPIAnchorAdapter  # type: ignore[attr-defined]
            anchor_adapter = _OddsAPIAnchorAdapter(odds_client)
        elif rt.policy.automation.external_anchors_path:
            anchor_adapter = FileAnchorAdapter(rt.policy.automation.external_anchors_path)
        else:
            anchor_adapter = None

        news_adapter = RSSNewsAdapter(
            feed_urls=rt.policy.automation.news_rss_urls,
            max_items_per_feed=rt.policy.automation.news_max_items_per_feed,
        )
        btc_feed = BtcPriceFeed()
        commodities_feed = CommoditiesFeed()

        # Macro calendar — operator-curated YAML. Missing file = empty calendar.
        macro_path = _P("configs/macro_calendar.yaml")
        macro_calendar = (
            MacroCalendar.from_yaml(macro_path) if macro_path.exists() else None
        )

        circuit_breakers = CircuitBreakers(
            max_consecutive_losses=5,
            final_blackout_seconds=60,
        )
        strategy_automation = StrategyAutomation(
            runtime=rt,
            store=rt.store,
            logger=rt.logger,
            anchor_adapter=anchor_adapter,
            news_adapter=news_adapter,
            btc_feed=btc_feed,
            commodities_feed=commodities_feed,
            macro_calendar=macro_calendar,
            circuit_breakers=circuit_breakers,
            max_markets=rt.policy.automation.max_markets_per_strategy_cycle,
            allow_order_placement=rt.policy.automation.allow_order_placement,
        )
        rt.scheduler.register(
            SubagentTask(
                name="strategy_automation",
                period_seconds=float(rt.policy.subagents.strategy_automation_seconds),
                fn=strategy_automation.tick,
            )
        )
        trade_activity = TradeActivityAnalyzer(
            wallet_address=rt.wallet_address,
            logger=rt.logger,
            store=rt.store,
        )
        rt.scheduler.register(
            SubagentTask(
                name="trade_activity_analyzer",
                period_seconds=float(rt.policy.subagents.trade_activity_seconds),
                fn=trade_activity.tick,
            )
        )

    # Resolution monitor closes the calibration loop — only register if we have a store.
    if rt.store is not None:
        resolution = ResolutionMonitor(gamma=rt.gamma, store=rt.store)

        async def _safe_resolution() -> None:
            try:
                await resolution.tick()
            except Exception as exc:  # noqa: BLE001
                # Log but DO NOT trip_degraded for transient errors (Gamma
                # 422 on conditionId lookup, network hiccup, etc.) — that
                # would freeze trading on every tick. The scheduler already
                # records the failure in subagent.last_error.
                rt.logger.log(
                    actor="resolution_monitor",
                    action="tick_failed",
                    payload={"error": str(exc)[:200]},
                )

        rt.scheduler.register(
            SubagentTask(
                name="resolution_monitor",
                period_seconds=float(resolution_seconds),
                fn=_safe_resolution,
            )
        )

    # Order sync runs against any CLOB adapter that exposes get_open_orders.
    if rt.store is not None and hasattr(rt.clob, "get_open_orders"):
        order_sync = OrderSync(
            adapter=rt.clob,  # type: ignore[arg-type]
            store=rt.store,
            incidents=rt.incidents,
        )

        async def _safe_order_sync() -> None:
            try:
                await order_sync.tick()
            except Exception as exc:  # noqa: BLE001
                rt.logger.log(
                    actor="order_sync",
                    action="tick_failed",
                    payload={"error": str(exc)[:200]},
                )

        rt.scheduler.register(
            SubagentTask(
                name="order_sync",
                period_seconds=float(order_sync_seconds),
                fn=_safe_order_sync,
            )
        )

    await rt.scheduler.start()
    try:
        while rt.incidents.state.value != "killed":
            await asyncio.sleep(1.0)
    finally:
        await rt.scheduler.stop()


async def _safe_scan(rt: Runtime) -> None:
    """Wrapper so scan exceptions degrade rather than crash the scheduler."""
    try:
        await rt.tick_scan()
    except KillSwitch as ks:
        rt.incidents.trip_killed(code="KILL_SWITCH", detail=str(ks), actor="market_scanner")
    except Exception as exc:  # noqa: BLE001
        rt.incidents.trip_degraded(code="SCAN_FAILED", detail=str(exc), actor="market_scanner")
        raise
