import "server-only";
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

const matchSet = (value: string | null | undefined, target: string | string[] | undefined) => {
  if (!target) return true;
  if (Array.isArray(target)) return value !== null && value !== undefined && target.includes(value);
  return value === target;
};

async function streamLines(file: string): Promise<readline.Interface | null> {
  if (!fs.existsSync(file)) return null;
  const stream = fs.createReadStream(file, { encoding: "utf8" });
  return readline.createInterface({ input: stream, crlfDelay: Infinity });
}

/**
 * Read the tail of the immutable log. We stream line-by-line to avoid
 * loading the whole file, but to get the *last* N matching records we keep
 * a bounded ring buffer.
 */
export async function readLogTail(
  tail: number,
  filter: LogFilter = {},
): Promise<LogRecord[]> {
  const rl = await streamLines(logPath);
  if (!rl) return [];
  const ring: LogRecord[] = [];
  for await (const line of rl) {
    if (!line) continue;
    let rec: LogRecord;
    try {
      rec = JSON.parse(line) as LogRecord;
    } catch {
      continue;
    }
    if (!matchSet(rec.actor, filter.actor)) continue;
    if (!matchSet(rec.action, filter.action)) continue;
    if (filter.marketId && rec.market_id !== filter.marketId) continue;
    if (filter.signalId) {
      const sid =
        (rec.payload?.["signal_id"] as string | undefined) ??
        (rec.payload?.["id"] as string | undefined);
      if (sid !== filter.signalId) continue;
    }
    ring.push(rec);
    if (ring.length > tail) ring.shift();
  }
  return ring;
}

export async function readAllMatching(filter: LogFilter): Promise<LogRecord[]> {
  return readLogTail(Number.MAX_SAFE_INTEGER, filter);
}

/** Latest record matching the filter, or null. */
export async function readLatest(filter: LogFilter): Promise<LogRecord | null> {
  const tail = await readLogTail(1, filter);
  return tail[0] ?? null;
}
