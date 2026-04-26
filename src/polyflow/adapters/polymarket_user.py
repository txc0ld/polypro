"""Polymarket *user* read endpoints.

These endpoints surface positions, activity, and balances for a given wallet
address. They require only the wallet address — no signing — so we can wire
them up with the credentials currently provided in ``.env.local``.

Live order placement requires the full L2 key set (api_key + api_secret +
api_passphrase) plus the L1 private key for signing; that lives in a separate
``polymarket_clob_trade.py`` adapter that intentionally remains a stub until
the missing credentials are provided.
"""

from __future__ import annotations

from typing import Any

import httpx

_DATA_BASE = "https://data-api.polymarket.com"


class PolymarketUserAdapter:
    """Async read-only client for the Polymarket Data API."""

    def __init__(
        self,
        *,
        wallet_address: str,
        base_url: str = _DATA_BASE,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not wallet_address:
            raise ValueError("wallet_address is required")
        self._wallet = wallet_address.lower()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def __aenter__(self) -> "PolymarketUserAdapter":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def positions(self) -> list[dict[str, Any]]:
        """Open positions for the wallet."""
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            resp = await client.get(
                f"{self._base_url}/positions",
                params={"user": self._wallet},
            )
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns:
                await client.aclose()
        return data if isinstance(data, list) else data.get("positions", [])

    async def activity(self, *, limit: int = 50) -> list[dict[str, Any]]:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            resp = await client.get(
                f"{self._base_url}/activity",
                params={"user": self._wallet, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns:
                await client.aclose()
        return data if isinstance(data, list) else data.get("activity", [])
