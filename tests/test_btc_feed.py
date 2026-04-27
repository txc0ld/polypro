"""BTC multi-source price feed tests (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from polyflow.adapters.btc_feed import (
    BtcPriceFeed,
    disagreement_bps,
    summarize,
)


@pytest.mark.asyncio
async def test_fetch_aggregates_three_sources() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if "coingecko" in host:
            return httpx.Response(200, json={"bitcoin": {"usd": 100_000.0}})
        if "binance" in host:
            return httpx.Response(200, json={"price": "100050.0"})
        if "coinbase" in host:
            return httpx.Response(200, json={"data": {"amount": "100025"}})
        return httpx.Response(404)

    feed = BtcPriceFeed()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quotes = await feed.fetch(client=client)

    assert len(quotes) == 3
    assert {q.source for q in quotes} == {"coingecko:BTC", "binance:BTC", "coinbase:BTC"}


@pytest.mark.asyncio
async def test_one_source_failure_does_not_abort() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "binance" in request.url.host:
            return httpx.Response(503)
        if "coingecko" in request.url.host:
            return httpx.Response(200, json={"bitcoin": {"usd": 100_000}})
        if "coinbase" in request.url.host:
            return httpx.Response(200, json={"data": {"amount": "99950"}})
        return httpx.Response(404)

    feed = BtcPriceFeed()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quotes = await feed.fetch(client=client)

    assert len(quotes) == 2
    assert "binance:BTC" not in {q.source for q in quotes}


def test_disagreement_bps() -> None:
    from polyflow.adapters.btc_feed import _SourceQuote
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    quotes = [
        _SourceQuote("a", "u", 100_000.0, now),
        _SourceQuote("b", "u", 100_080.0, now),  # +8 bps from median
    ]
    bps = disagreement_bps(quotes)
    # max-min = 80; median = 100040; 80/100040 * 10000 ≈ 8.0
    assert 7.5 < bps < 8.5


@pytest.mark.asyncio
async def test_summary_builder() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "coingecko" in request.url.host:
            return httpx.Response(200, json={"bitcoin": {"usd": 100_000}})
        if "binance" in request.url.host:
            return httpx.Response(200, json={"price": "100050"})
        return httpx.Response(404)

    feed = BtcPriceFeed()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quotes = await feed.fetch(client=client)
    s = summarize(quotes)
    assert s is not None
    assert s.median_price_usd == 100_025.0
    assert s.disagreement_bps > 0


@pytest.mark.asyncio
async def test_realized_vol_needs_at_least_three_samples() -> None:
    counter = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["i"] += 1
        n = counter["i"]
        if "coingecko" in request.url.host:
            return httpx.Response(200, json={"bitcoin": {"usd": 100_000 + n * 5}})
        if "binance" in request.url.host:
            return httpx.Response(200, json={"price": str(100_050 + n * 3)})
        if "coinbase" in request.url.host:
            return httpx.Response(200, json={"data": {"amount": str(100_025 + n * 4)}})
        return httpx.Response(404)

    feed = BtcPriceFeed()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await feed.fetch(client=client)
        assert feed.realized_volatility_annualized() is None  # 1 sample
        await feed.fetch(client=client)
        # 2 samples = 1 return; pstdev needs >=2 returns -> still None
        assert feed.realized_volatility_annualized() is None
        await feed.fetch(client=client)
        vol = feed.realized_volatility_annualized()
    assert vol is not None and vol >= 0
