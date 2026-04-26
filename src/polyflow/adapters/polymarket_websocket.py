"""Polymarket CLOB WebSocket — user channel adapter (PRD §7.1, §11, §16.3).

Connects to ``wss://ws-subscriptions-clob.polymarket.com/ws/user``, sends an
auth+subscription handshake, and emits structured ``FillEvent`` /
``OrderUpdateEvent`` / ``CancelEvent`` payloads.

What this adapter is responsible for:
  - L2-authenticated handshake (apiKey + secret + passphrase, reused from
    ``polyflow.clob_auth``);
  - market-list subscription;
  - parsing each inbound JSON frame into a strict pydantic event;
  - exponential-backoff-with-jitter reconnect;
  - tracking ``last_event_at`` so the PortfolioSentinel staleness check works;
  - dispatching every event through an async callback.

What it deliberately does *not* do:
  - market-data channel (book / price changes) — separate adapter;
  - any persistence — the runtime owns SQLite writes;
  - any risk decisions — the runtime calls the post-order hook itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable

import structlog

from ..clob_auth import l2_headers
from ..types import (
    CancelEvent,
    FillEvent,
    OrderUpdateEvent,
    Outcome,
    Side,
    WebSocketEvent,
)

log = structlog.get_logger("polyflow.adapters.polymarket_websocket")


WS_USER_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"

EventHandler = Callable[[WebSocketEvent], Awaitable[None]]
"""Async function the runtime hands us; we call it once per parsed event."""

# Connector signature: ``await connect(url) -> websocket-like``. The real
# implementation is ``websockets.connect``; tests inject a fake to avoid the
# network. The returned object must support ``send(str)``, ``recv() -> str``,
# ``close()``, and async-iteration of incoming frames.
Connector = Callable[[str], Awaitable[Any]]


@dataclass
class BackoffPolicy:
    """Exponential backoff with full-jitter — clamped to a max."""

    initial_seconds: float = 1.0
    max_seconds: float = 30.0
    multiplier: float = 2.0
    jitter: float = 0.5  # 0..1, fraction of the computed delay

    def delay_for(self, attempt: int) -> float:
        base = min(self.max_seconds, self.initial_seconds * (self.multiplier ** max(0, attempt)))
        if self.jitter <= 0:
            return base
        return base * (1.0 - self.jitter) + base * self.jitter * random.random()


@dataclass
class PolymarketUserWebSocket:
    """Async runner for the Polymarket CLOB user channel.

    The runtime constructs one of these per process and registers
    :py:meth:`run` as a long-running task on the SubagentScheduler. ``stop``
    triggers a clean shutdown.
    """

    api_key: str
    secret: str
    passphrase: str
    markets: list[str]
    on_event: EventHandler

    url: str = WS_USER_URL
    connector: Connector | None = None
    backoff: BackoffPolicy = field(default_factory=BackoffPolicy)
    max_reconnects: int | None = None  # None = unlimited

    # ---- runtime state (not constructor args) ----
    last_event_at: datetime | None = field(default=None, init=False)
    last_connected_at: datetime | None = field(default=None, init=False)
    reconnect_count: int = field(default=0, init=False)
    event_count: int = field(default=0, init=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _ws: Any | None = field(default=None, init=False)

    # ---- payload helpers ----
    def auth_payload(self) -> dict[str, Any]:
        """The first JSON frame we send after the connection opens.

        Polymarket's user channel takes the L2 key set inline (apiKey, secret,
        passphrase) plus the channel ``type`` and the markets subscription
        list. The L2 HMAC headers are also attached at the WebSocket-handshake
        layer for venues that prefer header auth.
        """
        return {
            "auth": {
                "apiKey": self.api_key,
                "secret": self.secret,
                "passphrase": self.passphrase,
            },
            "type": "user",
            "markets": list(self.markets),
        }

    def handshake_headers(self) -> dict[str, str]:
        """L2 HMAC headers attached to the WebSocket upgrade request."""
        return l2_headers(
            api_key=self.api_key,
            secret=self.secret,
            passphrase=self.passphrase,
            method="GET",
            path="/ws/user",
        )

    # ---- public API ----
    async def run(self) -> None:
        """Reconnect loop. Returns only on ``stop()`` or when the reconnect
        budget is exhausted."""
        attempt = 0
        while not self._stop_event.is_set():
            try:
                await self._connect_and_consume()
                attempt = 0  # clean disconnect → reset backoff
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("ws_user_disconnect", error=f"{type(exc).__name__}: {exc}")

            if self._stop_event.is_set():
                break
            if self.max_reconnects is not None and self.reconnect_count >= self.max_reconnects:
                log.error("ws_user_max_reconnects", count=self.reconnect_count)
                break

            self.reconnect_count += 1
            delay = self.backoff.delay_for(attempt)
            attempt += 1
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                continue

    async def stop(self) -> None:
        self._stop_event.set()
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()

    def update_markets(self, markets: Iterable[str]) -> None:
        """Replace the active subscription list. Takes effect on next connect."""
        self.markets = list(markets)

    # ---- internals ----
    async def _connect_and_consume(self) -> None:
        if self.connector is None:
            self.connector = _default_connector(self.handshake_headers())
        ws = await self.connector(self.url)
        self._ws = ws
        self.last_connected_at = datetime.now(timezone.utc)
        try:
            await ws.send(json.dumps(self.auth_payload()))
            async for raw in _aiter(ws):
                await self._handle_frame(raw)
                if self._stop_event.is_set():
                    break
        finally:
            self._ws = None
            with contextlib.suppress(Exception):
                await ws.close()

    async def _handle_frame(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            log.warning("ws_user_bad_frame", raw=str(raw)[:200])
            return
        # Polymarket sends arrays of events sometimes; normalize to a list.
        items = msg if isinstance(msg, list) else [msg]
        for item in items:
            event = parse_event(item)
            if event is None:
                continue
            self.last_event_at = datetime.now(timezone.utc)
            self.event_count += 1
            try:
                await self.on_event(event)
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "ws_user_handler_failed",
                    error=f"{type(exc).__name__}: {exc}",
                    event_type=event.type.value,
                )


# ---- frame parsing -------------------------------------------------------


def _ts(item: dict[str, Any]) -> datetime:
    raw = item.get("timestamp") or item.get("ts") or item.get("created_at")
    if isinstance(raw, (int, float)):
        # Polymarket uses ms; tolerate seconds too.
        v = float(raw)
        if v > 1e12:
            v = v / 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _outcome(item: dict[str, Any]) -> Outcome:
    raw = (item.get("outcome") or "YES").upper()
    return Outcome.YES if raw == "YES" else Outcome.NO


def _side(item: dict[str, Any]) -> Side:
    raw = (item.get("side") or "BUY").upper()
    return Side.BUY if raw == "BUY" else Side.SELL


def _str(item: dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = item.get(k)
        if v is not None:
            return str(v)
    return default


def parse_event(item: dict[str, Any]) -> WebSocketEvent | None:
    """Map a single parsed JSON object onto one of our event types.

    Returns ``None`` for control frames (``pong``, subscription acks) and
    anything we don't recognize. Designed to be tolerant — the user channel
    wire format is not strictly versioned.
    """
    if not isinstance(item, dict):
        return None
    raw_type = (item.get("event_type") or item.get("type") or "").upper()
    if raw_type in ("PONG", "PING", "SUBSCRIBED", "AUTHED", ""):
        return None

    market_id = _str(item, "market_id", "marketId", "market")
    token_id = _str(item, "asset_id", "tokenId", "token_id")

    try:
        if raw_type in ("TRADE", "FILL", "MATCHED"):
            return FillEvent(
                market_id=market_id,
                token_id=token_id,
                outcome=_outcome(item),
                side=_side(item),
                price=float(_str(item, "price", default="0") or 0),
                size=float(_str(item, "size", "matched_amount", default="0") or 0),
                exchange_order_id=_str(item, "order_id", "orderId", "exchange_order_id"),
                client_order_id=_str(item, "client_order_id", "clientOrderId") or None,
                fill_id=_str(item, "id", "fill_id") or None,
                timestamp=_ts(item),
            )
        if raw_type in ("ORDER", "ORDER_UPDATE", "PLACEMENT", "UPDATE"):
            return OrderUpdateEvent(
                market_id=market_id,
                token_id=token_id,
                exchange_order_id=_str(item, "order_id", "orderId", "exchange_order_id"),
                client_order_id=_str(item, "client_order_id", "clientOrderId") or None,
                status=_str(item, "status", default="UNKNOWN"),
                remaining_size=float(_str(item, "size_remaining", "remaining", default="0") or 0),
                timestamp=_ts(item),
            )
        if raw_type in ("CANCEL", "CANCELLED", "CANCELED"):
            return CancelEvent(
                market_id=market_id,
                token_id=token_id,
                exchange_order_id=_str(item, "order_id", "orderId", "exchange_order_id"),
                client_order_id=_str(item, "client_order_id", "clientOrderId") or None,
                reason=_str(item, "reason") or None,
                timestamp=_ts(item),
            )
    except (TypeError, ValueError) as exc:
        log.warning("ws_user_parse_failed", raw_type=raw_type, error=str(exc))
        return None
    return None


# ---- connector helpers ---------------------------------------------------


async def _aiter(ws: Any):
    """Yield frames either via async-for support or via repeated ``recv()``."""
    if hasattr(ws, "__aiter__"):
        async for frame in ws:
            yield frame
        return
    while True:
        frame = await ws.recv()
        if frame is None:
            return
        yield frame


def _default_connector(extra_headers: dict[str, str]) -> Connector:
    """Build a connector that wraps ``websockets.connect`` with our headers."""

    async def connect(url: str) -> Any:
        # Lazy import — keep ``websockets`` out of the import path for tests
        # that supply their own connector.
        import websockets  # type: ignore[import-not-found]

        return await websockets.connect(url, additional_headers=list(extra_headers.items()))

    return connect
