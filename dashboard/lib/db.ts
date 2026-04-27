import fs from "node:fs";
import Database from "better-sqlite3";
import { dbPath } from "./paths";

let cached: Database.Database | null = null;

export function getDb(): Database.Database | null {
  if (cached) return cached;
  if (!fs.existsSync(dbPath)) return null;
  cached = new Database(dbPath, { readonly: true, fileMustExist: true });
  cached.pragma("query_only = true");
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

export type CalibrationBucketRow = {
  bucket: number;
  mean_predicted: number;
  empirical: number;
  n: number;
};

export function listMarketsByStatus(status: string): MarketRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare<[string], MarketRow>(
      "SELECT * FROM markets WHERE status = ? ORDER BY created_at DESC",
    )
    .all(status);
}

export function listAllMarkets(): MarketRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare<[], MarketRow>("SELECT * FROM markets ORDER BY created_at DESC")
    .all();
}

export function getMarket(marketId: string): MarketRow | undefined {
  const db = getDb();
  if (!db) return undefined;
  return db
    .prepare<[string], MarketRow>("SELECT * FROM markets WHERE id = ?")
    .get(marketId);
}

export function listOpenPositions(): PositionRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare<[], PositionRow>(
      "SELECT * FROM positions WHERE size > 0 AND status = 'OPEN' ORDER BY updated_at DESC",
    )
    .all();
}

export function listSignalsForMarket(marketId: string): SignalRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare<[string], SignalRow>(
      "SELECT * FROM signals WHERE market_id = ? ORDER BY created_at DESC",
    )
    .all(marketId);
}

export function getSignal(signalId: string): SignalRow | undefined {
  const db = getDb();
  if (!db) return undefined;
  return db
    .prepare<[string], SignalRow>("SELECT * FROM signals WHERE id = ?")
    .get(signalId);
}

export function calibrationBuckets(): CalibrationBucketRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare<[], CalibrationBucketRow>(
      `SELECT bucket,
              AVG(predicted_probability) AS mean_predicted,
              AVG(CAST(realized AS REAL)) AS empirical,
              COUNT(*) AS n
       FROM calibration_observations
       GROUP BY bucket
       ORDER BY bucket`,
    )
    .all();
}

export function dbAvailable(): boolean {
  return getDb() !== null;
}
