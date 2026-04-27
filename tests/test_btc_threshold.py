"""BTC threshold strategy tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.config import Policy
from polyflow.strategies import BtcThresholdSnapshot, btc_threshold_signal
from polyflow.strategies.btc_threshold import threshold_probability
from polyflow.types import Market, Outcome, Strategy


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _market(**overrides) -> Market:
    base = dict(
        id="btc-5m",
        event_id="btc-event",
        question="Will Bitcoin be above the price to beat?",
        category="crypto",
        close_time=_now() + timedelta(minutes=2),
        resolution_rules="Resolves against the public BTC oracle price at the end of the window.",
        liquidity_usd=250_000,
        volume_24h_usd=100_000,
        spread_pct=1.0,
        depth_within_5c_usd=50_000,
        best_bid=0.55,
        best_ask=0.56,
        yes_token_id="up-token",
        no_token_id="down-token",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=0.072,
        neg_risk=False,
        market_quality=0.90,
        resolution_risk=0.04,
    )
    base.update(overrides)
    return Market(**base)


def _snapshot(**overrides) -> BtcThresholdSnapshot:
    base = dict(
        source_name="public-btc-feed",
        source_url="https://example.com/btc",
        fetched_at=_now(),
        price_to_beat=100_000.0,
        btc_spot=100_200.0,
        seconds_to_resolution=120.0,
        realized_volatility_annualized=0.80,
        feed_disagreement_bps=2.0,
        oracle_latency_seconds=2.0,
        settlement_match=True,
    )
    base.update(overrides)
    return BtcThresholdSnapshot(**base)


class TestThresholdProbability:
    def test_probability_moves_with_gap(self) -> None:
        up = threshold_probability(_snapshot(btc_spot=100_200.0))
        down = threshold_probability(_snapshot(btc_spot=99_800.0))
        assert up is not None and up > 0.50
        assert down is not None and down < 0.50


class TestBtcThresholdSignal:
    def test_emits_buy_yes_on_strong_positive_gap(self) -> None:
        out = btc_threshold_signal(
            policy=Policy(),
            market=_market(),
            snapshot=_snapshot(),
        )
        assert out is not None
        est, sig = out
        assert sig.strategy is Strategy.BTC_THRESHOLD
        assert sig.outcome is Outcome.YES
        assert sig.token_id == "up-token"
        assert est.edge_after_costs > 0

    def test_emits_buy_no_on_strong_negative_gap(self) -> None:
        out = btc_threshold_signal(
            policy=Policy(),
            market=_market(best_bid=0.44, best_ask=0.45),
            snapshot=_snapshot(btc_spot=99_800.0),
        )
        assert out is not None
        _est, sig = out
        assert sig.outcome is Outcome.NO
        assert sig.token_id == "down-token"

    def test_stale_feed_rejected(self) -> None:
        out = btc_threshold_signal(
            policy=Policy(),
            market=_market(),
            snapshot=_snapshot(fetched_at=_now() - timedelta(seconds=30)),
        )
        assert out is None

    def test_feed_disagreement_rejected(self) -> None:
        out = btc_threshold_signal(
            policy=Policy(),
            market=_market(),
            snapshot=_snapshot(feed_disagreement_bps=20.0),
        )
        assert out is None

    def test_near_expiry_rejected(self) -> None:
        out = btc_threshold_signal(
            policy=Policy(),
            market=_market(),
            snapshot=_snapshot(seconds_to_resolution=10.0),
        )
        assert out is None

    def test_settlement_mismatch_rejected(self) -> None:
        out = btc_threshold_signal(
            policy=Policy(),
            market=_market(),
            snapshot=_snapshot(settlement_match=False),
        )
        assert out is None
