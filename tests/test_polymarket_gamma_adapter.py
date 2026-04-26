"""Tests for the Polymarket Gamma HTTP adapter using a mocked transport.

We never make a real network call from tests — ``httpx.MockTransport`` lets us
verify the request shape and the JSON parsing path.
"""

from __future__ import annotations

import json

import httpx
import pytest

from polyflow.adapters.polymarket_gamma import (
    PolymarketGammaAdapter,
    parse_gamma_market,
)


SAMPLE = {
    "conditionId": "0xCONDITION",
    "eventId": "0xEVENT",
    "question": "Will BTC close above 100k on 2026-04-30?",
    "category": "crypto",
    "endDate": "2026-04-30T00:00:00Z",
    "description": "Coinbase BTC-USD daily close at 00:00 UTC.",
    "liquidity": "412345.67",
    "volume24hr": "82345.10",
    "spread": "1.5",
    "depth5c": "32100.0",
    "bestBid": "0.55",
    "bestAsk": "0.57",
    "clobTokenIds": json.dumps(["0xYES", "0xNO"]),
    "orderPriceMinTickSize": "0.01",
    "orderMinSize": "5.0",
    "feeRateBps": "200",
    "negRisk": False,
}


class TestParse:
    def test_typical_record(self) -> None:
        m = parse_gamma_market(SAMPLE)
        assert m.id == "0xCONDITION"
        assert m.event_id == "0xEVENT"
        assert m.yes_token_id == "0xYES"
        assert m.no_token_id == "0xNO"
        assert m.tick_size == 0.01
        assert m.fee_rate_bps == 200
        assert m.best_bid == 0.55 and m.best_ask == 0.57

    def test_token_ids_as_list(self) -> None:
        # Some Gamma responses ship the array unstringified
        raw = {**SAMPLE, "clobTokenIds": ["a", "b"]}
        m = parse_gamma_market(raw)
        assert m.yes_token_id == "a"
        assert m.no_token_id == "b"

    def test_missing_id_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_gamma_market({"question": "x"})

    def test_missing_optional_fields_default_safely(self) -> None:
        sparse = {"conditionId": "0xX", "question": "Q"}
        m = parse_gamma_market(sparse)
        assert m.id == "0xX"
        assert m.liquidity_usd == 0.0
        assert m.tick_size is None
        assert m.fee_rate_bps is None


@pytest.mark.asyncio
async def test_list_active_markets_calls_correct_endpoint() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.params)
        return httpx.Response(200, json=[SAMPLE, SAMPLE])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketGammaAdapter(client=client)
        markets = await adapter.list_active_markets(limit=50)

    assert seen["path"] == "/markets"
    assert "active=true" in seen["query"]
    assert "limit=50" in seen["query"]
    assert len(markets) == 2
    assert markets[0].id == "0xCONDITION"


@pytest.mark.asyncio
async def test_malformed_record_skipped_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[SAMPLE, {"junk": True}, SAMPLE])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketGammaAdapter(client=client)
        markets = await adapter.list_active_markets()

    # The bad record is silently skipped — a single malformed market never kills a scan tick.
    assert len(markets) == 2


@pytest.mark.asyncio
async def test_get_market_404_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketGammaAdapter(client=client)
        m = await adapter.get_market("nope")
    assert m is None
