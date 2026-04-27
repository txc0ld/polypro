import fs from "node:fs";
import readline from "node:readline";
import { logPath } from "./paths";

export type LogRecord = {
  id: string;
  ts: string;
  actor: string;
  action: string;
  market_id: string | null;
  event_id: string | null;
  input_hash: string | null;
  output_hash: string | null;
  config_hash: string;
  code_version: string;
  payload: Record<string, unknown>;
};

export type LogFilter = {
  actor?: string | string[];
  action?: string | string[];
  marketId?: string;
  signalId?: string;
};

export function logExists(): boolean {
  return fs.existsSync(logPath);
}

const matches = (val: string | null, filter: string | string[] | undefined) => {
  if (filter === undefined) return true;
  if (Array.isArray(filter)) return val !== null && filter.includes(val);
  return val === filter;
};

const matchSignalId = (rec: LogRecord, signalId: string) => {
  const direct = (rec.payload as { signal_id?: unknown }).signal_id;
  if (typeof direct === "string" && direct === signalId) return true;
  // Some records nest the signal id in nested objects (formatter, place_order).
  const refs = ["risk_ref", "clientOrderId"];
  for (const k of refs) {
    const v = (rec.payload as Record<string, unknown>)[k];
    if (typeof v === "string" && v.includes(signalId)) return true;
  }
  return false;
};

/**
 * Stream-read the JSONL log line by line and return the most recent records
 * matching the filter. We keep a rolling buffer of size `limit` so we never
 * hold the whole file in memory.
 */
export async function tailLog(
  limit = 200,
  filter: LogFilter = {},
): Promise<LogRecord[]> {
  if (!logExists()) return [];

  const rl = readline.createInterface({
    input: fs.createReadStream(logPath, { encoding: "utf8" }),
    crlfDelay: Infinity,
  });

  const buf: LogRecord[] = [];
  for await (const line of rl) {
    if (!line) continue;
    let rec: LogRecord;
    try {
      rec = JSON.parse(line) as LogRecord;
    } catch {
      continue;
    }
    if (!matches(rec.actor, filter.actor)) continue;
    if (!matches(rec.action, filter.action)) continue;
    if (filter.marketId && rec.market_id !== filter.marketId) continue;
    if (filter.signalId && !matchSignalId(rec, filter.signalId)) continue;
    buf.push(rec);
    if (buf.length > limit) buf.shift();
  }
  return buf;
}

export async function loadHeartbeat(
  heartbeatPath: string,
): Promise<{ ts: string; pid: number } | null> {
  if (!fs.existsSync(heartbeatPath)) return null;
  try {
    const raw = await fs.promises.readFile(heartbeatPath, "utf8");
    return JSON.parse(raw) as { ts: string; pid: number };
  } catch {
    return null;
  }
}

export type IncidentState = "HEALTHY" | "DEGRADED" | "LOCKDOWN" | "KILLED";

const stateRank: Record<IncidentState, number> = {
  HEALTHY: 0,
  DEGRADED: 1,
  LOCKDOWN: 2,
  KILLED: 3,
};

/**
 * Walk the log forward and reconstruct the highest incident state reached.
 * Looks at `kill_switch` and `incident_*` actions in the payload.
 */
export async function currentIncidentState(): Promise<IncidentState> {
  if (!logExists()) return "HEALTHY";

  const rl = readline.createInterface({
    input: fs.createReadStream(logPath, { encoding: "utf8" }),
    crlfDelay: Infinity,
  });

  let highest: IncidentState = "HEALTHY";
  for await (const line of rl) {
    if (!line) continue;
    let rec: LogRecord;
    try {
      rec = JSON.parse(line) as LogRecord;
    } catch {
      continue;
    }
    let next: IncidentState | null = null;
    if (rec.action === "kill_switch") next = "KILLED";
    else if (rec.action === "incident_lockdown") next = "LOCKDOWN";
    else if (rec.action === "incident_degraded") next = "DEGRADED";
    else if (rec.action === "incident_recovered") next = "HEALTHY";
    if (next && stateRank[next] > stateRank[highest]) highest = next;
    if (next === "HEALTHY") highest = "HEALTHY";
  }
  return highest;
}
