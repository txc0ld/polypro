"""CLOB adapter (PRD §7.1, §11).

Order book reads + order placement. The real implementation talks to the
Polymarket CLOB REST API and the user/market WebSocket channels. The stub
echoes orders back for paper mode.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from ..types import OrderPayload, Position


class CLOBAdapter(Protocol):
    async def order_book(self, token_id: str) -> dict: ...
    async def place_order(self, payload: OrderPayload) -> dict: ...
    async def cancel_order(self, exchange_order_id: str) -> bool: ...
    async def get_positions(self) -> list[Position]: ...
    async def get_token_balance(self, token_id: str) -> float: ...


class PaperCLOBAdapter:
    """Records orders and reports them as filled at requested price.

    Use for paper / observe modes. Never makes a network call.
    """

    def __init__(self) -> None:
        self.placed: list[dict] = []
        self.cancelled: list[str] = []
        self._positions: dict[tuple[str, str], Position] = {}
        self._balances: dict[str, float] = {}

    async def order_book(self, token_id: str) -> dict:
        return {"token_id": token_id, "bids": [], "asks": []}

    async def place_order(self, payload: OrderPayload) -> dict:
        record = {
            "exchange_order_id": str(uuid4()),
            "client_order_id": payload.clientOrderId,
            "token_id": payload.tokenID,
            "market_id": payload.marketId,
            "side": payload.side.value,
            "price": payload.price,
            "size": payload.size,
            "order_type": payload.orderType.value,
            "status": "FILLED",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.placed.append(record)

        # Update paper position
        size = float(payload.size)
        price = float(payload.price)
        key = (payload.marketId, payload.tokenID)
        if payload.side.value == "BUY":
            existing = self._positions.get(key)
            if existing is None:
                self._positions[key] = Position(
                    market_id=payload.marketId,
                    token_id=payload.tokenID,
                    outcome="YES",  # paper adapter doesn't track outcome name
                    size=size,
                    avg_price=price,
                )
                self._balances[payload.tokenID] = self._balances.get(payload.tokenID, 0.0) + size
            else:
                new_size = existing.size + size
                new_avg = (existing.size * existing.avg_price + size * price) / new_size
                self._positions[key] = existing.model_copy(
                    update={"size": new_size, "avg_price": new_avg}
                )
                self._balances[payload.tokenID] = self._balances.get(payload.tokenID, 0.0) + size
        else:  # SELL
            existing = self._positions.get(key)
            if existing is not None:
                new_size = max(0.0, existing.size - size)
                self._positions[key] = existing.model_copy(update={"size": new_size})
                self._balances[payload.tokenID] = max(
                    0.0, self._balances.get(payload.tokenID, 0.0) - size
                )

        return record

    async def cancel_order(self, exchange_order_id: str) -> bool:
        self.cancelled.append(exchange_order_id)
        return True

    async def get_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.size > 0]

    async def get_token_balance(self, token_id: str) -> float:
        return self._balances.get(token_id, 0.0)
