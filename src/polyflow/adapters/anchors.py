"""External probability anchor adapters (sportsbooks, Kalshi, polling, crypto spot).

The strategy module consumes only normalized ``OddsAnchor`` records. Two
production-grade adapters live here:

  - ``FileAnchorAdapter`` — operator-curated JSON, useful for tests and for
    seeding anchors before a live odds API is configured.
  - ``_OddsAPIAnchorAdapter`` — wraps ``OddsAPIClient`` to match Polymarket
    questions against live sportsbook events.

Both implement the same ``AnchorAdapter`` protocol: ``fetch(market)`` returns
a list of anchors that the divergence strategy can consume directly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ..strategies.external_odds_divergence import OddsAnchor
from ..types import Market


class AnchorAdapter(Protocol):
    async def fetch(self, market: Market) -> list[OddsAnchor]: ...


class FileAnchorAdapter:
    """Reads a JSON file mapping ``market_id -> [{source, yes_decimal_odds, …}]``."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    async def fetch(self, market: Market | str) -> list[OddsAnchor]:
        market_id = market.id if isinstance(market, Market) else market
        if not self._path.exists():
            return []
        data = json.loads(self._path.read_text(encoding="utf-8"))
        records = data.get(market_id) or []
        out: list[OddsAnchor] = []
        for r in records:
            ts = r.get("fetched_at")
            try:
                fetched_at = (
                    datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
                )
            except ValueError:
                fetched_at = datetime.now(timezone.utc)
            out.append(
                OddsAnchor.from_decimal_odds(
                    source_name=r["source"],
                    fetched_at=fetched_at,
                    yes_decimal_odds=float(r["yes_decimal_odds"]),
                    no_decimal_odds=float(r["no_decimal_odds"]),
                    reliability=float(r.get("reliability", 0.80)),
                    settlement_match=bool(r.get("settlement_match", True)),
                )
            )
        return out


class _OddsAPIAnchorAdapter:
    """Adapter shim over ``OddsAPIClient`` matching against the Polymarket question."""

    def __init__(self, client) -> None:  # OddsAPIClient (avoid circular import)
        self._client = client

    async def fetch(self, market: Market | str) -> list[OddsAnchor]:
        if not isinstance(market, Market):
            return []
        return await self._client.anchors_for_market(market.question)
