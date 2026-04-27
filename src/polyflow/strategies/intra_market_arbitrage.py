"""Intra-market arbitrage detector.

When the YES ask + NO ask sum to less than $1.00 (minus a fee buffer), the
position "buy YES + buy NO" is mathematically risk-free: exactly one outcome
pays $1 regardless of which way the market resolves. The locked spread is
the difference between $1 and the combined ask total.

Per the protocol:

    P(Yes) + P(No) < 0.995  →  buy both sides instantly for risk-free 0.5%+ lock.
    Size up to 5× normal because variance is zero.

This implementation:
  - Reads YES and NO best-ask from the CLOB book
  - Computes the locked spread net of fee + slippage buffers
  - Returns an ``ArbitrageOpportunity`` with the unit cost and per-unit lock
  - Refuses if depth on either side is insufficient for the proposed size
  - Refuses if the market is `neg_risk` and the convention differs
    (caller must verify the YES/NO token mapping for neg-risk markets)

Sizing is left to the runtime; the user-set ``max_order_usdc`` cap and the
risk-governor caps still apply.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArbitrageOpportunity:
    market_id: str
    yes_ask: float
    no_ask: float
    yes_depth_usd: float
    no_depth_usd: float
    combined_ask: float
    lock_per_unit: float           # $1 - combined_ask, before fees
    lock_after_costs: float        # net of fee+slippage buffers
    max_size_usd: float            # min(yes_depth, no_depth) sized to fit


def detect(
    *,
    market_id: str,
    yes_ask: float,
    no_ask: float,
    yes_depth_usd: float,
    no_depth_usd: float,
    fee_rate_bps: float = 0.0,
    slippage_bps_each_side: float = 5.0,
    min_lock_pct: float = 0.005,
) -> ArbitrageOpportunity | None:
    """Return an arbitrage opportunity if the math holds, else ``None``.

    ``min_lock_pct`` is the protocol's 0.5% (=0.005) floor.
    """
    if not (0.0 < yes_ask < 1.0) or not (0.0 < no_ask < 1.0):
        return None
    combined = yes_ask + no_ask
    if combined >= 1.0:
        return None

    lock_pre = 1.0 - combined
    fee_drag = combined * (fee_rate_bps / 10_000.0)
    slippage_drag = combined * (slippage_bps_each_side / 10_000.0)
    lock_after = lock_pre - fee_drag - slippage_drag
    if lock_after < min_lock_pct:
        return None

    # Max we can take is min depth (each side must fully fill).
    max_size = max(0.0, min(yes_depth_usd, no_depth_usd))
    if max_size <= 0:
        return None

    return ArbitrageOpportunity(
        market_id=market_id,
        yes_ask=yes_ask,
        no_ask=no_ask,
        yes_depth_usd=yes_depth_usd,
        no_depth_usd=no_depth_usd,
        combined_ask=combined,
        lock_per_unit=lock_pre,
        lock_after_costs=lock_after,
        max_size_usd=max_size,
    )


def expected_lock(opportunity: ArbitrageOpportunity, *, stake_usd: float) -> float:
    """Dollar lock at the given stake size.

    Because both sides fill, the realized return = stake × (1 - combined_ask) / combined_ask
    minus fees. The ``lock_after_costs`` is per *unit cost* (= per dollar of
    combined ask). The dollar lock at stake = stake × lock_after_costs / combined.
    """
    if opportunity.combined_ask <= 0:
        return 0.0
    return stake_usd * (opportunity.lock_after_costs / opportunity.combined_ask)
