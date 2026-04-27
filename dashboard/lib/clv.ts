import { getDb } from "./db";
import { tailLog, type LogRecord } from "./log";

/**
 * Closing-Line Value
 * ------------------
 * For each resolved market we look at every signal that produced a fill,
 * find the *closing line* (the last `market_price` recorded before the
 * resolution entry), and compute:
 *
 *   CLV (BUY)  = closing_price - execution_price
 *   CLV (SELL) = execution_price - closing_price
 *
 * Positive CLV means we got a better price than the eventual closing crowd —
 * i.e. our edge survived market discovery. PRD §0 calls CLV out alongside
 * Brier as the institutional signal-quality metric. We also report Brier vs
 * the realized outcome when the market is resolved.
 */

type Resolution = { market_id: string; outcome: string; resolved_at: string };
type SignalDbRow = {
  id: string;
  market_id: string;
  token_id: string;
  strategy: string;
  side: string;
  status: string;
  created_at: string;
};

export type ClvRecord = {
  signalId: string;
  marketId: string;
  strategy: string;
  side: "BUY" | "SELL";
  outcome: string;
  executionPrice: number | null;
  closingLine: number | null;
  clv: number | null;
  resolvedAt: string;
};

function getResolutions(): Resolution[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare<[], Resolution>(
      "SELECT market_id, outcome, resolved_at FROM resolutions",
    )
    .all();
}

function getSignals(): SignalDbRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare<[], SignalDbRow>(
      `SELECT id, market_id, token_id, strategy, side, status, created_at
       FROM signals WHERE status NOT IN ('REJECT','WATCH')`,
    )
    .all();
}

function findExecutionPrice(
  records: LogRecord[],
  signalId: string,
): number | null {
  for (const r of records) {
    if (r.actor !== "clob_order_formatter" || r.action !== "format") continue;
    const p = r.payload as {
      risk_ref?: string;
      order_payload?: { price?: string | number };
    };
    if (p.risk_ref !== signalId) continue;
    const px = p.order_payload?.price;
    if (typeof px === "number") return px;
    if (typeof px === "string") {
      const n = Number(px);
      if (!Number.isNaN(n)) return n;
    }
  }
  return null;
}

function findClosingLine(
  records: LogRecord[],
  marketId: string,
  resolvedAt: string,
): number | null {
  // Last `signal_arbiter score` payload for this market before resolution
  // carries `market_price`. Walk in reverse for efficiency.
  const cutoff = new Date(resolvedAt).getTime();
  for (let i = records.length - 1; i >= 0; i--) {
    const r = records[i];
    if (r.market_id !== marketId) continue;
    if (new Date(r.ts).getTime() > cutoff) continue;
    const px = (r.payload as { market_price?: number }).market_price;
    if (typeof px === "number") return px;
  }
  return null;
}

export async function computeClv(): Promise<ClvRecord[]> {
  const resolutions = getResolutions();
  if (resolutions.length === 0) return [];
  const resolvedSet = new Map(resolutions.map((r) => [r.market_id, r]));
  const signals = getSignals().filter((s) => resolvedSet.has(s.market_id));
  if (signals.length === 0) return [];

  const records = await tailLog(50000);
  const formatterRecords = records.filter(
    (r) => r.actor === "clob_order_formatter",
  );
  const arbiterRecords = records.filter((r) => r.actor === "signal_arbiter");

  const out: ClvRecord[] = [];
  for (const s of signals) {
    const res = resolvedSet.get(s.market_id);
    if (!res) continue;
    const exec = findExecutionPrice(formatterRecords, s.id);
    const close = findClosingLine(arbiterRecords, s.market_id, res.resolved_at);
    let clv: number | null = null;
    if (exec !== null && close !== null) {
      clv = s.side === "BUY" ? close - exec : exec - close;
    }
    out.push({
      signalId: s.id,
      marketId: s.market_id,
      strategy: s.strategy,
      side: s.side as "BUY" | "SELL",
      outcome: res.outcome,
      executionPrice: exec,
      closingLine: close,
      clv,
      resolvedAt: res.resolved_at,
    });
  }
  return out;
}

export async function computeClvForSignal(
  signalId: string,
): Promise<ClvRecord | null> {
  const all = await computeClv();
  return all.find((c) => c.signalId === signalId) ?? null;
}

export type ClvByStrategy = {
  strategy: string;
  n: number;
  mean: number;
  positive: number;
};

export function aggregateByStrategy(records: ClvRecord[]): ClvByStrategy[] {
  const by = new Map<string, number[]>();
  for (const r of records) {
    if (r.clv === null) continue;
    const arr = by.get(r.strategy) ?? [];
    arr.push(r.clv);
    by.set(r.strategy, arr);
  }
  return [...by.entries()]
    .map(([strategy, vals]) => ({
      strategy,
      n: vals.length,
      mean: vals.reduce((a, b) => a + b, 0) / vals.length,
      positive: vals.filter((v) => v > 0).length,
    }))
    .sort((a, b) => b.n - a.n);
}
