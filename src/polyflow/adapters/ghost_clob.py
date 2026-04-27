"""Ghost-Mode CLOB adapter (Protocol §5).

Wraps the real ``PolymarketCLOBTradeAdapter`` but deliberately runs against a
wallet that holds 0 USDC. Every order the runtime would submit goes through
the full local validation + signing path; the actual ``POST /order`` is sent;
Polymarket rejects for "insufficient balance" / nonce / etc., and we record
every failure mode for replay-as-test in the simulator.

Protocol mandate: at least 72 hours of ghost-mode against any new strategy
before any capital touches the wire.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

import httpx

from .polymarket_clob_trade import PolymarketCLOBTradeAdapter
from ..types import OrderPayload, Position


@dataclass
class GhostFailure:
    ts: str
    market_id: str
    token_id: str
    side: str
    reason: str
    detail: str


class GhostCLOBAdapter:
    """Drop-in replacement for ``CLOBAdapter`` that exercises the live wire path
    against a wallet with no funds, recording every rejection.
    """

    def __init__(
        self,
        *,
        wrapped: PolymarketCLOBTradeAdapter,
        log_path: str | Path,
    ) -> None:
        self.wrapped = wrapped
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._failures: list[GhostFailure] = []
        self._lock = RLock()

    @property
    def failures(self) -> list[GhostFailure]:
        with self._lock:
            return list(self._failures)

    async def order_book(self, token_id: str) -> dict:
        return await self.wrapped.order_book(token_id)

    async def get_positions(self) -> list[Position]:
        return await self.wrapped.get_positions()

    async def get_token_balance(self, token_id: str) -> float:
        # Ghost-mode wallet: zero balance regardless of what the API says.
        return 0.0

    async def cancel_order(self, exchange_order_id: str) -> bool:
        try:
            return await self.wrapped.cancel_order(exchange_order_id)
        except httpx.HTTPStatusError as e:
            self._record(
                market_id="", token_id="", side="",
                reason=f"CANCEL_HTTP_{e.response.status_code}",
                detail=e.response.text[:300],
            )
            return False

    async def place_order(self, payload: OrderPayload, *, neg_risk: bool = False) -> dict:
        """Always attempt the wire submit. Capture every failure mode."""
        try:
            return await self.wrapped.place_order(payload, neg_risk=neg_risk)
        except httpx.HTTPStatusError as e:
            self._record(
                market_id=payload.marketId,
                token_id=payload.tokenID,
                side=payload.side.value,
                reason=f"HTTP_{e.response.status_code}",
                detail=self._extract_error(e.response),
            )
            return {"ghost": True, "rejected": True, "status": e.response.status_code}
        except Exception as exc:  # noqa: BLE001
            self._record(
                market_id=payload.marketId,
                token_id=payload.tokenID,
                side=payload.side.value,
                reason=type(exc).__name__,
                detail=str(exc)[:300],
            )
            return {"ghost": True, "rejected": True, "exception": type(exc).__name__}

    async def get_open_orders(self) -> list[dict]:
        return await self.wrapped.get_open_orders()

    # --- internals -------------------------------------------------------
    @staticmethod
    def _extract_error(resp: httpx.Response) -> str:
        try:
            data = resp.json()
            return str(data.get("error") or data)[:300]
        except (json.JSONDecodeError, ValueError):
            return resp.text[:300]

    def _record(self, *, market_id: str, token_id: str, side: str, reason: str, detail: str) -> None:
        failure = GhostFailure(
            ts=datetime.now(timezone.utc).isoformat(),
            market_id=market_id,
            token_id=token_id,
            side=side,
            reason=reason,
            detail=detail,
        )
        with self._lock:
            self._failures.append(failure)
            with self._log_path.open("ab") as f:
                f.write(
                    (
                        json.dumps(
                            {
                                "ts": failure.ts,
                                "market_id": failure.market_id,
                                "token_id": failure.token_id,
                                "side": failure.side,
                                "reason": failure.reason,
                                "detail": failure.detail,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                )


@dataclass
class GhostReport:
    total: int
    by_reason: dict[str, int] = field(default_factory=dict)


def summarize_ghost_log(path: str | Path) -> GhostReport:
    p = Path(path)
    if not p.exists():
        return GhostReport(total=0)
    by_reason: dict[str, int] = {}
    total = 0
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            reason = str(obj.get("reason") or "UNKNOWN")
            by_reason[reason] = by_reason.get(reason, 0) + 1
    return GhostReport(total=total, by_reason=by_reason)
