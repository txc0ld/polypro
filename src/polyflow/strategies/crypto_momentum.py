"""Crypto momentum / wick-fade strategy (scalp doctrine).

Two setups:

  1. **Break-and-lag** — spot velocity over the recent window points
     strongly toward (or away from) the threshold, but the Polymarket
     binary hasn't repriced. The implied probability gap creates an edge
     in the direction of the move.

  2. **Wick-fade** — the recent window saw a large range (high vs low)
     but velocity has flattened, suggesting an overreaction. Fade by
     buying the side opposite the wick when the spot has stabilized.

Both setups produce a model probability adjustment to the lognormal
threshold model in ``btc_threshold``. This module is *additive* — it
returns a probability + uncertainty estimate that the runtime treats the
same as any other strategy output.

Refusal rules:
  - feed disagreement > 8 bps  (dirty price)
  - perp basis > 50 bps        (basis blow-out, oracle risk)
  - market spread > 3c         (scalp doctrine)
  - mid price outside [0.20, 0.80]
  - elapsed seconds in window < 30  (insufficient history)
  - threshold market not parsed
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import erf, sqrt

from ..config import Policy
from ..probability import build_estimate, half_spread
from ..types import Market, Outcome, ProbabilityEstimate, Side, Signal, Strategy
from .btc_market_parser import BtcThresholdParse, parse_btc_threshold, seconds_to_close


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


@dataclass(frozen=True)
class CryptoMomentumInputs:
    """Combines spot, perp basis, momentum window into one decision input."""

    asset: str
    spot_usd: float
    perp_basis_bps: float
    feed_disagreement_bps: float
    velocity_bps_per_min: float
    range_bps: float
    window_seconds: float
    n_samples: int
    realized_vol_annualized: float


@dataclass(frozen=True)
class _MomentumDecision:
    direction: str        # 'up' (favors above-threshold) or 'down'
    confidence: float     # [0,1]
    setup: str            # 'break_and_lag' or 'wick_fade'


def _classify_momentum(inp: CryptoMomentumInputs) -> _MomentumDecision | None:
    """Decide whether the recent window is a break-and-lag or a wick-fade."""
    abs_velocity = abs(inp.velocity_bps_per_min)

    # Break-and-lag: high velocity, range is largely in the same direction
    # (i.e. the high vs low gap is mostly the directional move, not chop).
    if abs_velocity >= 4.0 and inp.range_bps >= 4.0:
        # Confidence scales with velocity up to a cap of 30 bps/min.
        confidence = min(1.0, abs_velocity / 30.0)
        return _MomentumDecision(
            direction="up" if inp.velocity_bps_per_min > 0 else "down",
            confidence=confidence,
            setup="break_and_lag",
        )

    # Wick-fade: recent range is large but velocity has flattened (chop or
    # snap-back). Direction is *against* the wick — fade the extreme.
    if inp.range_bps >= 8.0 and abs_velocity < 2.0:
        confidence = min(1.0, inp.range_bps / 30.0)
        # Without a sign on the wick we can't tell which side; surface this
        # as a *fade flat* signal — the strategy will use the perp basis
        # sign to guess the wick direction.
        if inp.perp_basis_bps > 5.0:
            return _MomentumDecision("down", confidence=confidence, setup="wick_fade")
        if inp.perp_basis_bps < -5.0:
            return _MomentumDecision("up", confidence=confidence, setup="wick_fade")
        return None

    return None


@dataclass
class CryptoMomentumStrategy:
    """Translate momentum into a Signal / Estimate against a threshold market."""

    policy: Policy
    max_feed_disagreement_bps: float = 8.0
    max_perp_basis_bps: float = 50.0
    max_spread_pct: float = 3.0
    min_window_seconds: float = 30.0
    min_mid_price: float = 0.20
    max_mid_price: float = 0.80

    def evaluate(
        self,
        *,
        market: Market,
        inputs: CryptoMomentumInputs,
    ) -> tuple[ProbabilityEstimate, Signal] | None:
        if market.best_bid is None or market.best_ask is None:
            return None
        if market.spread_pct > self.max_spread_pct:
            return None
        if inputs.feed_disagreement_bps > self.max_feed_disagreement_bps:
            return None
        if abs(inputs.perp_basis_bps) > self.max_perp_basis_bps:
            return None
        if inputs.window_seconds < self.min_window_seconds:
            return None

        mid = (market.best_bid + market.best_ask) / 2.0
        if not (self.min_mid_price <= mid <= self.max_mid_price):
            return None

        parsed = parse_btc_threshold(market.question)
        if parsed is None or parsed.asset != inputs.asset:
            return None

        decision = _classify_momentum(inputs)
        if decision is None:
            return None

        # Translate momentum into a probability nudge. Lognormal threshold
        # baseline:
        #   P(end > K) = Φ((ln(spot/K) + drift*τ) / (σ * sqrt(τ)))
        # plus a momentum-driven drift_adjustment scaled by confidence.
        ttc_seconds = seconds_to_close(market.close_time)
        if ttc_seconds <= 0:
            return None
        tau_years = ttc_seconds / 31_536_000.0
        sigma = max(inputs.realized_vol_annualized, 0.01)

        # Each bp/min of velocity translates to a ~0.001 drift adjustment;
        # multiplied by confidence, capped by absolute size.
        drift_per_year = decision.confidence * (
            inputs.velocity_bps_per_min / 10_000.0 * 60.0 * 24.0 * 365.0 * 0.05
        )
        drift_per_year = max(-2.0, min(2.0, drift_per_year))

        if parsed.direction == "above" and decision.direction == "down":
            # Spot moving down on an above-threshold YES market — model lowers P
            drift_per_year = -abs(drift_per_year)
        elif parsed.direction == "below" and decision.direction == "up":
            drift_per_year = -abs(drift_per_year)
        elif parsed.direction == "below" and decision.direction == "down":
            drift_per_year = abs(drift_per_year)

        z = (
            (inputs.spot_usd / parsed.price_to_beat - 1.0)
            + drift_per_year * tau_years
        ) / max(sigma * sqrt(tau_years), 1e-9)
        probability_yes = max(0.01, min(0.99, _normal_cdf(z)))

        if probability_yes >= mid:
            outcome = Outcome.YES
            token_id = market.yes_token_id
            executable_price = market.best_ask
        else:
            outcome = Outcome.NO
            token_id = market.no_token_id
            executable_price = market.best_bid
        if not token_id:
            return None

        # Uncertainty scales inversely with confidence and number of samples.
        uncertainty = max(
            0.04,
            0.10 * (1.0 - decision.confidence) + 0.02 * (5 / max(inputs.n_samples, 1)),
        )
        if uncertainty > self.policy.kelly.max_model_uncertainty:
            return None

        est = build_estimate(
            market_id=market.id,
            token_id=token_id,
            outcome=outcome,
            market_price=executable_price,
            model_probability=probability_yes,
            uncertainty=uncertainty,
            source_confidence=decision.confidence,
            resolution_risk=market.resolution_risk,
            half_spread_value=half_spread(market.best_bid, market.best_ask),
            fee_rate_bps=market.fee_rate_bps,
            reason_codes=[
                f"CRYPTO_MOMENTUM:{decision.setup}",
                f"VELOCITY_BPS_PER_MIN:{inputs.velocity_bps_per_min:+.2f}",
                f"RANGE_BPS:{inputs.range_bps:.2f}",
                f"PERP_BASIS_BPS:{inputs.perp_basis_bps:+.2f}",
            ],
            evidence_refs=[
                f"crypto_feed:{inputs.asset}:{datetime.now(timezone.utc).isoformat()}",
            ],
        )
        if est.edge_after_costs < self.policy.kelly.min_effective_edge:
            return None

        signal = Signal(
            market_id=market.id,
            event_id=market.event_id,
            token_id=token_id,
            outcome=outcome,
            side=Side.BUY,
            strategy=Strategy.BTC_THRESHOLD,  # reuse routing label until enum extended
            market_price=executable_price,
            model_probability=probability_yes if outcome is Outcome.YES else 1.0 - probability_yes,
            uncertainty=uncertainty,
            effective_edge=est.edge_after_costs,
            market_quality=market.market_quality,
            resolution_risk=est.resolution_risk,
            liquidity_score=min(1.0, market.depth_within_5c_usd / 50_000.0),
            confidence=decision.confidence,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            evidence_refs=est.evidence_refs,
        )
        return est, signal
