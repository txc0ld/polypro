"""Source reliability tracker tests."""

from __future__ import annotations

import pytest

from polyflow.persistence import SQLiteStore
from polyflow.source_reliability import (
    DEFAULT_PRIOR,
    PRIOR_WEIGHT,
    ReliabilityScore,
    score,
    update_posterior,
)


class TestPosterior:
    def test_no_observations_returns_prior(self) -> None:
        assert update_posterior(hits=0, misses=0) == DEFAULT_PRIOR

    def test_perfect_record_pulls_toward_one(self) -> None:
        p = update_posterior(hits=100, misses=0)
        assert p > 0.9

    def test_consistently_wrong_pulls_toward_zero(self) -> None:
        p = update_posterior(hits=0, misses=100)
        assert p < 0.05

    def test_smoothing(self) -> None:
        # 1 hit / 0 miss but PRIOR_WEIGHT=5 of mass at default 0.7 → tilt slightly up
        p = update_posterior(hits=1, misses=0)
        # (1 + 0.7*5) / (1 + 5) = 4.5 / 6 = 0.75
        assert p == pytest.approx((1 + DEFAULT_PRIOR * PRIOR_WEIGHT) / (1 + PRIOR_WEIGHT))


class TestStorePersistence:
    def test_update_and_read_back(self) -> None:
        store = SQLiteStore(":memory:")
        store.update_source_reliability(source_name="ap", hit=True, brier_increment=0.05)
        store.update_source_reliability(source_name="ap", hit=True)
        store.update_source_reliability(source_name="ap", hit=False)
        row = store.source_reliability("ap")
        assert row is not None
        assert row["hits"] == 2
        assert row["misses"] == 1

    def test_score_helper(self) -> None:
        store = SQLiteStore(":memory:")
        for _ in range(20):
            store.update_source_reliability(source_name="reuters", hit=True)
        for _ in range(5):
            store.update_source_reliability(source_name="reuters", hit=False)
        s: ReliabilityScore = score(store.source_reliability("reuters"))
        assert s.n == 25
        # 20/25 = 0.8 raw; smoothed slightly toward prior 0.7 → ~0.785
        assert 0.75 < s.posterior < 0.85
