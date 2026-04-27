"""The Odds API live odds adapter.

https://the-odds-api.com — free tier 500 requests/month, no scraping required.
Pulls h2h (moneyline) odds from US/UK bookmakers across NBA, NFL, NHL, MLB,
EPL, La Liga, Serie A, Bundesliga, Champions League, etc., normalizes the
prices to ``OddsAnchor`` records (vig stripped), and matches Polymarket
question text against bookmaker event names by team token overlap.

Set ``THE_ODDS_API_KEY`` in ``.env.local`` (or ``POLY_ODDS_API_KEY``).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import httpx

from ..strategies.external_odds_divergence import OddsAnchor


_BASE = "https://api.the-odds-api.com/v4"

# Sports we pull on each cycle. Light enough to fit free-tier budget on a
# 5-minute cadence: 8 sports × 12 ticks/hour × 24h = ~2300/day. We don't poll
# that aggressively in production — the runtime calls fetch_all once per
# strategy_automation tick.
DEFAULT_SPORTS = (
    "basketball_nba",
    "basketball_wnba",
    "americanfootball_nfl",
    "icehockey_nhl",
    "baseball_mlb",
    "soccer_epl",
    "soccer_uefa_champs_league",
    "soccer_italy_serie_a",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Lowercase token bag, ignoring stop words common to Polymarket questions."""
    stop = {
        "will", "the", "win", "vs", "v", "and", "on", "by", "in", "at",
        "fc", "bc", "cf", "afc", "lfc", "nfl", "nba", "mlb", "nhl",
        "match", "game", "today", "tonight", "tomorrow",
    }
    out = set()
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok in stop or len(tok) < 3:
            continue
        out.add(tok)
    return out


def question_match_score(question: str, home_team: str, away_team: str) -> float:
    """Jaccard-ish overlap between Polymarket question tokens and (home, away)."""
    q = _tokens(question)
    teams = _tokens(home_team + " " + away_team)
    if not q or not teams:
        return 0.0
    return len(q & teams) / len(q | teams)


@dataclass(frozen=True)
class OddsEvent:
    sport_key: str
    home_team: str
    away_team: str
    commence_time: datetime
    home_decimal_odds: float
    away_decimal_odds: float
    draw_decimal_odds: float | None
    book_count: int

    def yes_decimal_odds(self, *, home_is_yes: bool) -> float:
        """For two-way Polymarket markets, decide which side is YES.

        Convention: many Polymarket markets phrase "Will <home> win?" so we
        treat home as YES by default. The matcher also returns this flag so
        the caller can flip if "Will <away> win?" is the phrasing.
        """
        return self.home_decimal_odds if home_is_yes else self.away_decimal_odds

    def no_decimal_odds(self, *, home_is_yes: bool) -> float:
        return self.away_decimal_odds if home_is_yes else self.home_decimal_odds


