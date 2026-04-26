"""Calibration math tests (PRD §8.5)."""

from __future__ import annotations

import math

import pytest

from polyflow.calibration import bucket_calibration, brier, log_loss, report


class TestBrier:
    def test_perfect(self) -> None:
        assert brier([1.0, 0.0], [1, 0]) == 0.0

    def test_constant_half(self) -> None:
        assert brier([0.5] * 4, [1, 0, 1, 0]) == pytest.approx(0.25)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            brier([], [])


class TestLogLoss:
    def test_perfect_clipped(self) -> None:
        # Perfect predictions hit eps clipping → small but nonzero
        ll = log_loss([1.0, 0.0], [1, 0], eps=1e-9)
        assert ll < 1e-7

    def test_uniform(self) -> None:
        # Always 0.5 → log(0.5) ≈ -0.6931 per sample
        ll = log_loss([0.5] * 4, [1, 0, 1, 0])
        assert ll == pytest.approx(-math.log(0.5))


class TestBuckets:
    def test_buckets_split(self) -> None:
        buckets = bucket_calibration(
            [0.05, 0.15, 0.55, 0.95], [0, 0, 1, 1], n_buckets=10
        )
        # Every prediction falls in its own bucket here.
        assert sum(b["n"] for b in buckets.values()) == 4

    def test_bucket_empirical(self) -> None:
        # Four predictions all in the 0.6 bucket (ceil(p*10)/10 == 0.6 for 0.51–0.60).
        buckets = bucket_calibration(
            [0.55, 0.58, 0.59, 0.60], [1, 1, 0, 0], n_buckets=10
        )
        b6 = buckets.get(0.6)
        assert b6 is not None
        assert b6["n"] == 4
        assert b6["empirical"] == pytest.approx(0.5)


class TestReport:
    def test_report_includes_clv(self) -> None:
        rep = report(
            [0.55, 0.60, 0.70],
            [1, 1, 0],
            closing_line_values=[0.02, 0.01, -0.01],
        )
        assert rep.n == 3
        assert rep.closing_line_value_avg is not None
        assert rep.brier > 0
