"""Signal scoring + decision matrix tests (PRD §17)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from polyflow.signals import decide_action, score_signal
from polyflow.types import Outcome, Side, Signal, Strategy


def make_signal(**overrides) -> Signal:
    base = dict(
        market_id="m1",
        event_id="e1",
        token_id="t-yes",
        outcome=Outcome.YES,
        side=Side.BUY,
        strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
        market_price=0.62,
        model_probability=0.70,
        uncertainty=0.05,
        effective_edge=0.04,
        market_quality=0.85,
        resolution_risk=0.10,
        liquidity_score=0.80,
        confidence=0.85,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        evidence_refs=["ev1"],
    )
    base.update(overrides)
    return Signal(**base)


class TestScore:
    def test_score_in_0_100(self) -> None:
        s = score_signal(make_signal())
        assert 0 <= s <= 100

    def test_high_quality_high_score(self) -> None:
        good = score_signal(make_signal())
        weak = score_signal(
            make_signal(
                effective_edge=0.005,
                market_quality=0.40,
                liquidity_score=0.30,
                confidence=0.50,
            )
        )
        assert good > weak

    def test_high_uncertainty_penalty(self) -> None:
        a = score_signal(make_signal(uncertainty=0.05))
        b = score_signal(make_signal(uncertainty=0.20))
        assert a > b


class TestDecide:
    @pytest.mark.parametrize(
        "score,action",
        [
            (50, "REJECT"),
            (75, "WATCH"),
            (82, "PAPER"),
            (90, "LIVE_TINY"),
            (96, "LIVE_STANDARD"),
        ],
    )
    def test_thresholds(self, score: float, action: str) -> None:
        assert decide_action(score) == action
