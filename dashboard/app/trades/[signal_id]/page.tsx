import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, EmptyState, KeyRow, Stat } from "@/components/Card";
import { Pill } from "@/components/Pill";
import { StrategyBadge } from "@/components/StrategyBadge";
import { Timeline, type TimelineStep } from "@/components/Timeline";
import { getDb, getMarket, getSignal } from "@/lib/db";
import { tailLog, type LogRecord } from "@/lib/log";
import { computeClvForSignal } from "@/lib/clv";
import { fmtNum, fmtPct, fmtTime, fmtUsd, shortId } from "@/lib/format";

type ResolutionRow = {
  market_id: string;
  outcome: string;
  resolved_at: string;
};

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

  const records = await tailLog(8000, { signalId });
  const scoreRec = pickRecord(records, "signal_arbiter", "score");
  const riskRec = pickRecord(records, "risk_governor", "evaluate");
  const formatterRec = pickRecord(records, "clob_order_formatter", "format");
  const placeRec = pickRecord(records, "clob_adapter", "place_order");
  const fills = pickAll(records, "clob_adapter", "fill");
  const hookRec = pickRecord(records, "post_order_kelly_guard", "evaluate");
  const blockRec = pickRecord(records, "runtime", "incident_blocked");

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
        input_obj?: {
          model_probability?: number;
          market_price?: number;
          effective_edge?: number;
        };
      }
    | undefined;
  const probIn = scorePayload?.input_obj ?? scorePayload;
  const modelProb = probIn?.model_probability ?? null;
  const marketPrice = probIn?.market_price ?? null;
  const effectiveEdge = probIn?.effective_edge ?? null;

  const riskPayload = riskRec?.payload as
    | {
        approved?: boolean;
        approved_size_usdc?: number;
        raw_kelly?: number;
        fractional_kelly?: number;
        caps_applied?: string[];
        reason_codes?: string[];
      }
    | undefined;

  const orderPayload =
    (formatterRec?.payload as { order_payload?: Record<string, unknown> })
      ?.order_payload ?? null;
  const formatterReady = (formatterRec?.payload as { ready_to_submit?: boolean })
    ?.ready_to_submit;

  const guardPayload = hookRec?.payload as
    | { ok?: boolean; breaches?: string[] }
    | undefined;

  const placePayload = placeRec?.payload as
    | { exchange_order_id?: string; client_order_id?: string }
    | undefined;

  const steps: TimelineStep[] = [
    {
      ts: signal.created_at,
      actor: "signal_arbiter",
      action: "score",
      status:
        signal.status === "PLACE"
          ? "ok"
          : signal.status === "WATCH"
            ? "warn"
            : "skip",
      ref: shortId(signal.id, 10),
      payload: (
        <div className="space-y-1">
          <KeyRow k="strategy" v={<StrategyBadge strategy={signal.strategy} size="sm" />} />
          <KeyRow k="side" v={signal.side} />
          <KeyRow k="score" v={fmtNum(signal.score, 2)} />
          <KeyRow k="status" v={signal.status} />
          {reasonCodes.length > 0 ? (
            <KeyRow k="reasons" v={reasonCodes.join(", ")} />
          ) : null}
        </div>
      ),
    },
  ];

  if (blockRec) {
    steps.push({
      ts: blockRec.ts,
      actor: "runtime",
      action: "incident_blocked",
      status: "bad",
      payload: (
        <KeyRow
          k="state"
          v={(blockRec.payload as { state?: string }).state ?? ""}
        />
      ),
    });
  }

  if (riskRec) {
    steps.push({
      ts: riskRec.ts,
      actor: "risk_governor",
      action: "evaluate",
      status: riskPayload?.approved ? "ok" : "bad",
      payload: (
        <div className="space-y-1">
          <KeyRow
            k="approved"
            v={
              <span
                className={
                  riskPayload?.approved ? "text-accent" : "text-bad"
                }
              >
                {String(riskPayload?.approved ?? false)}
              </span>
            }
          />
          <KeyRow k="raw kelly" v={fmtNum(riskPayload?.raw_kelly ?? null, 4)} />
          <KeyRow
            k="fractional kelly"
            v={fmtNum(riskPayload?.fractional_kelly ?? null, 4)}
          />
          <KeyRow
            k="size approved"
            v={fmtUsd(riskPayload?.approved_size_usdc ?? null, 2)}
          />
          {riskPayload?.caps_applied && riskPayload.caps_applied.length > 0 ? (
            <KeyRow k="caps" v={riskPayload.caps_applied.join(", ")} />
          ) : null}
          {riskPayload?.reason_codes && riskPayload.reason_codes.length > 0 ? (
            <KeyRow
              k="reasons"
              v={
                <span className="text-warn">
                  {riskPayload.reason_codes.join(", ")}
                </span>
              }
            />
          ) : null}
        </div>
      ),
    });
  }

  if (formatterRec) {
    steps.push({
      ts: formatterRec.ts,
      actor: "clob_order_formatter",
      action: "format",
      status: formatterReady === false ? "bad" : "ok",
      payload: orderPayload ? (
        <pre className="overflow-x-auto rounded bg-bg p-2 font-mono text-[10px] text-muted">
          {JSON.stringify(orderPayload, null, 2)}
        </pre>
      ) : (
        <span className="text-muted">no order payload</span>
      ),
    });
  }

  if (placeRec) {
    steps.push({
      ts: placeRec.ts,
      actor: "clob_adapter",
      action: "place_order",
      status: "ok",
      ref: placePayload?.exchange_order_id
        ? shortId(placePayload.exchange_order_id, 12)
        : null,
      payload: (
        <div className="space-y-1">
          <KeyRow
            k="exchange order id"
            v={
              <span className="font-mono">
                {shortId(placePayload?.exchange_order_id ?? null, 16)}
              </span>
            }
          />
          {placePayload?.client_order_id ? (
            <KeyRow
              k="client order id"
              v={<span className="font-mono">{shortId(placePayload.client_order_id, 16)}</span>}
            />
          ) : null}
        </div>
      ),
    });
  }

  for (const f of fills) {
    const fp = f.payload as {
      price?: number;
      size?: number;
      fee_paid_usdc?: number;
    };
    steps.push({
      ts: f.ts,
      actor: "clob_adapter",
      action: "fill",
      status: "ok",
      payload: (
        <div className="space-y-1">
          <KeyRow k="size" v={fmtNum(fp.size ?? null, 4)} />
          <KeyRow k="price" v={fmtPct(fp.price ?? null, 2)} />
          <KeyRow k="fee" v={fmtUsd(fp.fee_paid_usdc ?? null, 4)} />
        </div>
      ),
    });
  }

  if (hookRec) {
    steps.push({
      ts: hookRec.ts,
      actor: "post_order_kelly_guard",
      action: "evaluate",
      status: guardPayload?.ok ? "ok" : "bad",
      payload: (
        <div className="space-y-1">
          <KeyRow
            k="ok"
            v={
              <span
                className={guardPayload?.ok ? "text-accent" : "text-bad"}
              >
                {String(guardPayload?.ok)}
              </span>
            }
          />
          {guardPayload?.breaches && guardPayload.breaches.length > 0 ? (
            <KeyRow
              k="breaches"
              v={<span className="text-bad">{guardPayload.breaches.join(", ")}</span>}
            />
          ) : null}
        </div>
      ),
    });
  }

  if (resolution) {
    steps.push({
      ts: resolution.resolved_at,
      actor: "resolution_monitor",
      action: "resolved",
      status:
        clv && clv.clv !== null && clv.clv > 0
          ? "ok"
          : clv && clv.clv !== null && clv.clv < 0
            ? "bad"
            : "skip",
      payload: (
        <div className="space-y-1">
          <KeyRow k="outcome" v={resolution.outcome} />
          {clv && clv.clv !== null ? (
            <KeyRow
              k="clv"
              v={
                <span
                  className={clv.clv > 0 ? "text-accent" : "text-bad"}
                >
                  {clv.clv > 0 ? "+" : ""}
                  {(clv.clv * 100).toFixed(2)}c
                </span>
              }
            />
          ) : null}
          {brier !== null ? (
            <KeyRow k="brier" v={fmtNum(brier, 4)} />
          ) : null}
        </div>
      ),
    });
  }

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between gap-3">
        <div>
          <h1 className="text-display font-semibold tracking-tight">
            Trade Court
          </h1>
          <p className="text-sm text-subtle">
            Signal{" "}
            <span className="font-mono text-muted">
              {shortId(signalId, 16)}
            </span>{" "}
            · chronological reconstruction
          </p>
        </div>
        <Pill tone="muted">PRD §19.5</Pill>
      </header>

      <Card>
        {market ? (
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <div>
              <Link
                href={`/probability/${encodeURIComponent(market.id)}`}
                className="text-lg font-medium text-ink hover:text-accent"
              >
                {market.question}
              </Link>
              <div className="mt-1 flex items-center gap-2 text-xs text-subtle">
                <Pill tone="info">{market.category ?? "—"}</Pill>
                <Pill
                  tone={market.status === "watching" ? "good" : "muted"}
                >
                  {market.status}
                </Pill>
                <span className="font-mono">{shortId(market.id, 16)}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StrategyBadge strategy={signal.strategy} />
              <Pill
                tone={
                  signal.status === "PLACE"
                    ? "good"
                    : signal.status === "REJECT"
                      ? "bad"
                      : "muted"
                }
              >
                {signal.status}
              </Pill>
            </div>
          </div>
        ) : (
          <EmptyState title="market not in store" hint={signal.market_id} />
        )}
      </Card>

      <div className="grid grid-cols-2 gap-px border border-border bg-border/40 md:grid-cols-4">
        <div className="bg-panel p-4">
          <Stat label="model" value={fmtPct(modelProb, 1)} tone="good" />
        </div>
        <div className="bg-panel p-4">
          <Stat label="market" value={fmtPct(marketPrice, 1)} tone="warn" />
        </div>
        <div className="bg-panel p-4">
          <Stat
            label="edge"
            value={
              effectiveEdge === null
                ? "—"
                : `${(effectiveEdge * 10000).toFixed(0)}bp`
            }
            tone={effectiveEdge !== null && effectiveEdge > 0 ? "good" : "default"}
          />
        </div>
        <div className="bg-panel p-4">
          <Stat
            label="size approved"
            value={fmtUsd(riskPayload?.approved_size_usdc ?? null, 2)}
          />
        </div>
      </div>

      {evidenceRefs.length > 0 ? (
        <Card title="evidence">
          <ul className="flex flex-wrap gap-2 text-xs">
            {evidenceRefs.map((r) => (
              <li
                key={r}
                className="rounded border border-hairline bg-surface px-2 py-1 font-mono text-muted"
              >
                {r}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card title="lifecycle">
        <Timeline steps={steps} />
      </Card>
    </div>
  );
}
