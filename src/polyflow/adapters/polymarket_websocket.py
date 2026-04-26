"""Polymarket CLOB *user* WebSocket adapter (PRD §7.1, §16.3, §21.2).

Connects to ``wss://ws-subscriptions-clob.polymarket.com/ws/user``,
authenticates with the L2 key set (``apiKey`` / ``secret`` / ``passphrase``),
and streams fills, order updates, and cancels for the markets in the active
watchlist.

Wire-format note: the user channel takes one initial JSON subscription
message of the form

    {"auth": {"apiKey": "...", "secret": "...", "passphrase": "..."},
     "type": "user",
     "markets": ["0x...", "0x..."]}

then emits one JSON message per event. We dispatch each message into a
strict ``WSEvent`` model (see ``polyflow.types``) and forward it through an
``asyncio.Queue`` for the runtime consumer.

Reconnect behavior is intentional: any disconnect (network blip, server
restart, auth burn) triggers an exponential backoff with jitter, capped at
``max_backoff_seconds``. The runtime never drops the channel for good — only
``stop()`` ends the loop.

Tests (``tests/test_polymarket_websocket.py``) inject a fake transport
that exposes the same ``send`` / ``recv`` / ``close`` shape as
``websockets.client.WebSocketClientProtocol`` so we never touch the network.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol

import structlog

from ..secrets import Credentials
from ..types import (
    Outcome,
    Side,
    WSCancelEvent,
    WSEvent,
    WSFillEvent,
    WSOrderUpdateEvent,
)

log = structlog.get_logger("polyflow.ws.user")


_USER_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"


class WebSocketLike(Protocol):
    """Minimal duck-typed surface we need from a websocket connection."""

    async def send(self, message: str) -> None: ...
    async def recv(self) -> str | bytes: ...
    async def close(self) -> None: ...


WebSocketConnector = Callable[[str], Awaitable[WebSocketLike]]
"""A callable that returns a connected ``WebSocketLike`` for the given URL.

