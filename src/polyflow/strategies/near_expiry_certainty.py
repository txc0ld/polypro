"""Near-expiry certainty scalper.

Per the protocol: when the resolution outcome is already >98% certain from
raw external data (truth-source already finalized or inevitable in the
remaining time window) and the market is still pricing the certain side at
95-99c, buy the certain side. EV = 1.00 - p, capped only by fees and
resolution risk.

Refusal rules (defensive):
  - volatility spike detected in the last 60s → skip (truth-source might
    flip near expiry)
  - market resolution rules ambiguous
  - certainty < 0.98
  - executable price already >= 0.99 (no edge after fees)
  - executable price < 0.95 (not yet a "certain side scalp" — use the
    threshold strategy)
  - time to close > target window (e.g. >15 min)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CertaintyScalpInputs:
    market_id: str
    side: str                  # 'YES' or 'NO' — which side raw data says will win
    p_executable: float        # ask price for the certain side
    certainty: float           # bot's probability the certain side wins, [0,1]
    seconds_to_resolution: float
    fee_rate_bps: float = 0.0
    volatility_spike_recent: bool = False
    resolution_rules_clear: bool = True


@dataclass(frozen=True)
class CertaintyScalpDecision:
    fire: bool
    ev_per_dollar: float       # expected return per $1 staked
    breakeven_certainty: float
    reason_codes: tuple[str, ...]


def evaluate(
    inp: CertaintyScalpInputs,
    *,
    min_certainty: float = 0.98,
    min_price: float = 0.95,
    max_price: float = 0.99,
    max_seconds_to_resolution: float = 15 * 60.0,
) -> CertaintyScalpDecision:
    reasons: list[str] = []
    fire = True

    if inp.certainty < min_certainty:
        reasons.append(f"CERTAINTY_BELOW_{min_certainty:.2f}")
        fire = False
    if not inp.resolution_rules_clear:
        reasons.append("AMBIGUOUS_RESOLUTION")
        fire = False
    if inp.volatility_spike_recent:
        reasons.append("VOLATILITY_SPIKE_RECENT")
        fire = False
    if not (min_price <= inp.p_executable <= max_price):
        if inp.p_executable < min_price:
            reasons.append(f"PRICE_BELOW_{min_price:.2f}_USE_THRESHOLD_STRATEGY")
        else:
            reasons.append(f"PRICE_ABOVE_{max_price:.2f}_NO_EDGE")
        fire = False
    if inp.seconds_to_resolution > max_seconds_to_resolution:
        reasons.append("TOO_FAR_FROM_CLOSE")
        fire = False
    if inp.seconds_to_resolution <= 0:
        reasons.append("ALREADY_RESOLVED_OR_INVALID")
        fire = False

    # EV per dollar: pay p, get 1 if certain side wins, 0 otherwise.
    # EV = certainty * (1/p) - 1, minus fee drag.
    if 0 < inp.p_executable < 1:
        gross_ev = inp.certainty * (1.0 / inp.p_executable) - 1.0
        fee_drag = inp.fee_rate_bps / 10_000.0
        ev = gross_ev - fee_drag
    else:
        ev = 0.0

    return CertaintyScalpDecision(
        fire=fire and ev > 0,
        ev_per_dollar=ev,
        breakeven_certainty=inp.p_executable,
        reason_codes=tuple(reasons),
    )
