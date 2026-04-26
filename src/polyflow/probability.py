"""Probability engine — edge calculation (PRD §8.4).

This module is intentionally *just* math + bookkeeping. Probability *production*
(news_probability_delta, external_odds_divergence) lives in the strategy modules
and adapters; those produce a `model_probability` and `uncertainty`, and we turn
them into an executable edge here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from .types import Outcome, ProbabilityEstimate


def remove_vig(decimal_odds: Iterable[float]) -> list[float]:
    """Convert bookmaker decimal odds to fair probabilities by stripping vig.

    Pass in all outcomes for a single event so the implied probabilities can be
    normalized to sum to 1.0.
    """
    odds = list(decimal_odds)
    if not odds or any(o <= 1.0 for o in odds):
        raise ValueError("decimal odds must be > 1.0")
    raw = [1.0 / o for o in odds]
    s = sum(raw)
    if s == 0:
        raise ValueError("invalid odds")
    return [p / s for p in raw]


def half_spread(best_bid: float | None, best_ask: float | None) -> float:
    if best_bid is None or best_ask is None:
        return 0.0
    if best_ask < best_bid:
        return 0.0
    return (best_ask - best_bid) / 2.0


def fee_impact(price: float, fee_rate_bps: float | None) -> float:
    """Fees on Polymarket are taken on the winning side; we approximate as
    ``fee_rate * price`` for buying YES at ``price``.
    """
    if fee_rate_bps is None:
        return 0.0
    return price * (fee_rate_bps / 10_000.0)


def effective_edge(
    *,
    q_model: float,
    p_executable: float,
    outcome: Outcome,
    half_spread_value: float,
    expected_slippage: float,
    fee: float,
    resolution_risk_buffer: float,
    model_uncertainty_buffer: float,
    liquidity_exit_buffer: float,
) -> float:
    """PRD §8.4 effective edge.

    edge_after_costs = |q - p| - half_spread - slippage - fee
                       - resolution_buffer - model_uncertainty_buffer - liquidity_buffer
    Sign is preserved by the side: BUY YES wants q > p, BUY NO wants q < p.
    """
    if outcome is Outcome.YES:
        gross = q_model - p_executable
    else:
        gross = p_executable - q_model

    cost = (
        half_spread_value
        + expected_slippage
        + fee
        + resolution_risk_buffer
        + model_uncertainty_buffer
        + liquidity_exit_buffer
    )
    return gross - cost


def build_estimate(
    *,
    market_id: str,
    token_id: str,
    outcome: Outcome,
    market_price: float,
    model_probability: float,
    uncertainty: float,
    source_confidence: float,
    resolution_risk: float,
    half_spread_value: float = 0.0,
    expected_slippage: float = 0.005,
    fee_rate_bps: float | None = 0.0,
    liquidity_exit_buffer: float = 0.005,
    reason_codes: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    ttl_minutes: int = 30,
) -> ProbabilityEstimate:
    """Construct a ProbabilityEstimate, computing fair_bid/ask and edges from inputs."""
    fair_bid = max(0.0, model_probability - uncertainty)
    fair_ask = min(1.0, model_probability + uncertainty)

    fee = fee_impact(market_price, fee_rate_bps)
    edge_before = abs(model_probability - market_price)
    edge_after = effective_edge(
        q_model=model_probability,
        p_executable=market_price,
        outcome=outcome,
        half_spread_value=half_spread_value,
        expected_slippage=expected_slippage,
        fee=fee,
        resolution_risk_buffer=resolution_risk * 0.5,
        model_uncertainty_buffer=uncertainty * 0.5,
        liquidity_exit_buffer=liquidity_exit_buffer,
    )

    if outcome is Outcome.YES:
        recommendation = "BUY_YES" if edge_after > 0 else "SKIP"
    else:
        recommendation = "BUY_NO" if edge_after > 0 else "SKIP"

    return ProbabilityEstimate(
        market_id=market_id,
        token_id=token_id,
        outcome=outcome,
        market_price=market_price,
        model_probability=model_probability,
        uncertainty=uncertainty,
        fair_bid=fair_bid,
        fair_ask=fair_ask,
        edge_before_costs=edge_before,
        edge_after_costs=edge_after,
        source_confidence=source_confidence,
        resolution_risk=resolution_risk,
        recommendation=recommendation,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        reason_codes=reason_codes or [],
        evidence_refs=evidence_refs or [],
    )


def brier_score(predictions: list[float], outcomes: list[int]) -> float:
    """Mean Brier score over a sequence of (probability, realized 0/1) pairs."""
    if len(predictions) != len(outcomes) or not predictions:
        raise ValueError("predictions and outcomes must be same nonzero length")
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)
