"""Heartbeat / deadman switch (PRD §21.2).

Writes a single timestamp to a file every tick. An external watchdog (cron,
systemd, k8s liveness probe) reads the file and restarts the runtime if the
timestamp is older than the configured threshold.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class Heartbeat:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def tick(self) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
        # Write + fsync. The runtime accepts the I/O cost — heartbeat skipped
        # is far worse than heartbeat slow.
        with self._path.open("wb") as f:
            f.write(json.dumps(payload).encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

    def last_seen(self) -> datetime | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return datetime.fromisoformat(data["ts"])
        except (json.JSONDecodeError, ValueError, KeyError):
            return None
