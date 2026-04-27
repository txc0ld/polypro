"""Reality-grade simulator tests (Protocol §2)."""

from __future__ import annotations

import pytest

from polyflow.simulator import (
    BookLevel,
    BookSnapshot,
    IntendedOrder,
    aggregate,
    realize,
    simulate_fill,
)


def _ask_book(*levels: tuple[float, float]) -> BookSnapshot:
    return BookSnapshot(yes_asks=[BookLevel(price=p, size_usdc=s) for p, s in levels])


def _bid_book(*levels: tuple[float, float]) -> BookSnapshot:
    return BookSnapshot(yes_bids=[BookLevel(price=p, size_usdc=s) for p, s in levels])


def _order(side: str, price: float, size: float) -> IntendedOrder:
    return IntendedOrder(market_id="m", side=side, limit_price=price, size_usdc=size, placed_at_ns=0)


class TestSimulateFill:
    def test_fills_at_best_ask(self) -> None:
        book = _ask_book((0.55, 100.0), (0.56, 100.0))
        fill = simulate_fill(_order("BUY_YES", 0.60, 50.0), book)
        assert fill.filled_usdc == 50.0
        assert fill.avg_price == pytest.approx(0.55)
        assert fill.shares == pytest.approx(50.0 / 0.55)

    def test_walks_through_levels(self) -> None:
        book = _ask_book((0.55, 30.0), (0.56, 100.0))
        fill = simulate_fill(_order("BUY_YES", 0.60, 50.0), book)
        # 30 at 0.55 + 20 at 0.56
        assert fill.filled_usdc == 50.0
        expected_shares = 30.0 / 0.55 + 20.0 / 0.56
        assert fill.shares == pytest.approx(expected_shares)

    def test_limit_caps_fill(self) -> None:
        book = _ask_book((0.55, 30.0), (0.56, 100.0))
        fill = simulate_fill(_order("BUY_YES", 0.555, 50.0), book)
        # Only the 0.55 level qualifies under the limit
        assert fill.filled_usdc == 30.0

    def test_queue_ahead_blocks_fill(self) -> None:
        book = _ask_book((0.55, 30.0), (0.56, 100.0))
        fill = simulate_fill(_order("BUY_YES", 0.60, 50.0), book, queue_ahead_usdc=30.0)
        # Queue absorbs the entire 0.55 level; we cross to 0.56 instead
        assert fill.avg_price > 0.55
        # 50 at 0.56 → 50 USDC, ~89.28 shares
        assert fill.filled_usdc == 50.0

    def test_buy_no_uses_yes_bids(self) -> None:
        # YES bid at 0.55 means buyers pay 0.55 for YES → seller of YES
        # gets 0.55 → equivalent NO ask = 0.45. Buying NO at limit 0.50
        # should fill 50 USDC at NO-price ~0.45.
        book = _bid_book((0.55, 100.0))
        fill = simulate_fill(_order("BUY_NO", 0.50, 30.0), book)
        assert fill.filled_usdc == 30.0
        assert fill.avg_price == pytest.approx(0.45)

    def test_fees_and_gas(self) -> None:
        book = _ask_book((0.50, 100.0))
        fill = simulate_fill(
            _order("BUY_YES", 0.60, 50.0), book, fee_rate_bps=200, gas_per_trade_usd=0.05
        )
        assert fill.gross_shares == pytest.approx(100.0)
        assert fill.fee_paid_usdc == pytest.approx(100.0 * 0.02 * 0.50 * 0.50)
        assert fill.shares == pytest.approx(99.0)
        assert fill.gas_paid_usdc == 0.05


class TestRealize:
    def test_buy_yes_wins_pays_payout(self) -> None:
        book = _ask_book((0.50, 100.0))
        fill = simulate_fill(_order("BUY_YES", 0.60, 50.0), book, fee_rate_bps=0, gas_per_trade_usd=0)
        outcome = realize(_order("BUY_YES", 0.60, 50.0), fill, realized_yes=True)
        # 100 shares * $1 - $50 cost - $0 fees - $0 gas = $50
        assert outcome.pnl_usdc == pytest.approx(50.0)

    def test_buy_yes_loses(self) -> None:
        book = _ask_book((0.50, 100.0))
        fill = simulate_fill(_order("BUY_YES", 0.60, 50.0), book, fee_rate_bps=0, gas_per_trade_usd=0)
        outcome = realize(_order("BUY_YES", 0.60, 50.0), fill, realized_yes=False)
        assert outcome.pnl_usdc == pytest.approx(-50.0)

    def test_buy_no_wins(self) -> None:
        book = _bid_book((0.55, 100.0))
        fill = simulate_fill(_order("BUY_NO", 0.50, 45.0), book, fee_rate_bps=0, gas_per_trade_usd=0)
        outcome = realize(_order("BUY_NO", 0.50, 45.0), fill, realized_yes=False)
        # 45 USDC at 0.45 = 100 shares; resolves NO so payout = 100 → pnl = 100 - 45 = 55
        assert outcome.pnl_usdc == pytest.approx(55.0)


class TestAggregate:
    def test_empty(self) -> None:
        rep = aggregate([])
        assert rep.n_filled == 0
        assert rep.expected_value_per_trade == 0.0

    def test_winning_strategy(self) -> None:
        # Three trades at 0.50, all paying off
        outcomes = []
        for _ in range(3):
            book = _ask_book((0.50, 100.0))
            fill = simulate_fill(_order("BUY_YES", 0.55, 20.0), book, fee_rate_bps=0, gas_per_trade_usd=0)
            outcomes.append(realize(_order("BUY_YES", 0.55, 20.0), fill, realized_yes=True))
        rep = aggregate(outcomes)
        assert rep.n_filled == 3
        assert rep.realized_win_rate == 1.0
        assert rep.expected_value_per_trade == pytest.approx(20.0)
        assert rep.max_drawdown_usd == 0.0

    def test_drawdown_tracked(self) -> None:
        # Win, lose, lose, win — drawdown should be 2 * loss size
        outcomes = []
        results = [True, False, False, True]
        for r in results:
            book = _ask_book((0.50, 100.0))
            fill = simulate_fill(_order("BUY_YES", 0.55, 10.0), book, fee_rate_bps=0, gas_per_trade_usd=0)
            outcomes.append(realize(_order("BUY_YES", 0.55, 10.0), fill, realized_yes=r))
        rep = aggregate(outcomes)
        assert rep.max_drawdown_usd == pytest.approx(20.0)