Production wires this to ``websockets.connect``. Tests inject a fake."""


async def _default_connector(url: str) -> WebSocketLike:
    """Lazy-import ``websockets`` so the adapter can be imported without it."""
    from websockets.client import connect  # type: ignore[import-not-found]

    return await connect(url, ping_interval=20, ping_timeout=20)  # type: ignore[return-value]


@dataclass
class BackoffPolicy:
    """Exponential backoff with full jitter (PRD §21.2 reconnect)."""

    initial_seconds: float = 0.5
    max_seconds: float = 30.0
    multiplier: float = 2.0
    jitter: float = 0.5  # full-jitter fraction in [0, 1]

    _attempt: int = field(default=0, init=False)

    def reset(self) -> None:
        self._attempt = 0

    def next_delay(self) -> float:
        base = min(
            self.max_seconds,
            self.initial_seconds * (self.multiplier**self._attempt),
        )
        self._attempt += 1
        if self.jitter <= 0:
            return base
        return base * (1.0 - self.jitter * random.random())


def _parse_event(raw: dict[str, Any]) -> WSEvent | None:
    """Map a raw user-channel JSON payload into a strict ``WSEvent``.

    Polymarket's user channel emits a small handful of message types:
      - ``trade`` — a fill against one of our orders
      - ``order`` — an order status update (placed, partial, matched, …)
      - ``cancel`` — order cancelled

    Anything we don't recognize returns ``None`` and is logged but not
    forwarded; the channel itself stays up.
    """
    et = (raw.get("event_type") or raw.get("type") or "").lower()
    market_id = str(raw.get("market") or raw.get("market_id") or "")
    token_id = str(raw.get("asset_id") or raw.get("token_id") or raw.get("tokenID") or "")
    if not market_id or not token_id:
        return None

    if et in ("trade", "fill", "trade_update"):
        side_raw = str(raw.get("side") or "BUY").upper()
        outcome_raw = str(raw.get("outcome") or "YES").upper()
        try:
            return WSFillEvent(
                market_id=market_id,
                token_id=token_id,
                outcome=Outcome(outcome_raw) if outcome_raw in ("YES", "NO") else Outcome.YES,
                side=Side.BUY if side_raw == "BUY" else Side.SELL,
                price=float(raw.get("price") or 0.0),
                size=float(raw.get("size") or raw.get("matched_amount") or 0.0),
                exchange_order_id=raw.get("order_id") or raw.get("exchange_order_id"),
                client_order_id=raw.get("client_order_id") or raw.get("clientOrderId"),
                trade_id=raw.get("trade_id") or raw.get("id"),
                fee_rate_bps=float(raw.get("fee_rate_bps") or 0.0),
            )
        except (ValueError, TypeError) as e:
            log.warning("ws_user_fill_parse_failed", error=str(e), raw=raw)
            return None

    if et in ("order", "order_update", "placement", "match"):
        try:
            return WSOrderUpdateEvent(
                market_id=market_id,
                token_id=token_id,
                exchange_order_id=str(raw.get("order_id") or raw.get("exchange_order_id") or ""),
                client_order_id=raw.get("client_order_id") or raw.get("clientOrderId"),
                status=str(raw.get("status") or raw.get("state") or "UNKNOWN"),
                size=float(raw.get("size") or raw.get("original_size") or 0.0),
                size_remaining=float(raw.get("size_remaining") or raw.get("remaining") or 0.0),
                price=float(raw.get("price") or 0.0),
            )
        except (ValueError, TypeError) as e:
            log.warning("ws_user_order_parse_failed", error=str(e), raw=raw)
            return None

    if et in ("cancel", "cancellation", "cancelled"):
        return WSCancelEvent(
            market_id=market_id,
            token_id=token_id,
            exchange_order_id=str(raw.get("order_id") or raw.get("exchange_order_id") or ""),
            client_order_id=raw.get("client_order_id") or raw.get("clientOrderId"),
            reason=raw.get("reason"),
        )

    return None


class PolymarketUserWebSocket:
    """Long-running task that owns the user-channel WebSocket connection.

    Usage::

        ws = PolymarketUserWebSocket(credentials=creds, markets_provider=watchlist_ids)
        task = asyncio.create_task(ws.run())
        async for event in ws.events():
            ...

    The adapter never raises out of ``run()`` for transient errors; it logs,
    backs off, and reconnects. ``stop()`` is the only clean exit.
    """

    def __init__(
        self,
        *,
        credentials: Credentials,
        markets_provider: Callable[[], list[str]],
        url: str = _USER_WS_URL,
        connector: WebSocketConnector | None = None,
        backoff: BackoffPolicy | None = None,
        queue_maxsize: int = 1024,
    ) -> None:
        if not credentials.has_trade_credentials:
            raise ValueError(
                "User WebSocket requires full L2 credentials. Missing: "
                + ",".join(credentials.missing_for_trading())
            )
        self.credentials = credentials
        self.markets_provider = markets_provider
        self.url = url
        self._connector = connector or _default_connector
        self._backoff = backoff or BackoffPolicy()
        self._queue: asyncio.Queue[WSEvent] = asyncio.Queue(maxsize=queue_maxsize)
        self._stop_event = asyncio.Event()
        self._connection: WebSocketLike | None = None
        self.last_event_at: datetime | None = None
        self.connect_count: int = 0
        self.disconnect_count: int = 0
        self.event_count: int = 0

    # ---- public API ------------------------------------------------------
    @property
    def queue(self) -> asyncio.Queue[WSEvent]:
        return self._queue

    async def stop(self) -> None:
        self._stop_event.set()
        if self._connection is not None:
            with contextlib.suppress(Exception):
                await self._connection.close()

    async def run(self) -> None:
        """Top-level reconnect loop. Returns only when ``stop()`` is called."""
        while not self._stop_event.is_set():
            try:
                await self._run_once()
                # _run_once returning cleanly = peer closed; reset backoff
                # only if we made it past the handshake, otherwise we'd hammer
                # a broken auth endpoint.
                if self.connect_count > 0:
                    self._backoff.reset()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("ws_user_run_iteration_failed", error=str(exc))

            if self._stop_event.is_set():
                return
            await self._sleep_with_stop(self._backoff.next_delay())

    async def _sleep_with_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    async def _run_once(self) -> None:
        """Connect, subscribe, drain. Any exit triggers reconnect."""
        conn = await self._connector(self.url)
        self._connection = conn
        self.connect_count += 1
        try:
            await self._send_subscribe(conn)
            await self._consume(conn)
        finally:
            self.disconnect_count += 1
            with contextlib.suppress(Exception):
                await conn.close()
            self._connection = None

    async def _send_subscribe(self, conn: WebSocketLike) -> None:
        markets = list(self.markets_provider() or [])
        payload = {
            "auth": {
                "apiKey": self.credentials.api_key,
                "secret": self.credentials.api_secret,
                "passphrase": self.credentials.api_passphrase,
            },
            "type": "user",
            "markets": markets,
        }
        await conn.send(json.dumps(payload, separators=(",", ":")))
        log.info("ws_user_subscribed", market_count=len(markets))

    async def _consume(self, conn: WebSocketLike) -> None:
        while not self._stop_event.is_set():
            raw = await conn.recv()
            self._record_event_received()
            try:
                payload = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                log.warning("ws_user_invalid_json")
                continue

            # The server may send a single event object OR a list of events.
            messages: list[dict[str, Any]] = (
                payload if isinstance(payload, list) else [payload]
            )
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                # Skip protocol messages (e.g. {"type": "subscribed"}).
                if msg.get("type") in ("subscribed", "ping", "pong"):
                    continue
                event = _parse_event(msg)
                if event is None:
                    continue
                self.event_count += 1
                # Backpressure: if the queue is full, drop the oldest event so
                # a wedged consumer never silently freezes the connection.
                try:
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    with contextlib.suppress(asyncio.QueueEmpty):
                        self._queue.get_nowait()
                    self._queue.put_nowait(event)

    def _record_event_received(self) -> None:
        self.last_event_at = datetime.now(timezone.utc)
