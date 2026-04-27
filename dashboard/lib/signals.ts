import { getDb, type SignalRow } from "./db";
import { tailLog, type LogRecord } from "./log";

/**
 * Active-signal materialisation.
 *
 * The Live Desk wants a single "active signals" stream — every signal in the
 * last N minutes joined with whatever happened to it downstream:
 *
 *   - signal_arbiter   → score, status (PLACE / WATCH / REJECT)
 *   - risk_governor    → approved / rejected, fractional kelly
 *   - clob_adapter     → place_order ⇒ exchange_order_id, fill ⇒ filled
 *   - strategy_automation → candidate_result.placed flag
 *   - runtime          → incident_blocked
 *
 * We resolve a coarse "action" enum the UI can colour-code without each row
 * having to know about the runtime's state machine.
 */

export type SignalAction =
  | "PLACED"
  | "FILLED"
  | "RISK_REJECTED"
  | "FORMATTER_REJECTED"
  | "INCIDENT_BLOCKED"
  | "WATCH"
  | "REJECT"
  | "PENDING";

export type ActiveSignal = {
  signalId: string;
  marketId: string;
  marketQuestion: string | null;
  category: string | null;
  strategy: string;
  side: "BUY" | "SELL" | string;
  score: number;
  modelProbability: number | null;
  marketPrice: number | null;
  effectiveEdgeBps: number | null;
  action: SignalAction;
  reason: string | null;
  approvedSizeUsdc: number | null;
  createdAt: string;
};

const ACTION_RANK: Record<SignalAction, number> = {
  FILLED: 0,
  PLACED: 1,
  RISK_REJECTED: 2,
  FORMATTER_REJECTED: 3,
  INCIDENT_BLOCKED: 4,
  WATCH: 5,
  REJECT: 6,
  PENDING: 7,
};

function getRecentSignals(sinceIso: string): SignalRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare<[string], SignalRow>(
      "SELECT * FROM signals WHERE created_at >= ? ORDER BY created_at DESC",
    )
    .all(sinceIso);
}

function getMarketLookup(marketIds: string[]): Map<
  string,
  { question: string; category: string | null }
> {
  const db = getDb();
  const out = new Map<string, { question: string; category: string | null }>();
  if (!db || marketIds.length === 0) return out;
  const placeholders = marketIds.map(() => "?").join(",");
  const rows = db
    .prepare(
      `SELECT id, question, category FROM markets WHERE id IN (${placeholders})`,
    )
    .all(...marketIds) as Array<{
    id: string;
    question: string;
    category: string | null;
  }>;
  for (const r of rows) out.set(r.id, { question: r.question, category: r.category });
  return out;
}

function readNumber(payload: Record<string, unknown>, key: string): number | null {
  const v = payload[key];
  if (typeof v === "number" && !Number.isNaN(v)) return v;
  if (typeof v === "string") {
    const n = Number(v);
    if (!Number.isNaN(n)) return n;
  }
  return null;
}

export async function loadActiveSignals(
  windowMs = 30 * 60 * 1000,
  maxRows = 60,
): Promise<ActiveSignal[]> {
  const sinceIso = new Date(Date.now() - windowMs).toISOString();
  const signalRows = getRecentSignals(sinceIso);
  if (signalRows.length === 0) return [];

  const marketMap = getMarketLookup([
    ...new Set(signalRows.map((s) => s.market_id)),
  ]);

  // One pass over the recent log, indexed by signal_id.
  const records = await tailLog(8000);
  const byId = new Map<string, LogRecord[]>();
  const byMarket = new Map<string, LogRecord[]>();
  for (const r of records) {
    const sid = (r.payload as { signal_id?: string }).signal_id;
    if (typeof sid === "string") {
      const arr = byId.get(sid) ?? [];
      arr.push(r);
      byId.set(sid, arr);
    }
    if (r.market_id) {
      const arr = byMarket.get(r.market_id) ?? [];
      arr.push(r);
      byMarket.set(r.market_id, arr);
    }
  }

  const out: ActiveSignal[] = [];
  for (const s of signalRows) {
    const sigRecs = byId.get(s.id) ?? [];
    const marketRecs = byMarket.get(s.market_id) ?? [];

    // Score record carries model_probability + market_price + effective_edge.
    const scoreRec = sigRecs.find(
      (r) => r.actor === "signal_arbiter" && r.action === "score",
    );
    const riskRec = sigRecs.find(
      (r) => r.actor === "risk_governor" && r.action === "evaluate",
    );
    const formatRec = sigRecs.find(
      (r) => r.actor === "clob_order_formatter" && r.action === "format",
    );
    const placeRec = marketRecs.find(
      (r) => r.actor === "clob_adapter" && r.action === "place_order",
    );
    const fillRec = marketRecs.find(
      (r) => r.actor === "clob_adapter" && r.action === "fill",
    );
    const blockRec = sigRecs.find(
      (r) => r.actor === "runtime" && r.action === "incident_blocked",
    );

    const scorePayload = (scoreRec?.payload ?? {}) as Record<string, unknown>;
    const inputObj = (scorePayload.input_obj ?? scorePayload) as Record<
      string,
      unknown
    >;
    const modelProb =
      readNumber(inputObj, "model_probability") ??
      readNumber(scorePayload, "model_probability");
    const marketPrice =
      readNumber(inputObj, "market_price") ??
      readNumber(scorePayload, "market_price");
    const effectiveEdge =
      readNumber(inputObj, "effective_edge") ??
      readNumber(scorePayload, "effective_edge");

    let action: SignalAction = "PENDING";
    let reason: string | null = null;
    if (fillRec) action = "FILLED";
    else if (placeRec) action = "PLACED";
    else if (formatRec) {
      const ready = (formatRec.payload as { ready_to_submit?: boolean })
        .ready_to_submit;
      if (ready === false) {
        action = "FORMATTER_REJECTED";
        reason = ((formatRec.payload as { reason_codes?: string[] })
          .reason_codes ?? [])[0] ?? null;
      } else action = "PLACED";
    } else if (riskRec) {
      const approved = (riskRec.payload as { approved?: boolean }).approved;
      if (approved === false) {
        action = "RISK_REJECTED";
        reason = ((riskRec.payload as { reason_codes?: string[] }).reason_codes ??
          [])[0] ?? null;
      }
    }
    if (blockRec && action === "PENDING") {
      action = "INCIDENT_BLOCKED";
      reason = (blockRec.payload as { state?: string }).state ?? null;
    }
    if (action === "PENDING") {
      if (s.status === "WATCH") action = "WATCH";
      else if (s.status === "REJECT") action = "REJECT";
    }

    const approvedSize = riskRec
      ? readNumber(riskRec.payload as Record<string, unknown>, "approved_size_usdc")
      : null;

    const meta = marketMap.get(s.market_id) ?? null;
    out.push({
      signalId: s.id,
      marketId: s.market_id,
      marketQuestion: meta?.question ?? null,
      category: meta?.category ?? null,
      strategy: s.strategy,
      side: s.side,
      score: s.score,
      modelProbability: modelProb,
      marketPrice: marketPrice,
      effectiveEdgeBps:
        effectiveEdge === null ? null : Math.round(effectiveEdge * 10000),
      action,
      reason,
      approvedSizeUsdc: approvedSize,
      createdAt: s.created_at,
    });
  }

  out.sort((a, b) => {
    const r = ACTION_RANK[a.action] - ACTION_RANK[b.action];
    if (r !== 0) return r;
    return b.createdAt.localeCompare(a.createdAt);
  });
  return out.slice(0, maxRows);
}
