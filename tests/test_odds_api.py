"""The Odds API adapter tests (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from polyflow.adapters.odds_api import (
    OddsAPIClient,
    OddsEvent,
    _anchors_from_events,
    question_match_score,
)


_SAMPLE_NBA = [
    {
        "id": "1",
        "sport_key": "basketball_nba",
        "home_team": "Oklahoma City Thunder",
        "away_team": "Phoenix Suns",
        "commence_time": "2026-04-28T01:30:00Z",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Oklahoma City Thunder", "price": 1.25},
                            {"name": "Phoenix Suns", "price": 4.50},
                        ],
                    }
                ],
            },
            {
                "key": "fanduel",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Oklahoma City Thunder", "price": 1.27},
                            {"name": "Phoenix Suns", "price": 4.20},
                        ],
                    }
                ],
            },
        ],
    }
]


class TestQuestionMatch:
    def test_strong_match(self) -> None:
        score = question_match_score("Thunder vs. Suns", "Oklahoma City Thunder", "Phoenix Suns")
        # Both team tokens appear in the short question → strong overlap (≥0.4)
        assert score >= 0.4

    def test_weak_match(self) -> None:
        score = question_match_score("Will Atalanta BC win on 2026-04-27?", "Oklahoma City Thunder", "Phoenix Suns")
        assert score == 0.0

    def test_partial(self) -> None:
        score = question_match_score("Will Lakers beat Celtics?", "Los Angeles Lakers", "Boston Celtics")
        assert score > 0.3


@pytest.mark.asyncio
async def test_fetch_sport_returns_events_when_keyed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "apiKey=fake-key" in str(request.url.params) or request.url.params.get("apiKey") == "fake-key"
        return httpx.Response(200, json=_SAMPLE_NBA)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        c = OddsAPIClient(api_key="fake-key", sports=("basketball_nba",))
        events = await c.fetch_sport("basketball_nba", client=client)

    assert len(events) == 1
    assert events[0].home_team == "Oklahoma City Thunder"
    # Median of 1.25/1.27 = 1.26
    assert 1.25 <= events[0].home_decimal_odds <= 1.27


@pytest.mark.asyncio
async def test_fetch_sport_no_key_returns_empty() -> None:
    c = OddsAPIClient(api_key=None, sports=("basketball_nba",))
    events = await c.fetch_sport("basketball_nba")
    assert events == []
    assert not c.configured


def test_anchors_from_events_matches_question() -> None:
    event = OddsEvent(
        sport_key="basketball_nba",
        home_team="Oklahoma City Thunder",
        away_team="Phoenix Suns",
        commence_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        home_decimal_odds=1.26,
        away_decimal_odds=4.20,
        draw_decimal_odds=None,
        book_count=2,
    )
    anchors = _anchors_from_events([event], question="Thunder vs. Suns", min_match_score=0.30)
    assert len(anchors) == 1
    # YES side = Thunder (home, since "Thunder" appears first in question).
    # vig-stripped YES probability should be near 0.77 (Thunder favored).
    assert anchors[0].yes_probability > 0.7


def test_anchors_skip_non_matching() -> None:
    event = OddsEvent(
        sport_key="basketball_nba",
        home_team="Oklahoma City Thunder",
        away_team="Phoenix Suns",
        commence_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        home_decimal_odds=1.26,
        away_decimal_odds=4.20,
        draw_decimal_odds=None,
        book_count=2,
    )
    anchors = _anchors_from_events([event], question="Atalanta vs Inter", min_match_score=0.30)
    assert anchors == []
