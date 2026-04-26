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
from .config import Policy
from .incident import IncidentManager
from .logger import ImmutableLogger
from .market_scanner import classify, market_quality_score
from .order_formatter import format_order
from .persistence import SQLiteStore
from .post_order_hook import evaluate_exposure
from .risk_governor import KillSwitch, evaluate
from .signals import decide_action, score_signal
from .subagents import SubagentScheduler, SubagentTask
from .subagents.heartbeat import Heartbeat
from .types import (
    Mode,
    OrderType,
    ProbabilityEstimate,
    RiskState,
    Side,
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
                input_obj={"market_id": m.id, "category": m.category},
                output_obj={
                    "approved": decision.approved,
                    "manual_only": decision.manual_only,
                    "reasons": list(decision.reasons),
                },
                payload={
                    "approved": decision.approved,
                    "manual_only": decision.manual_only,
                    "reasons": list(decision.reasons),
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


async def run_forever(rt: Runtime, *, scan_seconds: int = 300) -> None:
    """Minimal 24/7 loop. Subagent cadences run via the scheduler in production."""
    # Wire the heartbeat + scheduler if either is configured.
    if rt.heartbeat is not None:
        rt.scheduler.register(SubagentTask(name="heartbeat", period_seconds=10.0, fn=rt.heartbeat.tick))
    rt.scheduler.register(
        SubagentTask(
            name="market_scanner",
            period_seconds=float(scan_seconds),
            fn=lambda: _safe_scan(rt),
        )
    )
    await rt.scheduler.start()
    try:
        # Park the main task until something kills the runtime.
        while rt.incidents.state.value not in ("killed",):
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
