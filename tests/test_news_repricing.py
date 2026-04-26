"""News repricing strategy tests (PRD §9.1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.config import Policy
from polyflow.strategies.news_repricing import (
    NewsRepricingStrategy,
    PublicSourceEvent,
    hash_body,
)
from polyflow.types import Market, Strategy


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _market(**overrides) -> Market:
    base = dict(
        id="m1",
        event_id="e1",
        question="Q?",
        category="news",
        close_time=_now() + timedelta(hours=24),
        resolution_rules="rules",
        liquidity_usd=200_000,
        volume_24h_usd=60_000,
        spread_pct=2.0,
        depth_within_5c_usd=20_000,
        best_bid=0.50,
        best_ask=0.52,
        yes_token_id="t-yes",
        no_token_id="t-no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=200,
        neg_risk=False,
        market_quality=0.80,
        resolution_risk=0.05,
    )
    base.update(overrides)
    return Market(**base)


def _event(direction: float, *, name: str = "ap", reliability: float = 0.90, mins_old: int = 3, flags: tuple = ()) -> PublicSourceEvent:
    return PublicSourceEvent(
        source_name=name,
        source_url=f"https://{name}/article/{direction}",
        body_hash=hash_body(f"{name}-{direction}"),
        fetched_at=_now() - timedelta(minutes=mins_old),
        reliability=reliability,
        direction=direction,
        integrity_flags=flags,
    )


class TestNewsRepricing:
    def test_two_strong_sources_emit_signal(self) -> None:
        s = NewsRepricingStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(),
            prior_probability=0.50,
            events=[_event(0.18, name="ap"), _event(0.16, name="reuters")],
        )
        assert out is not None
        _est, sig = out
        assert sig.strategy is Strategy.NEWS_REPRICING

    def test_single_source_major_delta_refused(self) -> None:
        s = NewsRepricingStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(),
            prior_probability=0.50,
            events=[_event(0.18, name="ap")],
        )
        assert out is None

    def test_integrity_flag_refuses(self) -> None:
        s = NewsRepricingStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(),
            prior_probability=0.50,
            events=[
                _event(0.18, name="ap", flags=("LEAKED",)),
                _event(0.18, name="reuters"),
            ],
        )
        assert out is None

    def test_low_reliability_refused(self) -> None:
        s = NewsRepricingStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(),
            prior_probability=0.50,
            events=[_event(0.18, name="blog", reliability=0.40),
                    _event(0.18, name="forum", reliability=0.40)],
        )
        assert out is None

    def test_stale_events_dropped(self) -> None:
        s = NewsRepricingStrategy(policy=Policy())
        out = s.evaluate(
            market=_market(),
            prior_probability=0.50,
            events=[_event(0.18, name="ap", mins_old=120),
                    _event(0.18, name="reuters", mins_old=120)],
        )
        assert out is None
