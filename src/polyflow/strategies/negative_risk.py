"""Strategy E — Negative-risk basket optimizer (PRD §9.5).

Polymarket's neg-risk markets bundle related outcomes such that *exactly one*
resolves YES. If you can buy YES tokens across all related outcomes for less
than $1 in aggregate, you have a guaranteed-profit basket. More commonly,
prices are inconsistent at the margin — buying a *subset* may show positive
EV under bounded downside.

This module is **research-only** until thoroughly tested on paper. It produces
a basket allocation; it does *not* go through the runtime's order path.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BasketLeg:
    """One YES position in the basket."""

    market_id: str
    token_id: str
    yes_ask: float          # executable price to buy YES (1 unit)
    yes_min_size: float     # minimum tradeable USDC
    yes_depth_usd: float    # depth at the ask
    weight: float = 1.0     # fraction of bankroll to allocate, [0,1]


@dataclass(frozen=True)
class BasketDecision:
    legs: tuple[BasketLeg, ...]
    total_cost_per_unit: float    # sum of YES asks across legs
    guaranteed_profit_per_unit: float  # max(0, 1 - total_cost) when complete
    feasible: bool
    reason: str | None = None


def evaluate_basket(
    legs: list[BasketLeg],
    *,
    require_complete: bool = True,
    max_per_leg_usdc: float | None = None,
) -> BasketDecision:
    """Determine whether a set of related-outcome YES legs forms a tradable basket.

    A *complete* basket includes one leg per outcome and bounds downside at
    ``total_cost - 1`` per unit. An *incomplete* basket (subset) leaves
    residual outcome risk and is rejected when ``require_complete=True``.
    """
    if not legs:
        return BasketDecision(
            legs=(), total_cost_per_unit=0.0, guaranteed_profit_per_unit=0.0,
            feasible=False, reason="EMPTY_BASKET",
        )

    total = sum(Decimal(str(leg.yes_ask)) for leg in legs)
    if total <= 0:
        return BasketDecision(
            legs=tuple(legs), total_cost_per_unit=0.0,
            guaranteed_profit_per_unit=0.0, feasible=False,
            reason="ZERO_COST_INVALID",
        )

    if require_complete and total >= Decimal("1.0"):
        return BasketDecision(
            legs=tuple(legs), total_cost_per_unit=float(total),
            guaranteed_profit_per_unit=0.0, feasible=False,
            reason="NO_GUARANTEED_PROFIT",
        )

    if max_per_leg_usdc is not None:
        for leg in legs:
            if leg.yes_min_size > max_per_leg_usdc:
                return BasketDecision(
                    legs=tuple(legs), total_cost_per_unit=float(total),
                    guaranteed_profit_per_unit=0.0, feasible=False,
                    reason=f"LEG_MIN_SIZE_OVER_CAP:{leg.market_id}",
                )

    profit = max(Decimal("0"), Decimal("1") - total) if require_complete else Decimal("0")
    return BasketDecision(
        legs=tuple(legs),
        total_cost_per_unit=float(total),
        guaranteed_profit_per_unit=float(profit),
        feasible=True,
    )


def expected_value(decision: BasketDecision, *, bankroll_fraction: float) -> float:
    """EV of executing the basket with the given bankroll fraction (per $1 of bankroll).

    For a complete basket:  EV = bankroll_fraction * (1 - total_cost_per_unit) / total_cost_per_unit.
    """
    if not decision.feasible or decision.total_cost_per_unit <= 0:
        return 0.0
    if decision.guaranteed_profit_per_unit <= 0:
        return 0.0
    units = bankroll_fraction / decision.total_cost_per_unit
    return units * decision.guaranteed_profit_per_unit
