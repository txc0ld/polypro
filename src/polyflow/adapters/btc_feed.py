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


# Per-asset endpoint config: (asset_symbol, [(source, url, parser_fn), ...])
_ASSET_ENDPOINTS: dict[str, tuple[tuple[str, str, callable], ...]] = {
    "BTC": (
        ("coingecko", "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd", lambda d: d["bitcoin"]["usd"]),
        ("binance", "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", lambda d: d["price"]),
        ("coinbase", "https://api.coinbase.com/v2/prices/BTC-USD/spot", lambda d: d["data"]["amount"]),
    ),
    "ETH": (
        ("coingecko", "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd", lambda d: d["ethereum"]["usd"]),
        ("binance", "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT", lambda d: d["price"]),
        ("coinbase", "https://api.coinbase.com/v2/prices/ETH-USD/spot", lambda d: d["data"]["amount"]),
    ),
    "SOL": (
        ("coingecko", "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", lambda d: d["solana"]["usd"]),
        ("binance", "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT", lambda d: d["price"]),
        ("coinbase", "https://api.coinbase.com/v2/prices/SOL-USD/spot", lambda d: d["data"]["amount"]),
    ),
}

# Binance USD-M perpetual futures premium index — gives spot/perp basis +
# last funding rate + mark price. Per scalp doctrine: spot/perp divergence
# is one of the cleanest BTC scalping signals.
_PERP_PREMIUM_ENDPOINTS = {
    "BTC": "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT",
    "ETH": "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT",
    "SOL": "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=SOLUSDT",
}


@dataclass
class BtcPriceFeed:
    """Multi-asset crypto spot price feed.

    Name kept for back-compat. Now supports BTC / ETH / SOL via the
    ``asset`` parameter on ``fetch``. Per-asset rolling history powers the
    realized-volatility calculation.
    """

    history_seconds: int = 600
    timeout_seconds: float = 5.0
    asset: str = "BTC"
    _history: dict[str, deque[tuple[float, float]]] = field(default_factory=dict, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    async def fetch(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        asset: str | None = None,
    ) -> list[_SourceQuote]:
        """Pull a fresh snapshot for the given asset (default BTC).

        Skips any source that returns an HTTP error or unparseable payload.
        """
        target = (asset or self.asset).upper()
        endpoints = _ASSET_ENDPOINTS.get(target)
        if not endpoints:
            return []

        owns = client is None
        client = client or httpx.AsyncClient(timeout=self.timeout_seconds)
        out: list[_SourceQuote] = []
        try:
            for source, url, parser in endpoints:
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
                        source=f"{source}:{target}",
                        url=url,
                        price_usd=price,
                        fetched_at=datetime.now(timezone.utc),
                    )
                )
        finally:
            if owns:
                await client.aclose()

        # Record the median into per-asset history for vol computation.
        if out:
            mid = statistics.median(q.price_usd for q in out)
            with self._lock:
                self._history.setdefault(target, deque()).append((time.time(), mid))
                self._evict_stale(target)
        return out

    def _evict_stale(self, asset: str | None = None) -> None:
        cutoff = time.time() - self.history_seconds
        targets = [asset] if asset else list(self._history.keys())
        for tgt in targets:
            history = self._history.get(tgt)
            if history is None:
                continue
            while history and history[0][0] < cutoff:
                history.popleft()

    def momentum(self, *, asset: str | None = None, window_seconds: float = 300.0) -> MomentumSnapshot | None:
        """Compute price velocity (bps/min) and range (bps) over the last
        ``window_seconds`` for the given asset. Returns None when fewer than
        2 samples fall inside the window.
        """
        target = (asset or self.asset).upper()
        with self._lock:
            samples = list(self._history.get(target, ()))
        if len(samples) < 2:
            return None
        cutoff = time.time() - window_seconds
        window = [(t, p) for (t, p) in samples if t >= cutoff and p > 0]
        if len(window) < 2:
            return None
        prices = [p for _t, p in window]
        first_t, first_p = window[0]
        last_t, last_p = window[-1]
        elapsed = max(last_t - first_t, 1.0)
        # bps/min = (last - first) / first × 10000 / minutes
        bps_per_min = ((last_p - first_p) / first_p) * 10_000 * (60.0 / elapsed)
        high = max(prices)
        low = min(prices)
        range_bps = ((high - low) / first_p) * 10_000 if first_p > 0 else 0.0
        return MomentumSnapshot(
            window_seconds=elapsed,
            n_samples=len(window),
            velocity_bps_per_min=bps_per_min,
            range_bps=range_bps,
            high_usd=high,
            low_usd=low,
        )

    def realized_volatility_annualized(self, asset: str | None = None) -> float | None:
        """Compute realized vol from the rolling price history for the asset.

        Uses log-returns over the window, annualized. Returns None when fewer
        than 3 samples are available (need 2 returns for pstdev).
        """
        target = (asset or self.asset).upper()
        with self._lock:
            samples = list(self._history.get(target, ()))
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
class PerpSnapshot:
    """Binance USD-M perp basis + funding for the asset."""

    mark_price: float
    index_price: float
    funding_rate: float           # last funding rate, fraction (e.g. 0.0001 = 1bp)
    next_funding_time_ms: int
    fetched_at: datetime

    @property
    def basis_bps(self) -> float:
        if self.index_price <= 0:
            return 0.0
        return ((self.mark_price - self.index_price) / self.index_price) * 10_000


@dataclass(frozen=True)
class MomentumSnapshot:
    """Short-window price velocity + range (wick) features.

    Two scalp setups consume this:
      - "Spot breaks level" → if velocity_bps_per_min > +X and Polymarket
        price for the YES side has not repriced, buy YES.
      - "Large wick → market overreacts" → if range_bps over the recent
        window is large but velocity has flattened, fade the extreme.
    """

    window_seconds: float
    n_samples: int
    velocity_bps_per_min: float
    range_bps: float
    high_usd: float
    low_usd: float


@dataclass(frozen=True)
class FeedSummary:
    median_price_usd: float
    sources: tuple[str, ...]
    disagreement_bps: float
    fetched_at: datetime
    perp: PerpSnapshot | None = None
    momentum: MomentumSnapshot | None = None


def summarize(
    quotes: list[_SourceQuote],
    *,
    perp: PerpSnapshot | None = None,
    momentum: MomentumSnapshot | None = None,
) -> FeedSummary | None:
    if not quotes:
        return None
    return FeedSummary(
        median_price_usd=statistics.median(q.price_usd for q in quotes),
        sources=tuple(q.source for q in quotes),
        disagreement_bps=disagreement_bps(quotes),
        fetched_at=max(q.fetched_at for q in quotes),
        perp=perp,
        momentum=momentum,
    )


async def fetch_perp_snapshot(
    asset: str, *, client: httpx.AsyncClient | None = None, timeout_seconds: float = 5.0
) -> PerpSnapshot | None:
    url = _PERP_PREMIUM_ENDPOINTS.get(asset.upper())
    if not url:
        return None
    owns = client is None
    client = client or httpx.AsyncClient(timeout=timeout_seconds)
    try:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
    finally:
        if owns:
            await client.aclose()

    try:
        return PerpSnapshot(
            mark_price=float(data["markPrice"]),
            index_price=float(data["indexPrice"]),
            funding_rate=float(data.get("lastFundingRate") or 0.0),
            next_funding_time_ms=int(data.get("nextFundingTime") or 0),
            fetched_at=datetime.now(timezone.utc),
        )
    except (KeyError, TypeError, ValueError):
        return None


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
