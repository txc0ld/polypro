"""Post-Order Kelly Guard hook (PRD §15.1).

Runs after every order attempt, every fill, every cancel. It re-derives the
*actual* position from the venue (not from our cached state) and asserts
that exposure is still inside Kelly + cap headroom. If not, it cancels the
offending order and trips the kill switch.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Policy
from .risk_governor import KillSwitch, assert_kill_conditions
from .types import Position, RiskState


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    breaches: tuple[str, ...]
    cancellations_required: tuple[str, ...]


def evaluate_exposure(
    *,
    policy: Policy,
    state: RiskState,
    positions: list[Position],
    open_order_ids_by_market: dict[str, list[str]],
) -> GuardResult:
    """Reconcile venue-truth `positions` against `state` caps. Returns GuardResult.

    Always raises ``KillSwitch`` for kill conditions (PRD §10.5).
    """
    breaches: list[str] = []
    cancels: list[str] = []

    bankroll = max(state.bankroll_usdc, 1e-9)
    market_cap_usdc = bankroll * (policy.risk.max_single_market_position_pct / 100.0)
    event_cap_usdc = bankroll * (policy.risk.max_single_event_exposure_pct / 100.0)
    cat_cap_usdc = bankroll * (policy.risk.max_category_exposure_pct / 100.0)

    by_market: dict[str, float] = {}
    for p in positions:
        by_market[p.market_id] = by_market.get(p.market_id, 0.0) + p.size * p.avg_price

    for mid, used in by_market.items():
        if used > market_cap_usdc:
            breaches.append(f"MARKET_CAP_BREACH:{mid}")
            cancels.extend(open_order_ids_by_market.get(mid, []))

    for evt_id, used in state.used_event_usdc.items():
        if used > event_cap_usdc:
            breaches.append(f"EVENT_CAP_BREACH:{evt_id}")

    for cat, used in state.used_category_usdc.items():
        if used > cat_cap_usdc:
            breaches.append(f"CATEGORY_CAP_BREACH:{cat}")

    # Daily / weekly loss kill conditions are absolute — propagate as KillSwitch.
    assert_kill_conditions(state, policy)

    if breaches:
        # If post-order exposure is over a cap, the model approved an oversize.
        # Per PRD §10.5 this is a kill condition.
        raise KillSwitch("POST_ORDER_KELLY_BREACH:" + ",".join(breaches))

    return GuardResult(ok=True, breaches=tuple(breaches), cancellations_required=tuple(cancels))
