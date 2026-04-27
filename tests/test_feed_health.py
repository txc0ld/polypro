"""Feed health monitor tests (Protocol §1)."""

from __future__ import annotations

from polyflow.feed_health import FeedHealthMonitor


class TestHealthTransitions:
    def test_starts_healthy(self) -> None:
        m = FeedHealthMonitor()
        assert m.is_healthy("f1") is True

    def test_below_threshold_stays_healthy(self) -> None:
        m = FeedHealthMonitor(max_median_ms=150.0)
        for _ in range(50):
            m.record_latency("f1", 80.0)
        assert m.is_healthy("f1")

    def test_consecutive_breaches_flips_unhealthy(self) -> None:
        m = FeedHealthMonitor(
            max_median_ms=150.0, consecutive_for_unhealthy=3, consecutive_for_recovery=5,
        )
        for _ in range(50):
            m.record_latency("f1", 50.0)
        assert m.is_healthy("f1")

        # Push median above threshold via repeated high samples
        for _ in range(30):
            m.record_latency("f1", 800.0)
        assert m.is_healthy("f1") is False

    def test_recovery_requires_sustained_low(self) -> None:
        m = FeedHealthMonitor(
            max_median_ms=150.0, consecutive_for_unhealthy=2, consecutive_for_recovery=5,
        )
        for _ in range(50):
            m.record_latency("f1", 800.0)
        assert m.is_healthy("f1") is False

        # Drag median back down with many low samples
        for _ in range(300):
            m.record_latency("f1", 30.0)
        assert m.is_healthy("f1") is True

    def test_p95_breach_alone_can_unhealthy(self) -> None:
        m = FeedHealthMonitor(
            max_median_ms=150.0, max_p95_ms=400.0,
            consecutive_for_unhealthy=2,
        )
        # median 50, p95 1200 → unhealthy on p95 alone
        samples = [50.0] * 90 + [1200.0] * 10
        for s in samples:
            m.record_latency("f1", s)
        assert m.is_healthy("f1") is False

    def test_independent_feeds(self) -> None:
        m = FeedHealthMonitor(consecutive_for_unhealthy=2)
        for _ in range(20):
            m.record_latency("good", 30.0)
        for _ in range(20):
            m.record_latency("bad", 800.0)
        assert m.healthy_feeds() == ["good"]


class TestReport:
    def test_report_shape(self) -> None:
        m = FeedHealthMonitor()
        for s in [40, 50, 60, 70, 80]:
            m.record_latency("f1", float(s))
        rep = m.report()
        assert "f1" in rep
        assert rep["f1"]["n"] == 5
        assert rep["f1"]["median_ms"] == 60.0
