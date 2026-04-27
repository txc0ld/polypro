"""Streaming Bayesian probability updater.

The protocol's mandate: ``q`` is never static. Every new evidence event
(temperature reading, BTC tick, new news source) updates the model
probability via Bayes:

    P(outcome | evidence) = P(evidence | outcome) × prior / P(evidence)

This module owns the bookkeeping. Strategies hand it (a) the current
``prior``, (b) a likelihood ratio for each evidence event, and (c) the
event itself; it returns the posterior probability in [eps, 1-eps] (clipped
to avoid numerical pathologies).

For continuous variables (e.g. temperature trajectory) callers should
discretize first (e.g. P(temp_at_close > 50F | current=48F, rate=+0.5F/h)).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from threading import RLock


_EPS = 1e-6


def clip(p: float) -> float:
    return max(_EPS, min(1.0 - _EPS, p))


def update(*, prior: float, likelihood_ratio: float) -> float:
    """One Bayesian step in odds space.

    posterior_odds = prior_odds × likelihood_ratio
    """
    if likelihood_ratio < 0:
        raise ValueError("likelihood_ratio must be >= 0")
    p = clip(prior)
    if likelihood_ratio == 0:
        return _EPS
    prior_odds = p / (1.0 - p)
    posterior_odds = prior_odds * likelihood_ratio
    return clip(posterior_odds / (1.0 + posterior_odds))


def update_log_odds(*, prior: float, log_likelihood_ratio: float) -> float:
    """Numerically-stable variant for very large/small likelihood ratios."""
    p = clip(prior)
    log_prior_odds = math.log(p / (1.0 - p))
    log_post = log_prior_odds + log_likelihood_ratio
    odds = math.exp(log_post)
    return clip(odds / (1.0 + odds))


@dataclass
class BayesianTracker:
    """Stateful tracker for one outcome variable.

    Each call to ``observe`` consumes a likelihood ratio (P(evidence | YES)
    / P(evidence | NO)) and updates the posterior. The history of updates
    is preserved for audit + decay (older evidence can be down-weighted).
    """

    prior: float
    decay_per_observation: float = 1.0   # 1.0 = no decay; <1 fades old evidence
    _posterior: float = field(init=False)
    _history: list[float] = field(default_factory=list, init=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self._posterior = clip(self.prior)

    @property
    def posterior(self) -> float:
        with self._lock:
            return self._posterior

    def observe(self, *, likelihood_ratio: float) -> float:
        """Apply one evidence event; return the updated posterior."""
        with self._lock:
            if self.decay_per_observation < 1.0:
                # Fade toward the prior before applying the new evidence
                self._posterior = (
                    self.decay_per_observation * self._posterior
                    + (1.0 - self.decay_per_observation) * self.prior
                )
            self._posterior = update(
                prior=self._posterior, likelihood_ratio=likelihood_ratio
            )
            self._history.append(likelihood_ratio)
            return self._posterior

    def reset(self) -> None:
        with self._lock:
            self._posterior = clip(self.prior)
            self._history.clear()
