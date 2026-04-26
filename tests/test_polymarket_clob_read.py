"""Polymarket CLOB read adapter tests (mock transport)."""

from __future__ import annotations

import httpx
import pytest

from polyflow.adapters.polymarket_clob_read import OrderBook, PolymarketCLOBReadAdapter


SAMPLE_BOOK = {
    "bids": [
        {"price": "0.55", "size": "1000"},
        {"price": "0.54", "size": "2000"},
        {"price": "0.50", "size": "3000"},
    ],
    "asks": [
        {"price": "0.57", "size": "1500"},
        {"price": "0.58", "size": "1500"},
    ],
}


class TestOrderBookHelpers:
    def test_best_bid_ask(self) -> None:
        book = OrderBook(
            token_id="t",
            bids=[type("L", (), {"price": 0.55, "size": 1000})()],  # type: ignore[arg-type]
            asks=[type("L", (), {"price": 0.57, "size": 1500})()],  # type: ignore[arg-type]
        )
        assert book.best_bid == 0.55
        assert book.best_ask == 0.57

    def test_spread_pct(self) -> None:
        book = OrderBook(
            token_id="t",
            bids=[type("L", (), {"price": 0.55, "size": 1000})()],  # type: ignore[arg-type]
            asks=[type("L", (), {"price": 0.57, "size": 1500})()],  # type: ignore[arg-type]
        )
        # mid 0.56 → (0.02 / 0.56) * 100 ≈ 3.57
        assert 3.0 < book.spread_pct < 4.0


@pytest.mark.asyncio
async def test_fetch_book() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.params)
        return httpx.Response(200, json=SAMPLE_BOOK)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketCLOBReadAdapter(client=client)
        book = await adapter.order_book("0xTOKEN")

    assert seen["path"] == "/book"
    assert "token_id=0xTOKEN" in seen["query"]
    assert book.best_bid == 0.55
    assert book.best_ask == 0.57
    depth = book.depth_within(cents=0.05)
    assert depth["bid"] > 0 and depth["ask"] > 0


@pytest.mark.asyncio
async def test_midpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"mid": "0.56"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketCLOBReadAdapter(client=client)
        m = await adapter.midpoint("0xTOKEN")

    assert m == 0.56
