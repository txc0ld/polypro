"""Multi-source BTC spot price feed.

Pulls BTC/USD from CoinGecko + Binance + Coinbase (all public, no API key
required), keeps a rolling window for realized-volatility computation, and
exposes a ``BtcThresholdSnapshot`` builder used by the BTC threshold
strategy.

Feed disagreement is computed as the spread between min and max source
prices, expressed in basis points of the median. The btc_threshold strategy
refuses if disagreement > 8 bps — which means we need *all three* feeds to
agree closely.
"""

from __future__ import annotations

import math
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Iterable

import httpx

from ..strategies.btc_threshold import BtcThresholdSnapshot

SECONDS_PER_YEAR = 31_536_000.0


@dataclass(frozen=True)
class _SourceQuote:
    source: str
    url: str
    price_usd: float
    fetched_at: datetime


@dataclass
class BtcPriceFeed:
    """Aggregates BTC spot prices from multiple public endpoints."""

    history_seconds: int = 600
    timeout_seconds: float = 5.0
    _history: deque[tuple[float, float]] = field(default_factory=deque, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    async def fetch(self, *, client: httpx.AsyncClient | None = None) -> list[_SourceQuote]:
        """Pull a fresh snapshot from each source. Skips a source on any HTTP error."""
        owns = client is None
        client = client or httpx.AsyncClient(timeout=self.timeout_seconds)
        out: list[_SourceQuote] = []
        try:
            for source, url, parser in self._endpoints():
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    raw_price = parser(resp.json())
                    price = float(raw_price)
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    continue
                if price <= 0:
                    continue
                out.append(
                    _SourceQuote(
                        source=source,
                        url=url,
                        price_usd=price,
                        fetched_at=datetime.now(timezone.utc),
                    )
                )
        finally:
            if owns:
                await client.aclose()

        # Record the median for vol computation
        if out:
            mid = statistics.median(q.price_usd for q in out)
            with self._lock:
                self._history.append((time.time(), mid))
                self._evict_stale()
        return out

    def _endpoints(self) -> Iterable[tuple[str, str, callable]]:
        return (
            (
                "coingecko",
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
                lambda data: data["bitcoin"]["usd"],
            ),
            (
                "binance",
                "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
                lambda data: data["price"],
            ),
            (
                "coinbase",
                "https://api.coinbase.com/v2/prices/BTC-USD/spot",
                lambda data: data["data"]["amount"],
            ),
        )

    def _evict_stale(self) -> None:
        cutoff = time.time() - self.history_seconds
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

    def realized_volatility_annualized(self) -> float | None:
        """Compute realized vol from the rolling price history.

        Uses log-returns over the window, annualized. Returns None when fewer
        than 2 samples are available.
        """
        with self._lock:
            samples = list(self._history)
        if len(samples) < 2:
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


def disagreement_bps(quotes: list[_SourceQuote]) -> float:
    """Spread between min and max source prices in basis points of median."""
    if len(quotes) < 2:
        return 0.0
    prices = [q.price_usd for q in quotes]
    median = statistics.median(prices)
    if median <= 0:
        return 0.0
    return ((max(prices) - min(prices)) / median) * 10_000


@dataclass(frozen=True)
class FeedSummary:
    median_price_usd: float
    sources: tuple[str, ...]
    disagreement_bps: float
    fetched_at: datetime


def summarize(quotes: list[_SourceQuote]) -> FeedSummary | None:
    if not quotes:
        return None
    return FeedSummary(
        median_price_usd=statistics.median(q.price_usd for q in quotes),
        sources=tuple(q.source for q in quotes),
        disagreement_bps=disagreement_bps(quotes),
        fetched_at=max(q.fetched_at for q in quotes),
    )


def build_snapshot(
    *,
    summary: FeedSummary,
    realized_vol: float,
    price_to_beat: float,
    seconds_to_resolution: float,
    oracle_latency_seconds: float = 0.0,
    drift_adjustment: float = 0.0,
) -> BtcThresholdSnapshot:
    """Wrap a feed summary into the strategy's input snapshot."""
    return BtcThresholdSnapshot(
        source_name=",".join(summary.sources),
        source_url="multi:" + ",".join(summary.sources),
        fetched_at=summary.fetched_at,
        price_to_beat=price_to_beat,
        btc_spot=summary.median_price_usd,
        seconds_to_resolution=seconds_to_resolution,
        realized_volatility_annualized=realized_vol,
        feed_disagreement_bps=summary.disagreement_bps,
        oracle_latency_seconds=oracle_latency_seconds,
        drift_adjustment=drift_adjustment,
    )
