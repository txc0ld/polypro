"""Reality-Grade Simulator (Protocol §2).

Replays a recorded order book + trade stream against the strategy's intended
orders to produce realistic fills, slippage, fees, and gas drag. Outputs:

  - expected_value_per_trade   (USD)
  - breakeven_win_rate         (under realised RTR)
  - realised_win_rate          (decisive trades only)
  - max_drawdown_usd
  - total_fee_drag, total_gas_drag

The simulator deliberately does *not* try to model the entire universe — it
focuses on the four mechanics that distinguish Polymarket from a generic
backtest: depth-based fill probability, FIFO queue position, fee+gas drag,
and binary settlement at resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Polymarket gas drag is small (proxy meta-tx is sponsored for trading), but we
# keep a non-zero default so simulators stay honest.
DEFAULT_GAS_PER_TRADE_USD = 0.005

# Default Polymarket maker fee. Override per-market when known.
DEFAULT_MAKER_FEE_BPS = 0


@dataclass
class IntendedOrder:
    market_id: str
    side: str           # 'BUY_YES' or 'BUY_NO'
    limit_price: float  # 0 < price < 1
    size_usdc: float    # the USD we're willing to spend
    placed_at_ns: int


@dataclass
class BookLevel:
    price: float
    size_usdc: float


@dataclass
class BookSnapshot:
    """Instantaneous L2 view at a moment in time."""

    yes_bids: list[BookLevel] = field(default_factory=list)
    yes_asks: list[BookLevel] = field(default_factory=list)


@dataclass
class FillResult:
    filled_usdc: float
    avg_price: float
    slippage_bps: float
    fee_paid_usdc: float
    gas_paid_usdc: float

    @property
    def shares(self) -> float:
        return self.filled_usdc / self.avg_price if self.avg_price > 0 else 0.0


def simulate_fill(
    order: IntendedOrder,
    book: BookSnapshot,
    *,
    queue_ahead_usdc: float = 0.0,
    fee_rate_bps: float = DEFAULT_MAKER_FEE_BPS,
    gas_per_trade_usd: float = DEFAULT_GAS_PER_TRADE_USD,
) -> FillResult:
    """Walk the book to fill ``size_usdc`` at or below ``limit_price``.

    ``queue_ahead_usdc`` reflects the FIFO position: USDC of resting orders at
    the same price level that arrived before us. Their depth must clear before
    any of our size fills.
    """
    side_book = book.yes_asks if order.side == "BUY_YES" else book.yes_bids
    # For BUY_NO we cross YES bids — interpret depth in NO frame:
    #   "selling YES at price p" == "buying NO at price (1 - p)".
    # The effective limit for accepting is: yes_bid_price >= 1 - order.limit_price
    if order.side == "BUY_NO":
        effective_levels = [
            BookLevel(price=1.0 - lvl.price, size_usdc=lvl.size_usdc) for lvl in side_book
        ]
        # Sort ascending by NO-equivalent price (best NO-ask first)
        effective_levels.sort(key=lambda lvl: lvl.price)
    else:
        effective_levels = sorted(side_book, key=lambda lvl: lvl.price)

    remaining = order.size_usdc
    queue = queue_ahead_usdc
    spent = 0.0
    shares = 0.0

    for lvl in effective_levels:
        if remaining <= 0:
            break
        if lvl.price > order.limit_price:
            break

        depth = max(0.0, lvl.size_usdc - queue)
        queue = max(0.0, queue - lvl.size_usdc)
        if depth <= 0:
            continue

        take = min(remaining, depth)
        spent += take
        shares += take / lvl.price
        remaining -= take

    if shares <= 0:
        return FillResult(
            filled_usdc=0.0, avg_price=0.0, slippage_bps=0.0,
            fee_paid_usdc=0.0, gas_paid_usdc=gas_per_trade_usd,
        )

    avg_price = spent / shares
    slippage_bps = abs((avg_price - order.limit_price) / order.limit_price) * 10_000
    fee = spent * (fee_rate_bps / 10_000.0)
    return FillResult(
        filled_usdc=spent,
        avg_price=avg_price,
        slippage_bps=slippage_bps,
        fee_paid_usdc=fee,
        gas_paid_usdc=gas_per_trade_usd,
    )


@dataclass
class TradeOutcome:
    order: IntendedOrder
    fill: FillResult
    realized_yes: bool       # did YES win at resolution?
    pnl_usdc: float          # realized P&L net of fees + gas


def realize(order: IntendedOrder, fill: FillResult, *, realized_yes: bool) -> TradeOutcome:
    """Compute realized P&L for one filled trade after the market resolves."""
    if fill.filled_usdc <= 0:
        return TradeOutcome(order=order, fill=fill, realized_yes=realized_yes, pnl_usdc=0.0)

    # Each filled share pays $1 if our side wins, $0 if it doesn't.
    won = (order.side == "BUY_YES" and realized_yes) or (
        order.side == "BUY_NO" and not realized_yes
    )
    payout = fill.shares * (1.0 if won else 0.0)
    pnl = payout - fill.filled_usdc - fill.fee_paid_usdc - fill.gas_paid_usdc
    return TradeOutcome(order=order, fill=fill, realized_yes=realized_yes, pnl_usdc=pnl)


@dataclass
class SimulationReport:
    n_intended: int
    n_filled: int
    n_decisive: int               # filled trades whose market actually resolved
    realized_win_rate: float
    expected_value_per_trade: float
    breakeven_win_rate: float
    total_fee_drag_usd: float
    total_gas_drag_usd: float
    total_pnl_usd: float
    max_drawdown_usd: float


def aggregate(outcomes: list[TradeOutcome]) -> SimulationReport:
    """Reduce a list of TradeOutcomes to the headline simulation metrics."""
    n_intended = len(outcomes)
    filled = [o for o in outcomes if o.fill.filled_usdc > 0]
    n_filled = len(filled)
    n_decisive = n_filled

    if n_filled == 0:
        return SimulationReport(
            n_intended=n_intended, n_filled=0, n_decisive=0,
            realized_win_rate=0.0, expected_value_per_trade=0.0,
            breakeven_win_rate=0.0, total_fee_drag_usd=0.0,
            total_gas_drag_usd=0.0, total_pnl_usd=0.0, max_drawdown_usd=0.0,
        )

    wins = sum(1 for o in filled if (o.order.side == "BUY_YES") == o.realized_yes)
    realized_wr = wins / n_filled
    total_pnl = sum(o.pnl_usdc for o in filled)
    fee_drag = sum(o.fill.fee_paid_usdc for o in filled)
    gas_drag = sum(o.fill.gas_paid_usdc for o in filled)
    ev_per_trade = total_pnl / n_filled

    # Breakeven win rate from average price paid: payoff = 1, cost = avg_price + fees + gas drag fraction
    avg_price = sum(o.fill.avg_price * o.fill.filled_usdc for o in filled) / sum(
        o.fill.filled_usdc for o in filled
    )
    avg_drag_per_dollar = (fee_drag + gas_drag) / sum(o.fill.filled_usdc for o in filled)
    breakeven = (avg_price + avg_drag_per_dollar) / 1.0
    breakeven = max(0.0, min(1.0, breakeven))

    # Max drawdown by walking equity curve
    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for o in filled:
        equity += o.pnl_usdc
        peak = max(peak, equity)
        mdd = max(mdd, peak - equity)

    return SimulationReport(
        n_intended=n_intended,
        n_filled=n_filled,
        n_decisive=n_decisive,
        realized_win_rate=realized_wr,
        expected_value_per_trade=ev_per_trade,
        breakeven_win_rate=breakeven,
        total_fee_drag_usd=fee_drag,
        total_gas_drag_usd=gas_drag,
        total_pnl_usd=total_pnl,
        max_drawdown_usd=mdd,
    )
