"""Feed Health Monitor (Protocol §1).

Tracks per-feed median latency over a rolling window. When median latency
exceeds the threshold (default 150ms) the feed is marked unhealthy and the
runtime should respawn it. The runtime is responsible for the respawn —
this module only owns the measurement and the verdict.
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from threading import RLock


@dataclass
class FeedStats:
    feed_id: str
    sample_window: int = 200
    samples_ms: deque[float] = field(default_factory=deque)
    healthy: bool = True
    last_unhealthy_at_ns: int | None = None
    consecutive_failures: int = 0
    consecutive_recoveries: int = 0


class FeedHealthMonitor:
    """One monitor instance manages many feeds in parallel."""

    def __init__(
        self,
        *,
        max_median_ms: float = 150.0,
        max_p95_ms: float = 400.0,
        sample_window: int = 200,
        consecutive_for_unhealthy: int = 3,
        consecutive_for_recovery: int = 5,
    ) -> None:
        self.max_median_ms = max_median_ms
        self.max_p95_ms = max_p95_ms
        self.sample_window = sample_window
        self.consecutive_for_unhealthy = consecutive_for_unhealthy
        self.consecutive_for_recovery = consecutive_for_recovery
        self._feeds: dict[str, FeedStats] = {}
        self._lock = RLock()

    def record_latency(self, feed_id: str, latency_ms: float) -> bool:
        """Record one sample. Returns the feed's *current* healthy bool after evaluation."""
        with self._lock:
            stats = self._feeds.setdefault(
                feed_id, FeedStats(feed_id=feed_id, sample_window=self.sample_window)
            )
            stats.samples_ms.append(latency_ms)
            while len(stats.samples_ms) > self.sample_window:
                stats.samples_ms.popleft()

            if len(stats.samples_ms) < 5:
                return stats.healthy  # not enough data to flip yet

            median = statistics.median(stats.samples_ms)
            p95 = self._p95(stats.samples_ms)
            unhealthy_now = median > self.max_median_ms or p95 > self.max_p95_ms

            if unhealthy_now:
                stats.consecutive_failures += 1
                stats.consecutive_recoveries = 0
                if (
                    stats.healthy
                    and stats.consecutive_failures >= self.consecutive_for_unhealthy
                ):
                    stats.healthy = False
                    stats.last_unhealthy_at_ns = time.time_ns()
            else:
                stats.consecutive_recoveries += 1
                stats.consecutive_failures = 0
                if (
                    not stats.healthy
                    and stats.consecutive_recoveries >= self.consecutive_for_recovery
                ):
                    stats.healthy = True

            return stats.healthy

    def is_healthy(self, feed_id: str) -> bool:
        with self._lock:
            stats = self._feeds.get(feed_id)
            return True if stats is None else stats.healthy

    def healthy_feeds(self) -> list[str]:
        with self._lock:
            return [fid for fid, s in self._feeds.items() if s.healthy]

    def report(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        with self._lock:
            for fid, s in self._feeds.items():
                samples = list(s.samples_ms)
                out[fid] = {
                    "healthy": s.healthy,
                    "n": len(samples),
                    "median_ms": (statistics.median(samples) if samples else None),
                    "p95_ms": (self._p95(samples) if samples else None),
                    "consecutive_failures": s.consecutive_failures,
                }
        return out

    @staticmethod
    def _p95(samples: list[float] | deque[float]) -> float:
        sorted_samples = sorted(samples)
        if not sorted_samples:
            return 0.0
        idx = max(0, int(0.95 * len(sorted_samples)) - 1)
        return sorted_samples[idx]
