"""Strategy B — External odds divergence (PRD §9.2).

Compares Polymarket executable price against credible external probability
anchors (sportsbooks, Kalshi, polling forecasts, liquid spot markets). Emits a
Signal only when the divergence survives vig removal, fees, slippage, and
resolution-mismatch adjustments.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..config import Policy
from ..probability import build_estimate, half_spread, remove_vig
from ..types import (
    Market,
    Outcome,
    ProbabilityEstimate,
    Side,
    Signal,
    Strategy,
)


@dataclass(frozen=True)
class OddsAnchor:
    """A normalized snapshot of an external probability anchor for one event."""

    source_name: str
    fetched_at: datetime
    # YES probabilities for the candidate outcome and its complement after vig
    # removal — sums to 1.0.
    yes_probability: float
    reliability: float  # prior in [0,1]
    settlement_match: bool = True

    @classmethod
    def from_decimal_odds(
        cls,
        *,
        source_name: str,
        fetched_at: datetime,
        yes_decimal_odds: float,
        no_decimal_odds: float,
        reliability: float,
        settlement_match: bool = True,
    ) -> "OddsAnchor":
        ps = remove_vig([yes_decimal_odds, no_decimal_odds])
        return cls(
            source_name=source_name,
            fetched_at=fetched_at,
            yes_probability=ps[0],
            reliability=reliability,
            settlement_match=settlement_match,
        )


@dataclass(frozen=True)
class _Aggregate:
    yes_probability: float
    confidence: float
    n_sources: int
    reasons: tuple[str, ...]


def _aggregate(anchors: list[OddsAnchor], *, max_age_seconds: int) -> _Aggregate | None:
    """Reliability-weighted mean YES probability across fresh, matching sources.

    Returns None if no anchors are usable.
    """
    if not anchors:
        return None

    now = datetime.now(timezone.utc)
    fresh: list[OddsAnchor] = []
    for a in anchors:
        if not a.settlement_match:
            continue
        if (now - a.fetched_at).total_seconds() > max_age_seconds:
            continue
        if a.reliability < 0.50:
            continue
        fresh.append(a)

    if not fresh:
        return None

    total_w = sum(a.reliability for a in fresh)
    if total_w <= 0:
        return None
    p = sum(a.yes_probability * a.reliability for a in fresh) / total_w
    confidence = min(1.0, total_w / max(len(fresh), 1))
    reasons = tuple(f"ANCHOR:{a.source_name}" for a in fresh)
    return _Aggregate(
        yes_probability=p, confidence=confidence, n_sources=len(fresh), reasons=reasons
    )


@dataclass
class ExternalOddsDivergence:
    """Divergence detector. Construct once, call ``evaluate`` per market."""

    policy: Policy
    max_anchor_age_seconds: int = 30
    min_anchor_sources: int = 1  # PRD §9.2: 1 high-reliability anchor sufficient

    def evaluate(
        self,
        *,
        market: Market,
        anchors: list[OddsAnchor],
    ) -> tuple[ProbabilityEstimate, Signal] | None:
        """Return (estimate, signal) if the divergence is tradable, else None.

        Returns None — and never raises — for any structural reason the trade
        should not be considered.
        """
        if market.best_bid is None or market.best_ask is None:
            return None

        agg = _aggregate(anchors, max_age_seconds=self.max_anchor_age_seconds)
        if agg is None or agg.n_sources < self.min_anchor_sources:
            return None

        # Decide direction: BUY YES if external > Polymarket YES mid; BUY NO otherwise.
        # build_estimate / effective_edge use YES-frame coordinates throughout — we pass
        # the YES probability and the YES-side executable price regardless of which
        # outcome we trade. The Outcome enum tells the math which sign convention to use.
        mid = (market.best_bid + market.best_ask) / 2.0
        if agg.yes_probability >= mid:
            outcome = Outcome.YES
            token_id = market.yes_token_id
            executable_price = market.best_ask  # cross to lift YES
        else:
            outcome = Outcome.NO
            token_id = market.no_token_id
            executable_price = market.best_bid  # cross the YES bid to acquire NO

        if not token_id:
            return None

        # Probability uncertainty: 6c floor for a single anchor, shrinks with
        # more sources via 1/sqrt(n). Always clipped to the policy ceiling.
        uncertainty = max(0.03, 0.06 / max(agg.n_sources, 1) ** 0.5)
        if uncertainty > self.policy.kelly.max_model_uncertainty:
            return None

        est = build_estimate(
            market_id=market.id,
            token_id=token_id,
            outcome=outcome,
            market_price=executable_price,
            model_probability=agg.yes_probability,  # always YES prob; effective_edge handles the side
            uncertainty=uncertainty,
            source_confidence=agg.confidence,
            resolution_risk=market.resolution_risk,
            half_spread_value=half_spread(market.best_bid, market.best_ask),
            fee_rate_bps=market.fee_rate_bps,
            reason_codes=list(agg.reasons),
            evidence_refs=[f"external_odds:{a.source_name}:{a.fetched_at.isoformat()}" for a in anchors],
        )
        if est.edge_after_costs < self.policy.kelly.min_effective_edge:
            return None

        signal = Signal(
            market_id=market.id,
            event_id=market.event_id,
            token_id=token_id,
            outcome=outcome,
            side=Side.BUY,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            market_price=executable_price,
            # Signal records the model probability *for the side we're trading*, which
            # is the more useful number for downstream calibration vs realized outcome.
            model_probability=(
                agg.yes_probability if outcome is Outcome.YES else 1.0 - agg.yes_probability
            ),
            uncertainty=uncertainty,
            effective_edge=est.edge_after_costs,
            market_quality=market.market_quality,
            resolution_risk=est.resolution_risk,
            liquidity_score=min(1.0, market.depth_within_5c_usd / 50_000.0),
            confidence=agg.confidence,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            evidence_refs=est.evidence_refs,
        )
        return est, signal


def divergence_signal(
    *, policy: Policy, market: Market, anchors: list[OddsAnchor]
) -> tuple[ProbabilityEstimate, Signal] | None:
    """Convenience function — single-call entry point used by the runtime."""
    return ExternalOddsDivergence(policy=policy).evaluate(market=market, anchors=anchors)
