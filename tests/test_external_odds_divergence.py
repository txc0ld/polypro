"""External odds divergence strategy tests (PRD §9.2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polyflow.config import Policy
from polyflow.strategies import OddsAnchor, divergence_signal
from polyflow.types import Market, Outcome, Strategy


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _market(**overrides) -> Market:
    base = dict(
        id="m1",
        event_id="e1",
        question="Q?",
        category="sports",
        close_time=_now() + timedelta(hours=12),
        resolution_rules="rules",
        liquidity_usd=300_000,
        volume_24h_usd=80_000,
        spread_pct=2.0,
        depth_within_5c_usd=30_000,
        best_bid=0.55,
        best_ask=0.57,
        yes_token_id="t-yes",
        no_token_id="t-no",
        tick_size=0.01,
        min_order_size=5.0,
        fee_rate_bps=200,
        neg_risk=False,
        market_quality=0.85,
        resolution_risk=0.05,
    )
    base.update(overrides)
    return Market(**base)


def _anchor(yes_dec: float, no_dec: float, *, name: str = "book", reliability: float = 0.85, age_s: int = 5) -> OddsAnchor:
    return OddsAnchor.from_decimal_odds(
        source_name=name,
        fetched_at=_now() - timedelta(seconds=age_s),
        yes_decimal_odds=yes_dec,
        no_decimal_odds=no_dec,
        reliability=reliability,
    )


class TestDivergenceSignal:
    def test_emits_buy_yes_when_anchor_higher(self) -> None:
        # Bookmaker implies YES ~0.71, Polymarket ask = 0.57 → strong BUY YES edge
        out = divergence_signal(
            policy=Policy(),
            market=_market(),
            anchors=[_anchor(1.41, 3.40)],
        )
        assert out is not None
        est, sig = out
        assert sig.strategy is Strategy.EXTERNAL_ODDS_DIVERGENCE
        assert sig.outcome is Outcome.YES
        assert est.edge_after_costs > 0

    def test_no_signal_when_anchor_matches_market(self) -> None:
        out = divergence_signal(
            policy=Policy(),
            market=_market(),
            anchors=[_anchor(1.82, 1.99)],  # implies ~0.52 YES; Polymarket mid = 0.56
        )
        # Edge after costs should be too small to qualify.
        assert out is None or out[0].edge_after_costs >= 0.03

    def test_stale_anchor_rejected(self) -> None:
        out = divergence_signal(
            policy=Policy(),
            market=_market(),
            anchors=[_anchor(1.41, 3.40, age_s=600)],
        )
        assert out is None

    def test_settlement_mismatch_rejected(self) -> None:
        bad = OddsAnchor(
            source_name="book",
            fetched_at=_now(),
            yes_probability=0.71,
            reliability=0.9,
            settlement_match=False,
        )
        out = divergence_signal(policy=Policy(), market=_market(), anchors=[bad])
        assert out is None

    def test_buy_no_when_anchor_below_market(self) -> None:
        # Polymarket book at 0.55/0.57, anchor implies YES ~0.30 → BUY NO
        out = divergence_signal(
            policy=Policy(),
            market=_market(),
            anchors=[_anchor(3.40, 1.41)],
        )
        assert out is not None
        _est, sig = out
        assert sig.outcome is Outcome.NO
