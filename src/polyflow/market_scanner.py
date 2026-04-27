"""Market Scanner skill — deterministic hard filters (PRD §6, §14.1).

This is the *first* refusal layer. Most markets must die here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .config import MarketFilters
from .types import Market, Strategy

# Categories the bot must refuse outright.
FORBIDDEN_CATEGORIES: frozenset[str] = frozenset(
    {"war", "death", "terror", "assassination"}
)
FORBIDDEN_TEXT_TERMS: frozenset[str] = frozenset(
    {
        "war",
        "ceasefire",
        "invasion",
        "invade",
        "military strike",
        "peace deal",
        "regime fall",
        "terror",
        "assassination",
    }
)

QUICKFIRE_MAX_TIME_TO_CLOSE_MINUTES = 72 * 60        # FAST: 72h scalp horizon
QUICKFIRE_MAX_SPREAD_PCT = 6.0                       # ≤6c
QUICKFIRE_MIN_VOLUME_24H_USD = 10_000                # ≥$10k (esports inclusive)
QUICKFIRE_MIN_LIQUIDITY_USD = 5_000                  # ≥$5k available liquidity

# Day-trade avoid list: long-duration / non-scalpable markets per the user's
# scalping doctrine. The scanner refuses anything matching these terms even
# if the liquidity numbers look attractive.
DAYTRADE_AVOID_TERMS: frozenset[str] = frozenset(
    {
        "world cup winner",
        "presidential nominee",
        "presidential election",
        "champion 2026",   # NBA Champion / NHL Champion / etc. — long horizon
        "champion 2027",
        "champion 2028",
        "drivers' champion",
        "drivers champion",
        "eurovision winner",
        "election winner 2028",
        "best picture",     # awards markets are long-duration with vague rules
    }
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
    ttc_minutes = _time_to_close_minutes(m.close_time)
    if ttc_minutes < f.min_time_to_close_minutes:
        reasons.append("CLOSES_TOO_SOON")
    if f.max_time_to_close_minutes is not None and ttc_minutes > f.max_time_to_close_minutes:
        reasons.append("CLOSES_TOO_LATE")
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
    text = f"{m.question} {cat}".lower()
    if any(bad in cat for bad in FORBIDDEN_CATEGORIES) or any(
        bad in text for bad in FORBIDDEN_TEXT_TERMS
    ):
        reasons.append("FORBIDDEN_CATEGORY")

    # Long-horizon / non-scalpable per the day-trade avoid list.
    if any(term in text for term in DAYTRADE_AVOID_TERMS):
        reasons.append("LONG_HORIZON_AVOID")

    # Price-zone gate (scalp doctrine: 20c-80c preferred; >95% priced markets
    # are unscalpable).
    if m.best_bid is not None and m.best_ask is not None:
        mid = (m.best_bid + m.best_ask) / 2.0
        if f.min_mid_price is not None and mid < f.min_mid_price:
            reasons.append("PRICE_BELOW_MIN_ZONE")
        if f.max_mid_price is not None and mid > f.max_mid_price:
            reasons.append("PRICE_ABOVE_MAX_ZONE")

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

    time_score = _daily_time_score(_time_to_close_minutes(m.close_time))

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


def _daily_time_score(ttc_min: float) -> float:
    if ttc_min == float("inf"):
        return 0.0
    if ttc_min < 60:
        return 0.0
    if ttc_min <= 6 * 60:
        return max(0.0, ttc_min / (6 * 60))
    if ttc_min <= 24 * 60:
        return 1.0
    if ttc_min <= QUICKFIRE_MAX_TIME_TO_CLOSE_MINUTES:
        return 0.75
    return 0.25


def quickfire_score(m: Market) -> float:
    """Rank daily candidates by tradability and strategy coverage."""
    liquidity = min(1.0, m.liquidity_usd / 500_000.0)
    volume = min(1.0, m.volume_24h_usd / 500_000.0)
    spread = max(0.0, 1.0 - (m.spread_pct / QUICKFIRE_MAX_SPREAD_PCT))
    depth = min(1.0, m.depth_within_5c_usd / 75_000.0)
    time_score = _daily_time_score(_time_to_close_minutes(m.close_time))
    strategy_breadth = min(1.0, len(strategy_candidates(m)) / 4.0)
    raw = (
        0.20 * liquidity
        + 0.25 * volume
        + 0.20 * spread
        + 0.15 * depth
        + 0.10 * time_score
        + 0.10 * strategy_breadth
    )
    return max(0.0, min(1.0, raw))


def quickfire_reasons(m: Market) -> tuple[str, ...]:
    """Return why a market is not a daily quick-turnover candidate."""
    reasons: list[str] = []
    ttc = _time_to_close_minutes(m.close_time)

    if ttc == float("inf"):
        reasons.append("NO_CLOSE_TIME")
    elif ttc > QUICKFIRE_MAX_TIME_TO_CLOSE_MINUTES:
        reasons.append("LONG_HORIZON")
    if m.volume_24h_usd < QUICKFIRE_MIN_VOLUME_24H_USD:
        reasons.append("LOW_INTRADAY_VOLUME")
    if m.liquidity_usd < QUICKFIRE_MIN_LIQUIDITY_USD:
        reasons.append("LOW_LIQUIDITY")
    if m.spread_pct > QUICKFIRE_MAX_SPREAD_PCT:
        reasons.append("SPREAD_NOT_QUICKFIRE")
    if not strategy_candidates(m):
        reasons.append("NO_STRATEGY_MATCH")

    return tuple(reasons)


def is_quickfire_candidate(m: Market) -> bool:
    """True when the market is liquid enough and close enough for daily turnover."""
    return not quickfire_reasons(m)


def strategy_candidates(m: Market) -> tuple[Strategy, ...]:
    """Return the tailored strategy families that may evaluate this market.

    This is routing metadata, not a trade recommendation. A strategy still has
    to produce a valid probability estimate, then pass Kelly/risk/order gates.
    """
    text = f"{m.question} {m.category or ''}".lower()
    out: list[Strategy] = []

    if m.neg_risk:
        out.append(Strategy.NEGATIVE_RISK_BASKET)

    crypto_terms = ("btc", "bitcoin", "eth", "ethereum", "solana", "crypto")
    threshold_terms = ("above", "below", "over", "under", "reach", "hit", "close")
    if any(term in text for term in crypto_terms) and any(term in text for term in threshold_terms):
        out.append(Strategy.BTC_THRESHOLD)

    anchor_categories = (
        "sports", "nba", "nfl", "mlb", "nhl", "soccer", "election",
        "politics", "crypto", "finance", "economics",
        # Esports — recognized so external_odds_divergence routes against
        # Odds API esports keys (CSGO/Dota2/LoL/Valorant).
        "counter-strike", "csgo", "cs:go", "cs2",
        "league of legends", "lol",
        "dota", "valorant", "esports",
    )
    if any(term in text for term in anchor_categories):
        out.append(Strategy.EXTERNAL_ODDS_DIVERGENCE)

    # Commodity threshold strategy (WTI / gold / silver / copper) — routes
    # parsed asset to the commodities Yahoo Finance feed.
    commodity_terms = ("wti", "crude oil", "oil", "gold", "silver", "copper", "xau", "xag")
    if any(term in text for term in commodity_terms) and any(t in text for t in threshold_terms):
        out.append(Strategy.BTC_THRESHOLD)

    # Weather threshold (NOAA/ASOS) — handled by news_repricing for now;
    # the weather adapter's trajectory_probability is the prior.
    weather_terms = ("temperature", "rain", "snow", "weather", "tokyo", "seoul", "beijing", "shanghai", "nyc", "new york")
    if any(term in text for term in weather_terms):
        out.append(Strategy.NEWS_REPRICING)

    news_categories = (
        "politics", "election", "economics", "finance", "business", "crypto",
        "weather", "technology", "tech", "ai", "geopolitics", "fed", "rates",
        "cpi", "pce", "nfp", "fomc", "treasury",
    )
    if any(term in text for term in news_categories):
        out.append(Strategy.NEWS_REPRICING)

    if (m.market_quality or market_quality_score(m)) >= 0.70 and m.liquidity_usd >= 100_000:
        out.append(Strategy.FOUR_LAYER_ALIGNMENT)

    if m.spread_pct <= 2.0 and m.depth_within_5c_usd >= 25_000:
        out.append(Strategy.SPREAD_CAPTURE)

    if m.depth_within_5c_usd >= 50_000 and m.liquidity_usd >= 250_000:
        out.append(Strategy.PASSIVE_FAIR_VALUE_QUOTING)

    deduped: list[Strategy] = []
    for strategy in out:
        if strategy not in deduped:
            deduped.append(strategy)
    return tuple(deduped)


def classify(m: Market, f: MarketFilters) -> ScanDecision:
    """Classify a market: approved, manual_only, or skipped.

    The quality threshold is intentionally low (0.30) under the FAST profile
    so high-velocity esports / 5-min crypto markets aren't excluded for
    having lower aggregate book depth. Strategies still enforce their own
    quality / size / depth gates downstream.
    """
    reasons = hard_skip_reasons(m, f)
    if reasons:
        return ScanDecision(m.id, approved=False, manual_only=False, reasons=reasons)

    quality = m.market_quality or market_quality_score(m)
    if quality < 0.30:
        return ScanDecision(
            m.id, approved=False, manual_only=True, reasons=("LOW_QUALITY_REVIEW",)
        )

    if not strategy_candidates(m):
        return ScanDecision(
            m.id, approved=False, manual_only=True, reasons=("NO_STRATEGY_MATCH",)
        )

    if f.max_time_to_close_minutes is not None and quickfire_score(m) < 0.25:
        return ScanDecision(
            m.id, approved=False, manual_only=True, reasons=("LOW_QUICKFIRE_SCORE",)
        )

    return ScanDecision(m.id, approved=True, manual_only=False, reasons=())


def scan(markets: list[Market], f: MarketFilters) -> dict[str, list[dict]]:
    """Run scanner over a batch of markets. Returns the strict-JSON skill output."""
    approved: list[dict] = []
    manual_only: list[dict] = []
    skipped: list[dict] = []

    for m in markets:
        d = classify(m, f)
        entry = {
            "market_id": m.id,
            "question": m.question,
            "category": m.category,
            "market_quality": m.market_quality or market_quality_score(m),
            "liquidity_usd": m.liquidity_usd,
            "volume_24h_usd": m.volume_24h_usd,
            "spread_pct": m.spread_pct,
            "strategies": [s.value for s in strategy_candidates(m)],
            "quickfire_eligible": is_quickfire_candidate(m),
            "quickfire_reasons": list(quickfire_reasons(m)),
            "quickfire_score": quickfire_score(m),
        }
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
