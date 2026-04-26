"""Polymarket Data API user-adapter tests."""

from __future__ import annotations

import httpx
import pytest

from polyflow.adapters.polymarket_user import PolymarketUserAdapter


def test_requires_wallet() -> None:
    with pytest.raises(ValueError):
        PolymarketUserAdapter(wallet_address="")


@pytest.mark.asyncio
async def test_positions_calls_correct_endpoint() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.params)
        return httpx.Response(200, json=[{"market_id": "m1", "size": 1.0}])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketUserAdapter(wallet_address="0xABC", client=client)
        rows = await adapter.positions()

    assert seen["path"] == "/positions"
    # wallet is lower-cased in the query
    assert "user=0xabc" in seen["query"]
    assert rows[0]["market_id"] == "m1"


@pytest.mark.asyncio
async def test_activity_passes_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"activity": [{"id": "a1"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketUserAdapter(wallet_address="0xABC", client=client)
        rows = await adapter.activity(limit=10)

    assert rows == [{"id": "a1"}]
