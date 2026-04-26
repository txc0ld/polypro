"""CLOB Order Formatter tests (PRD §11, §14.4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.config import Policy
from polyflow.order_formatter import format_order
from polyflow.types import (
    Market,
    Mode,
    OrderType,
    Outcome,
    ProbabilityEstimate,
    RiskDecision,
    Side,
    Strategy,
)


def make_estimate(**overrides) -> ProbabilityEstimate:
    base = dict(
        market_id="m1",
        token_id="t-yes",
        outcome=Outcome.YES,
        market_price=0.625,
        model_probability=0.70,
        uncertainty=0.05,
        fair_bid=0.65,
        fair_ask=0.75,
        edge_before_costs=0.075,
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


def good_decision(**overrides) -> RiskDecision:
    base = dict(
        approved=True,
        approved_size_usdc=10.0,
        raw_kelly=0.20,
        fractional_kelly=0.01,
        caps_applied=[],
        reason_codes=[],
    )
    base.update(overrides)
    return RiskDecision(**base)


def live_tiny_policy() -> Policy:
    p = Policy()
    p.mode = Mode.LIVE_TINY
    return p


class TestFormatOrder:
    def test_happy_path_buy_yes(self) -> None:
        out = format_order(
            policy=live_tiny_policy(),
            market=make_market(),
            estimate=make_estimate(),
            decision=good_decision(),
            side=Side.BUY,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            order_type=OrderType.GTC,
            current_token_balance=0.0,
            evidence_ref="ev1",
            risk_ref="r1",
        )
        assert out.ready_to_submit
        assert out.order_payload is not None
        # BUY rounds price down to nearest tick
        assert out.order_payload.price in ("0.62", "0.63") and float(out.order_payload.price) <= 0.625
        # Size respects min_order_size grid (5.0)
        assert float(out.order_payload.size) >= 5.0

    def test_evidence_ref_required(self) -> None:
        out = format_order(
            policy=live_tiny_policy(),
            market=make_market(),
            estimate=make_estimate(),
            decision=good_decision(),
            side=Side.BUY,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            order_type=OrderType.GTC,
            evidence_ref=None,
        )
        assert out.rejected
        assert "EVIDENCE_REF_MISSING" in out.reason_codes

    def test_unapproved_risk_rejected(self) -> None:
        out = format_order(
            policy=live_tiny_policy(),
            market=make_market(),
            estimate=make_estimate(),
            decision=good_decision(approved=False, approved_size_usdc=0),
            side=Side.BUY,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            order_type=OrderType.GTC,
            evidence_ref="ev1",
        )
        assert out.rejected

    def test_missing_tick_size_rejected(self) -> None:
        out = format_order(
            policy=live_tiny_policy(),
            market=make_market(tick_size=None),
            estimate=make_estimate(),
            decision=good_decision(),
            side=Side.BUY,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            order_type=OrderType.GTC,
            evidence_ref="ev1",
        )
        assert out.rejected
        assert "TICK_SIZE_UNKNOWN" in out.reason_codes

    def test_fok_blocked_in_live_tiny(self) -> None:
        out = format_order(
            policy=live_tiny_policy(),
            market=make_market(),
            estimate=make_estimate(),
            decision=good_decision(),
            side=Side.BUY,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            order_type=OrderType.FOK,
            evidence_ref="ev1",
        )
        assert out.rejected
        # Either ORDER_TYPE_NOT_ALLOWED_LIVE_TINY or FOK_BLOCKED should fire.
        assert any(r in out.reason_codes for r in ("ORDER_TYPE_NOT_ALLOWED_LIVE_TINY", "FOK_BLOCKED"))

    def test_sell_exceeding_balance_rejected(self) -> None:
        out = format_order(
            policy=live_tiny_policy(),
            market=make_market(),
            estimate=make_estimate(),
            decision=good_decision(approved_size_usdc=10.0),
            side=Side.SELL,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            order_type=OrderType.GTC,
            current_token_balance=0.0,
            evidence_ref="ev1",
        )
        assert out.rejected
        assert "SELL_EXCEEDS_BALANCE" in out.reason_codes

    def test_size_below_min_order_size_rejected(self) -> None:
        out = format_order(
            policy=live_tiny_policy(),
            market=make_market(min_order_size=5.0),
            estimate=make_estimate(),
            # $1 / 0.625 ≈ 1.6 units → below min 5.0 → reject
            decision=good_decision(approved_size_usdc=1.0),
            side=Side.BUY,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            order_type=OrderType.GTC,
            evidence_ref="ev1",
        )
        assert out.rejected
        assert "SIZE_BELOW_MIN_ORDER_SIZE" in out.reason_codes

    def test_buy_price_rounds_down_sell_rounds_up(self) -> None:
        # BUY → floor; SELL → ceil
        m = make_market(tick_size=0.01)
        e_buy = make_estimate(market_price=0.6249)
        e_sell = make_estimate(market_price=0.6251)

        buy = format_order(
            policy=live_tiny_policy(),
            market=m,
            estimate=e_buy,
            decision=good_decision(),
            side=Side.BUY,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            order_type=OrderType.GTC,
            evidence_ref="ev1",
        )
        sell = format_order(
            policy=live_tiny_policy(),
            market=m,
            estimate=e_sell,
            decision=good_decision(),
            side=Side.SELL,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            order_type=OrderType.GTC,
            current_token_balance=10_000.0,
            evidence_ref="ev1",
        )
        assert buy.ready_to_submit and sell.ready_to_submit
        assert buy.order_payload is not None and sell.order_payload is not None
        assert float(buy.order_payload.price) <= 0.6249
        assert float(sell.order_payload.price) >= 0.6251
