"""Calibration tracking (PRD §8.5).

Reads logged probability estimates + recorded resolutions and emits Brier
score, log-loss, and bucket calibration. The Postgres / SQLite store is the
source of truth for production; this module is the math.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationReport:
    n: int
    brier: float
    log_loss: float
    buckets: dict[float, dict[str, float]]
    closing_line_value_avg: float | None = None


def brier(predictions: list[float], outcomes: list[int]) -> float:
    if len(predictions) != len(outcomes) or not predictions:
        raise ValueError("predictions and outcomes must be same nonzero length")
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)


def log_loss(predictions: list[float], outcomes: list[int], *, eps: float = 1e-9) -> float:
    if len(predictions) != len(outcomes) or not predictions:
        raise ValueError("predictions and outcomes must be same nonzero length")
    total = 0.0
    for p, o in zip(predictions, outcomes):
        p = min(max(p, eps), 1.0 - eps)
        total += -(o * math.log(p) + (1 - o) * math.log(1 - p))
    return total / len(predictions)


def bucket_calibration(
    predictions: list[float],
    outcomes: list[int],
    *,
    n_buckets: int = 10,
) -> dict[float, dict[str, float]]:
    """Return {bucket_upper: {mean_predicted, empirical, n}} sorted ascending."""
    if len(predictions) != len(outcomes) or not predictions:
        return {}
    out: dict[float, list[tuple[float, int]]] = {}
    for p, o in zip(predictions, outcomes):
        b = min(n_buckets, max(1, math.ceil(p * n_buckets))) / n_buckets
        out.setdefault(b, []).append((p, o))
    return {
        round(b, 2): {
            "mean_predicted": sum(p for p, _ in v) / len(v),
            "empirical": sum(o for _, o in v) / len(v),
            "n": len(v),
        }
        for b, v in sorted(out.items())
    }


def report(
    predictions: list[float],
    outcomes: list[int],
    *,
    closing_line_values: list[float] | None = None,
) -> CalibrationReport:
    """Build a full calibration snapshot."""
    if not predictions:
        return CalibrationReport(n=0, brier=0.0, log_loss=0.0, buckets={})
    clv_avg = (
        sum(closing_line_values) / len(closing_line_values)
        if closing_line_values
        else None
    )
    return CalibrationReport(
        n=len(predictions),
        brier=brier(predictions, outcomes),
        log_loss=log_loss(predictions, outcomes),
        buckets=bucket_calibration(predictions, outcomes),
        closing_line_value_avg=clv_avg,
    )
