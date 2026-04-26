"""End-to-end paper-mode smoke test through the full runtime gauntlet."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from polyflow.config import Policy
from polyflow.logger import ImmutableLogger
from polyflow.adapters.clob import PaperCLOBAdapter
from polyflow.adapters.gamma import StubGammaAdapter
from polyflow.runtime import Runtime
from polyflow.types import (
    Market,
    Mode,
    Outcome,
    ProbabilityEstimate,
    RiskState,
    Side,
    Signal,
    Strategy,
)


def _market() -> Market:
    return Market(
        id="m1",
        event_id="e1",
        question="Will BTC close above 100k on 2026-04-30?",
        category="crypto",
        close_time=datetime.now(timezone.utc) + timedelta(hours=24),
        resolution_rules="Coinbase BTC-USD daily close at 00:00 UTC.",
        liquidity_usd=400_000,
        volume_24h_usd=120_000,
        spread_pct=1.5,
        depth_within_5c_usd=40_000,
        yes_token_id="t-yes",
        no_token_id="t-no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=200,
        neg_risk=False,
        market_quality=0.85,
        resolution_risk=0.05,
    )


def _estimate(market: Market) -> ProbabilityEstimate:
    return ProbabilityEstimate(
        market_id=market.id,
        token_id=market.yes_token_id,
        outcome=Outcome.YES,
        market_price=0.55,
        model_probability=0.75,
        uncertainty=0.04,
        fair_bid=0.71,
        fair_ask=0.79,
        edge_before_costs=0.20,
        edge_after_costs=0.16,
        source_confidence=0.90,
        resolution_risk=0.05,
        recommendation="BUY_YES",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
        reason_codes=["BOOKMAKER_DIVERGENCE"],
        evidence_refs=["sha256:abc"],
    )


def _signal(market: Market, est: ProbabilityEstimate) -> Signal:
    return Signal(
        market_id=market.id,
        event_id=market.event_id,
        token_id=est.token_id,
        outcome=est.outcome,
        side=Side.BUY,
        strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
        market_price=est.market_price,
        model_probability=est.model_probability,
        uncertainty=est.uncertainty,
        effective_edge=est.edge_after_costs,
        market_quality=market.market_quality,
        resolution_risk=est.resolution_risk,
        liquidity_score=0.85,
        confidence=est.source_confidence,
        expires_at=est.expires_at,
        evidence_refs=est.evidence_refs,
    )


@pytest.mark.asyncio
async def test_full_paper_run_places_order_and_logs(tmp_path: Path) -> None:
    market = _market()
    est = _estimate(market)
    sig = _signal(market, est)

    policy = Policy()
    policy.mode = Mode.LIVE_TINY  # so the gauntlet actually runs to placement

    log_path = tmp_path / "imm.jsonl"
    rt = Runtime(
        policy=policy,
        gamma=StubGammaAdapter([market]),
        clob=PaperCLOBAdapter(),
        logger=ImmutableLogger(log_path),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
    )

    approved = await rt.tick_scan()
    assert market.id in approved

    result = await rt.evaluate_candidate(
        signal=sig,
        estimate=est,
        market=market,
        strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
    )

    assert result["placed"] is True
    assert result["exchange_order_id"]

    # Position now visible on the paper adapter
    positions = await rt.clob.get_positions()
    assert positions and positions[0].market_id == market.id

    # Log file exists and contains entries from each actor
    lines = log_path.read_text(encoding="utf-8").splitlines()
    actors = {json.loads(line)["actor"] for line in lines}
    assert {
        "market_scanner",
        "signal_arbiter",
        "risk_governor",
        "clob_order_formatter",
        "clob_adapter",
        "post_order_kelly_guard",
    }.issubset(actors)


@pytest.mark.asyncio
async def test_probability_estimate_persisted_to_store(tmp_path: Path) -> None:
    """Once SQLiteStore is wired in, every evaluated candidate persists its estimate."""
    from polyflow.persistence import SQLiteStore

    market = _market()
    est = _estimate(market)
    sig = _signal(market, est)

    policy = Policy()
    policy.mode = Mode.LIVE_TINY

    store = SQLiteStore(":memory:")
    store.upsert_market(market, status="watching")

    rt = Runtime(
        policy=policy,
        gamma=StubGammaAdapter([market]),
        clob=PaperCLOBAdapter(),
        logger=ImmutableLogger(tmp_path / "imm.jsonl"),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
        store=store,
    )
    await rt.evaluate_candidate(
        signal=sig,
        estimate=est,
        market=market,
        strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
    )
    persisted = store.get_probability_estimates(market.id)
    assert len(persisted) == 1
    assert persisted[0]["outcome"] == est.outcome.value
    assert float(persisted[0]["model_probability"]) == est.model_probability


@pytest.mark.asyncio
async def test_observe_mode_blocks_placement(tmp_path: Path) -> None:
    market = _market()
    est = _estimate(market)
    sig = _signal(market, est)

    policy = Policy()  # mode defaults to OBSERVE

    rt = Runtime(
        policy=policy,
        gamma=StubGammaAdapter([market]),
        clob=PaperCLOBAdapter(),
        logger=ImmutableLogger(tmp_path / "imm.jsonl"),
        state=RiskState(bankroll_usdc=policy.risk.bankroll_usdc),
    )

    result = await rt.evaluate_candidate(
        signal=sig,
        estimate=est,
        market=market,
        strategy=Strategy.EXTERNAL_ODDS_DIVERGENCE,
    )
    assert result["placed"] is False
    assert result["reason"] == "RISK_REJECTED"


