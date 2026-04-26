import { notFound } from "next/navigation";
import Empty from "@/components/Empty";
import { getMarket, getResolution, getSignal } from "@/lib/db";
import { fmtNum, fmtTs, safeJson } from "@/lib/format";
import { readAllMatching, type LogRecord } from "@/lib/log";

function pickNumber(records: LogRecord[], keys: string[]): number | null {
  for (let i = records.length - 1; i >= 0; i--) {
    const p = records[i].payload ?? {};
    for (const k of keys) {
      const v = p[k];
      if (typeof v === "number" && Number.isFinite(v)) return v;
    }
  }
  return null;
}

function pickAny(records: LogRecord[], keys: string[]): unknown {
  for (let i = records.length - 1; i >= 0; i--) {
    const p = records[i].payload ?? {};
    for (const k of keys) {
      if (p[k] !== undefined && p[k] !== null) return p[k];
    }
  }
  return null;
}

export default async function TradeCourt({
  params,
}: {
  params: { signal_id: string };
}) {
  const records = await readAllMatching({ signalId: params.signal_id });
  const signal = getSignal(params.signal_id);
  if (records.length === 0 && !signal) notFound();

  const marketId =
    signal?.market_id ?? (records.find((r) => r.market_id)?.market_id ?? null);
  const market = marketId ? getMarket(marketId) : null;
  const resolution = marketId ? getResolution(marketId) : null;

  const modelP = pickNumber(records, ["model_probability", "p_model"]);
  const marketP = pickNumber(records, ["market_price", "p_market"]);
  const edge = pickNumber(records, ["edge", "effective_edge"]);
  const kellySize = pickNumber(records, ["kelly_size", "size_usdc", "size"]);
  const sources = pickAny(records, ["sources", "evidence"]);
  const orderPayload = pickAny(records, ["order", "order_payload"]);
  const fills = records.filter((r) => r.action === "order_filled");
  const postHook = records.find((r) => r.actor === "post_order_hook" || r.action === "post_order_hook_result");
  const brierEntry = records.find((r) => r.payload?.["brier"] !== undefined || r.payload?.["brier_impact"] !== undefined);
  const ruleSummary = pickAny(records, ["rule_summary", "rule", "strategy"]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Trade Court</h1>
        <p className="text-sm text-muted">PRD §19.5 — single-trade reconstruction from the immutable log.</p>
      </header>

      <section className="panel space-y-1">
        <div className="font-mono text-xs text-muted">signal {params.signal_id}</div>
        {market ? (
          <>
            <div className="text-base">{market.question}</div>
            <div className="text-xs text-muted">
              market <span className="font-mono">{market.id}</span> · category {market.category ?? "—"} · close {fmtTs(market.close_time)}
            </div>
          </>
        ) : (
          <div className="text-sm text-muted">No market metadata in SQLite for this signal.</div>
        )}
      </section>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card label="Model probability" value={fmtNum(modelP, 3)} />
        <Card label="Market price" value={fmtNum(marketP, 3)} />
        <Card label="Edge" value={fmtNum(edge, 3)} />
        <Card label="Kelly size (USDC)" value={fmtNum(kellySize, 2)} />
      </section>

      <Block title="Rule summary">
        {ruleSummary === null ? (
          <Empty message="No rule summary in payload." />
        ) : (
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs">{safeJson(ruleSummary)}</pre>
        )}
      </Block>

      <Block title="Sources / evidence">
        {!sources ? (
          <Empty message="No sources attached." />
        ) : (
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs">{safeJson(sources)}</pre>
        )}
      </Block>

      <Block title="Order payload">
        {!orderPayload ? (
          <Empty message="No order payload logged for this signal." />
        ) : (
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs">{safeJson(orderPayload)}</pre>
        )}
      </Block>

      <Block title="Fills">
        {fills.length === 0 ? (
          <Empty message="No fills logged." />
        ) : (
          <ul className="space-y-1 text-xs">
            {fills.map((f) => (
              <li key={f.id} className="font-mono">
                {fmtTs(f.ts)} · {String(f.payload?.["side"] ?? "?")} · price {fmtNum(f.payload?.["price"] as number, 4)} · size {fmtNum(f.payload?.["size"] as number, 2)}
              </li>
            ))}
          </ul>
        )}
      </Block>

      <Block title="Post-order hook result">
        {!postHook ? (
          <Empty message="No post-order hook entry." />
        ) : (
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs">{safeJson(postHook.payload)}</pre>
        )}
      </Block>

      <Block title="Exit plan">
        <Empty message="Exit plans are not yet emitted by the runtime; placeholder per PRD §19.5." />
      </Block>

      <Block title="Final result">
        {!resolution ? (
          <Empty message="Market not resolved yet." />
        ) : (
          <div className="text-sm">
            outcome <span className="font-mono">{resolution.outcome}</span> at {fmtTs(resolution.resolved_at)}
          </div>
        )}
      </Block>

      <Block title="Brier impact">
        {!brierEntry ? (
          <Empty message="No Brier observation logged for this trade." />
        ) : (
          <pre className="overflow-x-auto whitespace-pre-wrap text-xs">{safeJson(brierEntry.payload)}</pre>
        )}
      </Block>

      <Block title="Raw log entries">
        {records.length === 0 ? (
          <Empty message="No log entries reference this signal id." />
        ) : (
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-xs text-muted">
            {records.map((r) => `${fmtTs(r.ts)} ${r.actor}/${r.action} ${JSON.stringify(r.payload)}`).join("\n")}
          </pre>
        )}
      </Block>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">{title}</h2>
      <div className="panel">{children}</div>
    </section>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel">
      <div className="label">{label}</div>
      <div className="text-xl font-semibold">{value}</div>
    </div>
  );
}
