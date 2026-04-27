"""Tick Recorder (Protocol §2: own data for ≥30 days before any deploy).

Append-only JSONL of every accepted tick. The simulator replays from these
files. Files rotate hourly so a 30-day archive is ~720 files — easy to grep,
easy to back up.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from .tick_pipeline import Tick


class TickRecorder:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._open_path: Path | None = None
        self._open_handle = None
        self._lock = RLock()

    def record(self, tick: Tick) -> None:
        line = json.dumps(
            {
                "feed_id": tick.feed_id,
                "market_id": tick.market_id,
                "token_id": tick.token_id,
                "price": tick.price,
                "size": tick.size,
                "sequence": tick.sequence,
                "received_ns": tick.received_ns,
                "venue_ts_ms": tick.venue_ts_ms,
            },
            separators=(",", ":"),
        )
        path = self._current_path()
        with self._lock:
            if self._open_path != path:
                self._reopen(path)
            assert self._open_handle is not None
            self._open_handle.write((line + "\n").encode("utf-8"))
            self._open_handle.flush()

    def close(self) -> None:
        with self._lock:
            if self._open_handle is not None:
                try:
                    self._open_handle.flush()
                    os.fsync(self._open_handle.fileno())
                except OSError:
                    pass
                self._open_handle.close()
                self._open_handle = None
                self._open_path = None

    def _current_path(self) -> Path:
        now = datetime.now(timezone.utc)
        return self._root / f"ticks-{now:%Y%m%dT%H}.jsonl"

    def _reopen(self, path: Path) -> None:
        if self._open_handle is not None:
            self._open_handle.close()
        self._open_handle = path.open("ab")
        self._open_path = path
