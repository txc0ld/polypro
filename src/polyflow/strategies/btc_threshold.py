"""BTC short-horizon threshold strategy.

This strategy targets fast BTC UP/DOWN threshold markets, but it is designed
for observe/paper validation first. It uses only public BTC prices and refuses
when feed freshness, feed agreement, market structure, or resolution metadata
is not good enough.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import erf, log, sqrt

from ..config import Policy
from ..probability import build_estimate, half_spread
from ..types import Market, Outcome, ProbabilityEstimate, Side, Signal, Strategy

SECONDS_PER_YEAR = 31_536_000.0


@dataclass(frozen=True)
class BtcThresholdSnapshot:
    """Public BTC state for one threshold market evaluation."""

    source_name: str
    source_url: str
    fetched_at: datetime
    price_to_beat: float
    btc_spot: float
    seconds_to_resolution: float
    realized_volatility_annualized: float
    feed_disagreement_bps: float = 0.0
    oracle_latency_seconds: float = 0.0
    drift_adjustment: float = 0.0
    settlement_match: bool = True
    integrity_flags: tuple[str, ...] = ()


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def threshold_probability(snapshot: BtcThresholdSnapshot) -> float | None:
    """Estimate P(BTC finishes above threshold) with a short-horizon lognormal model."""
    if snapshot.price_to_beat <= 0 or snapshot.btc_spot <= 0:
        return None
    if snapshot.seconds_to_resolution <= 0:
        return None
    if snapshot.realized_volatility_annualized <= 0:
        return None

    tau = snapshot.seconds_to_resolution / SECONDS_PER_YEAR
    denom = snapshot.realized_volatility_annualized * sqrt(tau)
    if denom <= 0:
        return None

    z = (
        log(snapshot.btc_spot / snapshot.price_to_beat)
        + snapshot.drift_adjustment * tau
    ) / denom
    return max(0.0, min(1.0, normal_cdf(z)))


@dataclass
class BtcThresholdStrategy:
    """Public BTC threshold model. Emits a Signal only when edge survives costs."""

    policy: Policy
    # Defaults relaxed for the "daily / weekly threshold" universe the user
    # is actually trading. The 5-min-bar-only originals (8s feed age,
    # 5-min max horizon) gated all current Polymarket BTC markets out.
    max_feed_age_seconds: int = 120         # was 8 — 1-min spot polling is fine for daily horizon
    max_feed_disagreement_bps: float = 25.0 # was 8 — broader source spread tolerated for daily horizon
    max_oracle_latency_seconds: float = 120.0
    min_seconds_to_resolution: float = 60.0
    max_seconds_to_resolution: float = 7 * 24 * 3600.0  # 7 days — admits daily/weekly threshold markets
    max_late_entry_seconds: float = 60.0

    def evaluate(
        self,
        *,
        market: Market,
        snapshot: BtcThresholdSnapshot,
    ) -> tuple[ProbabilityEstimate, Signal] | None:
        if snapshot.integrity_flags:
            return None
        if not snapshot.settlement_match:
            return None

        now = datetime.now(timezone.utc)
        if (now - snapshot.fetched_at).total_seconds() > self.max_feed_age_seconds:
            return None
        if snapshot.feed_disagreement_bps > self.max_feed_disagreement_bps:
            return None
        if snapshot.oracle_latency_seconds > self.max_oracle_latency_seconds:
            return None
        if snapshot.seconds_to_resolution < self.min_seconds_to_resolution:
            return None
        if snapshot.seconds_to_resolution > self.max_seconds_to_resolution:
            return None
        if market.best_bid is None or market.best_ask is None:
            return None
        if not market.resolution_rules:
            return None

        q_up = threshold_probability(snapshot)
        if q_up is None:
            return None

        mid = (market.best_bid + market.best_ask) / 2.0
        if q_up >= mid:
            outcome = Outcome.YES
            token_id = market.yes_token_id
            executable_price = market.best_ask
        else:
            outcome = Outcome.NO
            token_id = market.no_token_id
            executable_price = market.best_bid

        if not token_id:
            return None

        feed_penalty = min(0.05, snapshot.feed_disagreement_bps / 10_000.0)
        latency_penalty = min(0.05, snapshot.oracle_latency_seconds / 1_000.0)
        late_penalty = (
            0.03
            if snapshot.seconds_to_resolution <= self.max_late_entry_seconds
            else 0.0
        )

        # High-conviction setup: when |spot-strike|/strike implies a z-score
        # well outside the noise band, drop the uncertainty floor toward
        # raw feed/latency penalties. Without this, a clearly-resolved
        # threshold market (e.g. spot $77.9k vs $74k strike) carries the
        # same 3c uncertainty floor as a knife-edge market.
        confident = abs(q_up - 0.5) > 0.40   # q < 0.10 or q > 0.90
        uncertainty_floor = 0.005 if confident else 0.02
        uncertainty = max(
            uncertainty_floor,
            min(0.25, feed_penalty + latency_penalty + late_penalty + (0.01 if confident else 0.03)),
        )
        if uncertainty > self.policy.kelly.max_model_uncertainty:
            return None

        est = build_estimate(
            market_id=market.id,
            token_id=token_id,
            outcome=outcome,
            market_price=executable_price,
            model_probability=q_up,
            uncertainty=uncertainty,
            source_confidence=max(0.0, 1.0 - uncertainty),
            resolution_risk=market.resolution_risk,
            half_spread_value=half_spread(market.best_bid, market.best_ask),
            fee_rate_bps=market.fee_rate_bps,
            resolution_risk_buffer_multiplier=0.10,
            uncertainty_buffer_multiplier=0.25,
            # Threshold markets are always held to resolution — no exit-side
            # cost. Saves ~1c of buffer that was eating real edge.
            hold_to_resolution=True,
            reason_codes=[
                "BTC_THRESHOLD_PUBLIC_FEED",
                f"GAP:{snapshot.btc_spot - snapshot.price_to_beat:.2f}",
                f"SECONDS_TO_RESOLUTION:{snapshot.seconds_to_resolution:.0f}",
                f"CONFIDENT" if confident else "BORDERLINE",
            ],
            evidence_refs=[
                f"btc_threshold:{snapshot.source_name}:{snapshot.source_url}:{snapshot.fetched_at.isoformat()}"
            ],
            ttl_minutes=1,
        )
        if est.edge_after_costs < self.policy.kelly.min_effective_edge:
            return None

        signal = Signal(
            market_id=market.id,
            event_id=market.event_id,
            token_id=token_id,
            outcome=outcome,
            side=Side.BUY,
            strategy=Strategy.BTC_THRESHOLD,
            market_price=executable_price,
            model_probability=q_up if outcome is Outcome.YES else 1.0 - q_up,
            uncertainty=uncertainty,
            effective_edge=est.edge_after_costs,
            market_quality=market.market_quality,
            resolution_risk=est.resolution_risk,
            liquidity_score=min(1.0, market.depth_within_5c_usd / 50_000.0),
            confidence=max(0.0, 1.0 - uncertainty),
            expires_at=now + timedelta(seconds=min(30.0, snapshot.seconds_to_resolution)),
            evidence_refs=est.evidence_refs,
            reason_codes=est.reason_codes,
        )
        return est, signal


def btc_threshold_signal(
    *, policy: Policy, market: Market, snapshot: BtcThresholdSnapshot
) -> tuple[ProbabilityEstimate, Signal] | None:
    return BtcThresholdStrategy(policy=policy).evaluate(
        market=market, snapshot=snapshot
    )
