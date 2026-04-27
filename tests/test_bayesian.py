"""Bayesian streaming updater tests."""

from __future__ import annotations

import math

import pytest

from polyflow.bayesian import BayesianTracker, clip, update, update_log_odds


class TestUpdate:
    def test_neutral_evidence_unchanged(self) -> None:
        # Likelihood ratio of 1 means no information → posterior == prior
        assert update(prior=0.4, likelihood_ratio=1.0) == pytest.approx(0.4, abs=1e-6)

    def test_evidence_supports_outcome(self) -> None:
        # LR=4 means evidence is 4x more likely if outcome is YES
        post = update(prior=0.5, likelihood_ratio=4.0)
        # prior_odds=1 → posterior_odds=4 → p=4/5=0.8
        assert post == pytest.approx(0.8, rel=1e-6)

    def test_evidence_against_outcome(self) -> None:
        post = update(prior=0.5, likelihood_ratio=0.25)
        # posterior_odds = 0.25 → p = 0.2
        assert post == pytest.approx(0.2, rel=1e-6)

    def test_clips_at_boundary(self) -> None:
        post = update(prior=0.999_999_999, likelihood_ratio=1.0)
        assert post < 1.0  # never exactly 1.0

    def test_negative_lr_raises(self) -> None:
        with pytest.raises(ValueError):
            update(prior=0.5, likelihood_ratio=-1.0)


class TestLogOdds:
    def test_matches_linear_for_moderate_values(self) -> None:
        post_lin = update(prior=0.5, likelihood_ratio=4.0)
        post_log = update_log_odds(prior=0.5, log_likelihood_ratio=math.log(4.0))
        assert post_lin == pytest.approx(post_log, rel=1e-9)


class TestTracker:
    def test_sequential_updates_compound(self) -> None:
        t = BayesianTracker(prior=0.5)
        t.observe(likelihood_ratio=2.0)
        # After 1 step: posterior 2/3
        assert t.posterior == pytest.approx(2.0 / 3.0, rel=1e-9)
        t.observe(likelihood_ratio=2.0)
        # 2 steps: posterior_odds = 4 → 0.8
        assert t.posterior == pytest.approx(0.8, rel=1e-9)

    def test_decay_pulls_toward_prior(self) -> None:
        t = BayesianTracker(prior=0.5, decay_per_observation=0.5)
        t.observe(likelihood_ratio=10.0)  # heavy evidence first
        first = t.posterior
        # Subsequent neutral observations should pull back toward 0.5
        for _ in range(10):
            t.observe(likelihood_ratio=1.0)
        assert t.posterior < first
        assert t.posterior > 0.5  # but not all the way back

    def test_reset(self) -> None:
        t = BayesianTracker(prior=0.5)
        t.observe(likelihood_ratio=10.0)
        assert t.posterior > 0.8
        t.reset()
        assert t.posterior == pytest.approx(0.5, abs=1e-6)


class TestClip:
    def test_clips_zero(self) -> None:
        assert clip(0.0) > 0.0

    def test_clips_one(self) -> None:
        assert clip(1.0) < 1.0
