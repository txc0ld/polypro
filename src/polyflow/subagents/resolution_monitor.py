"""Resolution Monitor — closes the calibration loop.

Periodically scans the watchlist for markets that have closed, fetches their
final outcome from Gamma, persists the resolution, and writes
``calibration_observations`` rows pairing every prior probability estimate
against the realized outcome.

The PRD calibration report (§8.5) and promotion gate (§20.3) both depend on
this loop running.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..adapters.gamma import GammaAdapter
from ..persistence import SQLiteStore


@dataclass(frozen=True)
class ResolutionResult:
    market_id: str
    outcome: str  # 'YES' or 'NO'
    closing_price_yes: float


def determine_outcome(*, best_bid: float | None, best_ask: float | None) -> str | None:
    """Heuristic: a fully resolved market trades YES at ~1.0 (winner) or ~0.0 (loser).

    Returns 'YES', 'NO', or None if the market hasn't fully settled.
    """
    if best_bid is None or best_ask is None:
        return None
    mid = (best_bid + best_ask) / 2.0
    if mid >= 0.97:
        return "YES"
    if mid <= 0.03:
        return "NO"
    return None  # not yet settled


class ResolutionMonitor:
    def __init__(self, *, gamma: GammaAdapter, store: SQLiteStore) -> None:
        self.gamma = gamma
        self.store = store

    async def tick(self) -> list[ResolutionResult]:
        """One resolution-check pass over watching markets that have closed."""
        results: list[ResolutionResult] = []
        watching = self.store.get_markets_by_status("watching")
        now = datetime.now(timezone.utc)

        for row in watching:
            close_time = row.get("close_time")
            if not close_time:
                continue
            try:
                ct = datetime.fromisoformat(close_time)
                if ct.tzinfo is None:
                    ct = ct.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if ct > now:
                continue

            market = await self.gamma.get_market(row["id"])
            if market is None:
                continue
            outcome = determine_outcome(best_bid=market.best_bid, best_ask=market.best_ask)
            if outcome is None:
                continue

            self.store.record_resolution(market_id=market.id, outcome=outcome)
            self.store.set_market_status(market.id, "resolved")

            # Generate calibration observations from every prior probability estimate.
            for est in self.store.get_probability_estimates(market.id):
                est_outcome = est["outcome"]
                # Realized 1 if our estimate predicted the winner; 0 otherwise.
                realized = (est_outcome == outcome)
                self.store.insert_calibration_observation(
                    market_id=market.id,
                    token_id=est["token_id"],
                    predicted_probability=float(est["model_probability"]),
                    realized=realized,
                )

            results.append(
                ResolutionResult(
                    market_id=market.id,
                    outcome=outcome,
                    closing_price_yes=market.best_bid or 0.0,
                )
            )
        return results
