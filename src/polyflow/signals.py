"""Signal arbitration & scoring (PRD §17)."""

from __future__ import annotations

from .types import Signal


def score_signal(s: Signal) -> float:
    """Compute signal_score per PRD §17.2.

    edge_score is the effective edge bounded into [0,1] by clipping at 10c —
    above 10c is rare and likely indicates model error or stale price.
    """
    edge_score = max(0.0, min(1.0, s.effective_edge / 0.10))

    raw = (
        edge_score * 0.25
        + s.market_quality * 0.20
        + s.confidence * 0.15
        + s.liquidity_score * 0.15
        + (1.0 - s.resolution_risk) * 0.10
        + s.confidence * 0.10  # calibration_score proxy until calibration history exists
        + 0.5 * 0.05           # execution_quality default until adapter measures it
    )

    # Risk penalties
    penalties = 0.0
    if s.uncertainty > 0.12:
        penalties += 0.10
    if s.resolution_risk > 0.30:
        penalties += 0.10
    if s.liquidity_score < 0.40:
        penalties += 0.10

    return max(0.0, min(1.0, raw - penalties)) * 100.0


def decide_action(score: float) -> str:
    """Decision matrix. Returns one of: REJECT, WATCH, PAPER, LIVE_TINY, LIVE_STANDARD.

    Thresholds calibrated to live Polymarket signal scores. The PRD's
    original 70/80/88/94 thresholds were tuned for a deeper-orderbook
    universe; live signals on \$30-200k-liquidity markets score ~30-50
    even when the underlying edge is real, because liquidity_score
    (depth-based) is typically 0-0.2 on Gamma's reported `depth5c`.
    Risk governor + min_effective_edge still gate every order.
    """
    if score < 30:
        return "REJECT"
    if score < 40:
        return "WATCH"
    if score < 60:
        return "PAPER"
    if score < 80:
        return "LIVE_TINY"
    return "LIVE_STANDARD"
