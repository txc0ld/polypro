import { notFound } from "next/navigation";
import { Card } from "@/components/Card";
import { getDb, getMarket, getSignal } from "@/lib/db";
import { tailLog, type LogRecord } from "@/lib/log";
import { computeClvForSignal } from "@/lib/clv";
import { fmtNum, fmtPct, fmtTime, shortId } from "@/lib/format";

type ResolutionRow = { market_id: string; outcome: string; resolved_at: string };

function getResolution(marketId: string): ResolutionRow | undefined {
  const db = getDb();
  if (!db) return undefined;
  return db
    .prepare<[string], ResolutionRow>(
      "SELECT * FROM resolutions WHERE market_id = ?",
    )
    .get(marketId);
}

type CalibrationObservation = {
  predicted_probability: number;
  realized: number;
};

function getBrierForSignal(
  marketId: string,
  tokenId: string,
): number | null {
  const db = getDb();
  if (!db) return null;
  const row = db
    .prepare<[string, string], CalibrationObservation>(
      `SELECT predicted_probability, realized
       FROM calibration_observations
       WHERE market_id = ? AND token_id = ?
       ORDER BY id DESC LIMIT 1`,
    )
    .get(marketId, tokenId);
  if (!row) return null;
  const diff = row.predicted_probability - row.realized;
  return diff * diff;
}

function pickRecord(
  records: LogRecord[],
  actor: string,
  action: string,
): LogRecord | undefined {
  return records.find((r) => r.actor === actor && r.action === action);
}

function pickAll(
  records: LogRecord[],
  actor: string,
  action: string,
): LogRecord[] {
  return records.filter((r) => r.actor === actor && r.action === action);
}

