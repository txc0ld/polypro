"""Kelly math tests (PRD §8.2/§8.3)."""

from __future__ import annotations

import pytest

from polyflow.kelly import (
    confidence_multiplier,
    fractional_kelly,
    liquidity_multiplier,
    raw_kelly,
    resolution_multiplier,
)
from polyflow.types import Outcome


class TestRawKelly:
    def test_yes_basic(self) -> None:
        # PRD example: q=0.70, p=0.62 → (0.70-0.62)/(1-0.62) ≈ 0.2105
        k = raw_kelly(0.62, 0.70, Outcome.YES)
        assert k == pytest.approx((0.70 - 0.62) / (1 - 0.62), rel=1e-9)

    def test_yes_no_edge(self) -> None:
        assert raw_kelly(0.70, 0.70, Outcome.YES) == 0.0

    def test_yes_negative_edge_clamped_to_zero(self) -> None:
        assert raw_kelly(0.70, 0.50, Outcome.YES) == 0.0

    def test_no_basic(self) -> None:
        k = raw_kelly(0.62, 0.50, Outcome.NO)
        assert k == pytest.approx((0.62 - 0.50) / 0.62, rel=1e-9)

    def test_no_negative_edge_clamped(self) -> None:
        assert raw_kelly(0.50, 0.70, Outcome.NO) == 0.0

    @pytest.mark.parametrize("p", [0.0, 1.0, -0.1, 1.1])
    def test_degenerate_price_returns_zero(self, p: float) -> None:
        assert raw_kelly(p, 0.5, Outcome.YES) == 0.0

    @pytest.mark.parametrize("q", [-0.1, 1.1])
    def test_invalid_q_returns_zero(self, q: float) -> None:
        assert raw_kelly(0.5, q, Outcome.YES) == 0.0


class TestFractionalKelly:
    def test_default_fraction(self) -> None:
        out = fractional_kelly(0.20, kelly_fraction=0.05)
        assert out == pytest.approx(0.20 * 0.05)

    def test_all_multipliers(self) -> None:
        out = fractional_kelly(
            0.20,
            kelly_fraction=0.05,
            confidence_multiplier=0.8,
            liquidity_multiplier=0.6,
            resolution_multiplier=0.9,
            portfolio_multiplier=0.5,
        )
        assert out == pytest.approx(0.20 * 0.05 * 0.8 * 0.6 * 0.9 * 0.5)

    def test_clamped_to_one(self) -> None:
        # Even with raw_kelly above 1, the output must clamp.
        out = fractional_kelly(5.0, kelly_fraction=1.0)
        assert out == 1.0

    def test_rejects_out_of_range_multiplier(self) -> None:
        with pytest.raises(ValueError):
            fractional_kelly(0.1, kelly_fraction=1.5)


class TestConfidenceMultiplier:
    def test_high_confidence_low_uncertainty(self) -> None:
        assert confidence_multiplier(0.9, 0.05) == pytest.approx(0.9 * 0.95)

    def test_zero_confidence_zero_size(self) -> None:
        assert confidence_multiplier(0.0, 0.0) == 0.0


class TestLiquidityMultiplier:
    def test_no_target_returns_one(self) -> None:
        assert liquidity_multiplier(10_000, 0) == 1.0

    def test_no_depth_returns_zero(self) -> None:
        assert liquidity_multiplier(0, 100) == 0.0

    def test_within_book_no_shrink(self) -> None:
        # target = 5% of depth → well within 10% threshold → no shrink
        assert liquidity_multiplier(10_000, 500) == 1.0

    def test_exceeds_book_shrinks(self) -> None:
        m = liquidity_multiplier(10_000, 5_000)
        assert 0.0 < m < 1.0


class TestResolutionMultiplier:
    def test_zero_risk_full_size(self) -> None:
        assert resolution_multiplier(0.0, 0.35) == 1.0

    def test_at_cap_zero_size(self) -> None:
        assert resolution_multiplier(0.35, 0.35) == 0.0

    def test_over_cap_zero_size(self) -> None:
        assert resolution_multiplier(0.50, 0.35) == 0.0
