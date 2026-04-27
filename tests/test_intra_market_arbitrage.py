"""Intra-market arbitrage detector tests."""

from __future__ import annotations

import pytest

from polyflow.strategies.intra_market_arbitrage import detect, expected_lock


class TestDetect:
    def test_clear_arbitrage(self) -> None:
        # YES ask 0.45, NO ask 0.50 → combined 0.95, lock = 5c per unit
        opp = detect(
            market_id="m1",
            yes_ask=0.45,
            no_ask=0.50,
            yes_depth_usd=10_000,
            no_depth_usd=10_000,
            fee_rate_bps=0,
            slippage_bps_each_side=0,
        )
        assert opp is not None
        assert opp.combined_ask == pytest.approx(0.95)
        assert opp.lock_per_unit == pytest.approx(0.05)
        assert opp.lock_after_costs == pytest.approx(0.05)

    def test_no_arbitrage_when_combined_at_or_above_one(self) -> None:
        opp = detect(
            market_id="m1",
            yes_ask=0.50, no_ask=0.50,
            yes_depth_usd=1000, no_depth_usd=1000,
        )
        assert opp is None

    def test_below_min_lock_threshold_refused(self) -> None:
        # Combined 0.998 → lock 0.2c → fails default 0.5% min
        opp = detect(
            market_id="m1",
            yes_ask=0.50, no_ask=0.498,
            yes_depth_usd=1000, no_depth_usd=1000,
        )
        assert opp is None

    def test_fee_drag_eats_lock(self) -> None:
        opp = detect(
            market_id="m1",
            yes_ask=0.49, no_ask=0.50,        # combined 0.99 → 1c lock
            yes_depth_usd=1000, no_depth_usd=1000,
            fee_rate_bps=100,                  # 1% fee both sides → eats edge
            slippage_bps_each_side=20,
        )
        # 1c gross lock, ~1.2c drag → no positive lock
        assert opp is None

    def test_size_capped_by_min_depth(self) -> None:
        opp = detect(
            market_id="m1",
            yes_ask=0.45, no_ask=0.50,
            yes_depth_usd=2000, no_depth_usd=500,
            fee_rate_bps=0, slippage_bps_each_side=0,
        )
        assert opp is not None
        assert opp.max_size_usd == 500


class TestExpectedLock:
    def test_lock_dollar_value(self) -> None:
        opp = detect(
            market_id="m",
            yes_ask=0.40, no_ask=0.50,
            yes_depth_usd=2000, no_depth_usd=2000,
            fee_rate_bps=0, slippage_bps_each_side=0,
        )
        assert opp is not None
        # Stake $90 → buy 1 unit (cost $0.90) → win $0.10 = lock 11.1% of stake
        lock = expected_lock(opp, stake_usd=90.0)
        assert lock == pytest.approx(90.0 * (0.10 / 0.90))
