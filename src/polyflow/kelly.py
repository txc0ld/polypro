"""Fractional Kelly sizer (PRD §8.2 / §8.3).

Pure math. No I/O. Deterministic.
"""

from __future__ import annotations

from .types import Outcome


def raw_kelly(p_market: float, q_model: float, outcome: Outcome) -> float:
    """Raw Kelly fraction for a single binary outcome bet.

    YES at price p with model probability q:  (q - p) / (1 - p)
    NO at YES-price p with model YES prob q:  (p - q) / p

    Returns 0 when there is no positive edge or the price is at a degenerate boundary.
    """
    if not (0.0 < p_market < 1.0):
        return 0.0
    if not (0.0 <= q_model <= 1.0):
        return 0.0

    if outcome is Outcome.YES:
        k = (q_model - p_market) / (1.0 - p_market)
    else:
        k = (p_market - q_model) / p_market

    return max(0.0, k)


def fractional_kelly(
    raw: float,
    *,
    kelly_fraction: float,
    confidence_multiplier: float = 1.0,
    liquidity_multiplier: float = 1.0,
    resolution_multiplier: float = 1.0,
    portfolio_multiplier: float = 1.0,
) -> float:
    """Apply the conservative multipliers from PRD §8.2.

    Each multiplier must be in [0, 1]. The output is clamped to [0, 1] —
    the absolute final cap is enforced by Risk Governor, not here.
    """
    for name, m in (
        ("kelly_fraction", kelly_fraction),
        ("confidence_multiplier", confidence_multiplier),
        ("liquidity_multiplier", liquidity_multiplier),
        ("resolution_multiplier", resolution_multiplier),
        ("portfolio_multiplier", portfolio_multiplier),
    ):
        if not (0.0 <= m <= 1.0):
            raise ValueError(f"{name}={m} out of [0,1]")

    out = max(0.0, raw) * kelly_fraction
    out *= confidence_multiplier
    out *= liquidity_multiplier
    out *= resolution_multiplier
    out *= portfolio_multiplier
    return min(1.0, out)


def confidence_multiplier(source_confidence: float, uncertainty: float) -> float:
    """Combine source confidence and probability uncertainty into a [0,1] multiplier.

    High uncertainty or low confidence shrinks size aggressively.
    """
    sc = max(0.0, min(1.0, source_confidence))
    u = max(0.0, min(1.0, uncertainty))
    return sc * (1.0 - u)


def liquidity_multiplier(depth_within_5c_usd: float, target_usdc: float) -> float:
    """Scale down if we'd consume more than ~10% of the visible 5c-depth book.

    target_usdc 0 returns 1.0 (no constraint).
    """
    if target_usdc <= 0:
        return 1.0
    if depth_within_5c_usd <= 0:
        return 0.0
    ratio = target_usdc / (0.10 * depth_within_5c_usd)
    return max(0.0, min(1.0, 1.0 / ratio if ratio > 1.0 else 1.0))


def resolution_multiplier(resolution_risk: float, max_resolution_risk: float) -> float:
    """Linear shrink from 1.0 at zero resolution risk to 0.0 at the cap."""
    if max_resolution_risk <= 0:
        return 0.0
    if resolution_risk >= max_resolution_risk:
        return 0.0
    return 1.0 - (resolution_risk / max_resolution_risk)
