"""Watchlist — the set of approved markets the runtime monitors continuously.

A watchlist entry is added when ``market_scanner`` approves a market and is
removed when:
  - the market closes,
  - the scanner re-classifies it as no-longer-tradable, or
  - the operator manually evicts it.

This module is purely in-memory; persistence (markets table) is handled by
``SQLiteStore``.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .types import Market


@dataclass
class WatchlistEntry:
    market: Market
    added_at: datetime
    last_seen_at: datetime
    quality: float
    skip_reasons: tuple[str, ...] = ()


@dataclass
class Watchlist:
    _entries: dict[str, WatchlistEntry] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def upsert(self, market: Market, *, quality: float | None = None) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            existing = self._entries.get(market.id)
            self._entries[market.id] = WatchlistEntry(
                market=market,
                added_at=existing.added_at if existing else now,
                last_seen_at=now,
                quality=quality if quality is not None else (
                    existing.quality if existing else market.market_quality
                ),
            )

    def evict(self, market_id: str, *, reasons: tuple[str, ...] = ()) -> None:
        with self._lock:
            entry = self._entries.pop(market_id, None)
            if entry is not None and reasons:
                # Keep a short tombstone entry for diagnostics — quality 0, skip_reasons populated.
                self._entries[market_id] = WatchlistEntry(
                    market=entry.market,
                    added_at=entry.added_at,
                    last_seen_at=datetime.now(timezone.utc),
                    quality=0.0,
                    skip_reasons=reasons,
                )

    def active(self) -> list[Market]:
        with self._lock:
            return [e.market for e in self._entries.values() if e.quality > 0]

    def __len__(self) -> int:
        with self._lock:
            return sum(1 for e in self._entries.values() if e.quality > 0)

    def get(self, market_id: str) -> WatchlistEntry | None:
        with self._lock:
            return self._entries.get(market_id)
