"""Order sync subagent tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from polyflow.incident import IncidentManager, State
from polyflow.persistence import SQLiteStore
from polyflow.subagents.order_sync import OrderSync


class FakeAdapter:
    def __init__(self, *, open_orders: list[dict]) -> None:
        self.open_orders = open_orders
        self.cancelled: list[str] = []

    async def get_open_orders(self) -> list[dict]:
        return list(self.open_orders)

    async def cancel_order(self, exchange_order_id: str) -> bool:
        self.cancelled.append(exchange_order_id)
        # Pretend it succeeded by removing from upstream
        self.open_orders = [
            o for o in self.open_orders if o.get("exchange_order_id") != exchange_order_id
        ]
        return True


@pytest.mark.asyncio
async def test_fresh_order_persisted_no_action() -> None:
    store = SQLiteStore(":memory:")
    incidents = IncidentManager()
    order = {
        "exchange_order_id": "ord-1",
        "client_order_id": "c-1",
        "market_id": "m1",
        "token_id": "t-yes",
        "side": "BUY",
        "price": 0.55,
        "size": 10,
        "status": "OPEN",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    sync = OrderSync(adapter=FakeAdapter(open_orders=[order]), store=store, incidents=incidents)
    report = await sync.tick()

    assert report.open_count == 1
    assert report.stuck_cancelled == ()
    assert report.divergences == ()
    assert incidents.state is State.HEALTHY


@pytest.mark.asyncio
async def test_stuck_order_is_cancelled_and_degrades() -> None:
    store = SQLiteStore(":memory:")
    incidents = IncidentManager()
    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    order = {
        "exchange_order_id": "ord-2",
        "market_id": "m2",
        "token_id": "t-yes",
        "side": "BUY",
        "price": 0.50,
        "size": 5,
        "status": "OPEN",
        "ts": old_ts,
    }
    adapter = FakeAdapter(open_orders=[order])
    sync = OrderSync(adapter=adapter, store=store, incidents=incidents, max_age_minutes=5.0)
    report = await sync.tick()

    assert "ord-2" in adapter.cancelled
    assert report.stuck_cancelled == ("ord-2",)
    assert incidents.state is State.DEGRADED


@pytest.mark.asyncio
async def test_divergence_detected_on_missing_clob_order() -> None:
    store = SQLiteStore(":memory:")
    incidents = IncidentManager()
    # Simulate: store has an order the CLOB doesn't.
    store.upsert_open_order(
        exchange_order_id="ghost",
        client_order_id="c-g",
        market_id="m3",
        token_id="t-yes",
        side="BUY",
        price=0.50,
        size=5,
        status="OPEN",
    )
    sync = OrderSync(adapter=FakeAdapter(open_orders=[]), store=store, incidents=incidents)
    report = await sync.tick()

    assert "ghost" in report.divergences
    assert incidents.state is State.DEGRADED
    # Ghost was deleted from the snapshot to keep state in sync with truth.
    assert "ghost" not in {o["exchange_order_id"] for o in store.get_open_orders()}
