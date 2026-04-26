"""Closing-Line Value tracker (PRD §8.5, §20.3).

Closing-line value (CLV) is one of the cleanest *leading* indicators of model
edge: did the price move in our direction by close? CLV-positive without
realized-PnL-positive can still mean the model was right and variance was
unfavorable; CLV-negative with realized-PnL-positive is a luck warning.

Convention: CLV is reported in basis points, signed so positive = favorable
move from entry to close.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CLVRecord:
    market_id: str
    token_id: str
    signal_id: str | None
    side: str  # 'BUY_YES' or 'BUY_NO'
    entry_price: float
    closing_price: float
    clv_bps: float


def compute_clv_bps(*, entry_price: float, closing_price: float, side: str) -> float:
    if not (0.0 <= entry_price <= 1.0) or not (0.0 <= closing_price <= 1.0):
        raise ValueError("prices must be in [0, 1]")
    if side == "BUY_YES":
        return (closing_price - entry_price) * 10_000
    if side == "BUY_NO":
        return (entry_price - closing_price) * 10_000
    raise ValueError(f"unknown side: {side!r}")


def make_record(
    *, market_id: str, token_id: str, signal_id: str | None,
    entry_price: float, closing_price: float, side: str,
) -> CLVRecord:
    return CLVRecord(
        market_id=market_id,
        token_id=token_id,
        signal_id=signal_id,
        side=side,
        entry_price=entry_price,
        closing_price=closing_price,
        clv_bps=compute_clv_bps(
            entry_price=entry_price, closing_price=closing_price, side=side
        ),
    )
