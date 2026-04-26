"""Immutable trade logger (PRD §15.2).

Append-only JSONL on disk + (optionally) a Postgres `immutable_log` table.
The on-disk log is the source of truth if the DB is unavailable — fail-open
on persistence is *not* permitted, so we always write the local file first.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _sha256(obj: Any) -> str:
    """Stable SHA-256 of any JSON-serializable object."""
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class ImmutableLogger:
    """Append-only logger. Single file + an in-process lock.

    Production deployment writes to both this file *and* the `immutable_log`
    table in Postgres (with row-level grants forbidding UPDATE/DELETE).
    """

    def __init__(self, log_path: str | Path, *, code_version: str = "dev", config_hash: str = "") -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._code_version = code_version
        self._config_hash = config_hash

    def log(
        self,
        *,
        actor: str,
        action: str,
        payload: dict,
        market_id: str | None = None,
        event_id: str | None = None,
        input_obj: Any = None,
        output_obj: Any = None,
    ) -> dict:
        """Write one append-only record. Returns the record (with hashes filled in)."""
        record = {
            "id": str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "market_id": market_id,
            "event_id": event_id,
            "input_hash": _sha256(input_obj) if input_obj is not None else None,
            "output_hash": _sha256(output_obj) if output_obj is not None else None,
            "config_hash": self._config_hash,
            "code_version": self._code_version,
            "payload": payload,
        }
        line = json.dumps(record, default=str, separators=(",", ":")) + "\n"
        with self._lock:
            # Open in append-binary so OS-level append atomicity holds on POSIX.
            with self._path.open("ab") as f:
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
        return record
