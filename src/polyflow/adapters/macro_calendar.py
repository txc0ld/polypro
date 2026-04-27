"""Macro economic-events calendar.

Per the protocol: only trade *around* scheduled catalysts, never blindly
guess pre-release direction. The bot consumes a static YAML calendar of
release times and exposes:

  - ``is_in_pre_release_window(now)`` — true when a release is within the
    pre-release blackout (default 30min before)
  - ``is_in_post_release_window(now)`` — true within reaction window
    (default 5min after)
  - ``next_event(now)`` — the upcoming scheduled release

Operators maintain ``configs/macro_calendar.yaml`` with entries like:

    events:
      - kind: FOMC
        title: "FOMC rate decision"
        timestamp_utc: "2026-04-30T18:00:00Z"
      - kind: CPI
        title: "April CPI release"
        timestamp_utc: "2026-05-13T12:30:00Z"
      - kind: NFP
      - kind: PCE
      - kind: EIA_PETROLEUM
      - kind: TREASURY_AUCTION

Supported event kinds (per the user's macro target list):
  FOMC, FOMC_MINUTES, CPI, PCE, NFP, EIA_PETROLEUM, TREASURY_AUCTION
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import yaml


SUPPORTED_KINDS: frozenset[str] = frozenset(
    {
        "FOMC",
        "FOMC_MINUTES",
        "CPI",
        "PCE",
        "NFP",
        "EIA_PETROLEUM",   # weekly oil inventory (Wednesdays 14:30 UTC typically)
        "TREASURY_AUCTION",
    }
)


@dataclass(frozen=True)
class MacroEvent:
    kind: str
    title: str
    timestamp_utc: datetime


@dataclass
class MacroCalendar:
    """In-memory list of upcoming releases plus pre/post-release windows."""

    events: list[MacroEvent]
    pre_release_minutes: int = 30
    post_release_minutes: int = 5

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MacroCalendar":
        p = Path(path)
        if not p.exists():
            return cls(events=[])
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls(events=list(_parse_events(data.get("events") or [])))

    def upcoming(self, now: datetime | None = None) -> list[MacroEvent]:
        now = now or datetime.now(timezone.utc)
        return [e for e in self.events if e.timestamp_utc >= now]

    def next_event(self, now: datetime | None = None) -> MacroEvent | None:
        upcoming = self.upcoming(now)
        return min(upcoming, key=lambda e: e.timestamp_utc) if upcoming else None

    def is_in_pre_release_window(self, now: datetime | None = None) -> MacroEvent | None:
        """Return the event whose pre-release window we're inside, or None."""
        now = now or datetime.now(timezone.utc)
        for event in self.events:
            window_start = event.timestamp_utc - timedelta(minutes=self.pre_release_minutes)
            if window_start <= now < event.timestamp_utc:
                return event
        return None

    def is_in_post_release_window(self, now: datetime | None = None) -> MacroEvent | None:
        """Return the event whose post-release reaction window is active."""
        now = now or datetime.now(timezone.utc)
        for event in self.events:
            window_end = event.timestamp_utc + timedelta(minutes=self.post_release_minutes)
            if event.timestamp_utc <= now < window_end:
                return event
        return None


def _parse_events(records: Iterable[dict]) -> Iterable[MacroEvent]:
    for r in records:
        kind = str(r.get("kind") or "").upper().strip()
        if kind not in SUPPORTED_KINDS:
            continue
        ts_raw = r.get("timestamp_utc") or r.get("timestamp")
        if ts_raw is None:
            continue
        try:
            if isinstance(ts_raw, datetime):
                ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
            else:
                s = str(ts_raw).replace("Z", "+00:00")
                ts = datetime.fromisoformat(s)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        yield MacroEvent(
            kind=kind,
            title=str(r.get("title") or kind),
            timestamp_utc=ts,
        )
