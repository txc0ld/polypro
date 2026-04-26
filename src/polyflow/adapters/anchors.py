"""External probability anchor adapters (sportsbooks, Kalshi, polling, crypto spot).

These are deliberately a Protocol + simple file-based fallback. Production
implementations plug regulated odds APIs / Kalshi / public forecast APIs in.
The strategy module consumes only the normalized ``OddsAnchor`` records.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ..strategies.external_odds_divergence import OddsAnchor


class AnchorAdapter(Protocol):
    async def fetch(self, market_id: str) -> list[OddsAnchor]: ...


class FileAnchorAdapter:
    """Reads a JSON file mapping ``market_id -> [{source,odds_yes,odds_no,...}]``.

    Useful for tests and for one-off operator-curated anchors before live odds
    APIs are wired in.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    async def fetch(self, market_id: str) -> list[OddsAnchor]:
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
