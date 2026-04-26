"""Resolution monitor tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from polyflow.adapters.gamma import StubGammaAdapter
from polyflow.persistence import SQLiteStore
from polyflow.subagents.resolution_monitor import (
    ResolutionMonitor,
    determine_outcome,
)
from polyflow.types import Market


def _resolved_yes_market() -> Market:
    return Market(
        id="m1",
        event_id="e1",
        question="Q?",
        category="crypto",
        close_time=datetime.now(timezone.utc) - timedelta(hours=1),
        resolution_rules="rules",
        liquidity_usd=200_000,
        volume_24h_usd=50_000,
        spread_pct=2.0,
        depth_within_5c_usd=20_000,
        best_bid=0.99,
        best_ask=1.00,
        yes_token_id="t-yes",
        no_token_id="t-no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=200,
        market_quality=0.85,
        resolution_risk=0.05,
    )


def _unsettled_market() -> Market:
    m = _resolved_yes_market()
    return m.model_copy(update={"best_bid": 0.50, "best_ask": 0.52})


class TestDetermineOutcome:
    def test_yes_wins(self) -> None:
        assert determine_outcome(best_bid=0.98, best_ask=0.99) == "YES"

    def test_no_wins(self) -> None:
        assert determine_outcome(best_bid=0.01, best_ask=0.02) == "NO"

    def test_unsettled(self) -> None:
        assert determine_outcome(best_bid=0.5, best_ask=0.52) is None

    def test_missing_book(self) -> None:
        assert determine_outcome(best_bid=None, best_ask=0.99) is None


@pytest.mark.asyncio
async def test_resolves_market_and_writes_calibration() -> None:
    store = SQLiteStore(":memory:")
    market = _resolved_yes_market()
    store.upsert_market(market, status="watching")

    # Two prior estimates: one predicted YES (correct), one predicted NO (wrong).
    store.insert_probability_estimate(
        estimate_id="e1", market_id=market.id, token_id="t-yes",
        outcome="YES", market_price=0.55, model_probability=0.80,
        uncertainty=0.05, edge_after_costs=0.04,
        source_confidence=0.85, resolution_risk=0.05,
    )
    store.insert_probability_estimate(
        estimate_id="e2", market_id=market.id, token_id="t-no",
        outcome="NO", market_price=0.45, model_probability=0.60,
        uncertainty=0.05, edge_after_costs=0.04,
        source_confidence=0.85, resolution_risk=0.05,
    )

    gamma = StubGammaAdapter([market])
    mon = ResolutionMonitor(gamma=gamma, store=store)
    results = await mon.tick()

    assert len(results) == 1 and results[0].outcome == "YES"
    # Market status is now 'resolved'
    assert store.get_markets_by_status("watching") == []
    assert len(store.get_markets_by_status("resolved")) == 1
    # Two calibration observations were written, one realized=1, one realized=0
    buckets = store.calibration_buckets()
    assert sum(b["n"] for b in buckets.values()) == 2


@pytest.mark.asyncio
async def test_unsettled_market_is_skipped() -> None:
    store = SQLiteStore(":memory:")
    market = _unsettled_market()
    store.upsert_market(market, status="watching")

    gamma = StubGammaAdapter([market])
    results = await ResolutionMonitor(gamma=gamma, store=store).tick()

    assert results == []
    assert len(store.get_markets_by_status("watching")) == 1


@pytest.mark.asyncio
async def test_future_close_skipped() -> None:
    store = SQLiteStore(":memory:")
    market = _resolved_yes_market().model_copy(
        update={"close_time": datetime.now(timezone.utc) + timedelta(hours=1)}
    )
    store.upsert_market(market, status="watching")
    gamma = StubGammaAdapter([market])
    results = await ResolutionMonitor(gamma=gamma, store=store).tick()
    assert results == []
