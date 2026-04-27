"""Circuit-breaker tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.circuit_breakers import CircuitBreakers


class TestConsecutiveLosses:
    def test_initial_state_can_trade(self) -> None:
        cb = CircuitBreakers()
        assert cb.can_trade is True
        assert cb.consecutive_losses == 0

    def test_losing_trades_increment(self) -> None:
        cb = CircuitBreakers(max_consecutive_losses=5)
        for _ in range(3):
            cb.record_outcome(pnl_usdc=-1.0)
        assert cb.consecutive_losses == 3
        assert cb.can_trade is True

    def test_freezes_at_threshold(self) -> None:
        cb = CircuitBreakers(max_consecutive_losses=3)
        cb.record_outcome(pnl_usdc=-1.0)
        cb.record_outcome(pnl_usdc=-2.0)
        cb.record_outcome(pnl_usdc=-0.5)
        assert cb.consecutive_losses == 3
        assert cb.can_trade is False

    def test_win_resets_streak(self) -> None:
        cb = CircuitBreakers(max_consecutive_losses=5)
        cb.record_outcome(pnl_usdc=-1.0)
        cb.record_outcome(pnl_usdc=-1.0)
        assert cb.consecutive_losses == 2
        cb.record_outcome(pnl_usdc=+0.5)
        assert cb.consecutive_losses == 0

    def test_breakeven_resets_streak(self) -> None:
        cb = CircuitBreakers()
        cb.record_outcome(pnl_usdc=-1.0)
        cb.record_outcome(pnl_usdc=0.0)
        assert cb.consecutive_losses == 0

    def test_reset_clears_freeze(self) -> None:
        cb = CircuitBreakers(max_consecutive_losses=2)
        cb.record_outcome(pnl_usdc=-1.0)
        cb.record_outcome(pnl_usdc=-1.0)
        assert cb.can_trade is False
        cb.reset()
        assert cb.can_trade is True
        assert cb.consecutive_losses == 0


class TestFinalBlackout:
    def test_inside_window_blocks(self) -> None:
        cb = CircuitBreakers(final_blackout_seconds=60)
        close = datetime.now(timezone.utc) + timedelta(seconds=30)
        assert cb.in_final_blackout(close_time=close) is True

    def test_outside_window_allows(self) -> None:
        cb = CircuitBreakers(final_blackout_seconds=60)
        close = datetime.now(timezone.utc) + timedelta(minutes=10)
        assert cb.in_final_blackout(close_time=close) is False

    def test_already_closed_not_in_blackout(self) -> None:
        cb = CircuitBreakers(final_blackout_seconds=60)
        close = datetime.now(timezone.utc) - timedelta(seconds=10)
        assert cb.in_final_blackout(close_time=close) is False

    def test_no_close_time_not_blocked(self) -> None:
        cb = CircuitBreakers()
        assert cb.in_final_blackout(close_time=None) is False

    def test_whitelist_bypasses_blackout(self) -> None:
        cb = CircuitBreakers(final_blackout_seconds=60, whitelisted_market_ids=frozenset({"m1"}))
        close = datetime.now(timezone.utc) + timedelta(seconds=20)
        assert cb.in_final_blackout(close_time=close, market_id="m1") is False
        assert cb.in_final_blackout(close_time=close, market_id="m2") is True

    def test_naive_datetime_assumed_utc(self) -> None:
        cb = CircuitBreakers()
        close = datetime.utcnow() + timedelta(seconds=30)  # naive
        assert cb.in_final_blackout(close_time=close) is True
