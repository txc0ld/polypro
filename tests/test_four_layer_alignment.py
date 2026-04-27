"""Four-layer alignment strategy tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.config import Policy
from polyflow.strategies import (
    AlignmentCycle,
    AlignmentLayer,
    AlignmentLayerSignal,
    four_layer_alignment_signal,
)
from polyflow.types import Market, Outcome, Strategy


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _market(**overrides) -> Market:
    base = dict(
        id="m1",
        event_id="e1",
        question="Q?",
        category="sports",
        close_time=_now() + timedelta(hours=1),
        resolution_rules="Clear public resolution rules.",
        liquidity_usd=300_000,
        volume_24h_usd=100_000,
        spread_pct=1.0,
        depth_within_5c_usd=50_000,
        best_bid=0.50,
        best_ask=0.51,
        yes_token_id="t-yes",
        no_token_id="t-no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=0.03,
        neg_risk=False,
        market_quality=0.90,
        resolution_risk=0.03,
    )
    base.update(overrides)
    return Market(**base)


def _cycle(**overrides) -> AlignmentCycle:
    base = dict(
        received_at=_now(),
        feed_latency_ms=80.0,
        tracked_wallet_count=200,
        out_of_sequence=False,
        stale_snapshot=False,
        order_book_jump_pct=3.0,
        onchain_flow_confirmed=True,
    )
    base.update(overrides)
    return AlignmentCycle(**base)


def _sig(layer: AlignmentLayer, **overrides) -> AlignmentLayerSignal:
    base = dict(
        layer=layer,
        direction=Outcome.YES,
        observed_at=_now() - timedelta(minutes=3),
        confidence=0.90,
        fair_probability=0.74,
        evidence_ref=f"evidence:{layer.value}",
        reason_code=f"{layer.value.upper()}_CONFIRMED",
    )
    if layer is AlignmentLayer.ORDER_BOOK_DEPTH:
        base.update(depth_ratio_flip=3.0, volume_confirmed=True)
    elif layer is AlignmentLayer.WALLET_CONVICTION:
        base.update(
            wallet_accuracy=0.72,
            wallet_resolved_markets=80,
            wallet_realized_pnl_positive=True,
            wallet_position_delta_usdc=100.0,
        )
    elif layer is AlignmentLayer.NEWS_PRICE_LAG:
        base.update(price_moved_toward_fair=0.40, headline_age_minutes=5.0)
    elif layer is AlignmentLayer.POSITION_DELTA:
        base.update(wallet_position_delta_usdc=80.0, adding_against_price=True)
    base.update(overrides)
    return AlignmentLayerSignal(**base)


class TestFourLayerAlignment:
    def test_emits_when_three_layers_align(self) -> None:
        out = four_layer_alignment_signal(
            policy=Policy(),
            market=_market(),
            cycle=_cycle(),
            layer_signals=[
                _sig(AlignmentLayer.ORDER_BOOK_DEPTH),
                _sig(AlignmentLayer.WALLET_CONVICTION),
                _sig(AlignmentLayer.NEWS_PRICE_LAG),
            ],
        )
        assert out is not None
        est, sig = out
        assert sig.strategy is Strategy.FOUR_LAYER_ALIGNMENT
        assert sig.outcome is Outcome.YES
        assert "ALIGNED_LAYERS:3" in sig.reason_codes
        assert est.edge_after_costs > 0

    def test_silent_with_only_two_layers(self) -> None:
        out = four_layer_alignment_signal(
            policy=Policy(),
            market=_market(),
            cycle=_cycle(),
            layer_signals=[
                _sig(AlignmentLayer.ORDER_BOOK_DEPTH),
                _sig(AlignmentLayer.WALLET_CONVICTION),
            ],
        )
        assert out is None

    def test_four_layer_signal_can_buy_no(self) -> None:
        out = four_layer_alignment_signal(
            policy=Policy(),
            market=_market(best_bid=0.50, best_ask=0.51),
            cycle=_cycle(),
            layer_signals=[
                _sig(AlignmentLayer.ORDER_BOOK_DEPTH, direction=Outcome.NO, fair_probability=0.74),
                _sig(AlignmentLayer.WALLET_CONVICTION, direction=Outcome.NO, fair_probability=0.73),
                _sig(AlignmentLayer.POSITION_DELTA, direction=Outcome.NO, fair_probability=0.72),
            ],
        )
        assert out is not None
        _est, sig = out
        assert sig.outcome is Outcome.NO
        assert sig.token_id == "t-no"

    def test_trap_wallet_rejected(self) -> None:
        out = four_layer_alignment_signal(
            policy=Policy(),
            market=_market(),
            cycle=_cycle(),
            layer_signals=[
                _sig(AlignmentLayer.ORDER_BOOK_DEPTH),
                _sig(AlignmentLayer.WALLET_CONVICTION, wallet_is_trap=True),
                _sig(AlignmentLayer.NEWS_PRICE_LAG),
            ],
        )
        assert out is None

    def test_high_latency_cycle_rejected(self) -> None:
        out = four_layer_alignment_signal(
            policy=Policy(),
            market=_market(),
            cycle=_cycle(feed_latency_ms=150.0),
            layer_signals=[
                _sig(AlignmentLayer.ORDER_BOOK_DEPTH),
                _sig(AlignmentLayer.WALLET_CONVICTION),
                _sig(AlignmentLayer.NEWS_PRICE_LAG),
            ],
        )
        assert out is None

    def test_book_jump_without_onchain_flow_rejected(self) -> None:
        out = four_layer_alignment_signal(
            policy=Policy(),
            market=_market(),
            cycle=_cycle(order_book_jump_pct=20.0, onchain_flow_confirmed=False),
            layer_signals=[
                _sig(AlignmentLayer.ORDER_BOOK_DEPTH),
                _sig(AlignmentLayer.WALLET_CONVICTION),
                _sig(AlignmentLayer.NEWS_PRICE_LAG),
            ],
        )
        assert out is None

    def test_low_edge_rejected(self) -> None:
        out = four_layer_alignment_signal(
            policy=Policy(),
            market=_market(best_bid=0.60, best_ask=0.61),
            cycle=_cycle(),
            layer_signals=[
                _sig(AlignmentLayer.ORDER_BOOK_DEPTH, fair_probability=0.70),
                _sig(AlignmentLayer.WALLET_CONVICTION, fair_probability=0.70),
                _sig(AlignmentLayer.NEWS_PRICE_LAG, fair_probability=0.70),
            ],
        )
        assert out is None

    def test_late_cycle_requires_larger_edge(self) -> None:
        old = _now() - timedelta(minutes=8)
        out = four_layer_alignment_signal(
            policy=Policy(),
            market=_market(best_bid=0.50, best_ask=0.51),
            cycle=_cycle(received_at=_now()),
            layer_signals=[
                _sig(AlignmentLayer.ORDER_BOOK_DEPTH, observed_at=old, fair_probability=0.70),
                _sig(AlignmentLayer.WALLET_CONVICTION, observed_at=old, fair_probability=0.70),
                _sig(AlignmentLayer.NEWS_PRICE_LAG, observed_at=old, fair_probability=0.70),
            ],
        )
        assert out is None

    def test_requires_exact_wallet_universe_count(self) -> None:
        out = four_layer_alignment_signal(
            policy=Policy(),
            market=_market(),
            cycle=_cycle(tracked_wallet_count=199),
            layer_signals=[
                _sig(AlignmentLayer.ORDER_BOOK_DEPTH),
                _sig(AlignmentLayer.WALLET_CONVICTION),
                _sig(AlignmentLayer.NEWS_PRICE_LAG),
            ],
        )
        assert out is None
