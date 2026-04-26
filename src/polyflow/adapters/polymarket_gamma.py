"""Polymarket Gamma HTTP adapter.

Public endpoint: https://gamma-api.polymarket.com — no credentials required for
discovery / read. We only consume the documented fields and cross-reference
with the CLOB read adapter for tick size, fee rate, and order book depth.

Design constraints:
- never block the event loop; the adapter is async (httpx.AsyncClient)
- all parsing is defensive; fields the API may omit map to ``None``
- the deterministic core uses only ``Market`` instances, so this file is the
  *only* place gamma-shape JSON exists
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ..types import Market

_GAMMA_BASE = "https://gamma-api.polymarket.com"


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Gamma returns Z-suffixed UTC; fromisoformat in 3.11+ handles +00:00 only
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _safe_float(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def parse_gamma_market(raw: dict[str, Any]) -> Market:
    """Convert one Gamma market record to our ``Market`` type.

    Gamma's schema occasionally renames fields; we accept the common variants.
    """
    market_id = _safe_str(raw.get("conditionId") or raw.get("id"))
    if not market_id:
        raise ValueError("gamma record missing conditionId/id")

    token_ids = raw.get("clobTokenIds") or raw.get("tokenIds") or []
    if isinstance(token_ids, str):
        # Gamma sometimes ships as a JSON-encoded string
        import json

        try:
            token_ids = json.loads(token_ids)
        except json.JSONDecodeError:
            token_ids = []

    yes_token = token_ids[0] if len(token_ids) > 0 else None
    no_token = token_ids[1] if len(token_ids) > 1 else None

    return Market(
        id=market_id,
        event_id=_safe_str(raw.get("eventId") or raw.get("event_id")),
        question=_safe_str(raw.get("question")) or "(unknown)",
        category=_safe_str(raw.get("category")),
        close_time=_parse_iso(raw.get("endDate") or raw.get("end_date")),
        resolution_rules=_safe_str(raw.get("description") or raw.get("resolutionSource")),
        liquidity_usd=_safe_float(raw.get("liquidity") or raw.get("liquidityNum"), 0.0) or 0.0,
        volume_24h_usd=_safe_float(raw.get("volume24hr") or raw.get("volume24Hr"), 0.0) or 0.0,
        spread_pct=_safe_float(raw.get("spread"), 100.0) or 100.0,
        depth_within_5c_usd=_safe_float(raw.get("depth5c"), 0.0) or 0.0,
        best_bid=_safe_float(raw.get("bestBid")),
        best_ask=_safe_float(raw.get("bestAsk")),
        yes_token_id=_safe_str(yes_token),
        no_token_id=_safe_str(no_token),
        tick_size=_safe_float(raw.get("orderPriceMinTickSize") or raw.get("tickSize")),
        min_order_size=_safe_float(raw.get("orderMinSize") or raw.get("minOrderSize")),
        fee_rate_bps=_safe_float(raw.get("feeRateBps") or raw.get("makerFeeBps")),
        neg_risk=bool(raw.get("negRisk", False)),
        market_quality=0.0,  # filled in by the scanner
        resolution_risk=_safe_float(raw.get("resolutionRiskPrior"), 0.20) or 0.20,
    )


class PolymarketGammaAdapter:
    """Async HTTP adapter over the Polymarket Gamma read API."""

    def __init__(
        self,
        *,
        base_url: str = _GAMMA_BASE,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def __aenter__(self) -> "PolymarketGammaAdapter":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_active_markets(self, *, limit: int = 200) -> list[Market]:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            resp = await client.get(
                f"{self._base_url}/markets",
                params={"active": "true", "closed": "false", "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns:
                await client.aclose()

        markets: list[Market] = []
        records = data if isinstance(data, list) else data.get("markets", [])
        for raw in records:
            try:
                markets.append(parse_gamma_market(raw))
            except Exception:  # noqa: BLE001
                # Defensive: a single malformed record never kills a scan tick.
                continue
        return markets

    async def get_market(self, market_id: str) -> Market | None:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            resp = await client.get(f"{self._base_url}/markets/{market_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return parse_gamma_market(resp.json())
        finally:
            if owns:
                await client.aclose()
