"""Source reliability tracker.

Maintains a running prior over per-source reliability based on past calls vs
realized outcomes. Wikipedia-grade Bayesian update (Beta prior, hits/misses
posterior) — boring on purpose. Sources with too few observations fall back
to a conservative default prior.
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_PRIOR = 0.70
PRIOR_WEIGHT = 5.0   # equivalent observations baked into the default prior


@dataclass(frozen=True)
class ReliabilityScore:
    source_name: str
    prior: float
    hits: int
    misses: int
    n: int
    # Smoothed posterior: (hits + prior * weight) / (n + weight)
    posterior: float


def update_posterior(*, hits: int, misses: int, prior: float = DEFAULT_PRIOR) -> float:
    n = hits + misses
    return (hits + prior * PRIOR_WEIGHT) / (n + PRIOR_WEIGHT)


def score(row: dict) -> ReliabilityScore:
    hits = int(row.get("hits") or 0)
    misses = int(row.get("misses") or 0)
    prior = float(row.get("prior") or DEFAULT_PRIOR)
    return ReliabilityScore(
        source_name=str(row["source_name"]),
        prior=prior,
        hits=hits,
        misses=misses,
        n=hits + misses,
        posterior=update_posterior(hits=hits, misses=misses, prior=prior),
    )
