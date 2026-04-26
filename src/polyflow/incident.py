"""Incident state machine + global kill switch (PRD §10.5, §12.3).

The runtime owns one ``IncidentManager``. Subagents and hooks call ``trip`` to
signal a fault; ``can_trade`` is the gate every order code path consults.

States flow: HEALTHY → DEGRADED → LOCKDOWN → KILLED. Operators can ``recover``
DEGRADED but never KILLED — that's a redeploy event.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class State(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    LOCKDOWN = "lockdown"
    KILLED = "killed"


@dataclass
class Incident:
    code: str
    detail: str
    raised_at: datetime
    actor: str


@dataclass
class IncidentManager:
    state: State = State.HEALTHY
    incidents: list[Incident] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def can_trade(self) -> bool:
        with self._lock:
            return self.state is State.HEALTHY

    def can_quote(self) -> bool:
        """Quoting (passive) is allowed in HEALTHY and DEGRADED, never beyond."""
        with self._lock:
            return self.state in (State.HEALTHY, State.DEGRADED)

    def trip_degraded(self, *, code: str, detail: str = "", actor: str = "") -> None:
        with self._lock:
            if self.state is State.KILLED:
                return
            if self.state is State.HEALTHY:
                self.state = State.DEGRADED
            self.incidents.append(
                Incident(code=code, detail=detail, raised_at=datetime.now(timezone.utc), actor=actor)
            )

    def trip_lockdown(self, *, code: str, detail: str = "", actor: str = "") -> None:
        with self._lock:
            if self.state is State.KILLED:
                return
            self.state = State.LOCKDOWN
            self.incidents.append(
                Incident(code=code, detail=detail, raised_at=datetime.now(timezone.utc), actor=actor)
            )

    def trip_killed(self, *, code: str, detail: str = "", actor: str = "") -> None:
        with self._lock:
            self.state = State.KILLED
            self.incidents.append(
                Incident(code=code, detail=detail, raised_at=datetime.now(timezone.utc), actor=actor)
            )

    def recover_to_healthy(self) -> bool:
        """Operator-initiated recovery from DEGRADED. No-op for LOCKDOWN/KILLED."""
        with self._lock:
            if self.state is State.DEGRADED:
                self.state = State.HEALTHY
                return True
            return False

    def latest(self, n: int = 5) -> list[Incident]:
        with self._lock:
            return list(self.incidents[-n:])
