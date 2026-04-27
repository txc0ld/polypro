"""Commodities price feed (WTI crude, gold, silver, copper).

Yahoo Finance's public chart endpoint is free, no API key, and returns
front-month futures prices on a 1-min cadence with ~15-min delay during
regular hours and live during electronic sessions:

  https://query1.finance.yahoo.com/v8/finance/chart/CL=F   (WTI crude)
  https://query1.finance.yahoo.com/v8/finance/chart/GC=F   (gold)
  https://query1.finance.yahoo.com/v8/finance/chart/SI=F   (silver)
  https://query1.finance.yahoo.com/v8/finance/chart/HG=F   (copper)

We pull a 1-day / 1-min interval window and use the most recent close.
Per-asset rolling history powers a separate realized-vol calculation,
mirroring the BTC feed.
"""

from __future__ import annotations

import math
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock

import httpx


_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SECONDS_PER_YEAR = 31_536_000.0

# Map asset symbol → (yahoo_symbol, display_name)
_ASSETS = {
    "WTI":    ("CL=F", "WTI Crude Oil"),
    "OIL":    ("CL=F", "WTI Crude Oil"),     # alias
    "BRENT":  ("BZ=F", "Brent Crude Oil"),
    "GOLD":   ("GC=F", "Gold"),
    "XAU":    ("GC=F", "Gold"),
    "SILVER": ("SI=F", "Silver"),
    "XAG":    ("SI=F", "Silver"),
    "COPPER": ("HG=F", "Copper"),
}


@dataclass(frozen=True)
class CommodityQuote:
    asset: str
    yahoo_symbol: str
    price_usd: float
    fetched_at: datetime


@dataclass
class CommoditiesFeed:
    timeout_seconds: float = 8.0
    history_seconds: int = 6 * 3600  # 6 hours; commodities are slower than crypto
    _history: dict[str, deque[tuple[float, float]]] = field(default_factory=dict, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    async def fetch(
        self,
        asset: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> CommodityQuote | None:
        target = asset.upper()
        symbol_pair = _ASSETS.get(target)
        if symbol_pair is None:
            return None
        yahoo_symbol, _name = symbol_pair

        owns = client is None
        client = client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "Mozilla/5.0 (polyflow)"},
        )
        try:
            try:
                resp = await client.get(
                    _YAHOO_CHART.format(symbol=yahoo_symbol),
                    params={"interval": "1m", "range": "1d"},
                )
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                return None
        finally:
            if owns:
                await client.aclose()

        try:
            result = data["chart"]["result"][0]
            closes = result["indicators"]["quote"][0].get("close") or []
            timestamps = result.get("timestamp") or []
        except (KeyError, IndexError, TypeError):
            return None

        # Walk back from the end for the latest non-null close.
        last_price = None
        last_ts = None
        for price, ts in zip(reversed(closes), reversed(timestamps)):
            if price is None:
                continue
            try:
                last_price = float(price)
                last_ts = float(ts)
                break
            except (TypeError, ValueError):
                continue
        if last_price is None or last_price <= 0:
            return None

        with self._lock:
            self._history.setdefault(target, deque()).append((last_ts or time.time(), last_price))
            self._evict_stale(target)

        return CommodityQuote(
            asset=target,
            yahoo_symbol=yahoo_symbol,
            price_usd=last_price,
            fetched_at=datetime.fromtimestamp(last_ts, tz=timezone.utc) if last_ts else datetime.now(timezone.utc),
        )

    def _evict_stale(self, asset: str | None = None) -> None:
        cutoff = time.time() - self.history_seconds
        targets = [asset] if asset else list(self._history.keys())
        for tgt in targets:
            history = self._history.get(tgt)
            if history is None:
                continue
            while history and history[0][0] < cutoff:
                history.popleft()

    def realized_volatility_annualized(self, asset: str) -> float | None:
        target = asset.upper()
        with self._lock:
            samples = list(self._history.get(target, ()))
        if len(samples) < 3:
            return None
        returns: list[float] = []
        for (t1, p1), (t2, p2) in zip(samples, samples[1:]):
            if p1 <= 0 or p2 <= 0:
                continue
            dt = max(t2 - t1, 1.0)
            returns.append(math.log(p2 / p1) * math.sqrt(SECONDS_PER_YEAR / dt))
        if len(returns) < 2:
            return None
        return statistics.pstdev(returns)
