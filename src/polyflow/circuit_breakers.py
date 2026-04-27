"""Trade-time circuit breakers (doctrine §risk).

Three rails the strategy_automation consults *before* submitting any order:

  1. Consecutive-loss stop — stop trading after N losing trades in a row
     (default 5). Reset on the first win or operator unfreeze.
  2. Final-N-seconds blackout — refuse trades inside the last N seconds
     before resolution (default 60s) unless explicitly whitelisted.
  3. External-reference-required gate — refuse a market when no feed in
     the runtime can produce a fair-value reference for it. Killed at
     the strategy_automation level by checking that *some* strategy
     emitted a candidate before submitting.

This module owns the state for (1) and (2). (3) is enforced inline in
strategy_automation via the existing `candidate_signals == 0` path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock


@dataclass
class CircuitBreakers:
    """In-memory state for the protective rails."""

    max_consecutive_losses: int = 5
    final_blackout_seconds: int = 60
    whitelisted_market_ids: frozenset[str] = field(default_factory=frozenset)
    _consecutive_losses: int = 0
    _frozen_until_reset: bool = False
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    @property
    def can_trade(self) -> bool:
        with self._lock:
            return not self._frozen_until_reset

    @property
    def consecutive_losses(self) -> int:
        with self._lock:
            return self._consecutive_losses

    def record_outcome(self, *, pnl_usdc: float) -> None:
        """Update the consecutive-loss counter from a realized trade."""
        with self._lock:
            if pnl_usdc < 0:
                self._consecutive_losses += 1
                if self._consecutive_losses >= self.max_consecutive_losses:
                    self._frozen_until_reset = True
            else:
                self._consecutive_losses = 0

    def reset(self) -> None:
        with self._lock:
            self._consecutive_losses = 0
            self._frozen_until_reset = False

    def in_final_blackout(
        self, *, close_time: datetime | None, market_id: str | None = None
    ) -> bool:
        """True when we're inside the final-N-seconds window of the market."""
        if market_id and market_id in self.whitelisted_market_ids:
            return False
        if close_time is None:
            return False
        if close_time.tzinfo is None:
            close_time = close_time.replace(tzinfo=timezone.utc)
        seconds_left = (close_time - datetime.now(timezone.utc)).total_seconds()
        return 0 <= seconds_left < self.final_blackout_seconds
