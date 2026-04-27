"""Market scanner / hard-filter tests (PRD §6, §14.1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from polyflow.config import MarketFilters
from polyflow.market_scanner import (
    classify,
    hard_skip_reasons,
    market_quality_score,
    scan,
    quickfire_score,
    strategy_candidates,
)
from polyflow.types import Market, Strategy


def make_market(**overrides) -> Market:
    """Build a Market that passes every hard filter by default."""
    base = dict(
        id="m1",
        event_id="e1",
        question="Will it rain in NYC tomorrow?",
        category="weather",
        close_time=datetime.now(timezone.utc) + timedelta(hours=24),
        resolution_rules="NYC NWS daily report at 23:59 ET.",
        liquidity_usd=200_000,
        volume_24h_usd=50_000,
        spread_pct=2.0,
        depth_within_5c_usd=20_000,
        yes_token_id="t-yes",
        no_token_id="t-no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=200,
        neg_risk=False,
        market_quality=0.85,
        resolution_risk=0.10,
    )
    base.update(overrides)
    return Market(**base)


class TestHardFilters:
    def test_passing_market_has_no_reasons(self) -> None:
        assert hard_skip_reasons(make_market(), MarketFilters()) == ()

    def test_low_liquidity(self) -> None:
        r = hard_skip_reasons(make_market(liquidity_usd=10_000), MarketFilters())
        assert "LIQUIDITY_BELOW_MIN" in r

    def test_wide_spread(self) -> None:
        r = hard_skip_reasons(make_market(spread_pct=8.0), MarketFilters())
        assert "SPREAD_TOO_WIDE" in r

    def test_low_volume(self) -> None:
        r = hard_skip_reasons(make_market(volume_24h_usd=1_000), MarketFilters())
        assert "VOLUME_BELOW_MIN" in r

    def test_thin_depth(self) -> None:
        r = hard_skip_reasons(make_market(depth_within_5c_usd=500), MarketFilters())
        assert "DEPTH_TOO_THIN" in r

    def test_close_too_soon(self) -> None:
        r = hard_skip_reasons(
            make_market(close_time=datetime.now(timezone.utc) + timedelta(minutes=5)),
            MarketFilters(),
        )
        assert "CLOSES_TOO_SOON" in r

    def test_close_too_late_for_daily_market_policy(self) -> None:
        r = hard_skip_reasons(
            make_market(close_time=datetime.now(timezone.utc) + timedelta(days=5)),
            MarketFilters(max_time_to_close_minutes=36 * 60),
        )
        assert "CLOSES_TOO_LATE" in r

    def test_missing_token_ids(self) -> None:
        r = hard_skip_reasons(make_market(yes_token_id=None), MarketFilters())
        assert "MISSING_TOKEN_IDS" in r

    def test_missing_tick_size(self) -> None:
        r = hard_skip_reasons(make_market(tick_size=None), MarketFilters())
        assert "MISSING_TICK_SIZE" in r

    def test_missing_resolution_rules(self) -> None:
        r = hard_skip_reasons(make_market(resolution_rules=None), MarketFilters())
        assert "AMBIGUOUS_RESOLUTION" in r

    @pytest.mark.parametrize("cat", ["war", "death", "terror", "Assassination Watch"])
    def test_forbidden_categories(self, cat: str) -> None:
        r = hard_skip_reasons(make_market(category=cat), MarketFilters())
        assert "FORBIDDEN_CATEGORY" in r

    @pytest.mark.parametrize(
        "question",
        ["Will China invade Taiwan?", "Ceasefire by Friday?", "Permanent peace deal by May?"],
    )
    def test_forbidden_question_terms(self, question: str) -> None:
        r = hard_skip_reasons(make_market(question=question, category=None), MarketFilters())
        assert "FORBIDDEN_CATEGORY" in r


class TestMarketQuality:
    def test_score_in_unit_interval(self) -> None:
        s = market_quality_score(make_market())
        assert 0.0 <= s <= 1.0

    def test_better_market_scores_higher(self) -> None:
        weak = make_market(
            liquidity_usd=100_000,
            volume_24h_usd=25_000,
            spread_pct=4.5,
            depth_within_5c_usd=10_500,
            resolution_risk=0.30,
        )
        strong = make_market(
            liquidity_usd=600_000,
            volume_24h_usd=300_000,
            spread_pct=1.0,
            depth_within_5c_usd=80_000,
            resolution_risk=0.05,
        )
        assert market_quality_score(strong) > market_quality_score(weak)


class TestClassify:
    def test_passing_market_approved(self) -> None:
        d = classify(make_market(), MarketFilters())
        assert d.approved and not d.manual_only

    def test_skipped_market_listed_in_skipped(self) -> None:
        out = scan([make_market(liquidity_usd=10_000)], MarketFilters())
        assert out["skipped_markets"]
        assert not out["approved_markets"]

    def test_low_quality_routed_to_manual_only(self) -> None:
        # Pass hard filters but low-quality enough to need human eyes.
        m = make_market(market_quality=0.50)
        d = classify(m, MarketFilters())
        assert d.manual_only and not d.approved

class TestStrategyRouting:
    def test_crypto_threshold_market_maps_to_btc_strategy(self) -> None:
        routes = strategy_candidates(
            make_market(question="Will Bitcoin close above $120k by Friday?", category="crypto")
        )
        assert Strategy.BTC_THRESHOLD in routes
        assert Strategy.FOUR_LAYER_ALIGNMENT in routes

    def test_scan_output_includes_tailored_strategy_metadata(self) -> None:
        out = scan(
            [
                make_market(
                    question="Will Bitcoin close above $120k by Friday?",
                    category="crypto",
                    volume_24h_usd=150_000,
                )
            ],
            MarketFilters(),
        )
        approved = out["approved_markets"][0]
        assert "btc_threshold" in approved["strategies"]
        assert approved["quickfire_eligible"] is True
        assert approved["quickfire_score"] > 0.0
        assert approved["market_quality"] == 0.85

    def test_quickfire_score_prefers_liquid_tight_daily_markets(self) -> None:
        weak = make_market(volume_24h_usd=100_000, spread_pct=2.4, depth_within_5c_usd=10_000)
        strong = make_market(volume_24h_usd=600_000, spread_pct=0.5, depth_within_5c_usd=80_000)
        assert quickfire_score(strong) > quickfire_score(weak)
