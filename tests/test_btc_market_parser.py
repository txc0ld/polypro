"""BTC threshold question parser tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.strategies.btc_market_parser import (
    BtcThresholdParse,
    parse_btc_threshold,
    seconds_to_close,
)


class TestParseQuestion:
    def test_above_with_dollar_k(self) -> None:
        r = parse_btc_threshold("Will Bitcoin close above $120k by Friday?")
        assert r is not None
        assert r.price_to_beat == 120_000
        assert r.direction == "above"

    def test_below_with_full_dollar(self) -> None:
        r = parse_btc_threshold("Will BTC fall below $95,000 today?")
        assert r is not None
        assert r.price_to_beat == 95_000
        assert r.direction == "below"

    def test_btc_short_form(self) -> None:
        r = parse_btc_threshold("BTC > $110k by 4pm UTC")
        # No threshold word in the prefix → won't parse. This is intentional;
        # we want to be conservative and only fire on explicit threshold language.
        assert r is None

    def test_explicit_reach(self) -> None:
        r = parse_btc_threshold("Will Bitcoin reach $150,000 in April?")
        assert r is not None
        assert r.price_to_beat == 150_000

    def test_non_btc_market(self) -> None:
        assert parse_btc_threshold("Will the Lakers win tonight?") is None

    def test_btc_without_threshold(self) -> None:
        # Must have both a BTC term AND a threshold term.
        assert parse_btc_threshold("What is Bitcoin's price?") is None

    def test_million_suffix(self) -> None:
        r = parse_btc_threshold("Will BTC close above $1M this year?")
        assert r is not None
        assert r.price_to_beat == 1_000_000


class TestSecondsToClose:
    def test_future(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(seconds=120)
        assert 100 <= seconds_to_close(future) <= 130

    def test_past_returns_zero(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(seconds=60)
        assert seconds_to_close(past) == 0.0

    def test_none(self) -> None:
        assert seconds_to_close(None) == 0.0

    def test_naive_datetime_assumed_utc(self) -> None:
        future = datetime.utcnow() + timedelta(seconds=300)
        # Should not raise on missing tzinfo
        assert seconds_to_close(future) > 0
