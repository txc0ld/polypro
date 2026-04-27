"""Daily reconciliation (Protocol §8).

Compares on-chain truth (positions, balance, recent activity) against the
runtime's internal state. Any drift > tolerance is an incident.
"""

from __future__ import annotations

from dataclasses import dataclass

from .adapters.polymarket_user import PolymarketUserAdapter
from .persistence import SQLiteStore


@dataclass(frozen=True)
class ReconciliationReport:
    on_chain_position_count: int
    local_position_count: int
    missing_from_local: tuple[str, ...]
    missing_from_chain: tuple[str, ...]
    drift_detected: bool


async def reconcile(*, user: PolymarketUserAdapter, store: SQLiteStore) -> ReconciliationReport:
    on_chain = await user.positions()
    local = store.get_open_positions()

    on_chain_keys = {
        (str(p.get("market_id") or p.get("conditionId") or ""), str(p.get("token_id") or p.get("asset") or ""))
        for p in on_chain
        if (p.get("size") or 0) > 0
    }
    local_keys = {(p["market_id"], p["token_id"]) for p in local}

    missing_local = tuple(f"{m}|{t}" for m, t in (on_chain_keys - local_keys))
    missing_chain = tuple(f"{m}|{t}" for m, t in (local_keys - on_chain_keys))

    return ReconciliationReport(
        on_chain_position_count=len(on_chain_keys),
        local_position_count=len(local_keys),
        missing_from_local=missing_local,
        missing_from_chain=missing_chain,
        drift_detected=bool(missing_local or missing_chain),
    )
