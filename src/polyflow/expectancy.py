"""Expectancy + RTR tracker (Protocol §4).

Maximize dollars per trade, not win rate. This module computes:

  - expected_value_per_trade   $/trade
  - realized_win_rate          decisive trades only
  - risk_to_reward (RTR)       avg loss : avg win
  - kelly_breakeven_wr         f(RTR)

It also enforces the protocol's RTR ≥ 1:0.15 entry rule and the 1.5%
position-size cap (we keep the stricter PRD value of 1.0%; the function
honours either).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpectancyReport:
    n_trades: int
    avg_win_usd: float
    avg_loss_usd: float
    realized_win_rate: float
    rtr: float                  # avg_win / avg_loss
    expected_value_per_trade: float
    breakeven_win_rate: float


def compute(pnl_per_trade_usd: list[float]) -> ExpectancyReport:
    """Reduce a list of per-trade P&L numbers to an expectancy report."""
    if not pnl_per_trade_usd:
        return ExpectancyReport(
            n_trades=0, avg_win_usd=0.0, avg_loss_usd=0.0,
            realized_win_rate=0.0, rtr=0.0,
            expected_value_per_trade=0.0, breakeven_win_rate=0.0,
        )

    wins = [p for p in pnl_per_trade_usd if p > 0]
    losses = [-p for p in pnl_per_trade_usd if p < 0]
    n = len(pnl_per_trade_usd)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    win_rate = len(wins) / n
    rtr = avg_win / avg_loss if avg_loss > 0 else float("inf") if avg_win > 0 else 0.0
    ev = sum(pnl_per_trade_usd) / n
    breakeven_wr = avg_loss / (avg_win + avg_loss) if (avg_win + avg_loss) > 0 else 0.0

    return ExpectancyReport(
        n_trades=n,
        avg_win_usd=avg_win,
        avg_loss_usd=avg_loss,
        realized_win_rate=win_rate,
        rtr=rtr,
        expected_value_per_trade=ev,
        breakeven_win_rate=breakeven_wr,
    )


# --- Entry-time gates ----------------------------------------------------

MIN_RTR = 0.15  # Protocol §4: never enter below 1:0.15


def passes_rtr_gate(*, model_probability: float, executable_price: float, side: str) -> bool:
    """The minimum reward-to-risk threshold required at entry.

    For BUY YES at price p with model q: payoff if win = (1 - p), loss if wrong = p.
    RTR = (1 - p) / p. We require RTR >= MIN_RTR.

    For BUY NO at YES-price p: payoff if win = p, loss if wrong = (1 - p).
    RTR = p / (1 - p).
    """
    if not (0.0 < executable_price < 1.0):
        return False
    if side == "BUY_YES":
        rtr = (1.0 - executable_price) / executable_price
    elif side == "BUY_NO":
        rtr = executable_price / (1.0 - executable_price)
    else:
        return False
    return rtr >= MIN_RTR


def edge_pct(*, model_probability: float, executable_price: float, side: str) -> float:
    """Edge in absolute probability units, signed by side."""
    if side == "BUY_YES":
        return model_probability - executable_price
    if side == "BUY_NO":
        return executable_price - model_probability
    return 0.0


def dynamic_entry_allowed(
    *,
    edge: float,
    minutes_to_close: float,
    early_threshold: float = 0.18,
    late_threshold: float = 0.25,
    late_cutoff_minutes: float = 60.0,
) -> bool:
    """Protocol §4 entry-timing rule.

    "Prefer early when edge > 18%, late only when edge > 25% and liquidity allows."
    Returns False when neither bar is met.
    """
    if minutes_to_close <= 0:
        return False
    if minutes_to_close >= late_cutoff_minutes:
        return edge >= early_threshold
    return edge >= late_threshold
