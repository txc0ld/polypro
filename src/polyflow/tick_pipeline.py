"""Data Hygiene Layer (Protocol §1).

The strategy NEVER reads raw websocket ticks. It reads from the clean buffer
this module maintains. Every tick goes through:

  1. nanosecond receipt timestamp
  2. anomaly filters (8% jumps, post-reconnect discard, out-of-order reorder)
  3. enrichment with sequence info + provenance
  4. insertion into a 10-second clean rolling buffer

Discarded ticks are written to a JSONL audit log with the reject reason —
required by the protocol for forensics.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock


def now_ns() -> int:
    """Nanosecond receipt timestamp (monotonic-ish; uses time.time_ns)."""
    return time.time_ns()


@dataclass(frozen=True)
class Tick:
    feed_id: str          # which provider this came from
    market_id: str
    token_id: str
    price: float
    size: float           # depth at this level (USD or token units, consistent within a feed)
    sequence: int | None  # provider sequence number, when available
    received_ns: int
    venue_ts_ms: int | None = None   # exchange-side timestamp if the feed exposes one


@dataclass
class TickAuditEvent:
    ns: int
    feed_id: str
    reason: str
    raw: dict


class TickAuditLog:
    """Append-only JSONL of every discarded tick (reason + raw payload)."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def write(self, event: TickAuditEvent) -> None:
        line = json.dumps(
            {"ns": event.ns, "feed": event.feed_id, "reason": event.reason, "raw": event.raw},
            separators=(",", ":"),
        )
        with self._lock:
            with self._path.open("ab") as f:
                f.write((line + "\n").encode("utf-8"))


@dataclass
class TickFilterConfig:
    """Tunable anomaly filter parameters."""

    max_jump_pct: float = 0.08            # Protocol §1: >8% jumps in <2s without matching flow
    jump_window_ns: int = 2_000_000_000   # 2 seconds
    discard_first_n_after_reconnect: int = 15
    reorder_window_ns: int = 500_000_000   # 500 ms
    clean_buffer_seconds: float = 10.0


@dataclass
class _FeedState:
    last_price: float | None = None
    last_price_ns: int | None = None
    last_sequence: int | None = None
    ticks_since_reconnect: int = 0
    out_of_order_buffer: deque[Tick] = field(default_factory=deque)


class TickPipeline:
    """Single-token tick pipeline. Spin up one per (market_id, token_id, side)."""

    def __init__(
        self,
        *,
        config: TickFilterConfig | None = None,
        audit_log: TickAuditLog | None = None,
    ) -> None:
        self.config = config or TickFilterConfig()
        self.audit_log = audit_log
        self._feed_states: dict[str, _FeedState] = {}
        self._clean: deque[tuple[int, Tick]] = deque()
        self._lock = RLock()

    # --- ingress ---------------------------------------------------------
    def on_reconnect(self, feed_id: str) -> None:
        """Mark the start of a reconnect window — first N ticks must be discarded."""
        with self._lock:
            st = self._feed_states.setdefault(feed_id, _FeedState())
            st.ticks_since_reconnect = 0
            st.last_sequence = None
            st.out_of_order_buffer.clear()

    def submit(self, tick: Tick, *, raw: dict | None = None) -> bool:
        """Run the tick through the filters. Return True if it joined the clean buffer."""
        with self._lock:
            st = self._feed_states.setdefault(tick.feed_id, _FeedState())
            st.ticks_since_reconnect += 1

            # Filter 1: post-reconnect discard
            if st.ticks_since_reconnect <= self.config.discard_first_n_after_reconnect:
                self._discard(tick, "POST_RECONNECT_DISCARD", raw)
                return False

            # Filter 2: sequence-based out-of-order detection (when sequence numbers exist)
            if tick.sequence is not None and st.last_sequence is not None:
                if tick.sequence < st.last_sequence:
                    self._discard(tick, "OUT_OF_ORDER_SEQUENCE", raw)
                    return False
                if tick.sequence == st.last_sequence:
                    self._discard(tick, "DUPLICATE_SEQUENCE", raw)
                    return False

            # Filter 3: timestamp-based out-of-order with reorder window
            if (
                st.last_price_ns is not None
                and tick.received_ns < st.last_price_ns - self.config.reorder_window_ns
            ):
                self._discard(tick, "OUT_OF_ORDER_TIMESTAMP", raw)
                return False

            # Filter 4: 8% jump rule
            if (
                st.last_price is not None
                and st.last_price_ns is not None
                and st.last_price > 0
                and (tick.received_ns - st.last_price_ns) <= self.config.jump_window_ns
            ):
                pct = abs(tick.price - st.last_price) / st.last_price
                if pct > self.config.max_jump_pct:
                    self._discard(tick, f"PRICE_JUMP_{pct:.4f}_NO_FLOW_CONFIRM", raw)
                    return False

            # Accept
            st.last_price = tick.price
            st.last_price_ns = tick.received_ns
            if tick.sequence is not None:
                st.last_sequence = tick.sequence

            self._clean.append((tick.received_ns, tick))
            self._evict_stale()
            return True

    # --- egress ----------------------------------------------------------
    def clean_buffer(self) -> list[Tick]:
        """Return the current clean buffer, oldest first."""
        with self._lock:
            self._evict_stale()
            return [t for _, t in self._clean]

    def latest(self) -> Tick | None:
        with self._lock:
            self._evict_stale()
            return self._clean[-1][1] if self._clean else None

    # --- internals -------------------------------------------------------
    def _evict_stale(self) -> None:
        cutoff = now_ns() - int(self.config.clean_buffer_seconds * 1_000_000_000)
        while self._clean and self._clean[0][0] < cutoff:
            self._clean.popleft()

    def _discard(self, tick: Tick, reason: str, raw: dict | None) -> None:
        if self.audit_log is not None:
            self.audit_log.write(
                TickAuditEvent(
                    ns=now_ns(),
                    feed_id=tick.feed_id,
                    reason=reason,
                    raw=raw or {"price": tick.price, "size": tick.size, "seq": tick.sequence},
                )
            )
