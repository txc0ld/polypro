"""Pure expected-value math for binary Polymarket positions.

The protocol's mandate: never trade on simplified edge. Always compute the
full EV formula and size with fractional Kelly off the *true* probabilities,
not buffered approximations.

For a binary YES outcome at price ``p`` with model probability ``q``:

    EV(BUY_YES, per dollar)  = q * (1 - p) / p  -  (1 - q)
    EV(BUY_NO,  per dollar)  = (1 - q) * p / (1 - p)  -  q

We also expose the simpler edge-per-share form ``q - p`` (BUY YES) which is
the core gap the protocol calls "the only thing the bot is trading."

Costs (fee + slippage) are subtracted *after* the raw EV is computed, so the
pure number is always available for diagnostics and audit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EVResult:
    side: str            # 'BUY_YES' or 'BUY_NO'
    p_market: float      # market price for the side we're buying
    q_model: float       # model probability for the side we're buying
    edge_per_share: float        # q - p (the protocol's core gap)
    ev_per_dollar: float         # protocol's full EV formula, per $1 stake
    breakeven_q: float           # the q at which EV = 0


def buy_yes_ev(*, q: float, p_yes: float) -> EVResult:
    """EV of buying YES at YES-ask ``p_yes`` with model YES probability ``q``."""
    if not (0.0 < p_yes < 1.0):
        raise ValueError("p_yes must be in (0, 1)")
    if not (0.0 <= q <= 1.0):
        raise ValueError("q must be in [0, 1]")
    edge = q - p_yes
    # Per-dollar return: stake $1 → buy 1/p_yes shares → payout = 1/p_yes if YES wins, 0 if not
    ev = q * (1.0 / p_yes) - 1.0
    return EVResult(
        side="BUY_YES",
        p_market=p_yes,
        q_model=q,
        edge_per_share=edge,
        ev_per_dollar=ev,
        breakeven_q=p_yes,
    )


def buy_no_ev(*, q: float, p_yes: float) -> EVResult:
    """EV of buying NO at YES-bid ``p_yes`` with model YES probability ``q``.

    Buying NO at YES-price p means paying ``1 - p`` for NO, paying $1 if NO wins.
    """
    if not (0.0 < p_yes < 1.0):
        raise ValueError("p_yes must be in (0, 1)")
    if not (0.0 <= q <= 1.0):
        raise ValueError("q must be in [0, 1]")
    p_no = 1.0 - p_yes
    q_no = 1.0 - q
    edge = q_no - p_no
    ev = q_no * (1.0 / p_no) - 1.0
    return EVResult(
        side="BUY_NO",
        p_market=p_no,
        q_model=q_no,
        edge_per_share=edge,
        ev_per_dollar=ev,
        breakeven_q=q,
    )


def best_side(*, q_yes: float, p_yes_bid: float, p_yes_ask: float) -> EVResult:
    """Choose the side with the higher EV given the YES book."""
    yes = buy_yes_ev(q=q_yes, p_yes=p_yes_ask)
    no = buy_no_ev(q=q_yes, p_yes=p_yes_bid)
    return yes if yes.ev_per_dollar >= no.ev_per_dollar else no


def fractional_kelly_fraction(*, q: float, p_market: float) -> float:
    """Protocol's f* = max(0, (q - p) / (1 - p)).

    This is the *raw* Kelly fraction; the runtime applies the multipliers
    (¼ or ½ Kelly, confidence, liquidity, resolution risk) on top.
    """
    if not (0.0 < p_market < 1.0):
        return 0.0
    return max(0.0, (q - p_market) / (1.0 - p_market))


def costed_ev(
    *,
    raw_ev: float,
    fee_rate_bps: float = 0.0,
    expected_slippage_bps: float = 0.0,
    gas_cost_per_dollar: float = 0.0,
) -> float:
    """Subtract fee + slippage + gas drag from a raw EV figure.

    Each input is in basis points of stake, except ``gas_cost_per_dollar``
    which is a flat rate (e.g. 0.0005 = 5bps).
    """
    drag = (fee_rate_bps + expected_slippage_bps) / 10_000.0 + gas_cost_per_dollar
    return raw_ev - drag
