-- POLYFLOW PostgreSQL schema (PRD §18)

CREATE TABLE IF NOT EXISTS markets (
  id                TEXT PRIMARY KEY,
  event_id          TEXT,
  question          TEXT NOT NULL,
  category          TEXT,
  close_time        TIMESTAMPTZ,
  resolution_rules  TEXT,
  liquidity_usd     NUMERIC,
  volume_24h_usd    NUMERIC,
  spread_pct        NUMERIC,
  market_quality    NUMERIC,
  resolution_risk   NUMERIC,
  status            TEXT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS markets_status_idx       ON markets(status);
CREATE INDEX IF NOT EXISTS markets_close_time_idx   ON markets(close_time);
CREATE INDEX IF NOT EXISTS markets_event_idx        ON markets(event_id);

CREATE TABLE IF NOT EXISTS outcome_tokens (
  token_id        TEXT PRIMARY KEY,
  market_id       TEXT NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
  outcome         TEXT NOT NULL,
  tick_size       NUMERIC,
  min_order_size  NUMERIC,
  fee_rate_bps    NUMERIC,
  neg_risk        BOOLEAN
);

CREATE INDEX IF NOT EXISTS outcome_tokens_market_idx ON outcome_tokens(market_id);

CREATE TABLE IF NOT EXISTS probability_estimates (
  id                  UUID PRIMARY KEY,
  market_id           TEXT NOT NULL,
  token_id            TEXT NOT NULL,
  model_probability   NUMERIC NOT NULL,
  market_price        NUMERIC NOT NULL,
  uncertainty         NUMERIC NOT NULL,
  effective_edge      NUMERIC NOT NULL,
  source_confidence   NUMERIC NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS probability_estimates_market_idx
  ON probability_estimates(market_id, created_at DESC);

CREATE TABLE IF NOT EXISTS signals (
  id              UUID PRIMARY KEY,
  market_id       TEXT NOT NULL,
  token_id        TEXT NOT NULL,
  strategy        TEXT NOT NULL,
  side            TEXT NOT NULL,
  score           NUMERIC NOT NULL,
  status          TEXT NOT NULL,
  reason_codes    JSONB NOT NULL,
  evidence_refs   JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS signals_market_idx  ON signals(market_id, created_at DESC);
CREATE INDEX IF NOT EXISTS signals_status_idx  ON signals(status);

CREATE TABLE IF NOT EXISTS orders (
  id                UUID PRIMARY KEY,
  client_order_id   TEXT UNIQUE NOT NULL,
  exchange_order_id TEXT,
  market_id         TEXT NOT NULL,
  token_id          TEXT NOT NULL,
  side              TEXT NOT NULL,
  price             NUMERIC NOT NULL,
  size              NUMERIC NOT NULL,
  order_type        TEXT NOT NULL,
  status            TEXT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS orders_market_idx ON orders(market_id);
CREATE INDEX IF NOT EXISTS orders_status_idx ON orders(status);

CREATE TABLE IF NOT EXISTS positions (
  id            UUID PRIMARY KEY,
  market_id     TEXT NOT NULL,
  token_id      TEXT NOT NULL,
  outcome       TEXT NOT NULL,
  size          NUMERIC NOT NULL,
  avg_price     NUMERIC NOT NULL,
  market_value  NUMERIC,
  max_loss      NUMERIC,
  status        TEXT NOT NULL,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (market_id, token_id)
);

-- Append-only. Never UPDATE or DELETE. Enforced at the application layer
-- and via row-level grants in production.
CREATE TABLE IF NOT EXISTS immutable_log (
  id            UUID PRIMARY KEY,
  ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor         TEXT NOT NULL,
  action        TEXT NOT NULL,
  market_id     TEXT,
  event_id      TEXT,
  input_hash    TEXT,
  output_hash   TEXT,
  config_hash   TEXT,
  code_version  TEXT,
  payload       JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS immutable_log_ts_idx       ON immutable_log(ts DESC);
CREATE INDEX IF NOT EXISTS immutable_log_action_idx   ON immutable_log(action);
CREATE INDEX IF NOT EXISTS immutable_log_market_idx   ON immutable_log(market_id);
