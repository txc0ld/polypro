"""Subagent scheduler tests."""

from __future__ import annotations

import asyncio

import pytest

from polyflow.subagents import SubagentScheduler, SubagentTask


# Use an event-driven gate instead of wall-clock sleeps so the test stays
# deterministic on slow / loaded CI runners. The scheduler's first invocation
# happens immediately on start; we wait for a fixed number of iterations.


async def _wait_for(condition, *, timeout_s: float = 2.0, poll_s: float = 0.005) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if condition():
            return
        await asyncio.sleep(poll_s)
    raise AssertionError("condition not met within timeout")


@pytest.mark.asyncio
async def test_runs_subagent_repeatedly_and_stops_cleanly() -> None:
    counter = {"n": 0}

    async def tick() -> None:
        counter["n"] += 1

    sched = SubagentScheduler([SubagentTask(name="t", period_seconds=0.01, fn=tick)])
    await sched.start()
    try:
        await _wait_for(lambda: counter["n"] >= 2)
    finally:
        await sched.stop()

    assert counter["n"] >= 2
    assert sched.status()["t"]["success_count"] >= 2


@pytest.mark.asyncio
async def test_failing_tick_is_recorded_and_does_not_kill_loop() -> None:
    state = {"calls": 0}

    async def flaky() -> None:
        state["calls"] += 1
        raise RuntimeError("boom")

    sched = SubagentScheduler([SubagentTask(name="flaky", period_seconds=0.01, fn=flaky)])
    await sched.start()
    try:
        await _wait_for(lambda: state["calls"] >= 2)
    finally:
        await sched.stop()

    status = sched.status()["flaky"]
    assert status["failure_count"] >= 2
    assert status["last_error"] is not None
    assert state["calls"] >= 2
