"""Incident state machine tests (PRD §10.5)."""

from __future__ import annotations

from polyflow.incident import IncidentManager, State


class TestStateTransitions:
    def test_starts_healthy(self) -> None:
        m = IncidentManager()
        assert m.state is State.HEALTHY
        assert m.can_trade()
        assert m.can_quote()

    def test_degraded_blocks_trading_but_allows_quoting(self) -> None:
        m = IncidentManager()
        m.trip_degraded(code="API_DEGRADED", actor="test")
        assert m.state is State.DEGRADED
        assert not m.can_trade()
        assert m.can_quote()

    def test_lockdown_blocks_quoting(self) -> None:
        m = IncidentManager()
        m.trip_lockdown(code="USER_CHANNEL_STALE")
        assert not m.can_trade()
        assert not m.can_quote()

    def test_killed_is_terminal(self) -> None:
        m = IncidentManager()
        m.trip_killed(code="KELLY_BREACH")
        assert m.state is State.KILLED
        # Subsequent trips are no-ops.
        m.trip_lockdown(code="OTHER")
        assert m.state is State.KILLED
        assert not m.can_trade()
        assert not m.can_quote()

    def test_recovery_only_from_degraded(self) -> None:
        m = IncidentManager()
        m.trip_degraded(code="X")
        assert m.recover_to_healthy() is True
        assert m.state is State.HEALTHY

        m.trip_lockdown(code="Y")
        assert m.recover_to_healthy() is False
        assert m.state is State.LOCKDOWN
