"""Portfolio Sentinel subagent (PRD §16.3).

Pulls truth from the CLOB adapter, reconciles against ``RiskState``, and
trips the incident manager if anything is off. Final authority on portfolio
safety.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable

from ..adapters.clob import CLOBAdapter
from ..config import Policy
from ..incident import IncidentManager
from ..post_order_hook import evaluate_exposure
from ..risk_governor import KillSwitch
from ..types import RiskState


class PortfolioSentinel:
    def __init__(
        self,
        *,
        policy: Policy,
        clob: CLOBAdapter,
        state: RiskState,
        incidents: IncidentManager,
        on_breach: Callable[[str, str], Awaitable[None]] | None = None,
        max_user_channel_age_seconds: int = 90,
    ) -> None:
        self.policy = policy
        self.clob = clob
        self.state = state
        self.incidents = incidents
        self.on_breach = on_breach
        self.max_user_channel_age_seconds = max_user_channel_age_seconds
        self.last_user_channel_event: datetime | None = None

    async def tick(self) -> None:
        positions = await self.clob.get_positions()

        try:
            evaluate_exposure(
                policy=self.policy,
                state=self.state,
                positions=positions,
                open_order_ids_by_market={},
            )
        except KillSwitch as ks:
            self.incidents.trip_killed(
                code="POST_ORDER_KELLY_BREACH",
                detail=str(ks),
                actor="portfolio_sentinel",
            )
            if self.on_breach:
                await self.on_breach("POST_ORDER_KELLY_BREACH", str(ks))
            return

        # User-channel staleness check
        if self.last_user_channel_event is not None:
            age = (datetime.now(timezone.utc) - self.last_user_channel_event).total_seconds()
            if age > self.max_user_channel_age_seconds:
                self.incidents.trip_lockdown(
                    code="USER_CHANNEL_STALE",
                    detail=f"age={age:.0f}s",
                    actor="portfolio_sentinel",
                )
