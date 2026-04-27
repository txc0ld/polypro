import { getDb } from "./db";
import {
  currentIncidentState,
  loadHeartbeat,
  logExists,
  tailLog,
  type IncidentState,
  type LogRecord,
} from "./log";
import { heartbeatPath } from "./paths";
import { readPolicy, type PolicySummary } from "./policy";
import { fetchWalletValue, funderAddress, type WalletValue } from "./wallet";

const DAY_MS = 24 * 60 * 60 * 1000;
const HEARTBEAT_FRESH_MS = 30 * 1000;
const HEARTBEAT_STALE_MS = 5 * 60 * 1000;

export type HeartbeatStatus = "fresh" | "stale" | "missing";

export type RuntimeStatus = {
  incident: IncidentState;
  mode: string | null;
  policy: PolicySummary;
  heartbeat: { ts: string | null; pid: number | null; status: HeartbeatStatus };
  dailyPnlUsdc: number;
  openOrders: number;
  activeMarkets: number;
  lastTradeAt: string | null;
  walletAddress: string | null;
  wallet: WalletValue | null;
  recent: LogRecord[];
};

function dailyPnl(records: LogRecord[]): number {
  const cutoff = Date.now() - DAY_MS;
  let total = 0;
  for (const r of records) {
    const t = new Date(r.ts).getTime();
    if (Number.isNaN(t) || t < cutoff) continue;
    const pnl = (r.payload as { realized_pnl_usdc?: number }).realized_pnl_usdc;
    if (typeof pnl === "number") total += pnl;
  }
  return total;
}

function openOrdersFromLog(records: LogRecord[]): number {
  const open = new Set<string>();
  for (const r of records) {
    if (r.actor !== "clob_adapter") continue;
    const id = (r.payload as { exchange_order_id?: string }).exchange_order_id;
    if (!id) continue;
    if (r.action === "place_order") open.add(id);
    else if (r.action === "cancel_order" || r.action === "fill") open.delete(id);
  }
  return open.size;
}

function lastTradeAt(records: LogRecord[]): string | null {
  for (let i = records.length - 1; i >= 0; i--) {
    const r = records[i];
    if (
      r.actor === "clob_adapter" &&
      (r.action === "place_order" || r.action === "fill")
    ) {
      return r.ts;
    }
  }
  return null;
}

function activeMarketCount(): number {
  const db = getDb();
  if (!db) return 0;
  const row = db
    .prepare("SELECT COUNT(*) as n FROM markets WHERE status = 'watching'")
    .get() as { n: number } | undefined;
  return row?.n ?? 0;
}

export async function loadRuntimeStatus(): Promise<RuntimeStatus> {
  const policy = readPolicy();
  const incident = await currentIncidentState();
  const hb = await loadHeartbeat(heartbeatPath);

  const now = Date.now();
  const hbStatus: HeartbeatStatus = !hb
    ? "missing"
    : now - new Date(hb.ts).getTime() < HEARTBEAT_FRESH_MS
      ? "fresh"
      : now - new Date(hb.ts).getTime() < HEARTBEAT_STALE_MS
        ? "stale"
        : "missing";

  const recent = logExists() ? await tailLog(2000) : [];

  const address = funderAddress();
  const wallet = address ? await fetchWalletValue(address) : null;

  return {
    incident,
    mode: policy.mode,
    policy,
    heartbeat: { ts: hb?.ts ?? null, pid: hb?.pid ?? null, status: hbStatus },
    dailyPnlUsdc: dailyPnl(recent),
    openOrders: openOrdersFromLog(recent),
    activeMarkets: activeMarketCount(),
    lastTradeAt: lastTradeAt(recent),
    walletAddress: address,
    wallet,
    recent,
  };
}
