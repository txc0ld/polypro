"""Portfolio Sentinel subagent tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from polyflow.adapters.clob import PaperCLOBAdapter
from polyflow.config import Policy
from polyflow.incident import IncidentManager, State
from polyflow.subagents.portfolio_sentinel import PortfolioSentinel
from polyflow.types import Outcome, Position, RiskState


@pytest.mark.asyncio
async def test_clean_tick_keeps_state_healthy() -> None:
    incidents = IncidentManager()
    sentinel = PortfolioSentinel(
        policy=Policy(),
        clob=PaperCLOBAdapter(),
        state=RiskState(bankroll_usdc=1000),
        incidents=incidents,
    )
    await sentinel.tick()
    assert incidents.state is State.HEALTHY


@pytest.mark.asyncio
async def test_user_channel_stale_trips_lockdown() -> None:
    incidents = IncidentManager()
    sentinel = PortfolioSentinel(
        policy=Policy(),
        clob=PaperCLOBAdapter(),
        state=RiskState(bankroll_usdc=1000),
        incidents=incidents,
        max_user_channel_age_seconds=10,
    )
    sentinel.last_user_channel_event = datetime.now(timezone.utc) - timedelta(seconds=120)
    await sentinel.tick()
    assert incidents.state is State.LOCKDOWN


@pytest.mark.asyncio
async def test_market_cap_breach_kills_runtime() -> None:
    """A position that exceeds 1% of bankroll fires KillSwitch → KILLED."""
    incidents = IncidentManager()
    clob = PaperCLOBAdapter()
    # Simulate a $50 position on a $1000 bankroll (5% of bankroll, well above 1% cap)
    clob._positions[("m1", "t-yes")] = Position(  # type: ignore[attr-defined]
        market_id="m1", token_id="t-yes", outcome=Outcome.YES,
        size=100.0, avg_price=0.50,
    )
    sentinel = PortfolioSentinel(
        policy=Policy(),
        clob=clob,
        state=RiskState(bankroll_usdc=1000),
        incidents=incidents,
    )
    await sentinel.tick()
    assert incidents.state is State.KILLED
