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

from ..probability import clob_taker_fee_usdc


@dataclass(frozen=True)
class BasketLeg:
    """One YES position in the basket."""

    market_id: str
    token_id: str
    yes_ask: float          # executable price to buy YES (1 unit)
    yes_min_size: float     # minimum tradeable USDC
    yes_depth_usd: float    # depth at the ask
    weight: float = 1.0     # fraction of bankroll to allocate, [0,1]
    fee_rate: float | None = 0.0
    expected_slippage: float = 0.0
    is_placeholder: bool = False
    is_other: bool = False
    other_definition_stable: bool = True

    @property
    def executable_cost_per_unit(self) -> float:
        """Cost for one YES share including taker fee and slippage buffers."""
        return (
            self.yes_ask
            + clob_taker_fee_usdc(shares=1.0, price=self.yes_ask, fee_rate=self.fee_rate)
            + self.expected_slippage
        )


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

    for leg in legs:
        if leg.is_placeholder:
            return BasketDecision(
                legs=tuple(legs), total_cost_per_unit=0.0,
                guaranteed_profit_per_unit=0.0, feasible=False,
                reason=f"PLACEHOLDER_OUTCOME:{leg.market_id}",
            )
        if leg.is_other and not leg.other_definition_stable:
            return BasketDecision(
                legs=tuple(legs), total_cost_per_unit=0.0,
                guaranteed_profit_per_unit=0.0, feasible=False,
                reason=f"OTHER_DEFINITION_UNSTABLE:{leg.market_id}",
            )
        if leg.yes_depth_usd < leg.yes_ask:
            return BasketDecision(
                legs=tuple(legs), total_cost_per_unit=0.0,
                guaranteed_profit_per_unit=0.0, feasible=False,
                reason=f"INSUFFICIENT_DEPTH_FOR_UNIT:{leg.market_id}",
            )

    total = sum(Decimal(str(leg.executable_cost_per_unit)) for leg in legs)
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
