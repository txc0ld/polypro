"""Risk Governor — deterministic final approval (PRD §10).

Every code path that mutates exposure must funnel through this module.
The governor can reject, reduce size, demand human approval, or trigger
the global kill switch. It does not call the network.
"""

from __future__ import annotations

from .config import Policy
from .kelly import (
    confidence_multiplier,
    fractional_kelly,
    liquidity_multiplier,
    raw_kelly,
    resolution_multiplier,
)
from .types import Market, Mode, ProbabilityEstimate, RiskDecision, RiskState, Side


# Hard caps that apply on top of the percentage caps for the first live day (PRD §10.3).
FIRST_LIVE_DAY_HARD_USDC = {
    "max_order_usdc": 10.0,
    "max_market_position_usdc": 25.0,
    "max_event_exposure_usdc": 50.0,
    "max_daily_loss_usdc": 15.0,
    "max_trades": 5,
}


class KillSwitch(Exception):
    """Raised when the governor decides the runtime must stop accepting orders."""


def evaluate(
    *,
    policy: Policy,
    estimate: ProbabilityEstimate,
    market: Market,
    side: Side,
    state: RiskState,
    target_usdc: float | None = None,
) -> RiskDecision:
    """Run all gates from PRD §10. Returns a RiskDecision; never raises for
    a normal rejection — only raises ``KillSwitch`` on integrity failures.
    """
    caps: list[str] = []
    reasons: list[str] = []

    # --- Hard refusal gates -------------------------------------------------
    if policy.mode is Mode.LOCKDOWN:
        return RiskDecision(approved=False, reason_codes=["MODE_LOCKDOWN"])
    if policy.mode is Mode.OBSERVE:
        return RiskDecision(approved=False, reason_codes=["MODE_OBSERVE"])

    if estimate.uncertainty > policy.kelly.max_model_uncertainty:
        reasons.append("UNCERTAINTY_OVER_CAP")
    if estimate.source_confidence < policy.risk.min_confidence:
        reasons.append("CONFIDENCE_BELOW_MIN")
    if market.market_quality < policy.risk.min_market_quality:
        reasons.append("MARKET_QUALITY_BELOW_MIN")
    if estimate.resolution_risk > policy.risk.max_resolution_risk:
        reasons.append("RESOLUTION_RISK_OVER_CAP")
    if estimate.edge_after_costs < policy.kelly.min_effective_edge:
        reasons.append("EDGE_BELOW_MIN")

    if state.daily_loss_usdc / max(state.bankroll_usdc, 1e-9) >= (
        policy.risk.max_daily_loss_pct / 100.0
    ):
        reasons.append("DAILY_LOSS_CAP_HIT")
    if state.weekly_loss_usdc / max(state.bankroll_usdc, 1e-9) >= (
        policy.risk.max_weekly_loss_pct / 100.0
    ):
        reasons.append("WEEKLY_LOSS_CAP_HIT")
    if state.open_markets >= policy.risk.max_open_markets:
        reasons.append("OPEN_MARKETS_CAP_HIT")
    if state.orders_in_last_minute >= policy.risk.max_orders_per_minute:
        reasons.append("ORDER_RATE_CAP_HIT")

    if reasons:
        return RiskDecision(approved=False, reason_codes=reasons)

    # --- Sizing -------------------------------------------------------------
    rk = raw_kelly(estimate.market_price, estimate.model_probability, estimate.outcome)
    if rk <= 0:
        return RiskDecision(approved=False, reason_codes=["NO_POSITIVE_KELLY"])

    # Estimate the target $ for liquidity multiplier; fall back to a tiny seed.
    target_usdc = target_usdc or (
        rk * policy.kelly.fraction * state.bankroll_usdc
    ) or 1.0

    fk = fractional_kelly(
        rk,
        kelly_fraction=policy.kelly.fraction,
        confidence_multiplier=confidence_multiplier(
            estimate.source_confidence, estimate.uncertainty
        ),
        liquidity_multiplier=liquidity_multiplier(
            market.depth_within_5c_usd, target_usdc
        ),
        resolution_multiplier=resolution_multiplier(
            estimate.resolution_risk, policy.risk.max_resolution_risk
        ),
        portfolio_multiplier=_portfolio_multiplier(state, policy),
    )

    size_usdc = fk * state.bankroll_usdc

    # --- Position / event / category caps (PRD §10.2) ----------------------
    market_cap = state.bankroll_usdc * (policy.risk.max_single_market_position_pct / 100.0)
    used_market = state.used_market_usdc.get(market.id, 0.0)
    headroom_market = max(0.0, market_cap - used_market)
    if size_usdc > headroom_market:
        size_usdc = headroom_market
        caps.append("MARKET_CAP")

    if market.event_id:
        event_cap = state.bankroll_usdc * (policy.risk.max_single_event_exposure_pct / 100.0)
        used_event = state.used_event_usdc.get(market.event_id, 0.0)
        headroom_event = max(0.0, event_cap - used_event)
        if size_usdc > headroom_event:
            size_usdc = headroom_event
            caps.append("EVENT_CAP")

    if market.category:
        cat_cap = state.bankroll_usdc * (policy.risk.max_category_exposure_pct / 100.0)
        used_cat = state.used_category_usdc.get(market.category, 0.0)
        headroom_cat = max(0.0, cat_cap - used_cat)
        if size_usdc > headroom_cat:
            size_usdc = headroom_cat
            caps.append("CATEGORY_CAP")

    # --- First-live-day hard $ caps (PRD §10.3) ----------------------------
    if policy.mode is Mode.LIVE_TINY:
        if size_usdc > FIRST_LIVE_DAY_HARD_USDC["max_order_usdc"]:
            size_usdc = FIRST_LIVE_DAY_HARD_USDC["max_order_usdc"]
            caps.append("FIRST_DAY_ORDER_CAP")
        position_after = used_market + size_usdc
        if position_after > FIRST_LIVE_DAY_HARD_USDC["max_market_position_usdc"]:
            size_usdc = max(
                0.0,
                FIRST_LIVE_DAY_HARD_USDC["max_market_position_usdc"] - used_market,
            )
            caps.append("FIRST_DAY_MARKET_POSITION_CAP")

    if size_usdc <= 0:
        return RiskDecision(
            approved=False,
            raw_kelly=rk,
            fractional_kelly=fk,
            reason_codes=["NO_HEADROOM"],
            caps_applied=caps,
        )

    # SELL is reduce-only — must be backed by an existing long. The check
    # belongs in the order formatter (which knows current balance), so we
    # only mark it here for the audit trail.
    if side is Side.SELL:
        caps.append("REDUCE_ONLY_REQUIRED")

    return RiskDecision(
        approved=True,
        approved_size_usdc=size_usdc,
        raw_kelly=rk,
        fractional_kelly=fk,
        caps_applied=caps,
        reason_codes=[],
    )


def _portfolio_multiplier(state: RiskState, policy: Policy) -> float:
    """Shrink size as we approach the open-markets cap or the daily-loss cap."""
    open_ratio = state.open_markets / max(policy.risk.max_open_markets, 1)
    open_factor = max(0.0, 1.0 - open_ratio)

    daily_loss_cap = state.bankroll_usdc * (policy.risk.max_daily_loss_pct / 100.0)
    if daily_loss_cap <= 0:
        loss_factor = 0.0
    else:
        loss_factor = max(0.0, 1.0 - state.daily_loss_usdc / daily_loss_cap)

    return open_factor * loss_factor


def assert_kill_conditions(state: RiskState, policy: Policy) -> None:
    """Raise KillSwitch if any PRD §10.5 kill condition holds.

    Called from the post-order hook on every fill / order update.
    """
    if state.bankroll_usdc < 0:
        raise KillSwitch("WALLET_BALANCE_NEGATIVE")
    if (
        state.daily_loss_usdc / max(state.bankroll_usdc, 1e-9)
        >= (policy.risk.max_daily_loss_pct / 100.0)
    ):
        raise KillSwitch("DAILY_LOSS_CAP_HIT")
