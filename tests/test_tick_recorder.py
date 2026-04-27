"""Tick recorder tests (Protocol §2)."""

from __future__ import annotations

import json
from pathlib import Path

from polyflow.tick_pipeline import Tick, now_ns
from polyflow.tick_recorder import TickRecorder


def test_records_jsonl(tmp_path: Path) -> None:
    rec = TickRecorder(tmp_path)
    for i in range(3):
        rec.record(Tick(
            feed_id="f1", market_id="m", token_id="t",
            price=0.50 + i * 0.01, size=100.0, sequence=i, received_ns=now_ns(),
        ))
    rec.close()

    files = list(tmp_path.glob("ticks-*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    parsed = [json.loads(l) for l in lines]
    assert [p["sequence"] for p in parsed] == [0, 1, 2]
