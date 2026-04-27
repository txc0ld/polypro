"""24/7 strategy automation subagent tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from polyflow.adapters.clob import PaperCLOBAdapter
from polyflow.adapters.gamma import StubGammaAdapter
from polyflow.config import Policy
from polyflow.logger import ImmutableLogger
from polyflow.persistence import SQLiteStore
from polyflow.runtime import Runtime
from polyflow.strategies.external_odds_divergence import OddsAnchor
from polyflow.subagents.strategy_automation import StrategyAutomation, TradeActivityAnalyzer
from polyflow.types import Market, Mode, RiskState


class AnchorFixture:
    async def fetch(self, market_id: str) -> list[OddsAnchor]:
        return [
            OddsAnchor(
                source_name="regulated-anchor",
                fetched_at=datetime.now(timezone.utc),
                yes_probability=0.78,
                reliability=0.92,
                settlement_match=True,
            )
        ]


class EmptyNewsFixture:
    async def events_for_market(self, market: Market) -> list:
        return []


def _market() -> Market:
    return Market(
        id="m-auto",
        event_id="e-auto",
        question="Will Manchester United FC win today?",
        category="sports",
        close_time=datetime.now(timezone.utc) + timedelta(hours=8),
        resolution_rules="Official match result.",
        liquidity_usd=500_000,
        volume_24h_usd=600_000,
        spread_pct=1.0,
        depth_within_5c_usd=80_000,
        best_bid=0.50,
        best_ask=0.52,
        yes_token_id="yes",
        no_token_id="no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=0.0,
        neg_risk=False,
        market_quality=0.92,
        resolution_risk=0.04,
    )


def _runtime(tmp_path: Path, store: SQLiteStore, policy: Policy) -> Runtime:
    return Runtime(
        policy=policy,
        gamma=StubGammaAdapter([_market()]),
        clob=PaperCLOBAdapter(),
        logger=ImmutableLogger(tmp_path / "imm.jsonl"),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
        store=store,
    )


@pytest.mark.asyncio
async def test_strategy_automation_persists_signal_without_order_when_disabled(tmp_path: Path) -> None:
    policy = Policy()
    policy.mode = Mode.LIVE_TINY
    store = SQLiteStore(":memory:")
    market = _market()
    store.upsert_market(market, status="watching")
    rt = _runtime(tmp_path, store, policy)

    automation = StrategyAutomation(
        runtime=rt,
        store=store,
        logger=rt.logger,
        anchor_adapter=AnchorFixture(),
        news_adapter=EmptyNewsFixture(),
        allow_order_placement=False,
    )
    await automation.tick()

    assert store.get_recent_signals(10)
    assert isinstance(rt.clob, PaperCLOBAdapter)
    assert rt.clob.placed == []


@pytest.mark.asyncio
async def test_strategy_automation_places_paper_order_when_enabled(tmp_path: Path) -> None:
    policy = Policy()
    policy.mode = Mode.LIVE_TINY
    policy.automation.allow_order_placement = True
    store = SQLiteStore(":memory:")
    market = _market()
    store.upsert_market(market, status="watching")
    rt = _runtime(tmp_path, store, policy)

    automation = StrategyAutomation(
        runtime=rt,
        store=store,
        logger=rt.logger,
        anchor_adapter=AnchorFixture(),
        news_adapter=EmptyNewsFixture(),
        allow_order_placement=True,
    )
    await automation.tick()

    assert isinstance(rt.clob, PaperCLOBAdapter)
    assert len(rt.clob.placed) == 1
    assert rt.clob.placed[0]["market_id"] == "m-auto"


@pytest.mark.asyncio
async def test_trade_activity_analyzer_skips_without_wallet(tmp_path: Path) -> None:
    logger = ImmutableLogger(tmp_path / "imm.jsonl")
    analyzer = TradeActivityAnalyzer(wallet_address=None, logger=logger)
    await analyzer.tick()
    assert "NO_WALLET_ADDRESS" in (tmp_path / "imm.jsonl").read_text(encoding="utf-8")
