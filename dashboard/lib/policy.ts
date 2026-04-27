import fs from "node:fs";
import { policyPath } from "./paths";

export type PolicySummary = {
  mode: string | null;
  bankrollUsdc: number | null;
  raw: string;
  exists: boolean;
};

/**
 * Tiny YAML reader for the two scalars we surface (mode + bankroll). Avoids
 * pulling a YAML dep — policy.yaml is a flat-ish file and we only need top-
 * level scalars; everything else is rendered as the raw text.
 */
export function readPolicy(): PolicySummary {
  if (!fs.existsSync(policyPath)) {
    return { mode: null, bankrollUsdc: null, raw: "", exists: false };
  }
  const raw = fs.readFileSync(policyPath, "utf8");
  let mode: string | null = null;
  let bankrollUsdc: number | null = null;
  for (const line of raw.split(/\r?\n/)) {
    const m = line.match(/^mode:\s*([A-Za-z_]+)/);
    if (m) mode = m[1];
    const b = line.match(/^\s+bankroll_usdc:\s*([0-9.]+)/);
    if (b) bankrollUsdc = Number(b[1]);
  }
  return { mode, bankrollUsdc, raw, exists: true };
}
