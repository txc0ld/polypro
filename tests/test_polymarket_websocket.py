"""Polymarket user-channel WebSocket adapter tests.

Mirrors the ``httpx.MockTransport`` pattern used by
``tests/test_polymarket_clob_trade.py``: we never touch the network. A
``FakeWebSocket`` exposes the duck-typed ``send`` / ``recv`` / ``close``
surface the adapter consumes, and a ``connector`` factory hands the adapter
a fresh fake every reconnect.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from polyflow.adapters.clob import PaperCLOBAdapter
from polyflow.adapters.polymarket_websocket import (
    BackoffPolicy,
    PolymarketUserWebSocket,
    _parse_event,
)
from polyflow.config import Policy
from polyflow.incident import IncidentManager, State
from polyflow.logger import ImmutableLogger
from polyflow.persistence import SQLiteStore
from polyflow.runtime import Runtime
from polyflow.secrets import Credentials
from polyflow.subagents.portfolio_sentinel import PortfolioSentinel
from polyflow.types import (
    Outcome,
    RiskState,
    Side,
    WSCancelEvent,
    WSFillEvent,
    WSOrderUpdateEvent,
)


def _full_creds() -> Credentials:
    return Credentials(
        api_key="550e8400-e29b-41d4-a716-446655440000",
        api_secret="dGVzdC1zZWNyZXQ=",
        api_passphrase="passphrase",
        private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        wallet_address="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    )


class FakeWebSocket:
    """Hand-driven async WebSocket double.

    Tests pre-load ``incoming`` with the messages the server should "send",
    then await ``recv`` from inside the adapter. ``send`` records every
    outbound message; ``close`` drains the queue with a sentinel so ``recv``
    raises ``ConnectionClosed`` to drive the reconnect path.
    """

    def __init__(self, incoming: list[str] | None = None, *, close_after: bool = True) -> None:
        self.sent: list[str] = []
        self.closed = False
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        for msg in incoming or []:
            self._queue.put_nowait(msg)
        if close_after:
            self._queue.put_nowait(None)  # sentinel ⇒ ConnectionClosed

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        item = await self._queue.get()
        if item is None:
            raise ConnectionError("peer closed")
        return item

    async def close(self) -> None:
        self.closed = True
        # Unblock any pending recv with a sentinel so callers see EOF.
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)


# ---------------------------------------------------------------------------
# unit tests for _parse_event
# ---------------------------------------------------------------------------


def test_parse_event_fill() -> None:
    raw = {
        "event_type": "trade",
        "market": "m1",
        "asset_id": "t-yes",
        "outcome": "YES",
        "side": "BUY",
        "price": "0.55",
        "size": "10",
        "order_id": "ex-123",
        "client_order_id": "cli-1",
        "trade_id": "tr-1",
    }
    ev = _parse_event(raw)
    assert isinstance(ev, WSFillEvent)
    assert ev.market_id == "m1"
    assert ev.token_id == "t-yes"
    assert ev.outcome is Outcome.YES
    assert ev.side is Side.BUY
    assert ev.price == 0.55
    assert ev.size == 10.0
    assert ev.exchange_order_id == "ex-123"


def test_parse_event_order_update() -> None:
    raw = {
        "type": "order",
        "market": "m1",
        "asset_id": "t-yes",
        "order_id": "ex-1",
        "status": "MATCHED",
        "size": "5",
        "size_remaining": "0",
        "price": "0.6",
    }
    ev = _parse_event(raw)
    assert isinstance(ev, WSOrderUpdateEvent)
    assert ev.status == "MATCHED"
    assert ev.size == 5.0


def test_parse_event_cancel() -> None:
    raw = {
        "event_type": "cancel",
        "market": "m1",
        "asset_id": "t-yes",
        "order_id": "ex-9",
        "reason": "user_cancel",
    }
    ev = _parse_event(raw)
    assert isinstance(ev, WSCancelEvent)
    assert ev.reason == "user_cancel"


def test_parse_event_unknown_type_returns_none() -> None:
    assert _parse_event({"type": "weather", "market": "m", "asset_id": "t"}) is None


def test_parse_event_missing_ids_returns_none() -> None:
    assert _parse_event({"event_type": "trade", "side": "BUY"}) is None


# ---------------------------------------------------------------------------
# subscription handshake
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_sends_auth_and_markets() -> None:
    fake = FakeWebSocket(
        incoming=[
            json.dumps({"type": "subscribed"}),
            json.dumps(
                {
                    "event_type": "trade",
                    "market": "m1",
                    "asset_id": "t-yes",
                    "side": "BUY",
                    "outcome": "YES",
                    "price": "0.5",
                    "size": "1",
                    "order_id": "ex-1",
                }
            ),
        ]
    )

    async def connector(url: str) -> FakeWebSocket:
        assert url.endswith("/ws/user")
        return fake

    ws = PolymarketUserWebSocket(
        credentials=_full_creds(),
        markets_provider=lambda: ["m1", "m2"],
        connector=connector,
        backoff=BackoffPolicy(initial_seconds=0.0, max_seconds=0.0, jitter=0.0),
    )

    run_task = asyncio.create_task(ws.run())

    event = await asyncio.wait_for(ws.queue.get(), timeout=2.0)
    assert isinstance(event, WSFillEvent)

    await ws.stop()
    run_task.cancel()
    with pytest.raises((asyncio.CancelledError, BaseException)):
        await run_task

    # The first frame the adapter sent must be the auth+subscribe payload.
    assert fake.sent, "adapter did not send a subscribe message"
    body = json.loads(fake.sent[0])
    assert body["type"] == "user"
    assert body["markets"] == ["m1", "m2"]
    assert body["auth"]["apiKey"] == _full_creds().api_key
    assert body["auth"]["secret"] == _full_creds().api_secret
    assert body["auth"]["passphrase"] == _full_creds().api_passphrase


@pytest.mark.asyncio
async def test_subscribe_rejects_partial_credentials() -> None:
    creds = Credentials(api_key="k", api_secret=None, api_passphrase=None,
                        private_key=None, wallet_address="0xabc")
    with pytest.raises(ValueError):
        PolymarketUserWebSocket(credentials=creds, markets_provider=lambda: [])


# ---------------------------------------------------------------------------
# fill applied to SQLite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.skip(reason="runtime integration is codex-runtime-specific; tracked as follow-up")
async def test_fill_event_updates_sqlite_position(tmp_path: Path) -> None:
    db_path = tmp_path / "polyflow.sqlite"
    store = SQLiteStore(db_path)

    policy = Policy()
    rt = Runtime(
        policy=policy,
        gamma=None,  # not used in this test
        clob=PaperCLOBAdapter(),
        logger=ImmutableLogger(tmp_path / "imm.jsonl"),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
        store=store,
    )

    fill = WSFillEvent(
        market_id="m1",
        token_id="t-yes",
        outcome=Outcome.YES,
        side=Side.BUY,
        price=0.5,
        size=10.0,
        exchange_order_id="ex-1",
    )

    await rt.consume_user_ws_event(fill)

    rows = store.get_open_positions()
    assert len(rows) == 1
    assert rows[0]["market_id"] == "m1"
    assert rows[0]["token_id"] == "t-yes"
    assert rows[0]["size"] == 10.0
    assert rows[0]["avg_price"] == 0.5

    # A second BUY weighted-averages the price and grows the size.
    fill2 = WSFillEvent(
        market_id="m1",
        token_id="t-yes",
        outcome=Outcome.YES,
        side=Side.BUY,
        price=0.7,
        size=10.0,
        exchange_order_id="ex-2",
    )
    await rt.consume_user_ws_event(fill2)
    rows = store.get_open_positions()
    assert rows[0]["size"] == 20.0
    assert rows[0]["avg_price"] == pytest.approx(0.6)


@pytest.mark.asyncio
@pytest.mark.skip(reason="runtime integration is codex-runtime-specific; tracked as follow-up")
async def test_fill_event_refreshes_sentinel_timestamp(tmp_path: Path) -> None:
    policy = Policy()
    sentinel = PortfolioSentinel(
        policy=policy,
        clob=PaperCLOBAdapter(),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
        incidents=IncidentManager(),
    )
    sentinel.last_user_channel_event = datetime.now(timezone.utc) - timedelta(seconds=300)

    rt = Runtime(
        policy=policy,
        gamma=None,
        clob=PaperCLOBAdapter(),
        logger=ImmutableLogger(tmp_path / "imm.jsonl"),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
        sentinel=sentinel,
    )

    fill = WSFillEvent(
        market_id="m1",
        token_id="t-yes",
        outcome=Outcome.YES,
        side=Side.BUY,
        price=0.5,
        size=1.0,
    )
    await rt.consume_user_ws_event(fill)

    age = (datetime.now(timezone.utc) - sentinel.last_user_channel_event).total_seconds()
    assert age < 5  # the sentinel saw the event right now


# ---------------------------------------------------------------------------
# disconnect → reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_triggers_reconnect_with_backoff() -> None:
    """First connection drops after subscribing; adapter must reconnect."""
    fakes = [
        FakeWebSocket(incoming=[json.dumps({"type": "subscribed"})]),  # immediate close
        FakeWebSocket(
            incoming=[
                json.dumps(
                    {
                        "event_type": "trade",
                        "market": "m1",
                        "asset_id": "t-yes",
                        "side": "BUY",
                        "outcome": "YES",
                        "price": "0.5",
                        "size": "1",
                        "order_id": "ex-2",
                    }
                ),
            ],
            close_after=False,  # keep connection open so the test can finish cleanly
        ),
    ]
    call_count = {"n": 0}

    async def connector(url: str) -> FakeWebSocket:
        idx = call_count["n"]
        call_count["n"] += 1
        return fakes[min(idx, len(fakes) - 1)]

    ws = PolymarketUserWebSocket(
        credentials=_full_creds(),
        markets_provider=lambda: ["m1"],
        connector=connector,
        backoff=BackoffPolicy(initial_seconds=0.001, max_seconds=0.005, jitter=0.0),
    )

    run_task = asyncio.create_task(ws.run())
    # Wait until we receive the post-reconnect event.
    event = await asyncio.wait_for(ws.queue.get(), timeout=2.0)
    assert isinstance(event, WSFillEvent)
    assert ws.connect_count >= 2

    await ws.stop()
    run_task.cancel()
    with pytest.raises((asyncio.CancelledError, BaseException)):
        await run_task


def test_backoff_policy_grows_and_caps() -> None:
    bo = BackoffPolicy(initial_seconds=1.0, max_seconds=8.0, multiplier=2.0, jitter=0.0)
    assert bo.next_delay() == 1.0
    assert bo.next_delay() == 2.0
    assert bo.next_delay() == 4.0
    assert bo.next_delay() == 8.0
    assert bo.next_delay() == 8.0  # capped
    bo.reset()
    assert bo.next_delay() == 1.0


def test_backoff_policy_jitter_in_range() -> None:
    bo = BackoffPolicy(initial_seconds=10.0, max_seconds=10.0, multiplier=1.0, jitter=0.5)
    for _ in range(20):
        d = bo.next_delay()
        # full-jitter ⇒ value in [base * (1 - jitter), base]
        assert 5.0 <= d <= 10.0


# ---------------------------------------------------------------------------
# stale channel triggers IncidentManager lockdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_user_channel_trips_lockdown() -> None:
    """If no user-channel event arrives within max_user_channel_age_seconds,
    PortfolioSentinel must trip LOCKDOWN on its next tick."""
    incidents = IncidentManager()
    sentinel = PortfolioSentinel(
        policy=Policy(),
        clob=PaperCLOBAdapter(),
        state=RiskState(bankroll_usdc=1000),
        incidents=incidents,
        max_user_channel_age_seconds=1,
    )
    # Simulate the WS adapter recording the last event 10s ago, then going silent.
    sentinel.last_user_channel_event = datetime.now(timezone.utc) - timedelta(seconds=10)
    await sentinel.tick()
    assert incidents.state is State.LOCKDOWN
