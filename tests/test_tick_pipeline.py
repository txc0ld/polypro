"""Tick pipeline / data hygiene tests (Protocol §1)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from polyflow.tick_pipeline import (
    Tick,
    TickAuditLog,
    TickFilterConfig,
    TickPipeline,
    now_ns,
)


def _tick(price: float, *, feed: str = "f1", seq: int | None = None, ns: int | None = None) -> Tick:
    return Tick(
        feed_id=feed,
        market_id="m1",
        token_id="t-yes",
        price=price,
        size=100.0,
        sequence=seq,
        received_ns=ns if ns is not None else now_ns(),
    )


class TestPostReconnectDiscard:
    def test_first_n_ticks_dropped(self) -> None:
        cfg = TickFilterConfig(discard_first_n_after_reconnect=15)
        p = TickPipeline(config=cfg)
        p.on_reconnect("f1")
        accepted = [p.submit(_tick(0.50)) for _ in range(20)]
        # First 15 dropped, last 5 accepted
        assert sum(accepted) == 5


class TestPriceJumpFilter:
    def test_8pct_jump_in_2s_dropped(self) -> None:
        cfg = TickFilterConfig(discard_first_n_after_reconnect=0)
        p = TickPipeline(config=cfg)
        ns = now_ns()
        assert p.submit(_tick(0.50, ns=ns))
        # +9% jump within 0.5s — must be dropped
        assert not p.submit(_tick(0.5450001, ns=ns + 500_000_000))

    def test_8pct_jump_outside_window_allowed(self) -> None:
        cfg = TickFilterConfig(discard_first_n_after_reconnect=0)
        p = TickPipeline(config=cfg)
        ns = now_ns()
        assert p.submit(_tick(0.50, ns=ns))
        # 9% jump after 3s — outside the 2s window, should pass
        assert p.submit(_tick(0.545, ns=ns + 3_000_000_000))


class TestSequenceFilter:
    def test_out_of_order_sequence_dropped(self) -> None:
        cfg = TickFilterConfig(discard_first_n_after_reconnect=0)
        p = TickPipeline(config=cfg)
        assert p.submit(_tick(0.50, seq=10))
        assert not p.submit(_tick(0.51, seq=9))   # backwards seq
        assert not p.submit(_tick(0.51, seq=10))  # duplicate seq

    def test_increasing_sequence_allowed(self) -> None:
        cfg = TickFilterConfig(discard_first_n_after_reconnect=0)
        p = TickPipeline(config=cfg)
        for i in range(5):
            assert p.submit(_tick(0.50, seq=i))


class TestCleanBuffer:
    def test_evicts_old_ticks(self) -> None:
        cfg = TickFilterConfig(discard_first_n_after_reconnect=0, clean_buffer_seconds=0.05)
        p = TickPipeline(config=cfg)
        p.submit(_tick(0.50, ns=now_ns()))
        time.sleep(0.10)
        assert p.clean_buffer() == []

    def test_latest_returns_most_recent(self) -> None:
        cfg = TickFilterConfig(discard_first_n_after_reconnect=0)
        p = TickPipeline(config=cfg)
        p.submit(_tick(0.50))
        p.submit(_tick(0.51))
        latest = p.latest()
        assert latest is not None and latest.price == 0.51


class TestAuditLog:
    def test_discarded_ticks_logged(self, tmp_path: Path) -> None:
        log = TickAuditLog(tmp_path / "audit.jsonl")
        cfg = TickFilterConfig(discard_first_n_after_reconnect=2)
        p = TickPipeline(config=cfg, audit_log=log)
        p.on_reconnect("f1")
        p.submit(_tick(0.50))
        p.submit(_tick(0.51))
        p.submit(_tick(0.52))  # this should pass (3rd tick)

        lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        # The first two were discarded; the audit log got them
        assert len(lines) == 2
        for line in lines:
            assert "POST_RECONNECT_DISCARD" in line
