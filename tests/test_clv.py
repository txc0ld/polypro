"""Closing-line value tests."""

from __future__ import annotations

import pytest

from polyflow.clv import compute_clv_bps, make_record
from polyflow.persistence import SQLiteStore


class TestComputeCLV:
    def test_buy_yes_favorable(self) -> None:
        # Bought YES at 0.55, closed at 0.65 → +1000 bps
        assert compute_clv_bps(entry_price=0.55, closing_price=0.65, side="BUY_YES") == pytest.approx(1000.0)

    def test_buy_yes_unfavorable(self) -> None:
        assert compute_clv_bps(entry_price=0.65, closing_price=0.55, side="BUY_YES") == pytest.approx(-1000.0)

    def test_buy_no_favorable(self) -> None:
        # Bought NO (i.e. fading YES at 0.65), closed at 0.55 → +1000 bps
        assert compute_clv_bps(entry_price=0.65, closing_price=0.55, side="BUY_NO") == pytest.approx(1000.0)

    def test_invalid_side(self) -> None:
        with pytest.raises(ValueError):
            compute_clv_bps(entry_price=0.5, closing_price=0.5, side="HOLD")

    def test_out_of_range_price(self) -> None:
        with pytest.raises(ValueError):
            compute_clv_bps(entry_price=-0.1, closing_price=0.5, side="BUY_YES")


class TestPersistence:
    def test_insert_and_average(self) -> None:
        store = SQLiteStore(":memory:")
        store.insert_clv(
            market_id="m1", token_id="t", signal_id="s1",
            entry_price=0.55, closing_price=0.65, side="BUY_YES",
        )
        store.insert_clv(
            market_id="m1", token_id="t", signal_id="s2",
            entry_price=0.55, closing_price=0.50, side="BUY_YES",
        )
        # +1000 and -500 → avg = +250
        avg = store.average_clv_bps()
        assert avg == pytest.approx(250.0)


class TestMakeRecord:
    def test_round_trip(self) -> None:
        rec = make_record(
            market_id="m", token_id="t", signal_id="s",
            entry_price=0.55, closing_price=0.65, side="BUY_YES",
        )
        assert rec.clv_bps == pytest.approx(1000.0)
        assert rec.side == "BUY_YES"
