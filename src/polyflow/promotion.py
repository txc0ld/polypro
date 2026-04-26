"""Live promotion gate checker (PRD §20.3).

The runtime is not allowed to step from LIVE_TINY → LIVE_STANDARD until every
condition below holds. The gate is *deterministic* — no operator override at
the code level; if any check fails, the function returns the failing reasons.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionInputs:
    observer_days: int
    paper_days: int
    paper_trades: int
    live_tiny_trades: int
    unexplained_pnl_events: int
    kelly_breaches: int
    unlogged_actions: int
    calibration_report_present: bool
    closing_line_value_positive: bool
    post_order_hook_pass_rate: float


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    reasons: tuple[str, ...]


PROMOTION_REQUIREMENTS = {
    "observer_days": 14,
    "paper_days": 30,
    "paper_trades": 200,
    "live_tiny_trades": 50,
    "max_unexplained_pnl_events": 0,
    "max_kelly_breaches": 0,
    "max_unlogged_actions": 0,
    "calibration_report_required": True,
    "closing_line_value_positive": True,
    "post_order_hook_pass_rate": 1.0,
}


def evaluate(p: PromotionInputs) -> PromotionDecision:
    fails: list[str] = []
    r = PROMOTION_REQUIREMENTS

    if p.observer_days < r["observer_days"]:
        fails.append(f"OBSERVER_DAYS<{r['observer_days']}")
    if p.paper_days < r["paper_days"]:
        fails.append(f"PAPER_DAYS<{r['paper_days']}")
    if p.paper_trades < r["paper_trades"]:
        fails.append(f"PAPER_TRADES<{r['paper_trades']}")
    if p.live_tiny_trades < r["live_tiny_trades"]:
        fails.append(f"LIVE_TINY_TRADES<{r['live_tiny_trades']}")
    if p.unexplained_pnl_events > r["max_unexplained_pnl_events"]:
        fails.append("UNEXPLAINED_PNL_EVENTS>0")
    if p.kelly_breaches > r["max_kelly_breaches"]:
        fails.append("KELLY_BREACHES>0")
    if p.unlogged_actions > r["max_unlogged_actions"]:
        fails.append("UNLOGGED_ACTIONS>0")
    if r["calibration_report_required"] and not p.calibration_report_present:
        fails.append("CALIBRATION_REPORT_MISSING")
    if r["closing_line_value_positive"] and not p.closing_line_value_positive:
        fails.append("CLV_NOT_POSITIVE")
    if p.post_order_hook_pass_rate < r["post_order_hook_pass_rate"]:
        fails.append("POST_ORDER_HOOK_PASS_RATE<1.0")

    return PromotionDecision(promote=not fails, reasons=tuple(fails))
