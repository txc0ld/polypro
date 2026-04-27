"""Expectancy tracker + entry-gate tests (Protocol §4)."""

from __future__ import annotations

import pytest

from polyflow.expectancy import (
    MIN_RTR,
    compute,
    dynamic_entry_allowed,
    edge_pct,
    passes_rtr_gate,
)


class TestCompute:
    def test_empty(self) -> None:
        r = compute([])
        assert r.n_trades == 0

    def test_basic(self) -> None:
        r = compute([10, -5, 8, -4, 12])
        assert r.n_trades == 5
        assert r.realized_win_rate == 0.6
        # avg win = (10+8+12)/3 = 10; avg loss = (5+4)/2 = 4.5; rtr = 10/4.5
        assert r.rtr == pytest.approx(10 / 4.5)
        # ev = (10-5+8-4+12)/5 = 4.2
        assert r.expected_value_per_trade == pytest.approx(4.2)

    def test_breakeven_wr(self) -> None:
        # avg_win=8, avg_loss=4 → breakeven 4/(4+8) = 1/3
        r = compute([8, 8, 8, -4, -4, -4])
        assert r.breakeven_win_rate == pytest.approx(1 / 3)


class TestRtrGate:
    def test_yes_at_low_price_passes(self) -> None:
        # Buy YES at 0.20 → RTR = 0.80/0.20 = 4.0 → passes
        assert passes_rtr_gate(model_probability=0.5, executable_price=0.20, side="BUY_YES")

    def test_yes_at_extreme_price_blocks(self) -> None:
        # Buy YES at 0.95 → RTR = 0.05/0.95 ≈ 0.053 → fails (< 0.15)
        assert not passes_rtr_gate(model_probability=0.99, executable_price=0.95, side="BUY_YES")

    def test_yes_threshold_boundary(self) -> None:
        # RTR = (1-p)/p = 0.15 ⇒ p ≈ 0.8696
        assert passes_rtr_gate(model_probability=0.95, executable_price=0.86, side="BUY_YES")
        assert not passes_rtr_gate(model_probability=0.95, executable_price=0.88, side="BUY_YES")

    def test_no_at_high_yes_price(self) -> None:
        # Buy NO when YES is at 0.85 → effectively buying NO at 0.15.
        # RTR for NO = p/(1-p) = 0.85/0.15 ≈ 5.67 → passes
        assert passes_rtr_gate(model_probability=0.50, executable_price=0.85, side="BUY_NO")

    def test_invalid_inputs(self) -> None:
        assert not passes_rtr_gate(model_probability=0.5, executable_price=0.0, side="BUY_YES")
        assert not passes_rtr_gate(model_probability=0.5, executable_price=1.0, side="BUY_YES")
        assert not passes_rtr_gate(model_probability=0.5, executable_price=0.5, side="HODL")


class TestDynamicEntry:
    def test_early_high_edge_allowed(self) -> None:
        # Plenty of time, edge above early threshold
        assert dynamic_entry_allowed(edge=0.20, minutes_to_close=24 * 60)

    def test_early_low_edge_blocked(self) -> None:
        assert not dynamic_entry_allowed(edge=0.10, minutes_to_close=24 * 60)

    def test_late_requires_higher_edge(self) -> None:
        # Within 60min of close, edge 0.20 is no longer enough
        assert not dynamic_entry_allowed(edge=0.20, minutes_to_close=10)
        assert dynamic_entry_allowed(edge=0.30, minutes_to_close=10)

    def test_already_closed_blocked(self) -> None:
        assert not dynamic_entry_allowed(edge=0.50, minutes_to_close=0)
