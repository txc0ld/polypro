"""Four-layer alignment strategy.

This module implements the "Hermes" idea as a deterministic, compliance-safe
strategy surface. It does not scrape raw feeds. Callers pass cleaned,
timestamped layer signals from public sources; the evaluator refuses unless at
least three independent layers align in the same direction inside one window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from ..config import Policy
from ..probability import build_estimate, half_spread
from ..types import Market, Outcome, ProbabilityEstimate, Side, Signal, Strategy


class AlignmentLayer(str, Enum):
    ORDER_BOOK_DEPTH = "order_book_depth"
    WALLET_CONVICTION = "wallet_conviction"
    NEWS_PRICE_LAG = "news_price_lag"
    POSITION_DELTA = "position_delta"


@dataclass(frozen=True)
class AlignmentLayerSignal:
    """One cleaned, public, timestamped layer signal."""

    layer: AlignmentLayer
    direction: Outcome
    observed_at: datetime
    confidence: float
    # Probability of the signal's own direction resolving true.
    fair_probability: float
    evidence_ref: str
    reason_code: str

    # Layer-specific reality checks. Unused checks can stay at defaults.
    depth_ratio_flip: float = 0.0
    volume_confirmed: bool = False
    wallet_accuracy: float | None = None
    wallet_resolved_markets: int | None = None
    wallet_realized_pnl_positive: bool | None = None
    wallet_position_delta_usdc: float = 0.0
    wallet_is_trap: bool = False
    price_moved_toward_fair: float | None = None
    headline_age_minutes: float | None = None
    adding_against_price: bool = False
    full_flip: bool = False


@dataclass(frozen=True)
class AlignmentCycle:
    """Clean diff-cycle metadata produced by the snapshot engine."""

    received_at: datetime
    feed_latency_ms: float
    tracked_wallet_count: int
    out_of_sequence: bool = False
    stale_snapshot: bool = False
    order_book_jump_pct: float = 0.0
    onchain_flow_confirmed: bool = False


@dataclass
class FourLayerAlignmentStrategy:
    """Signal only when three or more independent public layers align."""

    policy: Policy
    cycle_seconds: int = 180
    alignment_window_minutes: int = 10
    min_aligned_layers: int = 3
    max_feed_latency_ms: float = 120.0
    required_wallet_count: int = 200
    min_depth_ratio_flip: float = 2.5
    max_order_book_jump_pct: float = 12.0
    min_wallet_accuracy: float = 0.65
    min_wallet_resolved_markets: int = 50
    min_wallet_delta_usdc: float = 1.0
    max_news_price_moved_toward_fair: float = 0.60
    min_headline_age_minutes: float = 2.0
    max_headline_age_minutes: float = 15.0
    min_early_cycle_edge: float = 0.18
    min_late_cycle_edge: float = 0.25
    late_cycle_seconds: float = 420.0

    def evaluate(
        self,
        *,
        market: Market,
        cycle: AlignmentCycle,
        layer_signals: list[AlignmentLayerSignal],
    ) -> tuple[ProbabilityEstimate, Signal] | None:
        if not self._cycle_is_clean(cycle):
            return None
        if market.best_bid is None or market.best_ask is None:
            return None

        usable = [
            s for s in layer_signals
            if self._signal_is_usable(s, cycle.received_at)
        ]
        if not usable:
            return None

        by_direction: dict[Outcome, list[AlignmentLayerSignal]] = {
            Outcome.YES: [],
            Outcome.NO: [],
        }
        for s in usable:
            by_direction[s.direction].append(s)

        aligned = max(
            by_direction.values(),
            key=lambda xs: len({s.layer for s in xs}),
        )
        aligned_layers = {s.layer for s in aligned}
        if len(aligned_layers) < self.min_aligned_layers:
            return None

        outcome = aligned[0].direction
        token_id = market.yes_token_id if outcome is Outcome.YES else market.no_token_id
        if not token_id:
            return None

        executable_price = market.best_ask if outcome is Outcome.YES else market.best_bid
        directional_price = executable_price if outcome is Outcome.YES else 1.0 - executable_price
        fair_probability = self._weighted_fair_probability(aligned)

        edge = fair_probability - directional_price
        min_edge = (
            self.min_late_cycle_edge
            if (cycle.received_at - min(s.observed_at for s in aligned)).total_seconds()
            >= self.late_cycle_seconds
            else self.min_early_cycle_edge
        )
        if edge < min_edge:
            return None

        confidence = sum(s.confidence for s in aligned) / len(aligned)
        uncertainty = max(0.02, min(0.12, 0.16 - confidence * 0.10))
        if uncertainty > self.policy.kelly.max_model_uncertainty:
            return None

        # build_estimate expects YES-frame probability; flip back for NO.
        q_yes = fair_probability if outcome is Outcome.YES else 1.0 - fair_probability
        est = build_estimate(
            market_id=market.id,
            token_id=token_id,
            outcome=outcome,
            market_price=executable_price,
            model_probability=q_yes,
            uncertainty=uncertainty,
            source_confidence=confidence,
            resolution_risk=market.resolution_risk,
            half_spread_value=half_spread(market.best_bid, market.best_ask),
            fee_rate_bps=market.fee_rate_bps,
            reason_codes=[
                "FOUR_LAYER_ALIGNMENT",
                f"ALIGNED_LAYERS:{len(aligned_layers)}",
                *[s.reason_code for s in aligned],
            ],
            evidence_refs=[s.evidence_ref for s in aligned],
            ttl_minutes=3,
        )
        if est.edge_after_costs < self.policy.kelly.min_effective_edge:
            return None

        signal = Signal(
            market_id=market.id,
            event_id=market.event_id,
            token_id=token_id,
            outcome=outcome,
            side=Side.BUY,
            strategy=Strategy.FOUR_LAYER_ALIGNMENT,
            market_price=executable_price,
            model_probability=fair_probability,
            uncertainty=uncertainty,
            effective_edge=est.edge_after_costs,
            market_quality=market.market_quality,
            resolution_risk=est.resolution_risk,
            liquidity_score=min(1.0, market.depth_within_5c_usd / 50_000.0),
            confidence=confidence,
            expires_at=cycle.received_at + timedelta(seconds=self.cycle_seconds),
            evidence_refs=est.evidence_refs,
            reason_codes=est.reason_codes,
        )
        return est, signal

    def _cycle_is_clean(self, cycle: AlignmentCycle) -> bool:
        if cycle.feed_latency_ms > self.max_feed_latency_ms:
            return False
        if cycle.out_of_sequence or cycle.stale_snapshot:
            return False
        if cycle.tracked_wallet_count != self.required_wallet_count:
            return False
        if (
            cycle.order_book_jump_pct > self.max_order_book_jump_pct
            and not cycle.onchain_flow_confirmed
        ):
            return False
        return True

    def _signal_is_usable(
        self, signal: AlignmentLayerSignal, received_at: datetime
    ) -> bool:
        if signal.confidence <= 0 or not (0.0 <= signal.fair_probability <= 1.0):
            return False
        if not signal.evidence_ref:
            return False
        if received_at - signal.observed_at > timedelta(minutes=self.alignment_window_minutes):
            return False

        if signal.layer is AlignmentLayer.ORDER_BOOK_DEPTH:
            return (
                signal.depth_ratio_flip >= self.min_depth_ratio_flip
                and signal.volume_confirmed
            )
        if signal.layer is AlignmentLayer.WALLET_CONVICTION:
            if signal.wallet_is_trap:
                return False
            return (
                (signal.wallet_accuracy or 0.0) >= self.min_wallet_accuracy
                and (signal.wallet_resolved_markets or 0) >= self.min_wallet_resolved_markets
                and signal.wallet_realized_pnl_positive is not False
                and abs(signal.wallet_position_delta_usdc) >= self.min_wallet_delta_usdc
            )
        if signal.layer is AlignmentLayer.NEWS_PRICE_LAG:
            if signal.price_moved_toward_fair is None or signal.headline_age_minutes is None:
                return False
            return (
                signal.price_moved_toward_fair < self.max_news_price_moved_toward_fair
                and self.min_headline_age_minutes
                <= signal.headline_age_minutes
                <= self.max_headline_age_minutes
            )
        if signal.layer is AlignmentLayer.POSITION_DELTA:
            return (
                abs(signal.wallet_position_delta_usdc) >= self.min_wallet_delta_usdc
                and (signal.adding_against_price or signal.full_flip)
                and not signal.wallet_is_trap
            )
        return False

    @staticmethod
    def _weighted_fair_probability(signals: list[AlignmentLayerSignal]) -> float:
        total_w = sum(max(0.0, s.confidence) for s in signals)
        if total_w <= 0:
            return 0.0
        return sum(s.fair_probability * max(0.0, s.confidence) for s in signals) / total_w


def four_layer_alignment_signal(
    *,
    policy: Policy,
    market: Market,
    cycle: AlignmentCycle,
    layer_signals: list[AlignmentLayerSignal],
) -> tuple[ProbabilityEstimate, Signal] | None:
    return FourLayerAlignmentStrategy(policy=policy).evaluate(
        market=market,
        cycle=cycle,
        layer_signals=layer_signals,
    )
