import fs from "node:fs";
import path from "node:path";

/**
 * Resolve the funder/proxy address. We honour, in order:
 *   1. process.env.POLY_FUNDER_ADDRESS (and POLYFUNDERADDRESS)
 *   2. process.env.POLY_WALLET_ADDRESS (the signing EOA, fallback)
 *   3. .env.local in the repo root (key=value pairs, no quoting)
 *
 * We never crash if none is set; the dashboard simply renders an empty
 * wallet widget with a hint.
 */
function readDotEnvLocal(): Record<string, string> {
  const repoRoot = path.resolve(process.cwd(), "..");
  const candidates = [
    path.join(repoRoot, ".env.local"),
    path.join(repoRoot, ".env"),
    path.join(process.cwd(), ".env.local"),
  ];
  for (const p of candidates) {
    if (!fs.existsSync(p)) continue;
    try {
      const out: Record<string, string> = {};
      for (const line of fs.readFileSync(p, "utf8").split(/\r?\n/)) {
        const m = line.match(/^([A-Z0-9_]+)\s*=\s*(.*)$/);
        if (!m) continue;
        const key = m[1];
        let val = m[2].trim();
        if (val.startsWith("\"") && val.endsWith("\"")) val = val.slice(1, -1);
        if (val.startsWith("'") && val.endsWith("'")) val = val.slice(1, -1);
        out[key] = val;
      }
      return out;
    } catch {
      /* noop */
    }
  }
  return {};
}

export function funderAddress(): string | null {
  const env = process.env;
  const direct =
    env.POLY_FUNDER_ADDRESS ||
    env.POLYFUNDERADDRESS ||
    env.POLY_WALLET_ADDRESS ||
    env.POLYWALLETADDRESS;
  if (direct) return direct;
  const dotenv = readDotEnvLocal();
  return (
    dotenv.POLY_FUNDER_ADDRESS ||
    dotenv.POLYFUNDERADDRESS ||
    dotenv.POLY_WALLET_ADDRESS ||
    dotenv.POLYWALLETADDRESS ||
    null
  );
}

export type WalletValue = {
  address: string;
  totalUsd: number;
  fetchedAt: string;
};

export type WalletPosition = {
  conditionId: string;
  market: string;
  outcome: string;
  size: number;
  avgPrice: number;
  currentPrice: number;
  initialValue: number;
  currentValue: number;
  realizedPnl: number;
  cashPnl: number;
  percentPnl: number;
};

const DATA_API = "https://data-api.polymarket.com";

async function fetchWithTimeout(url: string, ms = 4500): Promise<unknown> {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), ms);
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      cache: "no-store",
      headers: { accept: "application/json" },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  } finally {
    clearTimeout(id);
  }
}

function unwrap(json: unknown): unknown {
  if (json && typeof json === "object" && "data" in (json as object)) {
    return (json as { data: unknown }).data;
  }
  return json;
}

export async function fetchWalletValue(
  address: string,
): Promise<WalletValue | null> {
  const json = unwrap(await fetchWithTimeout(`${DATA_API}/value?user=${address}`));
  if (!json) return null;
  // The endpoint returns either { value: number } or [{ value: number, ... }].
  let total: number | null = null;
  if (Array.isArray(json) && json.length > 0) {
    const v = (json[0] as { value?: number }).value;
    if (typeof v === "number") total = v;
  } else if (typeof json === "object") {
    const v = (json as { value?: number }).value;
    if (typeof v === "number") total = v;
  } else if (typeof json === "number") {
    total = json;
  }
  if (total === null) return null;
  return {
    address,
    totalUsd: total,
    fetchedAt: new Date().toISOString(),
  };
}

export async function fetchWalletPositions(
  address: string,
): Promise<WalletPosition[]> {
  const json = unwrap(
    await fetchWithTimeout(`${DATA_API}/positions?user=${address}&sizeThreshold=1`),
  );
  if (!Array.isArray(json)) return [];
  return (json as Array<Record<string, unknown>>).map((row) => ({
    conditionId: String(row.conditionId ?? row.condition_id ?? ""),
    market: String(row.title ?? row.slug ?? row.eventSlug ?? ""),
    outcome: String(row.outcome ?? ""),
    size: Number(row.size ?? 0),
    avgPrice: Number(row.avgPrice ?? row.entry_price ?? 0),
    currentPrice: Number(row.curPrice ?? row.current_price ?? 0),
    initialValue: Number(row.initialValue ?? row.cost ?? 0),
    currentValue: Number(row.currentValue ?? row.value ?? 0),
    realizedPnl: Number(row.realizedPnl ?? 0),
    cashPnl: Number(row.cashPnl ?? 0),
    percentPnl: Number(row.percentPnl ?? 0),
  }));
}
