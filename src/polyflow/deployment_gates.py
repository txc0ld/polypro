"""Five-Gate Deployment Workflow (Protocol §7).

The protocol mandates a strict sequence:

  1. Manual validation on 5+ historical markets.
  2. Coded + full simulation suite (own data).
  3. Ghost-mode real-wallet execution testing (72h).
  4. Live dry-run with 0.1% bankroll for 7 days.
  5. Full deployment.

This module is the gate runner. It does NOT execute the gates — operators do
that. It only validates the artifacts each gate produces and refuses to
advance if any are missing or fail thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateInputs:
    # Gate 1
    historical_markets_validated: int
    historical_pnl_total_usd: float

    # Gate 2 (simulation)
    simulation_trades: int
    simulation_ev_per_trade_usd: float
    simulation_max_drawdown_usd: float
    simulation_realized_win_rate: float

    # Gate 3 (ghost-mode)
    ghost_mode_hours: float
    ghost_mode_orders_attempted: int
    ghost_mode_unhandled_failure_modes: int  # not in known-fix list

    # Gate 4 (live dry-run)
    live_dryrun_days: float
    live_dryrun_bankroll_pct_used: float
    live_dryrun_pnl_total_usd: float
    live_dryrun_kelly_breaches: int


# Hard thresholds — Protocol §2/§7 floors.
HISTORICAL_MIN = 5
SIMULATION_MIN_TRADES = 100
SIMULATION_MIN_EV_PER_TRADE = 0.12          # USD per trade
GHOST_MIN_HOURS = 72.0
LIVE_DRYRUN_MIN_DAYS = 7.0
LIVE_DRYRUN_MAX_BANKROLL_PCT = 0.1


@dataclass(frozen=True)
class GateDecision:
    stage: int                    # furthest cleared stage (0..5)
    promote: bool                 # ready for full deployment?
    blockers: tuple[str, ...]
    next_action: str


def evaluate(inputs: GateInputs) -> GateDecision:
    """Walk the gates in order; first failure short-circuits."""

    # Gate 1
    if inputs.historical_markets_validated < HISTORICAL_MIN:
        return GateDecision(
            stage=0,
            promote=False,
            blockers=(f"GATE1_HISTORICAL<{HISTORICAL_MIN}",),
            next_action="Validate the idea on at least 5 historical markets manually before coding.",
        )

    # Gate 2
    blockers: list[str] = []
    if inputs.simulation_trades < SIMULATION_MIN_TRADES:
        blockers.append(f"SIMULATION_TRADES<{SIMULATION_MIN_TRADES}")
    if inputs.simulation_ev_per_trade_usd < SIMULATION_MIN_EV_PER_TRADE:
        blockers.append(f"SIM_EV_PER_TRADE<{SIMULATION_MIN_EV_PER_TRADE}")
    if inputs.simulation_max_drawdown_usd < 0:
        blockers.append("SIM_MDD_NEGATIVE_DATA")  # paranoid input check
    if blockers:
        return GateDecision(
            stage=1, promote=False, blockers=tuple(blockers),
            next_action="Re-run the full simulation suite against ≥30 days of own tick data; need EV ≥ $0.12/trade and ≥100 trades.",
        )

    # Gate 3
    blockers = []
    if inputs.ghost_mode_hours < GHOST_MIN_HOURS:
        blockers.append(f"GHOST_HOURS<{GHOST_MIN_HOURS}")
    if inputs.ghost_mode_orders_attempted < 50:
        blockers.append("GHOST_ATTEMPTED_ORDERS<50")
    if inputs.ghost_mode_unhandled_failure_modes > 0:
        blockers.append("GHOST_UNHANDLED_FAILURES>0")
    if blockers:
        return GateDecision(
            stage=2, promote=False, blockers=tuple(blockers),
            next_action="Run ghost-mode for ≥72h with ≥50 attempted orders and zero unhandled failure modes.",
        )

    # Gate 4
    blockers = []
    if inputs.live_dryrun_days < LIVE_DRYRUN_MIN_DAYS:
        blockers.append(f"LIVE_DRYRUN_DAYS<{LIVE_DRYRUN_MIN_DAYS}")
    if inputs.live_dryrun_bankroll_pct_used > LIVE_DRYRUN_MAX_BANKROLL_PCT:
        blockers.append("LIVE_DRYRUN_BANKROLL_OVER_0.1PCT")
    if inputs.live_dryrun_kelly_breaches > 0:
        blockers.append("LIVE_DRYRUN_KELLY_BREACHES>0")
    if blockers:
        return GateDecision(
            stage=3, promote=False, blockers=tuple(blockers),
            next_action="Run live dry-run at 0.1% bankroll for ≥7 days with zero Kelly breaches.",
        )

    return GateDecision(
        stage=4, promote=True, blockers=(),
        next_action="All four pre-deployment gates passed. Promote to full deployment under the runtime's normal mode progression.",
    )
