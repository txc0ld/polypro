"""Probability engine / edge math tests (PRD §8.4)."""

from __future__ import annotations

import pytest

from polyflow.probability import (
    brier_score,
    build_estimate,
    clob_taker_fee_usdc,
    effective_edge,
    fee_impact,
    half_spread,
    net_buy_shares_after_fee,
    net_sell_proceeds_after_fee,
    normalize_fee_rate,
    remove_vig,
)
from polyflow.types import Outcome


class TestRemoveVig:
    def test_two_way_market(self) -> None:
        # Bookmaker offering 1.91 / 1.91 → vig-stripped = 0.5/0.5
        ps = remove_vig([1.91, 1.91])
        assert sum(ps) == pytest.approx(1.0)
        assert ps[0] == pytest.approx(0.5)

    def test_three_way_market(self) -> None:
        ps = remove_vig([2.5, 3.2, 3.5])
        assert sum(ps) == pytest.approx(1.0, abs=1e-9)

    @pytest.mark.parametrize("bad", [[1.0], [0.5, 1.5], []])
    def test_invalid_inputs(self, bad: list[float]) -> None:
        with pytest.raises(ValueError):
            remove_vig(bad)


class TestEffectiveEdge:
    def test_yes_positive_edge(self) -> None:
        e = effective_edge(
            q_model=0.70,
            p_executable=0.62,
            outcome=Outcome.YES,
            half_spread_value=0.005,
            expected_slippage=0.003,
            fee=0.001,
            resolution_risk_buffer=0.01,
            model_uncertainty_buffer=0.01,
            liquidity_exit_buffer=0.005,
        )
        # gross 0.08; cost ~0.034 → ~0.046
        assert e == pytest.approx(0.046, abs=1e-9)

    def test_no_side_uses_inverse(self) -> None:
        e = effective_edge(
            q_model=0.40,
            p_executable=0.62,
            outcome=Outcome.NO,
            half_spread_value=0.0,
            expected_slippage=0.0,
            fee=0.0,
            resolution_risk_buffer=0.0,
            model_uncertainty_buffer=0.0,
            liquidity_exit_buffer=0.0,
        )
        # NO: gross = p - q = 0.62 - 0.40 = 0.22
        assert e == pytest.approx(0.22)


class TestSpreadAndFee:
    def test_half_spread(self) -> None:
        assert half_spread(0.61, 0.63) == pytest.approx(0.01)

    def test_half_spread_missing(self) -> None:
        assert half_spread(None, 0.63) == 0.0

    def test_fee_impact(self) -> None:
        # 200 bps legacy input -> 0.02 * p * (1-p)
        assert fee_impact(0.62, 200) == pytest.approx(0.02 * 0.62 * 0.38)

    def test_fee_impact_accepts_clob_v2_decimal_rate(self) -> None:
        assert fee_impact(0.62, 0.03) == pytest.approx(0.03 * 0.62 * 0.38)

    def test_fee_impact_unknown(self) -> None:
        assert fee_impact(0.62, None) == 0.0

    def test_normalize_fee_rate_supports_legacy_bps_and_v2_decimal(self) -> None:
        assert normalize_fee_rate(200) == pytest.approx(0.02)
        assert normalize_fee_rate(0.03) == pytest.approx(0.03)

    def test_clob_taker_fee_usdc(self) -> None:
        assert clob_taker_fee_usdc(shares=6, price=0.64, fee_rate=0.072) == pytest.approx(
            6 * 0.072 * 0.64 * 0.36
        )

    def test_buy_fee_reduces_net_shares(self) -> None:
        net = net_buy_shares_after_fee(gross_shares=6, price=0.64, fee_rate=0.072)
        assert net == pytest.approx(5.84448)

    def test_sell_fee_reduces_net_proceeds(self) -> None:
        net = net_sell_proceeds_after_fee(
            gross_proceeds_usdc=3.84, shares=6, price=0.64, fee_rate=0.072
        )
        assert net == pytest.approx(3.84 - (6 * 0.072 * 0.64 * 0.36))


class TestBuildEstimate:
    def test_recommendation_buy_yes_when_positive_edge(self) -> None:
        # Use a wide gross edge so it survives the resolution + uncertainty buffers.
        est = build_estimate(
            market_id="m1",
            token_id="t-yes",
            outcome=Outcome.YES,
            market_price=0.55,
            model_probability=0.75,
            uncertainty=0.04,
            source_confidence=0.85,
            resolution_risk=0.05,
        )
        assert est.recommendation == "BUY_YES"
        assert est.edge_after_costs > 0

    def test_skip_when_no_edge(self) -> None:
        est = build_estimate(
            market_id="m1",
            token_id="t-yes",
            outcome=Outcome.YES,
            market_price=0.70,
            model_probability=0.70,
            uncertainty=0.05,
            source_confidence=0.85,
            resolution_risk=0.10,
        )
        assert est.recommendation == "SKIP"


class TestBrier:
    def test_perfect_forecast(self) -> None:
        assert brier_score([1.0, 0.0, 1.0], [1, 0, 1]) == 0.0

    def test_uniform_forecast(self) -> None:
        # Always predicting 0.5: each squared error = 0.25
        assert brier_score([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == pytest.approx(0.25)

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError):
            brier_score([0.5], [1, 0])
