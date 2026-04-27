"""Deployment gate tests (Protocol §7)."""

from __future__ import annotations

from polyflow.deployment_gates import GateInputs, evaluate


def _passing(**overrides) -> GateInputs:
    base = dict(
        historical_markets_validated=10,
        historical_pnl_total_usd=120.0,
        simulation_trades=200,
        simulation_ev_per_trade_usd=0.20,
        simulation_max_drawdown_usd=15.0,
        simulation_realized_win_rate=0.55,
        ghost_mode_hours=80.0,
        ghost_mode_orders_attempted=120,
        ghost_mode_unhandled_failure_modes=0,
        live_dryrun_days=8.0,
        live_dryrun_bankroll_pct_used=0.05,
        live_dryrun_pnl_total_usd=8.0,
        live_dryrun_kelly_breaches=0,
    )
    base.update(overrides)
    return GateInputs(**base)


class TestGates:
    def test_all_pass(self) -> None:
        d = evaluate(_passing())
        assert d.promote
        assert d.stage == 4
        assert d.blockers == ()

    def test_gate1_short_history_blocks(self) -> None:
        d = evaluate(_passing(historical_markets_validated=2))
        assert not d.promote
        assert d.stage == 0
        assert any("HISTORICAL" in r for r in d.blockers)

    def test_gate2_low_ev_blocks(self) -> None:
        d = evaluate(_passing(simulation_ev_per_trade_usd=0.05))
        assert d.stage == 1
        assert any("EV_PER_TRADE" in r for r in d.blockers)

    def test_gate3_short_ghost_blocks(self) -> None:
        d = evaluate(_passing(ghost_mode_hours=40.0))
        assert d.stage == 2
        assert any("GHOST_HOURS" in r for r in d.blockers)

    def test_gate3_unhandled_failures_block(self) -> None:
        d = evaluate(_passing(ghost_mode_unhandled_failure_modes=2))
        assert d.stage == 2
        assert "GHOST_UNHANDLED_FAILURES>0" in d.blockers

    def test_gate4_kelly_breach_blocks_promotion(self) -> None:
        d = evaluate(_passing(live_dryrun_kelly_breaches=1))
        assert d.stage == 3
        assert "LIVE_DRYRUN_KELLY_BREACHES>0" in d.blockers

    def test_gate4_too_much_bankroll_blocks(self) -> None:
        d = evaluate(_passing(live_dryrun_bankroll_pct_used=0.5))
        assert d.stage == 3
        assert any("BANKROLL" in r for r in d.blockers)
