"""Macro events calendar tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from polyflow.adapters.macro_calendar import MacroCalendar, MacroEvent, SUPPORTED_KINDS


def _yaml_text(events: list[dict]) -> str:
    import yaml
    return yaml.safe_dump({"events": events}, sort_keys=False)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "macro.yaml"
    p.write_text(body, encoding="utf-8")
    return p


class TestParse:
    def test_loads_supported_kinds(self, tmp_path: Path) -> None:
        future = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat().replace("+00:00", "Z")
        p = _write(tmp_path, _yaml_text([
            {"kind": "FOMC", "title": "Fed decision", "timestamp_utc": future},
            {"kind": "CPI", "title": "April CPI", "timestamp_utc": future},
            {"kind": "EIA_PETROLEUM", "title": "Weekly oil inventory", "timestamp_utc": future},
        ]))
        cal = MacroCalendar.from_yaml(p)
        kinds = {e.kind for e in cal.events}
        assert kinds == {"FOMC", "CPI", "EIA_PETROLEUM"}

    def test_drops_unknown_kinds(self, tmp_path: Path) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        p = _write(tmp_path, _yaml_text([
            {"kind": "MARS_LANDING", "timestamp_utc": future.isoformat()},
            {"kind": "FOMC", "timestamp_utc": future.isoformat()},
        ]))
        cal = MacroCalendar.from_yaml(p)
        assert {e.kind for e in cal.events} == {"FOMC"}

    def test_supported_kinds_match_user_list(self) -> None:
        # Per the user: Fed decision, CPI, PCE, NFP, oil inventory, FOMC minutes, treasury auctions
        assert SUPPORTED_KINDS == {
            "FOMC", "FOMC_MINUTES", "CPI", "PCE", "NFP",
            "EIA_PETROLEUM", "TREASURY_AUCTION",
        }


class TestWindows:
    def test_pre_release_window(self) -> None:
        now = datetime(2026, 4, 30, 17, 45, tzinfo=timezone.utc)
        cal = MacroCalendar(events=[
            MacroEvent(kind="FOMC", title="Fed", timestamp_utc=datetime(2026, 4, 30, 18, 0, tzinfo=timezone.utc)),
        ], pre_release_minutes=30)
        ev = cal.is_in_pre_release_window(now)
        assert ev is not None and ev.kind == "FOMC"

    def test_outside_pre_release_window(self) -> None:
        now = datetime(2026, 4, 30, 17, 0, tzinfo=timezone.utc)
        cal = MacroCalendar(events=[
            MacroEvent(kind="FOMC", title="Fed", timestamp_utc=datetime(2026, 4, 30, 18, 0, tzinfo=timezone.utc)),
        ], pre_release_minutes=30)
        assert cal.is_in_pre_release_window(now) is None

    def test_post_release_window(self) -> None:
        now = datetime(2026, 4, 30, 18, 2, tzinfo=timezone.utc)
        cal = MacroCalendar(events=[
            MacroEvent(kind="FOMC", title="Fed", timestamp_utc=datetime(2026, 4, 30, 18, 0, tzinfo=timezone.utc)),
        ], post_release_minutes=5)
        ev = cal.is_in_post_release_window(now)
        assert ev is not None

    def test_next_event(self) -> None:
        now = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
        cal = MacroCalendar(events=[
            MacroEvent(kind="CPI", title="CPI", timestamp_utc=datetime(2026, 4, 30, 12, 30, tzinfo=timezone.utc)),
            MacroEvent(kind="FOMC", title="Fed", timestamp_utc=datetime(2026, 4, 30, 18, 0, tzinfo=timezone.utc)),
        ])
        ev = cal.next_event(now)
        assert ev is not None and ev.kind == "CPI"


class TestPersistence:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        cal = MacroCalendar.from_yaml(tmp_path / "missing.yaml")
        assert cal.events == []
