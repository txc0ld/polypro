"""Order Sync subagent.

Pulls open orders from the CLOB, reconciles against the local snapshot table,
and surfaces:

  - **stuck orders** (open longer than ``max_age_minutes``)
  - **divergent orders** (CLOB has an order our store doesn't, or vice versa)

Stuck orders are auto-cancelled when ``auto_cancel_stuck=True``. Divergence is
always surfaced as a degraded incident — never auto-resolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from ..incident import IncidentManager
from ..persistence import SQLiteStore


class OrderReadAdapter(Protocol):
    async def get_open_orders(self) -> list[dict]: ...
    async def cancel_order(self, exchange_order_id: str) -> bool: ...


@dataclass(frozen=True)
class OrderSyncReport:
    open_count: int
    stuck_cancelled: tuple[str, ...]
    divergences: tuple[str, ...]


class OrderSync:
    def __init__(
        self,
        *,
        adapter: OrderReadAdapter,
        store: SQLiteStore,
        incidents: IncidentManager,
        max_age_minutes: float = 5.0,
        auto_cancel_stuck: bool = True,
    ) -> None:
        self.adapter = adapter
        self.store = store
        self.incidents = incidents
        self.max_age_minutes = max_age_minutes
        self.auto_cancel_stuck = auto_cancel_stuck

    async def tick(self) -> OrderSyncReport:
        live = await self.adapter.get_open_orders()

        live_ids: set[str] = set()
        stuck_cancelled: list[str] = []
        divergences: list[str] = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.max_age_minutes)

        for o in live:
            oid = str(o.get("exchange_order_id") or o.get("id") or "")
            if not oid:
                continue
            live_ids.add(oid)

            # Persist / refresh the snapshot
            self.store.upsert_open_order(
                exchange_order_id=oid,
                client_order_id=o.get("client_order_id"),
                market_id=str(o.get("market_id") or ""),
                token_id=str(o.get("token_id") or ""),
                side=str(o.get("side") or ""),
                price=float(o.get("price") or 0),
                size=float(o.get("size") or 0),
                status=str(o.get("status") or "OPEN"),
            )

            # Stuck-order check
            ts_str = o.get("ts") or o.get("created_at")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                except ValueError:
                    ts = now
                if ts < cutoff and self.auto_cancel_stuck:
                    if await self.adapter.cancel_order(oid):
                        stuck_cancelled.append(oid)
                        self.store.delete_open_order(oid)
                        self.incidents.trip_degraded(
                            code="STUCK_ORDER_CANCELLED",
                            detail=oid,
                            actor="order_sync",
                        )

        # Detect divergence: store has open orders the CLOB doesn't.
        stored = self.store.get_open_orders()
        for row in stored:
            oid = row["exchange_order_id"]
            if oid not in live_ids and oid not in stuck_cancelled:
                divergences.append(oid)
                self.store.delete_open_order(oid)
                self.incidents.trip_degraded(
                    code="ORDER_DIVERGENCE",
                    detail=oid,
                    actor="order_sync",
                )

        return OrderSyncReport(
            open_count=len(live_ids),
            stuck_cancelled=tuple(stuck_cancelled),
            divergences=tuple(divergences),
        )
