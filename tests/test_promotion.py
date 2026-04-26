"""Promotion gate tests (PRD §20.3)."""

from __future__ import annotations

from polyflow.promotion import PromotionInputs, evaluate


def _passing() -> PromotionInputs:
    return PromotionInputs(
        observer_days=14,
        paper_days=30,
        paper_trades=200,
        live_tiny_trades=50,
        unexplained_pnl_events=0,
        kelly_breaches=0,
        unlogged_actions=0,
        calibration_report_present=True,
        closing_line_value_positive=True,
        post_order_hook_pass_rate=1.0,
    )


class TestPromotion:
    def test_full_pass(self) -> None:
        d = evaluate(_passing())
        assert d.promote
        assert not d.reasons

    def test_paper_trades_short(self) -> None:
        p = _passing()
        p = PromotionInputs(**{**p.__dict__, "paper_trades": 50})
        d = evaluate(p)
        assert not d.promote
        assert any("PAPER_TRADES" in r for r in d.reasons)

    def test_kelly_breach_fails(self) -> None:
        p = _passing()
        p = PromotionInputs(**{**p.__dict__, "kelly_breaches": 1})
        d = evaluate(p)
        assert not d.promote
        assert "KELLY_BREACHES>0" in d.reasons

    def test_calibration_required(self) -> None:
        p = _passing()
        p = PromotionInputs(**{**p.__dict__, "calibration_report_present": False})
        d = evaluate(p)
        assert not d.promote
        assert "CALIBRATION_REPORT_MISSING" in d.reasons
