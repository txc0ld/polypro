"""End-to-end test of the authenticated trade adapter (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from polyflow.adapters.polymarket_clob_trade import PolymarketCLOBTradeAdapter
from polyflow.secrets import Credentials


def _full_creds() -> Credentials:
    return Credentials(
        api_key="550e8400-e29b-41d4-a716-446655440000",
        api_secret="dGVzdC1zZWNyZXQ=",  # base64("test-secret")
        api_passphrase="passphrase",
        private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        wallet_address="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    )


def test_constructor_rejects_partial_creds() -> None:
    partial = Credentials(
        api_key="k", api_secret=None, api_passphrase=None, private_key=None, wallet_address="0xabc"
    )
    with pytest.raises(ValueError):
        PolymarketCLOBTradeAdapter(credentials=partial)


@pytest.mark.asyncio
async def test_get_open_orders_attaches_l2_headers() -> None:
    seen: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = {k.lower(): v for k, v in request.headers.items()}
        seen["path"] = request.url.path
        return httpx.Response(200, json=[{"id": "o1"}])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketCLOBTradeAdapter(credentials=_full_creds(), client=client)
        rows = await adapter.get_open_orders()

    assert rows == [{"id": "o1"}]
    assert seen["path"] == "/orders"
    h = seen["headers"]
    assert h["poly_api_key"].startswith("550e8400")
    assert h["poly_passphrase"] == "passphrase"
    assert h["poly_signature"]
    assert h["poly_timestamp"]
    assert h["poly_address"].lower() == _full_creds().wallet_address.lower()


@pytest.mark.asyncio
async def test_place_order_signs_and_posts() -> None:
    pytest.importorskip("eth_account")
    from polyflow.types import OrderPayload, OrderType, Side, Strategy

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        seen["body"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"orderID": "ok-123", "status": "matched"})

    transport = httpx.MockTransport(handler)
    payload = OrderPayload(
        tokenID="42",
        side=Side.BUY,
        price="0.55",
        size="10",
        orderType=OrderType.GTC,
        strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
        marketId="m",
        eventId=None,
        maxPositionAfterFill="10",
        clientOrderId="abc",
    )

    creds = _full_creds()
    # Signature type 1 (POLY_PROXY) requires a funder address.
    creds = creds.__class__(
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        api_passphrase=creds.api_passphrase,
        private_key=creds.private_key,
        wallet_address=creds.wallet_address,
        funder_address="0x1111111111111111111111111111111111111111",
    )

    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketCLOBTradeAdapter(credentials=creds, client=client)
        result = await adapter.place_order(payload)

    assert seen["path"] == "/order"
    assert seen["method"] == "POST"
    assert result["orderID"] == "ok-123"

    import json as _json
    body = _json.loads(seen["body"])  # type: ignore[arg-type]
    assert body["order"]["maker"].lower() == "0x1111111111111111111111111111111111111111"
    assert body["order"]["signer"].lower() == creds.wallet_address.lower()
    assert body["order"]["signatureType"] == 1
    # 10 tokens at 0.55 → 5_500_000 USDC base units (6 decimals)
    assert body["order"]["makerAmount"] == "5500000"
    assert body["order"]["takerAmount"] == "10000000"


@pytest.mark.asyncio
async def test_get_token_balance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"token_id": "t-yes", "balance": "12.5"},
                {"token_id": "t-no", "balance": "0"},
            ],
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PolymarketCLOBTradeAdapter(credentials=_full_creds(), client=client)
        balance = await adapter.get_token_balance("t-yes")
        zero = await adapter.get_token_balance("t-missing")

    assert balance == 12.5
    assert zero == 0.0
