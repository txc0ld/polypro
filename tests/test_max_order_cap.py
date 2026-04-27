"""Tests for the operator-set max_order_usdc cap."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.config import Policy
from polyflow.risk_governor import evaluate
from polyflow.types import (
    Market,
    Mode,
    Outcome,
    ProbabilityEstimate,
    RiskState,
    Side,
)


def _market() -> Market:
    return Market(
        id="m1", event_id="e1", question="Q?", category="sports",
        close_time=datetime.now(timezone.utc) + timedelta(hours=12),
        resolution_rules="rules",
        liquidity_usd=200_000, volume_24h_usd=80_000, spread_pct=2.0,
        depth_within_5c_usd=20_000,
        yes_token_id="t-yes", no_token_id="t-no",
        tick_size=0.01, min_order_size=5.0, fee_rate_bps=200,
        market_quality=0.85, resolution_risk=0.05,
    )


def _est() -> ProbabilityEstimate:
    return ProbabilityEstimate(
        market_id="m1", token_id="t-yes", outcome=Outcome.YES,
        market_price=0.55, model_probability=0.75, uncertainty=0.04,
        fair_bid=0.71, fair_ask=0.79,
        edge_before_costs=0.20, edge_after_costs=0.16,
        source_confidence=0.90, resolution_risk=0.05,
        recommendation="BUY_YES",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        evidence_refs=["ev1"],
    )


def test_max_order_usdc_is_binding_when_smaller_than_other_caps() -> None:
    # Bankroll $1000 → market_cap = $10, first-day floor = $10. The operator
    # sets the absolute cap to $1; that should be the binding constraint.
    p = Policy()
    p.mode = Mode.LIVE_TINY
    p.risk.bankroll_usdc = 1000.0
    p.risk.max_order_usdc = 1.0
    d = evaluate(
        policy=p,
        estimate=_est(),
        market=_market(),
        side=Side.BUY,
        state=RiskState(bankroll_usdc=1000.0),
    )
    assert d.approved
    assert d.approved_size_usdc <= 1.0 + 1e-9
    assert "MAX_ORDER_USDC" in d.caps_applied


def test_no_cap_when_unset() -> None:
    p = Policy()
    p.mode = Mode.LIVE_TINY
    p.risk.bankroll_usdc = 1000.0
    p.risk.max_order_usdc = None
    d = evaluate(
        policy=p,
        estimate=_est(),
        market=_market(),
        side=Side.BUY,
        state=RiskState(bankroll_usdc=1000.0),
    )
    # Without operator cap, only the FIRST_DAY $10 cap binds in LIVE_TINY.
    assert d.approved_size_usdc <= 10.0 + 1e-9
    assert "MAX_ORDER_USDC" not in d.caps_applied
