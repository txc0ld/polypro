"""Watchlist tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.types import Market
from polyflow.watchlist import Watchlist


def _market(mid: str = "m1", quality: float = 0.85) -> Market:
    return Market(
        id=mid,
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
        market_quality=quality,
        resolution_risk=0.10,
    )


class TestWatchlist:
    def test_upsert_and_active(self) -> None:
        wl = Watchlist()
        wl.upsert(_market("m1", quality=0.9))
        wl.upsert(_market("m2", quality=0.8))
        assert {m.id for m in wl.active()} == {"m1", "m2"}
        assert len(wl) == 2

    def test_evict_with_reasons_keeps_tombstone(self) -> None:
        wl = Watchlist()
        wl.upsert(_market("m1", quality=0.9))
        wl.evict("m1", reasons=("LIQUIDITY_BELOW_MIN",))
        # Active list excludes evicted; tombstone is reachable via get()
        assert wl.active() == []
        ent = wl.get("m1")
        assert ent is not None
        assert ent.skip_reasons == ("LIQUIDITY_BELOW_MIN",)

    def test_evict_without_reasons_removes_entry(self) -> None:
        wl = Watchlist()
        wl.upsert(_market("m1", quality=0.9))
        wl.evict("m1")
        assert wl.get("m1") is None