@dataclass
class OddsAPIClient:
    api_key: str | None
    sports: tuple[str, ...] = DEFAULT_SPORTS
    regions: str = "us,us2,uk,eu"
    timeout_seconds: float = 8.0
    last_error: str | None = field(default=None, init=False)

    @classmethod
    def from_env(cls, *, sports: Iterable[str] | None = None) -> "OddsAPIClient":
        # Accept several common env var names; check both real env and the
        # project's .env.local so the runtime works without the operator
        # having to also export the variable.
        from ..secrets import load_env

        merged = {**load_env(), **os.environ}
        key = (
            merged.get("THE_ODDS_API_KEY")
            or merged.get("ODDS_API_KEY")
            or merged.get("POLY_ODDS_API_KEY")
        )
        return cls(api_key=key, sports=tuple(sports) if sports else DEFAULT_SPORTS)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def fetch_sport(
        self, sport_key: str, *, client: httpx.AsyncClient | None = None
    ) -> list[OddsEvent]:
        if not self.api_key:
            return []
        owns = client is None
        client = client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            resp = await client.get(
                f"{_BASE}/sports/{sport_key}/odds",
                params={
                    "apiKey": self.api_key,
                    "regions": self.regions,
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
            )
            if resp.status_code != 200:
                self.last_error = f"HTTP_{resp.status_code}: {resp.text[:200]}"
                return []
            data = resp.json()
        finally:
            if owns:
                await client.aclose()

        events: list[OddsEvent] = []
        for raw in data or []:
            try:
                event = _parse_event(raw, sport_key)
            except (KeyError, TypeError, ValueError):
                continue
            if event is not None:
                events.append(event)
        return events

    async def fetch_all(self, *, client: httpx.AsyncClient | None = None) -> list[OddsEvent]:
        owns = client is None
        client = client or httpx.AsyncClient(timeout=self.timeout_seconds)
        out: list[OddsEvent] = []
        try:
            for sport in self.sports:
                out.extend(await self.fetch_sport(sport, client=client))
        finally:
            if owns:
                await client.aclose()
        return out

    async def anchors_for_market(
        self,
        question: str,
        *,
        client: httpx.AsyncClient | None = None,
        min_match_score: float = 0.30,
    ) -> list[OddsAnchor]:
        """Return OddsAnchors that match the Polymarket question."""
        if not self.api_key:
            return []
        events = await self.fetch_all(client=client)
        return _anchors_from_events(events, question=question, min_match_score=min_match_score)


def _parse_event(raw: dict, sport_key: str) -> OddsEvent | None:
    home_team = str(raw.get("home_team") or "").strip()
    away_team = str(raw.get("away_team") or "").strip()
    if not home_team or not away_team:
        return None

    commence_raw = raw.get("commence_time") or ""
    try:
        commence_time = datetime.fromisoformat(str(commence_raw).replace("Z", "+00:00"))
        if commence_time.tzinfo is None:
            commence_time = commence_time.replace(tzinfo=timezone.utc)
    except ValueError:
        commence_time = datetime.now(timezone.utc)

    home_prices: list[float] = []
    away_prices: list[float] = []
    draw_prices: list[float] = []
    book_count = 0

    for book in raw.get("bookmakers") or []:
        for market in book.get("markets") or []:
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes") or []:
                name = str(outcome.get("name") or "").strip()
                price = outcome.get("price")
                if price is None:
                    continue
                try:
                    price = float(price)
                except (TypeError, ValueError):
                    continue
                if price <= 1.0:
                    continue
                if name.lower() == home_team.lower():
                    home_prices.append(price)
                elif name.lower() == away_team.lower():
                    away_prices.append(price)
                elif name.lower() == "draw":
                    draw_prices.append(price)
        book_count += 1

    if not home_prices or not away_prices:
        return None

    return OddsEvent(
        sport_key=sport_key,
        home_team=home_team,
        away_team=away_team,
        commence_time=commence_time,
        home_decimal_odds=_median(home_prices),
        away_decimal_odds=_median(away_prices),
        draw_decimal_odds=_median(draw_prices) if draw_prices else None,
        book_count=book_count,
    )


def _median(prices: list[float]) -> float:
    s = sorted(prices)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _anchors_from_events(
    events: list[OddsEvent], *, question: str, min_match_score: float
) -> list[OddsAnchor]:
    anchors: list[OddsAnchor] = []
    q = _tokens(question)
    if not q:
        return []
    for event in events:
        score = question_match_score(question, event.home_team, event.away_team)
        if score < min_match_score:
            continue

        # Decide YES side: find the *earliest token* from each team that
        # appears in the question and pick the team whose token comes first.
        # Handles "Pistons vs. Magic" → Pistons is YES even though Pistons is
        # the away team, because Polymarket's YES side is typically the team
        # mentioned first in the question.
        home_idx = _earliest_team_token_position(question, event.home_team)
        away_idx = _earliest_team_token_position(question, event.away_team)
        if home_idx < 0 and away_idx < 0:
            continue  # neither team's token found — refuse
        if home_idx < 0:
            home_is_yes = False
        elif away_idx < 0:
            home_is_yes = True
        else:
            home_is_yes = home_idx <= away_idx

        # If draw odds exist, build vig-stripped 2-way (YES vs NO=draw+other)
        # by combining draw + the other side's odds. Otherwise straight 2-way.
        yes_odds = event.yes_decimal_odds(home_is_yes=home_is_yes)
        no_odds = event.no_decimal_odds(home_is_yes=home_is_yes)
        if event.draw_decimal_odds is not None:
            no_implied = (1.0 / no_odds) + (1.0 / event.draw_decimal_odds)
            no_odds = 1.0 / no_implied if no_implied > 0 else no_odds

        try:
            anchor = OddsAnchor.from_decimal_odds(
                source_name=f"odds_api:{event.sport_key}:{event.book_count}books",
                fetched_at=datetime.now(timezone.utc),
                yes_decimal_odds=yes_odds,
                no_decimal_odds=no_odds,
                reliability=min(0.95, 0.70 + 0.05 * min(event.book_count, 5)),
                settlement_match=True,
            )
        except (ValueError, ZeroDivisionError):
            continue
        anchors.append(anchor)
    return anchors


def _earliest_index(haystack: str, needle: str) -> int:
    if not needle:
        return -1
    return haystack.find(needle)


def _earliest_team_token_position(question: str, team_name: str) -> int:
    """Earliest position in ``question`` where any meaningful token from
    ``team_name`` appears. Returns -1 when no team token is found.
    """
    q_lower = question.lower()
    best = -1
    for tok in _tokens(team_name):
        idx = q_lower.find(tok)
        if idx < 0:
            continue
        if best < 0 or idx < best:
            best = idx
    return best