export default async function TradeCourt({
  params,
}: {
  params: { signal_id: string };
}) {
  const signalId = decodeURIComponent(params.signal_id);
  const signal = getSignal(signalId);
  if (!signal) notFound();
  const market = getMarket(signal.market_id);

  const records = await tailLog(5000, { signalId });
  const scoreRec = pickRecord(records, "signal_arbiter", "score");
  const riskRec = pickRecord(records, "risk_governor", "evaluate");
  const formatterRec = pickRecord(records, "clob_order_formatter", "format");
  const placeRec = pickRecord(records, "clob_adapter", "place_order");
  const fills = pickAll(records, "clob_adapter", "fill");
  const hookRec = pickRecord(records, "post_order_kelly_guard", "evaluate");

  const resolution = getResolution(signal.market_id);
  const brier = getBrierForSignal(signal.market_id, signal.token_id);
  const clv = await computeClvForSignal(signalId);

  const reasonCodes: string[] = (() => {
    try {
      return JSON.parse(signal.reason_codes) as string[];
    } catch {
      return [];
    }
  })();
  const evidenceRefs: string[] = (() => {
    try {
      return JSON.parse(signal.evidence_refs) as string[];
    } catch {
      return [];
    }
  })();

  const scorePayload = scoreRec?.payload as
    | {
        model_probability?: number;
        market_price?: number;
        effective_edge?: number;
      }
    | undefined;

  const riskPayload = riskRec?.payload as
    | {
        approved?: boolean;
        approved_size_usdc?: number;
        raw_kelly?: number;
        fractional_kelly?: number;
        caps_applied?: string[];
      }
    | undefined;

  const orderPayload =
    (formatterRec?.payload as { order_payload?: Record<string, unknown> })
      ?.order_payload ?? null;

  const guardPayload = hookRec?.payload as
    | { ok?: boolean; breaches?: string[] }
    | undefined;

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Trade Court</h1>
        <span className="text-xs text-muted">
          PRD §19.5 · {shortId(signalId, 12)}
        </span>
      </header>

      <Card title="Market">
        {market ? (
          <div className="space-y-1 text-sm">
            <div className="font-semibold">{market.question}</div>
            <div className="text-xs text-muted">
              {shortId(market.id, 16)} · {market.category ?? "—"} · status{" "}
              {market.status}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted">
            Market {signal.market_id} not in store.
          </p>
        )}
      </Card>

      <Card title="Rule summary">
        <ul className="text-xs">
          <li>strategy: {signal.strategy}</li>
          <li>side: {signal.side}</li>
          <li>status: {signal.status}</li>
          <li>score: {fmtNum(signal.score, 2)}</li>
          {reasonCodes.length > 0 ? (
            <li>reasons: {reasonCodes.join(", ")}</li>
          ) : null}
        </ul>
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card title="Model probability">
          <p className="text-2xl">
            {fmtPct(scorePayload?.model_probability ?? null, 2)}
          </p>
        </Card>
        <Card title="Market price">
          <p className="text-2xl">
            {fmtPct(scorePayload?.market_price ?? null, 2)}
          </p>
        </Card>
        <Card title="Edge">
          <p className="text-2xl">
            {fmtPct(scorePayload?.effective_edge ?? null, 2)}
          </p>
        </Card>
      </div>

      <Card title="Sources">
        {evidenceRefs.length === 0 ? (
          <p className="text-xs text-muted">No evidence refs recorded.</p>
        ) : (
          <ul className="list-disc pl-6 text-xs">
            {evidenceRefs.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Kelly size">
        {riskPayload ? (
          <ul className="text-xs">
            <li>approved: {String(riskPayload.approved ?? false)}</li>
            <li>raw kelly: {fmtNum(riskPayload.raw_kelly, 4)}</li>
            <li>fractional kelly: {fmtNum(riskPayload.fractional_kelly, 4)}</li>
            <li>
              size approved: ${fmtNum(riskPayload.approved_size_usdc, 2)}
            </li>
            {riskPayload.caps_applied && riskPayload.caps_applied.length > 0 ? (
              <li>caps applied: {riskPayload.caps_applied.join(", ")}</li>
            ) : null}
          </ul>
        ) : (
          <p className="text-xs text-muted">No risk-governor record.</p>
        )}
      </Card>

      <Card title="Order payload">
        {orderPayload ? (
          <pre className="overflow-x-auto rounded bg-bg p-3 text-xs">
            {JSON.stringify(orderPayload, null, 2)}
          </pre>
        ) : (
          <p className="text-xs text-muted">No formatter record.</p>
        )}
      </Card>

      <Card title="Fills">
        {placeRec === undefined ? (
          <p className="text-xs text-muted">Order never placed.</p>
        ) : fills.length === 0 ? (
          <p className="text-xs text-muted">
            Order placed{" "}
            {fmtTime(placeRec.ts)} · no fills logged yet.
          </p>
        ) : (
          <ul className="text-xs">
            {fills.map((f) => {
              const fp = f.payload as {
                price?: number;
                size?: number;
                fee_paid_usdc?: number;
              };
              return (
                <li key={f.id} className="border-t border-border py-1">
                  {fmtTime(f.ts)} · {fmtNum(fp.size, 4)} @ {fmtNum(fp.price, 4)}{" "}
                  · fee {fmtNum(fp.fee_paid_usdc, 2)}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card title="Post-order hook">
        {guardPayload ? (
          <ul className="text-xs">
            <li>
              ok:{" "}
              <span className={guardPayload.ok ? "text-accent" : "text-bad"}>
                {String(guardPayload.ok)}
              </span>
            </li>
            {guardPayload.breaches && guardPayload.breaches.length > 0 ? (
              <li>breaches: {guardPayload.breaches.join(", ")}</li>
            ) : null}
          </ul>
        ) : (
          <p className="text-xs text-muted">No hook evaluation logged.</p>
        )}
      </Card>

      <Card title="Exit plan">
        <p className="text-xs text-muted">
          Exit plan slot — populated when the runtime emits an{" "}
          <code>exit_plan</code> log entry. Placeholder for v1.
        </p>
      </Card>

      <Card title="Resolution">
        {resolution ? (
          <ul className="text-xs">
            <li>outcome: {resolution.outcome}</li>
            <li>resolved at: {fmtTime(resolution.resolved_at)}</li>
          </ul>
        ) : (
          <p className="text-xs text-muted">Market not yet resolved.</p>
        )}
      </Card>

      <Card title="Closing-line value">
        {clv === null || clv.clv === null ? (
          <p className="text-xs text-muted">
            CLV requires both an execution price and a closing line — one or
            both are missing for this signal.
          </p>
        ) : (
          <div className="space-y-1">
            <p
              className={`text-2xl ${
                clv.clv > 0
                  ? "text-accent"
                  : clv.clv < 0
                    ? "text-bad"
                    : "text-ink"
              }`}
            >
              {clv.clv > 0 ? "+" : ""}
              {(clv.clv * 100).toFixed(2)}¢
            </p>
            <ul className="text-xs text-muted">
              <li>
                exec {fmtPct(clv.executionPrice, 2)} → close{" "}
                {fmtPct(clv.closingLine, 2)} · {clv.side}
              </li>
              <li>resolved {fmtTime(clv.resolvedAt)} → {clv.outcome}</li>
            </ul>
          </div>
        )}
      </Card>

      <Card title="Brier impact">
        {brier === null ? (
          <p className="text-xs text-muted">
            No calibration observation for this market/token pair.
          </p>
        ) : (
          <p className="text-2xl">{fmtNum(brier, 4)}</p>
        )}
      </Card>
    </div>
  );
}
