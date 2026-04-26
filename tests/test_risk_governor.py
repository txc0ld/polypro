"""Risk Governor tests (PRD §10)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from polyflow.config import Policy
from polyflow.risk_governor import KillSwitch, assert_kill_conditions, evaluate
from polyflow.types import (
    Market,
    Mode,
    Outcome,
    ProbabilityEstimate,
    RiskState,
    Side,
)


def make_estimate(**overrides) -> ProbabilityEstimate:
    base = dict(
        market_id="m1",
        token_id="t-yes",
        outcome=Outcome.YES,
        market_price=0.62,
        model_probability=0.70,
        uncertainty=0.05,
        fair_bid=0.65,
        fair_ask=0.75,
        edge_before_costs=0.08,
        edge_after_costs=0.04,
        source_confidence=0.85,
        resolution_risk=0.10,
        recommendation="BUY_YES",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        reason_codes=[],
        evidence_refs=["ev1"],
    )
    base.update(overrides)
    return ProbabilityEstimate(**base)


def make_market(**overrides) -> Market:
    base = dict(
        id="m1",
        event_id="e1",
        question="Q?",
        category="crypto",
        close_time=datetime.now(timezone.utc) + timedelta(hours=12),
        resolution_rules="rules",
        liquidity_usd=200_000,
        volume_24h_usd=50_000,
        spread_pct=2.0,
        depth_within_5c_usd=20_000,
        yes_token_id="t-yes",
        no_token_id="t-no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=200,
        neg_risk=False,
        market_quality=0.80,
        resolution_risk=0.10,
    )
    base.update(overrides)
    return Market(**base)


def live_tiny_policy() -> Policy:
    p = Policy()
    p.mode = Mode.LIVE_TINY
    return p


class TestEvaluate:
    def test_observe_mode_blocks_orders(self) -> None:
        p = Policy()  # default mode = OBSERVE
        d = evaluate(
            policy=p,
            estimate=make_estimate(),
            market=make_market(),
            side=Side.BUY,
            state=RiskState(bankroll_usdc=p.risk.bankroll_usdc),
        )
        assert not d.approved
        assert "MODE_OBSERVE" in d.reason_codes

    def test_lockdown_mode_blocks_orders(self) -> None:
        p = Policy(); p.mode = Mode.LOCKDOWN
        d = evaluate(
            policy=p,
            estimate=make_estimate(),
            market=make_market(),
            side=Side.BUY,
            state=RiskState(bankroll_usdc=1000),
        )
        assert not d.approved
        assert "MODE_LOCKDOWN" in d.reason_codes

    def test_happy_path_live_tiny(self) -> None:
        p = live_tiny_policy()
        d = evaluate(
            policy=p,
            estimate=make_estimate(),
            market=make_market(),
            side=Side.BUY,
            state=RiskState(bankroll_usdc=p.risk.bankroll_usdc),
        )
        assert d.approved
        assert d.approved_size_usdc > 0
        # First-day order cap is $10
        assert d.approved_size_usdc <= 10.0

    def test_below_min_edge_rejected(self) -> None:
        p = live_tiny_policy()
        d = evaluate(
            policy=p,
            estimate=make_estimate(edge_after_costs=0.001),
            market=make_market(),
            side=Side.BUY,
            state=RiskState(bankroll_usdc=1000),
        )
        assert not d.approved
        assert "EDGE_BELOW_MIN" in d.reason_codes

    def test_uncertainty_over_cap_rejected(self) -> None:
        p = live_tiny_policy()
        d = evaluate(
            policy=p,
            estimate=make_estimate(uncertainty=0.20),
            market=make_market(),
            side=Side.BUY,
            state=RiskState(bankroll_usdc=1000),
        )
        assert not d.approved
        assert "UNCERTAINTY_OVER_CAP" in d.reason_codes

    def test_resolution_risk_over_cap_rejected(self) -> None:
        p = live_tiny_policy()
        d = evaluate(
            policy=p,
            estimate=make_estimate(resolution_risk=0.50),
            market=make_market(resolution_risk=0.50),
            side=Side.BUY,
            state=RiskState(bankroll_usdc=1000),
        )
        assert not d.approved
        assert "RESOLUTION_RISK_OVER_CAP" in d.reason_codes

    def test_market_position_cap_clamps_size(self) -> None:
        p = live_tiny_policy()
        # Already used 90% of single-market cap ($1000 * 1% = $10)
        state = RiskState(
            bankroll_usdc=1000,
            used_market_usdc={"m1": 9.0},
        )
        d = evaluate(
            policy=p,
            estimate=make_estimate(),
            market=make_market(),
            side=Side.BUY,
            state=state,
        )
        assert d.approved
        assert d.approved_size_usdc <= 1.0 + 1e-9
        assert "MARKET_CAP" in d.caps_applied

    def test_open_markets_cap_blocks(self) -> None:
        p = live_tiny_policy()
        state = RiskState(bankroll_usdc=1000, open_markets=p.risk.max_open_markets)
        d = evaluate(
            policy=p,
            estimate=make_estimate(),
            market=make_market(),
            side=Side.BUY,
            state=state,
        )
        assert not d.approved
        assert "OPEN_MARKETS_CAP_HIT" in d.reason_codes


class TestKillSwitch:
    def test_daily_loss_kills(self) -> None:
        p = live_tiny_policy()
        state = RiskState(bankroll_usdc=1000, daily_loss_usdc=10.0)  # > 0.75%
        with pytest.raises(KillSwitch):
            assert_kill_conditions(state, p)

    def test_negative_balance_kills(self) -> None:
        p = live_tiny_policy()
        with pytest.raises(KillSwitch):
            assert_kill_conditions(RiskState(bankroll_usdc=-1.0), p)
