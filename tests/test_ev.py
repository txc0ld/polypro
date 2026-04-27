"""Pure EV math tests."""

from __future__ import annotations

import pytest

from polyflow.ev import (
    best_side,
    buy_no_ev,
    buy_yes_ev,
    costed_ev,
    fractional_kelly_fraction,
)


class TestBuyYes:
    def test_positive_edge(self) -> None:
        # q=0.70, p=0.55 → edge=0.15, EV per dollar = 0.70/0.55 - 1 ≈ 0.273
        r = buy_yes_ev(q=0.70, p_yes=0.55)
        assert r.side == "BUY_YES"
        assert r.edge_per_share == pytest.approx(0.15)
        assert r.ev_per_dollar == pytest.approx(0.70 / 0.55 - 1)
        assert r.breakeven_q == 0.55

    def test_no_edge(self) -> None:
        r = buy_yes_ev(q=0.55, p_yes=0.55)
        assert r.ev_per_dollar == pytest.approx(0.0)

    def test_negative_edge(self) -> None:
        r = buy_yes_ev(q=0.40, p_yes=0.55)
        assert r.ev_per_dollar < 0

    @pytest.mark.parametrize("p", [0.0, 1.0, -0.1, 1.5])
    def test_invalid_price_raises(self, p: float) -> None:
        with pytest.raises(ValueError):
            buy_yes_ev(q=0.5, p_yes=p)


class TestBuyNo:
    def test_positive_edge(self) -> None:
        # YES price 0.65 → NO price 0.35; q_no = 1 - 0.40 = 0.60
        r = buy_no_ev(q=0.40, p_yes=0.65)
        assert r.side == "BUY_NO"
        assert r.p_market == pytest.approx(0.35)
        assert r.q_model == pytest.approx(0.60)
        assert r.edge_per_share == pytest.approx(0.25)


class TestBestSide:
    def test_picks_yes_when_yes_edge_better(self) -> None:
        r = best_side(q_yes=0.70, p_yes_bid=0.62, p_yes_ask=0.64)
        assert r.side == "BUY_YES"

    def test_picks_no_when_no_edge_better(self) -> None:
        r = best_side(q_yes=0.30, p_yes_bid=0.40, p_yes_ask=0.42)
        # q=0.30 means market is overpriced → BUY NO is the better play
        assert r.side == "BUY_NO"


class TestKelly:
    def test_simple(self) -> None:
        # f* = (q - p) / (1 - p)
        assert fractional_kelly_fraction(q=0.70, p_market=0.55) == pytest.approx(0.15 / 0.45)

    def test_negative_clamped(self) -> None:
        assert fractional_kelly_fraction(q=0.30, p_market=0.55) == 0.0


class TestCostedEv:
    def test_costs_subtract(self) -> None:
        ev = costed_ev(raw_ev=0.20, fee_rate_bps=50, expected_slippage_bps=50)
        assert ev == pytest.approx(0.20 - 0.01)
