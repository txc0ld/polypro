"""Cooperative cadence scheduler for subagents.

Each ``SubagentTask`` is one async function called every ``period_seconds``.
The scheduler:
  - never lets one slow tick block another subagent,
  - tracks last-success / last-failure timestamps for the heartbeat,
  - swallows + logs exceptions so a flaky tick never crashes the runtime,
  - is cancellable via ``stop`` for clean shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

import structlog

log = structlog.get_logger("polyflow.subagents")


@dataclass
class SubagentTask:
    name: str
    period_seconds: float
    fn: Callable[[], Awaitable[None]]

    last_started_at: datetime | None = field(default=None, init=False)
    last_succeeded_at: datetime | None = field(default=None, init=False)
    last_failed_at: datetime | None = field(default=None, init=False)
    last_error: str | None = field(default=None, init=False)
    success_count: int = field(default=0, init=False)
    failure_count: int = field(default=0, init=False)


class SubagentScheduler:
    """Owns the pool of running subagent tasks."""

    def __init__(self, tasks: list[SubagentTask] | None = None) -> None:
        self._tasks: dict[str, SubagentTask] = {t.name: t for t in (tasks or [])}
        self._running: dict[str, asyncio.Task] = {}
        self._stop_event = asyncio.Event()

    def register(self, task: SubagentTask) -> None:
        self._tasks[task.name] = task

    def status(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for name, t in self._tasks.items():
            out[name] = {
                "period_seconds": t.period_seconds,
                "last_started_at": t.last_started_at.isoformat() if t.last_started_at else None,
                "last_succeeded_at": t.last_succeeded_at.isoformat() if t.last_succeeded_at else None,
                "last_failed_at": t.last_failed_at.isoformat() if t.last_failed_at else None,
                "last_error": t.last_error,
                "success_count": t.success_count,
                "failure_count": t.failure_count,
            }
        return out

    async def start(self) -> None:
        """Spawn one asyncio task per registered subagent."""
        for name, t in self._tasks.items():
            if name in self._running and not self._running[name].done():
                continue
            self._running[name] = asyncio.create_task(self._loop(t), name=f"subagent:{name}")

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._running.values():
            task.cancel()
        for task in self._running.values():
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._running.clear()
        self._stop_event.clear()

    async def _loop(self, t: SubagentTask) -> None:
        while not self._stop_event.is_set():
            t.last_started_at = datetime.now(timezone.utc)
            try:
                await t.fn()
                t.last_succeeded_at = datetime.now(timezone.utc)
                t.success_count += 1
                t.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                t.last_failed_at = datetime.now(timezone.utc)
                t.failure_count += 1
                t.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("subagent_tick_failed", subagent=t.name)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=t.period_seconds)
            except asyncio.TimeoutError:
                continue
