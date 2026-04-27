"""SQLite persistence — a thin synchronous repo backing the v1 runtime.

The Postgres schema in ``db/schema.sql`` is the production target; this is a
faithful subset used in development, paper mode, and tests. All writes are
done in autocommit so that a process crash never loses an immutable-log row.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..types import Market, Position, Signal


_SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
  id TEXT PRIMARY KEY,
  event_id TEXT,
  question TEXT NOT NULL,
  category TEXT,
  close_time TEXT,
  resolution_rules TEXT,
  liquidity_usd REAL,
  volume_24h_usd REAL,
  spread_pct REAL,
  market_quality REAL,
  resolution_risk REAL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS outcome_tokens (
  token_id TEXT PRIMARY KEY,
  market_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  tick_size REAL,
  min_order_size REAL,
  fee_rate_bps REAL,
  neg_risk INTEGER
);

CREATE TABLE IF NOT EXISTS signals (
  id TEXT PRIMARY KEY,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  strategy TEXT NOT NULL,
  side TEXT NOT NULL,
  score REAL NOT NULL,
  status TEXT NOT NULL,
  reason_codes TEXT NOT NULL,
  evidence_refs TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS positions (
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  size REAL NOT NULL,
  avg_price REAL NOT NULL,
  market_value REAL,
  max_loss REAL,
  status TEXT NOT NULL DEFAULT 'OPEN',
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (market_id, token_id)
);

CREATE TABLE IF NOT EXISTS resolutions (
  market_id TEXT PRIMARY KEY,
  outcome TEXT NOT NULL,        -- 'YES' or 'NO'
  resolved_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS calibration_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  predicted_probability REAL NOT NULL,
  realized INTEGER NOT NULL,    -- 0 or 1
  bucket REAL NOT NULL,         -- e.g. 0.10, 0.20, …, 1.00
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS probability_estimates (
  id TEXT PRIMARY KEY,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  market_price REAL NOT NULL,
  model_probability REAL NOT NULL,
  uncertainty REAL NOT NULL,
  edge_after_costs REAL NOT NULL,
  source_confidence REAL NOT NULL,
  resolution_risk REAL NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS probability_estimates_market_idx
  ON probability_estimates(market_id, created_at);

CREATE TABLE IF NOT EXISTS open_orders_snapshot (
  exchange_order_id TEXT PRIMARY KEY,
  client_order_id TEXT,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  side TEXT NOT NULL,
  price REAL NOT NULL,
  size REAL NOT NULL,
  status TEXT NOT NULL,
  observed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS closing_line_values (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id TEXT NOT NULL,
  token_id TEXT NOT NULL,
  signal_id TEXT,
  entry_price REAL NOT NULL,
  closing_price REAL NOT NULL,
  side TEXT NOT NULL,           -- 'BUY_YES' or 'BUY_NO'
  clv REAL NOT NULL,            -- in basis points, signed
  recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS source_reliability (
  source_name TEXT PRIMARY KEY,
  prior REAL NOT NULL DEFAULT 0.70,
  hits INTEGER NOT NULL DEFAULT 0,
  misses INTEGER NOT NULL DEFAULT 0,
  brier_sum REAL NOT NULL DEFAULT 0.0,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
"""


class SQLiteStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + lock — the runtime is asyncio so callers
        # may hand the connection between tasks, but we still serialize writes.
        self._conn = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    # ---------- markets ----------
    def upsert_market(self, m: Market, *, status: str = "watching") -> None:
        close_time = m.close_time.isoformat() if m.close_time else None
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO markets (
                    id, event_id, question, category, close_time, resolution_rules,
                    liquidity_usd, volume_24h_usd, spread_pct, market_quality,
                    resolution_risk, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    event_id=excluded.event_id,
                    question=excluded.question,
                    category=excluded.category,
                    close_time=excluded.close_time,
                    resolution_rules=excluded.resolution_rules,
                    liquidity_usd=excluded.liquidity_usd,
                    volume_24h_usd=excluded.volume_24h_usd,
                    spread_pct=excluded.spread_pct,
                    market_quality=excluded.market_quality,
                    resolution_risk=excluded.resolution_risk,
                    status=excluded.status
                """,
                (
                    m.id, m.event_id, m.question, m.category, close_time, m.resolution_rules,
                    m.liquidity_usd, m.volume_24h_usd, m.spread_pct, m.market_quality,
                    m.resolution_risk, status,
                ),
            )
            for token_id, outcome in (
                (m.yes_token_id, "YES"),
                (m.no_token_id, "NO"),
            ):
                if not token_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO outcome_tokens (token_id, market_id, outcome, tick_size,
                        min_order_size, fee_rate_bps, neg_risk)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(token_id) DO UPDATE SET
                        market_id=excluded.market_id,
                        outcome=excluded.outcome,
                        tick_size=excluded.tick_size,
                        min_order_size=excluded.min_order_size,
                        fee_rate_bps=excluded.fee_rate_bps,
                        neg_risk=excluded.neg_risk
                    """,
                    (
                        token_id, m.id, outcome, m.tick_size, m.min_order_size,
                        m.fee_rate_bps, 1 if m.neg_risk else 0,
                    ),
                )

    def get_markets_by_status(self, status: str) -> list[dict]:
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM markets WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        return [dict(r) for r in rows]

    def set_market_status(self, market_id: str, status: str) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE markets SET status=? WHERE id=?", (status, market_id))

    # ---------- signals ----------
    def insert_signal(self, s: Signal) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO signals (id, market_id, token_id, strategy, side, score,
                    status, reason_codes, evidence_refs)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(s.signal_id), s.market_id, s.token_id, s.strategy.value,
                    s.side.value, s.score, s.status,
                    json.dumps(s.reason_codes), json.dumps(s.evidence_refs),
                ),
            )

    def get_recent_signals(self, limit: int = 25) -> list[dict]:
        with self._cursor() as cur:
            rows = cur.execute(
                """
                SELECT * FROM signals
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def signal_counts_by_strategy(self) -> list[dict]:
        with self._cursor() as cur:
            rows = cur.execute(
                """
                SELECT strategy, status, COUNT(*) AS n, AVG(score) AS avg_score
                FROM signals
                GROUP BY strategy, status
                ORDER BY n DESC, strategy
                """
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- positions ----------
    def upsert_position(self, p: Position) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO positions (market_id, token_id, outcome, size, avg_price,
                    market_value, max_loss, status, updated_at)
                VALUES (?,?,?,?,?,?,?,'OPEN', strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(market_id, token_id) DO UPDATE SET
                    size=excluded.size,
                    avg_price=excluded.avg_price,
                    market_value=excluded.market_value,
                    max_loss=excluded.max_loss,
                    updated_at=excluded.updated_at
                """,
                (
                    p.market_id, p.token_id,
                    p.outcome.value if hasattr(p.outcome, "value") else str(p.outcome),
                    p.size, p.avg_price, p.market_value, p.max_loss,
                ),
            )

    def get_open_positions(self) -> list[dict]:
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM positions WHERE size > 0 AND status='OPEN'"
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- resolutions / calibration ----------
    def record_resolution(self, market_id: str, outcome: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO resolutions (market_id, outcome)
                VALUES (?, ?)
                ON CONFLICT(market_id) DO UPDATE SET outcome=excluded.outcome
                """,
                (market_id, outcome),
            )

    def insert_calibration_observation(
        self,
        *,
        market_id: str,
        token_id: str,
        predicted_probability: float,
        realized: bool,
    ) -> None:
        bucket = round(round(predicted_probability * 10) / 10, 1)
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO calibration_observations
                    (market_id, token_id, predicted_probability, realized, bucket)
                VALUES (?,?,?,?,?)
                """,
                (market_id, token_id, predicted_probability, 1 if realized else 0, bucket),
            )

    def calibration_buckets(self) -> dict[float, dict]:
        with self._cursor() as cur:
            rows = cur.execute(
                """
                SELECT bucket, AVG(predicted_probability) AS mean_predicted,
                       AVG(CAST(realized AS REAL)) AS empirical, COUNT(*) AS n
                FROM calibration_observations GROUP BY bucket ORDER BY bucket
                """
            ).fetchall()
        return {row["bucket"]: dict(row) for row in rows}

    # ---------- probability estimates ----------
    def insert_probability_estimate(
        self,
        *,
        estimate_id: str,
        market_id: str,
        token_id: str,
        outcome: str,
        market_price: float,
        model_probability: float,
        uncertainty: float,
        edge_after_costs: float,
        source_confidence: float,
        resolution_risk: float,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO probability_estimates (
                    id, market_id, token_id, outcome, market_price, model_probability,
                    uncertainty, edge_after_costs, source_confidence, resolution_risk
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    estimate_id, market_id, token_id, outcome, market_price,
                    model_probability, uncertainty, edge_after_costs,
                    source_confidence, resolution_risk,
                ),
            )

    def get_probability_estimates(self, market_id: str) -> list[dict]:
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM probability_estimates WHERE market_id=? ORDER BY created_at",
                (market_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- open orders snapshot (for the order-sync subagent) ----------
    def upsert_open_order(
        self,
        *,
        exchange_order_id: str,
        client_order_id: str | None,
        market_id: str,
        token_id: str,
        side: str,
        price: float,
        size: float,
        status: str,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO open_orders_snapshot (
                    exchange_order_id, client_order_id, market_id, token_id,
                    side, price, size, status, observed_at
                ) VALUES (?,?,?,?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(exchange_order_id) DO UPDATE SET
                    client_order_id=excluded.client_order_id,
                    market_id=excluded.market_id,
                    token_id=excluded.token_id,
                    side=excluded.side,
                    price=excluded.price,
                    size=excluded.size,
                    status=excluded.status,
                    observed_at=excluded.observed_at
                """,
                (
                    exchange_order_id, client_order_id, market_id, token_id,
                    side, price, size, status,
                ),
            )

    def get_open_orders(self) -> list[dict]:
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM open_orders_snapshot WHERE status='OPEN' ORDER BY observed_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_open_order(self, exchange_order_id: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM open_orders_snapshot WHERE exchange_order_id=?",
                (exchange_order_id,),
            )

    # ---------- closing line values ----------
    def insert_clv(
        self,
        *,
        market_id: str,
        token_id: str,
        signal_id: str | None,
        entry_price: float,
        closing_price: float,
        side: str,
    ) -> None:
        # CLV in basis points, sign convention: positive when entry was favorable.
        if side == "BUY_YES":
            clv_bps = (closing_price - entry_price) * 10_000
        elif side == "BUY_NO":
            clv_bps = (entry_price - closing_price) * 10_000
        else:
            raise ValueError(f"unknown side: {side!r}")
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO closing_line_values (
                    market_id, token_id, signal_id, entry_price, closing_price, side, clv
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (market_id, token_id, signal_id, entry_price, closing_price, side, clv_bps),
            )

    def average_clv_bps(self) -> float | None:
        with self._cursor() as cur:
            row = cur.execute("SELECT AVG(clv) AS a FROM closing_line_values").fetchone()
        return row["a"] if row and row["a"] is not None else None

    # ---------- source reliability ----------
    def update_source_reliability(
        self, *, source_name: str, hit: bool, brier_increment: float | None = None
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_reliability (source_name, prior, hits, misses, brier_sum)
                VALUES (?, 0.70, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    hits = source_reliability.hits + ?,
                    misses = source_reliability.misses + ?,
                    brier_sum = source_reliability.brier_sum + ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                """,
                (
                    source_name,
                    1 if hit else 0,
                    0 if hit else 1,
                    brier_increment or 0.0,
                    1 if hit else 0,
                    0 if hit else 1,
                    brier_increment or 0.0,
                ),
            )

    def source_reliability(self, source_name: str) -> dict | None:
        with self._cursor() as cur:
            row = cur.execute(
                "SELECT * FROM source_reliability WHERE source_name=?", (source_name,)
            ).fetchone()
        return dict(row) if row else None

    def all_source_reliabilities(self) -> list[dict]:
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM source_reliability ORDER BY hits + misses DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
