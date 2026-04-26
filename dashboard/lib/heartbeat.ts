import "server-only";
import fs from "node:fs";
import { heartbeatPath } from "./paths";

export type Heartbeat = {
  ts: string | null;
  ageSeconds: number | null;
  raw: Record<string, unknown> | null;
};

export function readHeartbeat(): Heartbeat {
  if (!fs.existsSync(heartbeatPath)) {
    return { ts: null, ageSeconds: null, raw: null };
  }
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(fs.readFileSync(heartbeatPath, "utf8")) as Record<string, unknown>;
  } catch {
    return { ts: null, ageSeconds: null, raw: null };
  }
  const ts = (raw["ts"] as string | undefined) ?? (raw["timestamp"] as string | undefined) ?? null;
  let ageSeconds: number | null = null;
  if (ts) {
    const parsed = Date.parse(ts);
    if (!Number.isNaN(parsed)) ageSeconds = Math.floor((Date.now() - parsed) / 1000);
  }
  return { ts, ageSeconds, raw };
}
