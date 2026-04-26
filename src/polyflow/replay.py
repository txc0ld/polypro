"""Replay tool — reconstructs decisions from the immutable JSONL log.

Use cases:
  - audit a trade end-to-end after the fact
  - rebuild calibration / promotion gate inputs from history
  - regression-test policy changes by re-running the risk governor against
    historical signals (does the new policy reject what the old one approved?)

The log is append-only and stores every actor's input/output, so replay is
deterministic. Hashes are *not* re-verified here; the operator runs that as a
separate audit step.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class LogRecord:
    ts: str
    actor: str
    action: str
    market_id: str | None
    event_id: str | None
    payload: dict


def iter_log(path: str | Path) -> Iterator[LogRecord]:
    """Stream the JSONL one record at a time. Skips malformed lines."""
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield LogRecord(
                ts=str(obj.get("ts") or ""),
                actor=str(obj.get("actor") or ""),
                action=str(obj.get("action") or ""),
                market_id=obj.get("market_id"),
                event_id=obj.get("event_id"),
                payload=obj.get("payload") or {},
            )


def reconstruct_trade(path: str | Path, *, signal_id: str) -> list[LogRecord]:
    """Pull every log record relevant to a single signal_id, in time order.

    Walks the entire log once — fine for v1; later we can index by signal_id.
    """
    out: list[LogRecord] = []
    for r in iter_log(path):
        if r.action == "score" and str(r.payload.get("signal_id")) == signal_id:
            out.append(r)
            continue
        if r.payload.get("risk_ref") == signal_id:
            out.append(r)
            continue
        if r.payload.get("signal_id") == signal_id:
            out.append(r)
    return out


@dataclass(frozen=True)
class ReplayStats:
    total_records: int
    by_actor: dict[str, int]
    by_action: dict[str, int]
    kill_switch_events: int
    placed_orders: int
    rejected_orders: int


def summarize(path: str | Path) -> ReplayStats:
    by_actor: dict[str, int] = {}
    by_action: dict[str, int] = {}
    kills = 0
    placed = 0
    rejected = 0
    total = 0
    for r in iter_log(path):
        total += 1
        by_actor[r.actor] = by_actor.get(r.actor, 0) + 1
        by_action[r.action] = by_action.get(r.action, 0) + 1
        if r.action == "kill_switch":
            kills += 1
        if r.actor == "clob_adapter" and r.action == "place_order":
            placed += 1
        if r.actor == "clob_order_formatter" and r.payload.get("rejected"):
            rejected += 1
    return ReplayStats(
        total_records=total,
        by_actor=by_actor,
        by_action=by_action,
        kill_switch_events=kills,
        placed_orders=placed,
        rejected_orders=rejected,
    )
