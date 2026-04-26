"""CLOB Order Formatter (PRD §11, §14.4).

Pure validation + formatting. No network. The CLOB adapter is what actually
submits the payload this module produces.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_DOWN, Decimal
from uuid import uuid4

from .config import Policy
from .types import (
    FormattedOrder,
    Market,
    Mode,
    OrderPayload,
    OrderType,
    ProbabilityEstimate,
    RiskDecision,
    Side,
    Strategy,
)


def _align_to_tick(price: float, tick_size: float, side: Side) -> Decimal:
    """Round price to the nearest tick. BUY rounds down, SELL rounds up so
    we never cross fair value through rounding.
    """
    p = Decimal(str(price))
    t = Decimal(str(tick_size))
    if t == 0:
        raise ValueError("tick_size cannot be 0")
    n = p / t
    if side is Side.BUY:
        n = n.to_integral_value(rounding="ROUND_FLOOR")
    else:
        n = n.to_integral_value(rounding="ROUND_CEILING")
    return (n * t).quantize(t, rounding=ROUND_HALF_DOWN)


def format_order(
    *,
    policy: Policy,
    market: Market,
    estimate: ProbabilityEstimate,
    decision: RiskDecision,
    side: Side,
    strategy: Strategy,
    order_type: OrderType,
    current_token_balance: float = 0.0,
    risk_ref: str | None = None,
    evidence_ref: str | None = None,
) -> FormattedOrder:
    """Run every formatter validation, return a FormattedOrder.

    Returns ``rejected=True`` for any policy/structural failure. Never raises
    for ordinary rejections — caller logs the reason_codes.
    """
    reasons: list[str] = []

    if not decision.approved:
        reasons.append("RISK_NOT_APPROVED")
    if decision.approved_size_usdc <= 0:
        reasons.append("ZERO_SIZE")
    if not evidence_ref:
        reasons.append("EVIDENCE_REF_MISSING")

    if not estimate.token_id:
        reasons.append("TOKEN_ID_UNKNOWN")
    if market.tick_size is None and policy.orders.require_tick_size:
        reasons.append("TICK_SIZE_UNKNOWN")
    if market.fee_rate_bps is None and policy.orders.require_fee_rate:
        reasons.append("FEE_RATE_UNKNOWN")
    if market.min_order_size is None and policy.orders.require_min_order_size:
        reasons.append("MIN_ORDER_SIZE_UNKNOWN")

    # Order-type policy
    if policy.mode is Mode.LIVE_TINY:
        if order_type not in policy.orders.allowed_types_live_tiny:
            reasons.append("ORDER_TYPE_NOT_ALLOWED_LIVE_TINY")
    if order_type is OrderType.FOK and not policy.orders.allow_market_orders:
        # FOK is allowed only after live maturity; in initial modes it's blocked.
        reasons.append("FOK_BLOCKED")

    # Reduce-only emulation for SELL (PRD §11.3)
    size_units = decision.approved_size_usdc / max(estimate.market_price, 1e-9)
    if side is Side.SELL and size_units > current_token_balance + 1e-9:
        reasons.append("SELL_EXCEEDS_BALANCE")

    if reasons:
        return FormattedOrder(
            ready_to_submit=False,
            order_payload=None,
            rejected=True,
            reason_codes=reasons,
            risk_ref=risk_ref,
            evidence_ref=evidence_ref,
        )

    # All gates passed — build the payload.
    aligned_price = _align_to_tick(estimate.market_price, market.tick_size, side)
    if not (Decimal("0") < aligned_price < Decimal("1")):
        return FormattedOrder(
            ready_to_submit=False,
            order_payload=None,
            rejected=True,
            reason_codes=["PRICE_OUT_OF_BOUNDS_AFTER_TICK_ALIGN"],
            risk_ref=risk_ref,
            evidence_ref=evidence_ref,
        )

    # Size: convert USDC into token units, floor to min_order_size grid.
    min_size = market.min_order_size or 0.0
    if min_size > 0:
        size_units = math.floor(size_units / min_size) * min_size
    if size_units < min_size:
        return FormattedOrder(
            ready_to_submit=False,
            order_payload=None,
            rejected=True,
            reason_codes=["SIZE_BELOW_MIN_ORDER_SIZE"],
            risk_ref=risk_ref,
            evidence_ref=evidence_ref,
        )

    payload = OrderPayload(
        tokenID=estimate.token_id,
        side=side,
        price=str(aligned_price),
        size=f"{size_units:.6f}".rstrip("0").rstrip(".") or "0",
        orderType=order_type,
        strategy=strategy,
        marketId=market.id,
        eventId=market.event_id,
        maxPositionAfterFill=f"{decision.approved_size_usdc:.6f}",
        clientOrderId=str(uuid4()),
    )

    return FormattedOrder(
        ready_to_submit=True,
        order_payload=payload,
        rejected=False,
        reason_codes=[],
        risk_ref=risk_ref,
        evidence_ref=evidence_ref,
    )
