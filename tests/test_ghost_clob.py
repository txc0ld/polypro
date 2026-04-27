"""Ghost-mode CLOB adapter tests (Protocol §5)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from polyflow.adapters.ghost_clob import GhostCLOBAdapter, summarize_ghost_log
from polyflow.adapters.polymarket_clob_trade import PolymarketCLOBTradeAdapter
from polyflow.secrets import Credentials
from polyflow.types import OrderPayload, OrderType, Side, Strategy


def _full_creds() -> Credentials:
    return Credentials(
        api_key="key", api_secret="dGVzdC1zZWNyZXQ=", api_passphrase="pass",
        private_key="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        wallet_address="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        funder_address="0x1111111111111111111111111111111111111111",
    )


def _payload() -> OrderPayload:
    return OrderPayload(
        tokenID="42", side=Side.BUY, price="0.55", size="10",
        orderType=OrderType.GTC, strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
        marketId="m1", eventId=None, maxPositionAfterFill="10", clientOrderId="abc",
    )


@pytest.mark.asyncio
async def test_zero_balance_reported(tmp_path: Path) -> None:
    pytest.importorskip("eth_account")

    def handler(request: httpx.Request) -> httpx.Response:
        # The wrapped adapter would call /balance-allowances; ghost overrides → no call.
        return httpx.Response(500, json={"error": "should not be called"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        wrapped = PolymarketCLOBTradeAdapter(credentials=_full_creds(), client=client)
        ghost = GhostCLOBAdapter(wrapped=wrapped, log_path=tmp_path / "ghost.jsonl")
        balance = await ghost.get_token_balance("anything")
    assert balance == 0.0


@pytest.mark.asyncio
async def test_place_order_records_4xx_failure(tmp_path: Path) -> None:
    pytest.importorskip("eth_account")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "insufficient balance"})

    transport = httpx.MockTransport(handler)
    log_path = tmp_path / "ghost.jsonl"
    async with httpx.AsyncClient(transport=transport) as client:
        wrapped = PolymarketCLOBTradeAdapter(credentials=_full_creds(), client=client)
        ghost = GhostCLOBAdapter(wrapped=wrapped, log_path=log_path)
        result = await ghost.place_order(_payload())

    assert result["rejected"] is True
    assert result["status"] == 400
    failures = ghost.failures
    assert len(failures) == 1
    assert failures[0].reason == "HTTP_400"
    assert "insufficient balance" in failures[0].detail

    rep = summarize_ghost_log(log_path)
    assert rep.total == 1
    assert rep.by_reason["HTTP_400"] == 1


@pytest.mark.asyncio
async def test_summary_handles_missing_file(tmp_path: Path) -> None:
    rep = summarize_ghost_log(tmp_path / "does-not-exist.jsonl")
    assert rep.total == 0
