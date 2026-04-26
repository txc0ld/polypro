"""Replay tool tests."""

from __future__ import annotations

import json
from pathlib import Path

from polyflow.replay import iter_log, reconstruct_trade, summarize


def _write_log(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "imm.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def test_iter_log_skips_blank_and_malformed(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    p.write_text(
        '\n{"ts":"1","actor":"a","action":"x","payload":{}}\n'
        "not-json\n"
        '{"ts":"2","actor":"b","action":"y","payload":{}}\n',
        encoding="utf-8",
    )
    records = list(iter_log(p))
    assert [r.actor for r in records] == ["a", "b"]


def test_reconstruct_trade(tmp_path: Path) -> None:
    p = _write_log(
        tmp_path,
        [
            {"ts": "1", "actor": "signal_arbiter", "action": "score",
             "payload": {"signal_id": "sig-1", "score": 92.0}},
            {"ts": "2", "actor": "risk_governor", "action": "evaluate",
             "payload": {"approved": True}, "market_id": "m1"},
            # Different signal — should be excluded
            {"ts": "3", "actor": "signal_arbiter", "action": "score",
             "payload": {"signal_id": "sig-2", "score": 50.0}},
            {"ts": "4", "actor": "clob_order_formatter", "action": "format",
             "payload": {"risk_ref": "sig-1", "ready_to_submit": True}},
        ],
    )
    records = reconstruct_trade(p, signal_id="sig-1")
    assert [r.action for r in records] == ["score", "format"]


def test_summarize(tmp_path: Path) -> None:
    p = _write_log(
        tmp_path,
        [
            {"ts": "1", "actor": "market_scanner", "action": "classify", "payload": {}},
            {"ts": "2", "actor": "clob_adapter", "action": "place_order", "payload": {}},
            {"ts": "3", "actor": "clob_order_formatter", "action": "format",
             "payload": {"rejected": True}},
            {"ts": "4", "actor": "post_order_kelly_guard", "action": "kill_switch",
             "payload": {}},
        ],
    )
    s = summarize(p)
    assert s.total_records == 4
    assert s.kill_switch_events == 1
    assert s.placed_orders == 1
    assert s.rejected_orders == 1
    assert s.by_actor["market_scanner"] == 1


def test_summarize_missing_file(tmp_path: Path) -> None:
    s = summarize(tmp_path / "does-not-exist.jsonl")
    assert s.total_records == 0
    assert s.by_actor == {}
