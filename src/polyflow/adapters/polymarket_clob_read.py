"""Polymarket CLOB *read* adapter.

Public endpoints (no auth required for reads):
    https://clob.polymarket.com/book?token_id=…
    https://clob.polymarket.com/midpoint?token_id=…
    https://clob.polymarket.com/price?token_id=…&side=BUY

Order placement / cancel / user channels require API keys + L1/L2 signatures
and are intentionally out of scope here — that lives in a separate
``polymarket_clob_trade.py`` adapter (not implemented yet — needs key management).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_CLOB_BASE = "https://clob.polymarket.com"


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class OrderBook:
    token_id: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    def depth_within(self, *, cents: float) -> dict[str, float]:
        """USDC depth on each side within ±cents of best."""
        out = {"bid": 0.0, "ask": 0.0}
        if self.best_bid is not None:
            cutoff = self.best_bid - cents
            out["bid"] = sum(lvl.size * lvl.price for lvl in self.bids if lvl.price >= cutoff)
        if self.best_ask is not None:
            cutoff = self.best_ask + cents
            out["ask"] = sum(lvl.size * lvl.price for lvl in self.asks if lvl.price <= cutoff)
        return out

    @property
    def spread_pct(self) -> float:
        if self.best_bid is None or self.best_ask is None:
            return 100.0
        mid = (self.best_bid + self.best_ask) / 2.0
        if mid <= 0:
            return 100.0
        return ((self.best_ask - self.best_bid) / mid) * 100.0


def _parse_book(raw: dict[str, Any], token_id: str) -> OrderBook:
    def _levels(side: list[Any]) -> list[OrderBookLevel]:
        out: list[OrderBookLevel] = []
        for lvl in side or []:
            try:
                out.append(OrderBookLevel(price=float(lvl["price"]), size=float(lvl["size"])))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    return OrderBook(
        token_id=token_id,
        # CLOB returns asks ascending and bids descending — preserve that.
        bids=_levels(raw.get("bids", [])),
        asks=_levels(raw.get("asks", [])),
    )


class PolymarketCLOBReadAdapter:
    """Read-only async client for the Polymarket CLOB."""

    def __init__(
        self,
        *,
        base_url: str = _CLOB_BASE,
        timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def __aenter__(self) -> "PolymarketCLOBReadAdapter":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def order_book(self, token_id: str) -> OrderBook:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            resp = await client.get(f"{self._base_url}/book", params={"token_id": token_id})
            resp.raise_for_status()
            return _parse_book(resp.json(), token_id)
        finally:
            if owns:
                await client.aclose()

    async def midpoint(self, token_id: str) -> float | None:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            resp = await client.get(f"{self._base_url}/midpoint", params={"token_id": token_id})
            resp.raise_for_status()
            data = resp.json()
            return float(data.get("mid")) if "mid" in data else None
        finally:
            if owns:
                await client.aclose()
