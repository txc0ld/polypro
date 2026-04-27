"""24/7 strategy automation loop.

The automation loop does not invent trades. It evaluates scanner-approved
quickfire markets against public evidence sources, persists analysis, and only
routes signals through the runtime's existing risk/order gauntlet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..adapters.anchors import AnchorAdapter
from ..adapters.news import NewsAdapter
from ..adapters.polymarket_user import PolymarketUserAdapter
from ..logger import ImmutableLogger
from ..persistence import SQLiteStore
from ..strategies.external_odds_divergence import ExternalOddsDivergence
from ..strategies.news_repricing import NewsRepricingStrategy
from ..types import Market, Mode, ProbabilityEstimate, Signal, Strategy


@dataclass
class CandidateResult:
    strategy: Strategy
    estimate: ProbabilityEstimate
    signal: Signal


class StrategyAutomation:
    """Analyze approved quickfire markets and run real signals through gates."""

    def __init__(
        self,
        *,
        runtime,
        store: SQLiteStore,
        logger: ImmutableLogger,
        anchor_adapter: AnchorAdapter | None = None,
        news_adapter: NewsAdapter | None = None,
        max_markets: int = 12,
        allow_order_placement: bool = False,
    ) -> None:
        self.runtime = runtime
        self.store = store
        self.logger = logger
        self.anchor_adapter = anchor_adapter
        self.news_adapter = news_adapter
        self.max_markets = max_markets
        self.allow_order_placement = allow_order_placement

    async def tick(self) -> None:
        rows = [
            row for row in self.store.get_markets_by_status("watching")
            if row.get("quickfire_eligible")
        ]
        rows.sort(key=lambda row: float(row.get("quickfire_score") or 0.0), reverse=True)
        analyzed = 0
        emitted = 0
        placed = 0

        for row in rows[: self.max_markets]:
            market = self.store.get_market(str(row["id"]))
            if market is None:
                continue
            analyzed += 1
            candidates = await self._evaluate_market(market)
            emitted += len(candidates)
            self.logger.log(
                actor="strategy_automation",
                action="analyze_market",
                market_id=market.id,
                event_id=market.event_id,
                input_obj={
                    "question": market.question,
                    "quickfire_score": row.get("quickfire_score"),
                    "strategy_candidates": row.get("strategy_candidates", []),
                },
                output_obj={
                    "candidate_signals": len(candidates),
                    "order_placement_allowed": self.allow_order_placement,
                },
                payload={
                    "candidate_signals": len(candidates),
                    "strategies": [c.strategy.value for c in candidates],
                    "quickfire_score": row.get("quickfire_score"),
                },
            )
            for candidate in candidates:
                result = await self._submit_candidate(market, candidate)
                if result.get("placed"):
                    placed += 1

        self.logger.log(
            actor="strategy_automation",
            action="cycle",
            payload={
                "analyzed_markets": analyzed,
                "candidate_signals": emitted,
                "placed_orders": placed,
                "order_placement_allowed": self.allow_order_placement,
            },
        )

    async def _evaluate_market(self, market: Market) -> list[CandidateResult]:
        out: list[CandidateResult] = []
        if self.anchor_adapter is not None:
            anchors = await self.anchor_adapter.fetch(market.id)
            signal = ExternalOddsDivergence(policy=self.runtime.policy).evaluate(
                market=market,
                anchors=anchors,
            )
            if signal is not None:
                est, sig = signal
                out.append(CandidateResult(Strategy.EXTERNAL_ODDS_DIVERGENCE, est, sig))

        if self.news_adapter is not None and market.best_bid is not None and market.best_ask is not None:
            events = await self.news_adapter.events_for_market(market)
            prior = (market.best_bid + market.best_ask) / 2.0
            signal = NewsRepricingStrategy(policy=self.runtime.policy).evaluate(
                market=market,
                prior_probability=prior,
                events=events,
            )
            self.logger.log(
                actor="news_analyzer",
                action="market_news",
                market_id=market.id,
                event_id=market.event_id,
                payload={
                    "events": len(events),
                    "signal": signal is not None,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            if signal is not None:
                est, sig = signal
                out.append(CandidateResult(Strategy.NEWS_REPRICING, est, sig))
        return out

    async def _submit_candidate(self, market: Market, candidate: CandidateResult) -> dict:
        original_mode = self.runtime.policy.mode
        if not self.allow_order_placement:
            self.runtime.policy.mode = Mode.OBSERVE
        try:
            result = await self.runtime.evaluate_candidate(
                signal=candidate.signal,
                estimate=candidate.estimate,
                market=market,
                strategy=candidate.strategy,
            )
        finally:
            self.runtime.policy.mode = original_mode
        self.logger.log(
            actor="strategy_automation",
            action="candidate_result",
            market_id=market.id,
            event_id=market.event_id,
            payload={
                "strategy": candidate.strategy.value,
                "placed": bool(result.get("placed")),
                "reason": result.get("reason"),
                "order_placement_allowed": self.allow_order_placement,
            },
        )
        return result


class TradeActivityAnalyzer:
    """Poll wallet activity/positions and write analysis records."""

    def __init__(
        self,
        *,
        wallet_address: str | None,
        logger: ImmutableLogger,
        store: SQLiteStore | None = None,
    ) -> None:
        self.wallet_address = wallet_address
        self.logger = logger
        self.store = store

    async def tick(self) -> None:
        if not self.wallet_address:
            self.logger.log(
                actor="trade_activity_analyzer",
                action="skip",
                payload={"reason": "NO_WALLET_ADDRESS"},
            )
            return
        async with PolymarketUserAdapter(wallet_address=self.wallet_address) as adapter:
            positions = await adapter.positions()
            activity = await adapter.activity(limit=50)
        self.logger.log(
            actor="trade_activity_analyzer",
            action="wallet_snapshot",
            payload={
                "positions": len(positions),
                "activity": len(activity),
                "open_position_value": _sum_float(positions, "currentValue", "market_value"),
            },
        )


def _sum_float(rows: list[dict], *keys: str) -> float:
    total = 0.0
    for row in rows:
        for key in keys:
            try:
                total += float(row.get(key) or 0.0)
                break
            except (TypeError, ValueError):
                continue
    return total
