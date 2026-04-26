"""Market Scanner skill — deterministic hard filters (PRD §6, §14.1).

This is the *first* refusal layer. Most markets must die here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .config import MarketFilters
from .types import Market

# Categories the bot must refuse outright.
FORBIDDEN_CATEGORIES: frozenset[str] = frozenset(
    {"war", "death", "terror", "assassination"}
)


@dataclass(frozen=True)
class ScanDecision:
    market_id: str
    approved: bool
    manual_only: bool
    reasons: tuple[str, ...]


def _time_to_close_minutes(close_time: datetime | None) -> float:
    if close_time is None:
        return float("inf")
    if close_time.tzinfo is None:
        close_time = close_time.replace(tzinfo=timezone.utc)
    delta = close_time - datetime.now(timezone.utc)
    return delta.total_seconds() / 60.0


def hard_skip_reasons(m: Market, f: MarketFilters) -> tuple[str, ...]:
    """Return the list of skip reasons for a market. Empty tuple = passes hard filters."""
    reasons: list[str] = []

    if m.liquidity_usd < f.min_liquidity_usd:
        reasons.append("LIQUIDITY_BELOW_MIN")
    if m.volume_24h_usd < f.min_volume_24h_usd:
        reasons.append("VOLUME_BELOW_MIN")
    if m.spread_pct > f.max_spread_pct:
        reasons.append("SPREAD_TOO_WIDE")
    if m.depth_within_5c_usd < f.min_depth_within_5c_usd:
        reasons.append("DEPTH_TOO_THIN")
    if _time_to_close_minutes(m.close_time) < f.min_time_to_close_minutes:
        reasons.append("CLOSES_TOO_SOON")
    if not m.yes_token_id or not m.no_token_id:
        reasons.append("MISSING_TOKEN_IDS")
    if m.tick_size is None:
        reasons.append("MISSING_TICK_SIZE")
    if m.fee_rate_bps is None:
        reasons.append("MISSING_FEE_RATE")
    if m.min_order_size is None:
        reasons.append("MISSING_MIN_ORDER_SIZE")
    if not m.resolution_rules:
        reasons.append("AMBIGUOUS_RESOLUTION")

    cat = (m.category or "").lower()
    if any(bad in cat for bad in FORBIDDEN_CATEGORIES):
        reasons.append("FORBIDDEN_CATEGORY")

    return tuple(reasons)


def market_quality_score(m: Market) -> float:
    """Heuristic quality score in [0,1] from PRD §10.4.

    Combines liquidity, spread, volume, clarity, time-to-close, and resolution-risk
    into a single number for signal arbitration.
    """
    liq = min(1.0, m.liquidity_usd / 500_000.0)
    spread = max(0.0, 1.0 - m.spread_pct / 10.0)
    volume = min(1.0, m.volume_24h_usd / 250_000.0)
    depth = min(1.0, m.depth_within_5c_usd / 50_000.0)

    ttc_min = _time_to_close_minutes(m.close_time)
    if ttc_min == float("inf"):
        time_score = 0.5
    else:
        # peak around 6h–7d to close, drop off near both ends
        time_score = max(0.0, min(1.0, ttc_min / (7 * 24 * 60)))

    clarity = 1.0 if m.resolution_rules else 0.0
    res_penalty = m.resolution_risk

    raw = (
        0.25 * liq
        + 0.20 * spread
        + 0.15 * volume
        + 0.15 * depth
        + 0.10 * time_score
        + 0.15 * clarity
        - 0.20 * res_penalty
    )
    return max(0.0, min(1.0, raw))


def classify(m: Market, f: MarketFilters) -> ScanDecision:
    """Classify a market: approved, manual_only, or skipped."""
    reasons = hard_skip_reasons(m, f)
    if reasons:
        return ScanDecision(m.id, approved=False, manual_only=False, reasons=reasons)

    quality = m.market_quality or market_quality_score(m)
    if quality < 0.70:
        return ScanDecision(
            m.id, approved=False, manual_only=True, reasons=("LOW_QUALITY_REVIEW",)
        )

    return ScanDecision(m.id, approved=True, manual_only=False, reasons=())


def scan(markets: list[Market], f: MarketFilters) -> dict[str, list[dict]]:
    """Run scanner over a batch of markets. Returns the strict-JSON skill output."""
    approved: list[dict] = []
    manual_only: list[dict] = []
    skipped: list[dict] = []

    for m in markets:
        d = classify(m, f)
        entry = {"market_id": m.id, "question": m.question}
        if d.approved:
            approved.append(entry)
        elif d.manual_only:
            manual_only.append({**entry, "reasons": list(d.reasons)})
        else:
            skipped.append({**entry, "reasons": list(d.reasons)})

    return {
        "approved_markets": approved,
        "manual_only_markets": manual_only,
        "skipped_markets": skipped,
    }
