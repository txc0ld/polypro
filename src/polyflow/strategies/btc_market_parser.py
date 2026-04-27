"""Parse Polymarket question text to extract BTC threshold + resolution time.

Polymarket BTC threshold questions follow predictable patterns:

  - "Will Bitcoin reach $X by [date]?"
  - "Will BTC close above $X on [date]?"
  - "Bitcoin above $X by [date]?"
  - "BTC > $X by [date]?"

We extract the dollar threshold and (optionally) a resolution time. If
``close_time`` on the market is set we use that; otherwise we refuse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone


_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)([kKmM]?)")
_BTC_TERMS = ("bitcoin", "btc")
_THRESHOLD_TERMS = ("above", "below", "over", "under", "reach", "hit", "exceed", "close")


def _to_number(raw: str, suffix: str) -> float:
    val = float(raw.replace(",", ""))
    if suffix.lower() == "k":
        val *= 1_000
    elif suffix.lower() == "m":
        val *= 1_000_000
    return val


@dataclass(frozen=True)
class BtcThresholdParse:
    price_to_beat: float
    direction: str  # 'above' or 'below'


def parse_btc_threshold(question: str) -> BtcThresholdParse | None:
    """Return parsed threshold, or None if the question isn't a BTC threshold market."""
    if not question:
        return None
    lowered = question.lower()
    if not any(term in lowered for term in _BTC_TERMS):
        return None
    if not any(term in lowered for term in _THRESHOLD_TERMS):
        return None

    match = _PRICE_RE.search(question)
    if not match:
        return None
    price = _to_number(match.group(1), match.group(2))
    if price <= 0 or price > 10_000_000:
        return None

    # Direction: default 'above' when ambiguous (most BTC threshold markets are upside).
    if any(term in lowered for term in ("below", "under")):
        direction = "below"
    else:
        direction = "above"

    return BtcThresholdParse(price_to_beat=price, direction=direction)


def seconds_to_close(close_time: datetime | None) -> float:
    if close_time is None:
        return 0.0
    if close_time.tzinfo is None:
        close_time = close_time.replace(tzinfo=timezone.utc)
    return max(0.0, (close_time - datetime.now(timezone.utc)).total_seconds())
