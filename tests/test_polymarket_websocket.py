"""Polymarket CLOB user-channel WebSocket adapter tests.

We never make a real network call — the adapter is parametrized with a
``connector`` callable, and the tests inject a fake server that yields
prebuilt JSON frames. The ``handle_user_event`` runtime path is exercised
end-to-end through an in-memory SQLite store + IncidentManager.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from polyflow.adapters.clob import PaperCLOBAdapter
from polyflow.adapters.gamma import StubGammaAdapter
from polyflow.adapters.polymarket_websocket import (
    BackoffPolicy,
    PolymarketUserWebSocket,
    parse_event,
)
from polyflow.config import Policy
from polyflow.incident import IncidentManager, State
from polyflow.logger import ImmutableLogger
from polyflow.persistence import SQLiteStore
from polyflow.post_order_hook import evaluate_exposure
from polyflow.runtime import Runtime
from polyflow.subagents.portfolio_sentinel import PortfolioSentinel
from polyflow.types import (
    CancelEvent,
    FillEvent,
    OrderUpdateEvent,
    Outcome,
    Position,
    RiskState,
    Side,
    WebSocketEventType,
)


class FakeWS:
    """Single-use fake WebSocket. Captures sends, replays a script of frames."""

    def __init__(self, frames: list[Any], *, raise_on_close: bool = False) -> None:
        self._frames = list(frames)
        self.sent: list[str] = []
        self.closed = False
        self._raise_on_close = raise_on_close

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    def __aiter__(self) -> "FakeWS":
        return self

    async def __anext__(self) -> Any:
        if not self._frames:
            raise StopAsyncIteration
        item = self._frames.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        self.closed = True
        if self._raise_on_close:
            raise RuntimeError("close failure")


def _frame(**kwargs: Any) -> str:
    return json.dumps(kwargs)


# ---- parsing ------------------------------------------------------------


def test_parse_event_handles_fill_trade_and_cancel() -> None:
    fill = parse_event({
        "event_type": "TRADE",
        "market_id": "m1",
        "asset_id": "t-yes",
        "outcome": "YES",
        "side": "BUY",
        "price": "0.55",
        "size": "10",
        "order_id": "x-1",
        "client_order_id": "c-1",
        "timestamp": "2026-04-26T12:00:00Z",
    })
    assert isinstance(fill, FillEvent)
    assert fill.market_id == "m1"
    assert fill.size == 10.0
    assert fill.side is Side.BUY
    assert fill.outcome is Outcome.YES

    upd = parse_event({
        "type": "ORDER_UPDATE",
        "market_id": "m1",
        "asset_id": "t-yes",
        "order_id": "x-1",
        "status": "LIVE",
        "size_remaining": "8",
    })
    assert isinstance(upd, OrderUpdateEvent)
    assert upd.status == "LIVE"
    assert upd.remaining_size == 8.0

    cancel = parse_event({
        "type": "CANCEL",
        "market_id": "m1",
        "asset_id": "t-yes",
        "order_id": "x-1",
        "reason": "USER",
    })
    assert isinstance(cancel, CancelEvent)
    assert cancel.reason == "USER"


def test_parse_event_skips_control_frames() -> None:
    assert parse_event({"type": "PONG"}) is None
    assert parse_event({"type": "SUBSCRIBED"}) is None
    assert parse_event({"event_type": "UNKNOWN_THING"}) is None
    assert parse_event("not a dict") is None  # type: ignore[arg-type]


# ---- handshake ----------------------------------------------------------


@pytest.mark.asyncio
async def test_subscription_handshake_sends_auth_and_markets() -> None:
    fake = FakeWS(frames=[])  # disconnect immediately after handshake

    async def connector(url: str) -> Any:
        connector.url = url  # type: ignore[attr-defined]
        return fake

    seen: list = []

    async def on_event(ev: Any) -> None:
        seen.append(ev)

    ws = PolymarketUserWebSocket(
        api_key="k-1",
        secret="dGVzdA==",
        passphrase="pp",
        markets=["m1", "m2"],
        on_event=on_event,
        connector=connector,
        max_reconnects=0,
        backoff=BackoffPolicy(initial_seconds=0.001, max_seconds=0.001, jitter=0),
    )
    await ws.run()

    assert connector.url == ws.url  # type: ignore[attr-defined]
    assert len(fake.sent) == 1
    payload = json.loads(fake.sent[0])
    assert payload["type"] == "user"
    assert payload["markets"] == ["m1", "m2"]
    assert payload["auth"] == {"apiKey": "k-1", "secret": "dGVzdA==", "passphrase": "pp"}
    assert seen == []


@pytest.mark.asyncio
async def test_event_dispatch_updates_last_event_at() -> None:
    fake = FakeWS(frames=[
        _frame(type="PONG"),
        _frame(
            event_type="TRADE",
            market_id="m1",
            asset_id="t-yes",
            outcome="YES",
            side="BUY",
            price="0.50",
            size="1",
            order_id="x",
        ),
    ])

    async def connector(url: str) -> Any:
        return fake

    delivered: list = []

    async def on_event(ev: Any) -> None:
        delivered.append(ev)

    ws = PolymarketUserWebSocket(
        api_key="k", secret="s", passphrase="p",
        markets=["m1"], on_event=on_event,
        connector=connector, max_reconnects=0,
        backoff=BackoffPolicy(initial_seconds=0.001, max_seconds=0.001, jitter=0),
    )
    await ws.run()
    assert len(delivered) == 1
    assert isinstance(delivered[0], FillEvent)
    assert ws.last_event_at is not None
    assert ws.event_count == 1


# ---- reconnect ----------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_triggers_reconnect_with_backoff() -> None:
    """First connection raises mid-stream; second connection delivers a fill;
    then we hit the reconnect cap. Backoff is observed via attempt counter."""
    attempt_log: list[int] = []

    fakes = [
        FakeWS(frames=[ConnectionResetError("boom")]),
        FakeWS(frames=[_frame(
            event_type="TRADE",
            market_id="m1",
            asset_id="t-yes",
            outcome="YES",
            side="BUY",
            price="0.50",
            size="1",
            order_id="x",
        )]),
        FakeWS(frames=[]),  # third connect: clean disconnect, run loop exits
    ]

    async def connector(url: str) -> Any:
        idx = len(attempt_log)
        attempt_log.append(idx)
        return fakes[idx]

    received: list = []

    async def on_event(ev: Any) -> None:
        received.append(ev)

    ws = PolymarketUserWebSocket(
        api_key="k", secret="s", passphrase="p",
        markets=["m1"], on_event=on_event,
        connector=connector,
        backoff=BackoffPolicy(initial_seconds=0.001, max_seconds=0.001, jitter=0),
        max_reconnects=2,
    )
    await ws.run()

    # Initial attempt + at least one reconnect that delivered the fill.
    assert len(attempt_log) >= 2
    assert ws.reconnect_count >= 1
    assert len(received) == 1
    assert isinstance(received[0], FillEvent)


@pytest.mark.asyncio
async def test_stop_halts_reconnect_loop() -> None:
    """Once ``stop`` is set, ``run`` returns even between reconnect attempts."""
    fake = FakeWS(frames=[ConnectionError("x")])

    async def connector(url: str) -> Any:
        return FakeWS(frames=[ConnectionError("x")])

    async def on_event(ev: Any) -> None:
        pass

    ws = PolymarketUserWebSocket(
        api_key="k", secret="s", passphrase="p",
        markets=["m1"], on_event=on_event,
        connector=connector,
        backoff=BackoffPolicy(initial_seconds=10.0, max_seconds=10.0, jitter=0),
    )

    async def run_then_stop() -> None:
        task = asyncio.create_task(ws.run())
        await asyncio.sleep(0.05)
        await ws.stop()
        await asyncio.wait_for(task, timeout=1.0)

    await run_then_stop()
    assert ws._stop_event.is_set()  # type: ignore[attr-defined]


def test_backoff_policy_jitter_clamps_to_max() -> None:
    p = BackoffPolicy(initial_seconds=1.0, max_seconds=4.0, multiplier=2.0, jitter=0.5)
    # attempt=0 → ~1s, attempt=1 → ~2s, attempt=2+ → clamped to 4s
    delays = [p.delay_for(i) for i in range(6)]
    for d in delays:
        assert 0.0 <= d <= 4.0
    # No-jitter path is deterministic
    p2 = BackoffPolicy(initial_seconds=1.0, max_seconds=10.0, multiplier=2.0, jitter=0.0)
    assert p2.delay_for(0) == 1.0
    assert p2.delay_for(1) == 2.0
    assert p2.delay_for(3) == 8.0
    assert p2.delay_for(10) == 10.0


# ---- runtime integration ------------------------------------------------


def _runtime(tmp_path: Path) -> Runtime:
    policy = Policy()
    rt = Runtime(
        policy=policy,
        gamma=StubGammaAdapter([]),
        clob=PaperCLOBAdapter(),
        logger=ImmutableLogger(tmp_path / "imm.jsonl"),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
        store=SQLiteStore(":memory:"),
    )
    rt.sentinel = PortfolioSentinel(
        policy=policy, clob=rt.clob, state=rt.state, incidents=rt.incidents
    )
    return rt


@pytest.mark.asyncio
async def test_fill_event_updates_sqlite_position(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)

    fill = FillEvent(
        market_id="m1",
        token_id="t-yes",
        outcome=Outcome.YES,
        side=Side.BUY,
        price=0.55,
        size=4.0,
        exchange_order_id="x-1",
        client_order_id="c-1",
        timestamp=datetime.now(timezone.utc),
    )
    await rt.handle_user_event(fill)

    rows = rt.store.get_open_positions()
    assert len(rows) == 1
    assert rows[0]["market_id"] == "m1"
    assert rows[0]["token_id"] == "t-yes"
    assert rows[0]["size"] == 4.0
    assert rows[0]["avg_price"] == pytest.approx(0.55)

    # Sentinel staleness clock was bumped
    assert rt.sentinel.last_user_channel_event == fill.timestamp

    # A second BUY recomputes the weighted-average price
    fill2 = fill.model_copy(update={"price": 0.65, "size": 6.0, "exchange_order_id": "x-2"})
    await rt.handle_user_event(fill2)
    rows = rt.store.get_open_positions()
    assert rows[0]["size"] == 10.0
    assert rows[0]["avg_price"] == pytest.approx((4 * 0.55 + 6 * 0.65) / 10.0)


@pytest.mark.asyncio
async def test_fill_event_logs_to_immutable_log(tmp_path: Path) -> None:
    rt = _runtime(tmp_path)
    log_path = tmp_path / "imm.jsonl"

    fill = FillEvent(
        market_id="m1", token_id="t-yes", outcome=Outcome.YES, side=Side.BUY,
        price=0.55, size=1.0, exchange_order_id="x-1",
        timestamp=datetime.now(timezone.utc),
    )
    await rt.handle_user_event(fill)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    actors = {json.loads(line)["actor"] for line in lines}
    assert "user_ws" in actors
    assert "post_order_kelly_guard" in actors


@pytest.mark.asyncio
async def test_kelly_breach_on_fill_kills_runtime(tmp_path: Path) -> None:
    """A fill that pushes exposure over the per-market cap must kill the runtime
    and route the breach through ``IncidentManager.trip_killed``."""
    rt = _runtime(tmp_path)
    # Pre-load the paper adapter with a position big enough that the post-order
    # hook will fail when re-evaluated. Bankroll=$1000, market cap=1% → $10.
    rt.clob._positions[("m1", "t-yes")] = Position(  # type: ignore[attr-defined]
        market_id="m1", token_id="t-yes", outcome=Outcome.YES,
        size=200.0, avg_price=0.50,  # $100 exposure >> $10 cap
    )

    fill = FillEvent(
        market_id="m1", token_id="t-yes", outcome=Outcome.YES, side=Side.BUY,
        price=0.50, size=1.0, exchange_order_id="x-1",
        timestamp=datetime.now(timezone.utc),
    )
    await rt.handle_user_event(fill)

    assert rt.incidents.state is State.KILLED
    codes = [i.code for i in rt.incidents.incidents]
    assert "POST_ORDER_KELLY_BREACH" in codes


@pytest.mark.asyncio
async def test_stale_user_channel_trips_lockdown(tmp_path: Path) -> None:
    """If no event arrives for longer than the staleness threshold, the
    Portfolio Sentinel must trip LOCKDOWN."""
    rt = _runtime(tmp_path)
    assert rt.sentinel is not None
    rt.sentinel.max_user_channel_age_seconds = 5
    # Last seen 2 minutes ago — well past the threshold.
    rt.sentinel.last_user_channel_event = datetime.now(timezone.utc) - timedelta(seconds=120)

    await rt.sentinel.tick()
    assert rt.incidents.state is State.LOCKDOWN
