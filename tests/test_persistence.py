"""SQLite persistence tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.persistence import SQLiteStore
from polyflow.types import Market, Outcome, Position, Side, Signal, Strategy


def _market() -> Market:
    return Market(
        id="m1",
        event_id="e1",
        question="Q?",
        category="crypto",
        close_time=datetime.now(timezone.utc) + timedelta(hours=12),
        resolution_rules="rules",
        liquidity_usd=200_000,
        volume_24h_usd=150_000,
        spread_pct=2.0,
        depth_within_5c_usd=20_000,
        yes_token_id="t-yes",
        no_token_id="t-no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=200,
        neg_risk=False,
        market_quality=0.85,
        resolution_risk=0.05,
    )


class TestMarkets:
    def test_upsert_then_fetch_by_status(self) -> None:
        store = SQLiteStore(":memory:")
        store.upsert_market(_market(), status="approved")
        rows = store.get_markets_by_status("approved")
        assert len(rows) == 1 and rows[0]["id"] == "m1"
        assert "external_odds_divergence" in rows[0]["strategy_candidates"]
        assert rows[0]["quickfire_eligible"] is True
        assert rows[0]["quickfire_reasons"] == []
        assert rows[0]["quickfire_score"] > 0.0
        assert rows[0]["depth_within_5c_usd"] == 20_000

    def test_upsert_is_idempotent(self) -> None:
        store = SQLiteStore(":memory:")
        store.upsert_market(_market(), status="approved")
        store.upsert_market(_market(), status="approved")
        assert len(store.get_markets_by_status("approved")) == 1

    def test_status_change(self) -> None:
        store = SQLiteStore(":memory:")
        store.upsert_market(_market(), status="approved")
        store.set_market_status("m1", "skipped")
        assert store.get_markets_by_status("approved") == []
        assert len(store.get_markets_by_status("skipped")) == 1

    def test_get_market_rehydrates_tokens_and_metadata(self) -> None:
        store = SQLiteStore(":memory:")
        store.upsert_market(_market(), status="watching")
        market = store.get_market("m1")
        assert market is not None
        assert market.yes_token_id == "t-yes"
        assert market.no_token_id == "t-no"
        assert market.tick_size == 0.01
        assert market.best_bid is None


class TestSignals:
    def test_insert_signal(self) -> None:
        store = SQLiteStore(":memory:")
        sig = Signal(
            market_id="m1",
            event_id="e1",
            token_id="t-yes",
            outcome=Outcome.YES,
            side=Side.BUY,
            strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
            market_price=0.55,
            model_probability=0.70,
            uncertainty=0.05,
            effective_edge=0.04,
            market_quality=0.80,
            resolution_risk=0.10,
            liquidity_score=0.80,
            confidence=0.85,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            evidence_refs=["ev1"],
        )
        sig.score = 91.0
        sig.status = "LIVE_TINY"
        store.insert_signal(sig)
        # Round-trip via raw cursor to verify
        with store._cursor() as cur:  # type: ignore[attr-defined]
            row = cur.execute("SELECT * FROM signals WHERE id=?", (str(sig.signal_id),)).fetchone()
        assert row["status"] == "LIVE_TINY"
        assert row["score"] == 91.0


class TestPositions:
    def test_upsert_and_fetch_open(self) -> None:
        store = SQLiteStore(":memory:")
        store.upsert_position(
            Position(
                market_id="m1", token_id="t-yes", outcome=Outcome.YES,
                size=10.0, avg_price=0.62,
            )
        )
        open_pos = store.get_open_positions()
        assert len(open_pos) == 1
        assert open_pos[0]["market_id"] == "m1"


class TestCalibration:
    def test_observations_bucketed(self) -> None:
        store = SQLiteStore(":memory:")
        # Predicted 0.7, realized 1
        store.insert_calibration_observation(
            market_id="m1", token_id="t", predicted_probability=0.70, realized=True
        )
        store.insert_calibration_observation(
            market_id="m1", token_id="t", predicted_probability=0.72, realized=False
        )
        buckets = store.calibration_buckets()
        # Both round to bucket 0.7
        assert 0.7 in buckets
        assert buckets[0.7]["n"] == 2
