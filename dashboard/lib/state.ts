import "server-only";
import { readLatest, type LogRecord } from "./log";

export type SystemState = "HEALTHY" | "DEGRADED" | "LOCKDOWN" | "KILLED" | "UNKNOWN";

const STATE_VALUES: SystemState[] = ["HEALTHY", "DEGRADED", "LOCKDOWN", "KILLED", "UNKNOWN"];

function coerceState(value: unknown): SystemState | null {
  if (typeof value !== "string") return null;
  const upper = value.toUpperCase();
  return (STATE_VALUES as string[]).includes(upper) ? (upper as SystemState) : null;
}

/**
 * The live system state. We look at the latest entry from incident-emitting
 * actors (kill_switch, portfolio_sentinel, runtime). If nothing is found we
 * report UNKNOWN — the runtime hasn't booted yet on this host.
 */
export async function readSystemState(): Promise<{ state: SystemState; source: LogRecord | null }> {
  const latest = await readLatest({
    actor: ["kill_switch", "portfolio_sentinel", "runtime"],
  });
  if (!latest) return { state: "UNKNOWN", source: null };
  const payload = latest.payload ?? {};
  const candidate =
    coerceState(payload["state"]) ??
    coerceState(payload["status"]) ??
    coerceState(payload["mode"]);
  return { state: candidate ?? "HEALTHY", source: latest };
}
