"""Gamma API adapter (PRD §7.1).

Reads market/event metadata: questions, categories, close times, descriptions,
tags. No order placement.
"""

from __future__ import annotations

from typing import Protocol

from ..types import Market


class GammaAdapter(Protocol):
    """Anything that can produce a list of currently-open Polymarket Markets."""

    async def list_active_markets(self, *, limit: int = 200) -> list[Market]: ...
    async def get_market(self, market_id: str) -> Market | None: ...


class StubGammaAdapter:
    """In-memory adapter for tests / observe mode without network access."""

    def __init__(self, markets: list[Market] | None = None) -> None:
        self._markets: dict[str, Market] = {m.id: m for m in (markets or [])}

    async def list_active_markets(self, *, limit: int = 200) -> list[Market]:
        return list(self._markets.values())[:limit]

    async def get_market(self, market_id: str) -> Market | None:
        return self._markets.get(market_id)

    def upsert(self, market: Market) -> None:
        self._markets[market.id] = market
