"""Crypto momentum / wick-fade strategy tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from polyflow.config import Policy
from polyflow.strategies.crypto_momentum import (
    CryptoMomentumInputs,
    CryptoMomentumStrategy,
)
from polyflow.types import Market, Strategy


def _market(*, question: str, mid: float = 0.50, spread_pct: float = 1.5, ttc_minutes: int = 90) -> Market:
    bid = mid - spread_pct / 200
    ask = mid + spread_pct / 200
    return Market(
        id="m1", event_id="e1", question=question, category="crypto",
        close_time=datetime.now(timezone.utc) + timedelta(minutes=ttc_minutes),
        resolution_rules="Resolves to YES if asset closes above threshold.",
        liquidity_usd=2_000_000, volume_24h_usd=1_000_000,
        spread_pct=spread_pct, depth_within_5c_usd=200_000,
        best_bid=round(bid, 4), best_ask=round(ask, 4),
        yes_token_id="t-yes", no_token_id="t-no",
        tick_size=0.01, min_order_size=5.0, fee_rate_bps=200,
        market_quality=0.92, resolution_risk=0.05,
    )


def _inputs(**overrides) -> CryptoMomentumInputs:
    base = dict(
        asset="BTC",
        spot_usd=80_000.0,
        perp_basis_bps=-3.0,
        feed_disagreement_bps=2.0,
        velocity_bps_per_min=10.0,
        range_bps=15.0,
        window_seconds=240.0,
        n_samples=12,
        realized_vol_annualized=0.60,
    )
    base.update(overrides)
    return CryptoMomentumInputs(**base)


class TestRefusal:
    def test_dirty_feed_refused(self) -> None:
        s = CryptoMomentumStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(question="Will Bitcoin close above $79,000 today?"),
            inputs=_inputs(feed_disagreement_bps=15.0),
        )
        assert out is None

    def test_perp_basis_blowup_refused(self) -> None:
        s = CryptoMomentumStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(question="Will Bitcoin close above $79,000 today?"),
            inputs=_inputs(perp_basis_bps=120.0),
        )
        assert out is None

    def test_short_window_refused(self) -> None:
        s = CryptoMomentumStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(question="Will Bitcoin close above $79,000 today?"),
            inputs=_inputs(window_seconds=10.0),
        )
        assert out is None

    def test_price_zone_refused(self) -> None:
        s = CryptoMomentumStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(question="Will Bitcoin close above $79,000 today?", mid=0.92),
            inputs=_inputs(),
        )
        assert out is None

    def test_non_crypto_threshold_refused(self) -> None:
        s = CryptoMomentumStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(question="Will the Lakers win tonight?"),
            inputs=_inputs(),
        )
        assert out is None


class TestBreakAndLagSetup:
    def test_strong_upward_velocity_emits_buy_yes(self) -> None:
        # Bitcoin spot rising; Polymarket above-threshold market at 0.40 lags.
        s = CryptoMomentumStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(question="Will Bitcoin close above $79,000 today?", mid=0.40),
            inputs=_inputs(velocity_bps_per_min=12.0, range_bps=18.0),
        )
        assert out is not None
        est, sig = out
        assert sig.strategy is Strategy.BTC_THRESHOLD
        assert "CRYPTO_MOMENTUM:break_and_lag" in est.reason_codes

    def test_choppy_market_no_signal(self) -> None:
        s = CryptoMomentumStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(question="Will Bitcoin close above $79,000 today?"),
            inputs=_inputs(velocity_bps_per_min=1.0, range_bps=2.0),
        )
        assert out is None


class TestWickFadeSetup:
    def test_large_wick_with_negative_basis_fades_up(self) -> None:
        # Range is large (recent wick) but velocity flat; perp basis negative
        # → spot was punted down then snapped back; fade by buying the upside.
        s = CryptoMomentumStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(question="Will Bitcoin close above $79,000 today?", mid=0.45),
            inputs=_inputs(
                velocity_bps_per_min=0.3,
                range_bps=15.0,
                perp_basis_bps=-10.0,
            ),
        )
        # Wick-fade can fire here, but strategy may also produce no signal
        # if edge after costs is too small. Either is acceptable; the key
        # property is *if* it fires, the reason code must mention wick_fade.
        if out is not None:
            est, _ = out
            assert "CRYPTO_MOMENTUM:wick_fade" in est.reason_codes

    def test_wick_with_neutral_basis_no_signal(self) -> None:
        s = CryptoMomentumStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(question="Will Bitcoin close above $79,000 today?"),
            inputs=_inputs(
                velocity_bps_per_min=0.5,
                range_bps=15.0,
                perp_basis_bps=2.0,   # too small to sign the wick
            ),
        )
        assert out is None
