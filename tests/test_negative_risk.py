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

    def test_fees_and_slippage_reduce_basket_edge(self) -> None:
        legs = [
            BasketLeg(
                market_id="m1",
                token_id="t-m1",
                yes_ask=0.30,
                yes_min_size=1.0,
                yes_depth_usd=50_000.0,
                fee_rate=0.05,
                expected_slippage=0.01,
            ),
            _leg(0.30, "m2"),
            _leg(0.30, "m3"),
        ]
        d = evaluate_basket(legs)
        assert d.feasible
        assert d.total_cost_per_unit > 0.91
        assert d.guaranteed_profit_per_unit < 0.10

    def test_placeholder_rejected(self) -> None:
        leg = BasketLeg(
            market_id="m1",
            token_id="t-m1",
            yes_ask=0.30,
            yes_min_size=1.0,
            yes_depth_usd=50_000.0,
            is_placeholder=True,
        )
        d = evaluate_basket([leg, _leg(0.30, "m2")])
        assert not d.feasible
        assert "PLACEHOLDER_OUTCOME" in (d.reason or "")

    def test_unstable_other_rejected(self) -> None:
        leg = BasketLeg(
            market_id="other",
            token_id="t-other",
            yes_ask=0.30,
            yes_min_size=1.0,
            yes_depth_usd=50_000.0,
            is_other=True,
            other_definition_stable=False,
        )
        d = evaluate_basket([leg, _leg(0.30, "m2")])
        assert not d.feasible
        assert "OTHER_DEFINITION_UNSTABLE" in (d.reason or "")

    def test_depth_must_cover_one_unit(self) -> None:
        d = evaluate_basket([_leg(0.30, "m1").__class__(**{
            **_leg(0.30, "m1").__dict__,
            "yes_depth_usd": 0.10,
        })])
        assert not d.feasible
        assert "INSUFFICIENT_DEPTH_FOR_UNIT" in (d.reason or "")


class TestEV:
    def test_ev_zero_when_infeasible(self) -> None:
        d = evaluate_basket([_leg(0.50, "m1"), _leg(0.50, "m2")])
        assert expected_value(d, bankroll_fraction=0.05) == 0.0

    def test_ev_positive_for_real_basket(self) -> None:
        d = evaluate_basket([_leg(0.30, "m1"), _leg(0.30, "m2"), _leg(0.30, "m3")])
        ev = expected_value(d, bankroll_fraction=0.10)
        # 0.10 / 0.90 units, each yields 0.10 → ev ≈ 0.0111
        assert ev == pytest.approx(0.10 / 0.90 * 0.10, rel=1e-9)
