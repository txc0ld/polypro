"""Near-expiry certainty scalper tests."""

from __future__ import annotations

import pytest

from polyflow.strategies.near_expiry_certainty import (
    CertaintyScalpInputs,
    evaluate,
)


def _inp(**overrides) -> CertaintyScalpInputs:
    base = dict(
        market_id="m1", side="YES",
        p_executable=0.97, certainty=0.99,
        seconds_to_resolution=300,
        fee_rate_bps=0, volatility_spike_recent=False,
        resolution_rules_clear=True,
    )
    base.update(overrides)
    return CertaintyScalpInputs(**base)


class TestFire:
    def test_clear_fire(self) -> None:
        d = evaluate(_inp())
        assert d.fire
        # EV = 0.99 * (1/0.97) - 1 ≈ 0.0206
        assert d.ev_per_dollar > 0.015
        assert d.reason_codes == ()

    def test_low_certainty_no_fire(self) -> None:
        d = evaluate(_inp(certainty=0.85))
        assert not d.fire
        assert any("CERTAINTY_BELOW" in r for r in d.reason_codes)

    def test_volatility_spike_no_fire(self) -> None:
        d = evaluate(_inp(volatility_spike_recent=True))
        assert not d.fire
        assert "VOLATILITY_SPIKE_RECENT" in d.reason_codes

    def test_too_far_from_close_no_fire(self) -> None:
        d = evaluate(_inp(seconds_to_resolution=3600))
        assert not d.fire
        assert "TOO_FAR_FROM_CLOSE" in d.reason_codes

    def test_price_too_high_no_fire(self) -> None:
        d = evaluate(_inp(p_executable=0.995))
        assert not d.fire
        assert any("PRICE_ABOVE" in r for r in d.reason_codes)

    def test_price_too_low_no_fire(self) -> None:
        d = evaluate(_inp(p_executable=0.85))
        assert not d.fire
        assert any("PRICE_BELOW" in r for r in d.reason_codes)

    def test_ambiguous_resolution_blocks(self) -> None:
        d = evaluate(_inp(resolution_rules_clear=False))
        assert not d.fire
        assert "AMBIGUOUS_RESOLUTION" in d.reason_codes
