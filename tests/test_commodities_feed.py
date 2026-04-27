"""Commodities price feed (Yahoo Finance) tests."""

from __future__ import annotations

import httpx
import pytest

from polyflow.adapters.commodities import CommoditiesFeed


def _yahoo_payload(prices: list[float | None], *, start_ts: int | None = None) -> dict:
    import time as _time
    if start_ts is None:
        start_ts = int(_time.time()) - 60 * len(prices)
    closes = list(prices)
    timestamps = [start_ts + i * 60 for i in range(len(prices))]
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ]
        }
    }


@pytest.mark.asyncio
async def test_fetch_wti() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json=_yahoo_payload([72.10, 72.15, 72.30]))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        feed = CommoditiesFeed()
        quote = await feed.fetch("WTI", client=client)

    assert "/CL%3DF" in seen["path"] or "/CL=F" in seen["path"]
    assert quote is not None
    assert quote.asset == "WTI"
    assert quote.price_usd == pytest.approx(72.30)


@pytest.mark.asyncio
async def test_alias_oil_routes_to_wti() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_yahoo_payload([70.00]))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        feed = CommoditiesFeed()
        quote = await feed.fetch("OIL", client=client)
    assert quote is not None
    assert quote.asset == "OIL"
    assert quote.price_usd == 70.00


@pytest.mark.asyncio
async def test_gold_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_yahoo_payload([2_315.50]))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        feed = CommoditiesFeed()
        quote = await feed.fetch("GOLD", client=client)
    assert quote is not None
    assert quote.price_usd == pytest.approx(2_315.50)


@pytest.mark.asyncio
async def test_skips_null_closes_at_end() -> None:
    """Yahoo returns nulls for incomplete bars at the end of the window."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_yahoo_payload([72.10, 72.20, None]))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        feed = CommoditiesFeed()
        quote = await feed.fetch("WTI", client=client)
    assert quote is not None
    assert quote.price_usd == pytest.approx(72.20)


@pytest.mark.asyncio
async def test_unknown_asset_returns_none() -> None:
    feed = CommoditiesFeed()
    quote = await feed.fetch("DOGE")
    assert quote is None


@pytest.mark.asyncio
async def test_realized_vol_needs_three_samples() -> None:
    counter = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["i"] += 1
        # Tiny price changes per call so log returns are non-zero
        return httpx.Response(200, json=_yahoo_payload([2_300 + counter["i"] * 0.5]))

    transport = httpx.MockTransport(handler)
    feed = CommoditiesFeed()
    async with httpx.AsyncClient(transport=transport) as client:
        await feed.fetch("GOLD", client=client)
        assert feed.realized_volatility_annualized("GOLD") is None
        await feed.fetch("GOLD", client=client)
        assert feed.realized_volatility_annualized("GOLD") is None
        await feed.fetch("GOLD", client=client)
        vol = feed.realized_volatility_annualized("GOLD")
    assert vol is not None and vol >= 0
