import "server-only";
import fs from "node:fs";
import Database, { type Database as Db } from "better-sqlite3";
import { dbPath } from "./paths";

let cached: Db | null = null;

export function getDb(): Db | null {
  if (cached) return cached;
  if (!fs.existsSync(dbPath)) return null;
  cached = new Database(dbPath, { readonly: true, fileMustExist: true });
  cached.pragma("journal_mode = WAL");
  return cached;
}

export type MarketRow = {
  id: string;
  event_id: string | null;
  question: string;
  category: string | null;
  close_time: string | null;
  resolution_rules: string | null;
  liquidity_usd: number | null;
  volume_24h_usd: number | null;
  spread_pct: number | null;
  market_quality: number | null;
  resolution_risk: number | null;
  status: string;
  created_at: string;
};

export type OutcomeTokenRow = {
  token_id: string;
  market_id: string;
  outcome: string;
  tick_size: number | null;
  min_order_size: number | null;
  fee_rate_bps: number | null;
  neg_risk: number | null;
};

export type PositionRow = {
  market_id: string;
  token_id: string;
  outcome: string;
  size: number;
  avg_price: number;
  market_value: number | null;
  max_loss: number | null;
  status: string;
  updated_at: string;
};

export type SignalRow = {
  id: string;
  market_id: string;
  token_id: string;
  strategy: string;
  side: string;
  score: number;
  status: string;
  reason_codes: string;
  evidence_refs: string;
  created_at: string;
};

export type ResolutionRow = {
  market_id: string;
  outcome: string;
  resolved_at: string;
};

export type CalibrationBucketRow = {
  bucket: number;
  mean_predicted: number;
  empirical: number;
  n: number;
};

export function listMarkets(): MarketRow[] {
  const db = getDb();
  if (!db) return [];
  return db.prepare("SELECT * FROM markets ORDER BY created_at DESC").all() as MarketRow[];
}

export function getMarket(id: string): MarketRow | null {
  const db = getDb();
  if (!db) return null;
  const row = db.prepare("SELECT * FROM markets WHERE id = ?").get(id) as MarketRow | undefined;
  return row ?? null;
}

export function getMarketsByStatus(status: string): MarketRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare("SELECT * FROM markets WHERE status = ? ORDER BY created_at DESC")
    .all(status) as MarketRow[];
}

export function getOutcomeTokens(marketId: string): OutcomeTokenRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare("SELECT * FROM outcome_tokens WHERE market_id = ?")
    .all(marketId) as OutcomeTokenRow[];
}

export function getOpenPositions(): PositionRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare("SELECT * FROM positions WHERE size > 0 AND status = 'OPEN'")
    .all() as PositionRow[];
}

export function getSignal(id: string): SignalRow | null {
  const db = getDb();
  if (!db) return null;
  const row = db.prepare("SELECT * FROM signals WHERE id = ?").get(id) as SignalRow | undefined;
  return row ?? null;
}

export function getResolution(marketId: string): ResolutionRow | null {
  const db = getDb();
  if (!db) return null;
  const row = db
    .prepare("SELECT * FROM resolutions WHERE market_id = ?")
    .get(marketId) as ResolutionRow | undefined;
  return row ?? null;
}

export function getCalibrationBuckets(): CalibrationBucketRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare(
      `SELECT bucket,
              AVG(predicted_probability) AS mean_predicted,
              AVG(CAST(realized AS REAL))  AS empirical,
              COUNT(*)                     AS n
       FROM calibration_observations GROUP BY bucket ORDER BY bucket`,
    )
    .all() as CalibrationBucketRow[];
}

export function calibrationBucketFor(p: number): number {
  return Math.round(Math.round(p * 10) / 10 * 10) / 10;
}
