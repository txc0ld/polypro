"""Negative-risk basket optimizer tests (PRD §9.5)."""

from __future__ import annotations

import pytest

from polyflow.strategies.negative_risk import (
    BasketLeg,
    evaluate_basket,
    expected_value,
)


def _leg(price: float, mid: str = "m1") -> BasketLeg:
    return BasketLeg(
        market_id=mid,
        token_id=f"t-{mid}",
        yes_ask=price,
        yes_min_size=1.0,
        yes_depth_usd=50_000.0,
    )


class TestEvaluate:
    def test_complete_basket_with_profit(self) -> None:
        legs = [_leg(0.30, "m1"), _leg(0.30, "m2"), _leg(0.30, "m3")]
        d = evaluate_basket(legs)
        assert d.feasible
        assert d.total_cost_per_unit == pytest.approx(0.90)
        assert d.guaranteed_profit_per_unit == pytest.approx(0.10)

    def test_overpriced_basket_rejected(self) -> None:
        legs = [_leg(0.40, "m1"), _leg(0.40, "m2"), _leg(0.40, "m3")]
        d = evaluate_basket(legs)
        assert not d.feasible
        assert d.reason == "NO_GUARANTEED_PROFIT"

    def test_empty_rejected(self) -> None:
        assert not evaluate_basket([]).feasible

    def test_min_size_over_cap(self) -> None:
        legs = [_leg(0.30, "m1"), _leg(0.30, "m2")]
        legs = [legs[0].__class__(**{**legs[0].__dict__, "yes_min_size": 100.0}), legs[1]]
        d = evaluate_basket(legs, max_per_leg_usdc=10.0)
        assert not d.feasible
        assert "LEG_MIN_SIZE_OVER_CAP" in (d.reason or "")


class TestEV:
    def test_ev_zero_when_infeasible(self) -> None:
        d = evaluate_basket([_leg(0.50, "m1"), _leg(0.50, "m2")])
        assert expected_value(d, bankroll_fraction=0.05) == 0.0

    def test_ev_positive_for_real_basket(self) -> None:
        d = evaluate_basket([_leg(0.30, "m1"), _leg(0.30, "m2"), _leg(0.30, "m3")])
        ev = expected_value(d, bankroll_fraction=0.10)
        # 0.10 / 0.90 units, each yields 0.10 → ev ≈ 0.0111
        assert ev == pytest.approx(0.10 / 0.90 * 0.10, rel=1e-9)
