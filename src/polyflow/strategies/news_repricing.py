"""Strategy A — Public news repricing (PRD §9.1).

The news subagent pushes ``PublicSourceEvent`` records here; this module
decides whether the new public information should move event probability and
emits a Signal if so. Refuses on any integrity violation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from ..config import Policy
from ..probability import build_estimate, half_spread
from ..types import (
    Market,
    Outcome,
    ProbabilityEstimate,
    Side,
    Signal,
    Strategy,
)


@dataclass(frozen=True)
class PublicSourceEvent:
    """One public-source emission considered for repricing.

    The ``integrity_flags`` carries any per-source red flags surfaced by the
    monitor (e.g. ``LEAKED``, ``OUTCOME_INFLUENCER``, ``NON_PUBLIC``). Any
    non-empty flag set is a hard refusal.
    """

    source_name: str
    source_url: str
    body_hash: str
    fetched_at: datetime
    reliability: float  # prior in [0,1]
    direction: float    # signed nudge to YES probability in [-1, 1]
    integrity_flags: tuple[str, ...] = ()
    settlement_match: bool = True


@dataclass
class NewsRepricingStrategy:
    """Aggregates source events into a probability delta."""

    policy: Policy
    min_sources_for_major_delta: int = 2
    major_delta_threshold: float = 0.06
    fresh_within_minutes: int = 20
    min_average_reliability: float = 0.75

    def evaluate(
        self,
        *,
        market: Market,
        prior_probability: float,
        events: list[PublicSourceEvent],
    ) -> tuple[ProbabilityEstimate, Signal] | None:
        # --- Integrity gates --------------------------------------------------
        for ev in events:
            if ev.integrity_flags:
                return None
            if not ev.settlement_match:
                return None

        # --- Freshness + reliability filter ----------------------------------
        now = datetime.now(timezone.utc)
        fresh = [
            ev
            for ev in events
            if (now - ev.fetched_at) <= timedelta(minutes=self.fresh_within_minutes)
        ]
        if not fresh:
            return None

        avg_reliability = sum(ev.reliability for ev in fresh) / len(fresh)
        if avg_reliability < self.min_average_reliability:
            return None

        # --- Aggregate delta -------------------------------------------------
        total_w = sum(ev.reliability for ev in fresh)
        if total_w <= 0:
            return None
        delta = sum(ev.direction * ev.reliability for ev in fresh) / total_w
        new_p = max(0.0, min(1.0, prior_probability + delta))
        magnitude = abs(new_p - prior_probability)

        if magnitude >= self.major_delta_threshold and len(fresh) < self.min_sources_for_major_delta:
            # Single-source rumor on a large delta — refuse.
            return None

        if market.best_bid is None or market.best_ask is None:
            return None
        mid = (market.best_bid + market.best_ask) / 2.0

        # YES-frame for build_estimate (see external_odds_divergence for the rationale).
        if new_p > mid:
            outcome = Outcome.YES
            token_id = market.yes_token_id
            executable_price = market.best_ask
        else:
            outcome = Outcome.NO
            token_id = market.no_token_id
            executable_price = market.best_bid

        if not token_id:
            return None

        uncertainty = max(0.03, 0.10 - magnitude * 0.5)  # tighter when delta is well-supported
        if uncertainty > self.policy.kelly.max_model_uncertainty:
            return None

        est = build_estimate(
            market_id=market.id,
            token_id=token_id,
            outcome=outcome,
            market_price=executable_price,
            model_probability=new_p,  # YES probability; effective_edge handles the flip
            uncertainty=uncertainty,
            source_confidence=avg_reliability,
            resolution_risk=market.resolution_risk,
            half_spread_value=half_spread(market.best_bid, market.best_ask),
            fee_rate_bps=market.fee_rate_bps,
            reason_codes=["PUBLIC_NEWS_CONFIRMED", f"SOURCES:{len(fresh)}"],
            evidence_refs=[f"news:{ev.source_url}:{ev.body_hash}" for ev in fresh],
        )
        if est.edge_after_costs < self.policy.kelly.min_effective_edge:
            return None

        signal_prob = new_p if outcome is Outcome.YES else 1.0 - new_p
        signal = Signal(
            market_id=market.id,
            event_id=market.event_id,
            token_id=token_id,
            outcome=outcome,
            side=Side.BUY,
            strategy=Strategy.NEWS_REPRICING,
            market_price=executable_price,
            model_probability=signal_prob,
            uncertainty=uncertainty,
            effective_edge=est.edge_after_costs,
            market_quality=market.market_quality,
            resolution_risk=est.resolution_risk,
            liquidity_score=min(1.0, market.depth_within_5c_usd / 50_000.0),
            confidence=avg_reliability,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            evidence_refs=est.evidence_refs,
        )
        return est, signal


def hash_body(text: str) -> str:
    """Helper for callers building ``PublicSourceEvent`` records."""
    return "sha256:" + sha256(text.encode("utf-8")).hexdigest()
