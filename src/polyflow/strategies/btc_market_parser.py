"""Parse Polymarket question text to extract crypto threshold + asset.

Accepts the standard Polymarket phrasing for BTC, ETH, and SOL markets:

  - "Will Bitcoin reach $X by [date]?"
  - "Will BTC close above $X on [date]?"
  - "Will ETH be above $X by [date]?"
  - "Will Solana hit $X this week?"

We extract the asset symbol, the dollar threshold, and a direction. The
market's ``close_time`` carries the resolution timestamp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone


_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)([kKmM]?)")
_THRESHOLD_TERMS = ("above", "below", "over", "under", "reach", "hit", "exceed", "close")

# Asset detection. Word-boundary patterns so "ETH" doesn't match inside
# "ethnicity" / etc. Order matters for fall-through readability.
_ASSET_PATTERNS = (
    ("BTC",    re.compile(r"\b(?:bitcoin|btc)\b", re.IGNORECASE)),
    ("ETH",    re.compile(r"\b(?:ethereum|ether|eth)\b", re.IGNORECASE)),
    ("SOL",    re.compile(r"\b(?:solana|sol)\b", re.IGNORECASE)),
    # Commodities — per the EV-harvester target shortlist (gold/oil markets
    # have clean external truth via Yahoo Finance front-month futures).
    ("WTI",    re.compile(r"\b(?:wti|crude\s*oil|oil)\b", re.IGNORECASE)),
    ("GOLD",   re.compile(r"\b(?:gold|xau)\b", re.IGNORECASE)),
    ("SILVER", re.compile(r"\b(?:silver|xag)\b", re.IGNORECASE)),
    ("COPPER", re.compile(r"\bcopper\b", re.IGNORECASE)),
)


def _to_number(raw: str, suffix: str) -> float:
    val = float(raw.replace(",", ""))
    if suffix.lower() == "k":
        val *= 1_000
    elif suffix.lower() == "m":
        val *= 1_000_000
    return val


@dataclass(frozen=True)
class BtcThresholdParse:
    """Parsed crypto threshold market.

    Name retained for back-compat with existing imports; the ``asset``
    field distinguishes BTC / ETH / SOL.
    """

    price_to_beat: float
    direction: str          # 'above' or 'below'
    asset: str = "BTC"      # 'BTC' | 'ETH' | 'SOL'


def _detect_asset(question: str) -> str | None:
    for symbol, pattern in _ASSET_PATTERNS:
        if pattern.search(question):
            return symbol
    return None


def parse_btc_threshold(question: str) -> BtcThresholdParse | None:
    """Return parsed threshold for any supported crypto, or None."""
    if not question:
        return None
    asset = _detect_asset(question)
    if asset is None:
        return None
    lowered = question.lower()
    if not any(term in lowered for term in _THRESHOLD_TERMS):
        return None

    match = _PRICE_RE.search(question)
    if not match:
        return None
    price = _to_number(match.group(1), match.group(2))
    if price <= 0 or price > 10_000_000:
        return None

    if any(term in lowered for term in ("below", "under")):
        direction = "below"
    else:
        direction = "above"

    return BtcThresholdParse(asset=asset, price_to_beat=price, direction=direction)


def seconds_to_close(close_time: datetime | None) -> float:
    if close_time is None:
        return 0.0
    if close_time.tzinfo is None:
        close_time = close_time.replace(tzinfo=timezone.utc)
    return max(0.0, (close_time - datetime.now(timezone.utc)).total_seconds())
