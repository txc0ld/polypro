import { notFound } from "next/navigation";
import Empty from "@/components/Empty";
import ProbabilityChart, { type ProbabilityPoint } from "@/components/ProbabilityChart";
import {
  calibrationBucketFor,
  getCalibrationBuckets,
  getMarket,
  getOutcomeTokens,
} from "@/lib/db";
import { fmtNum, fmtTs } from "@/lib/format";
import { readAllMatching } from "@/lib/log";

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export default async function ProbabilityLab({
  params,
}: {
  params: { market_id: string };
}) {
  const market = getMarket(params.market_id);
  if (!market) notFound();
  const tokens = getOutcomeTokens(params.market_id);
  const yes = tokens.find((t) => t.outcome === "YES");

  const records = await readAllMatching({
    actor: ["signal_arbiter", "probability_engine", "market_scanner"],
    marketId: params.market_id,
  });

  const series: ProbabilityPoint[] = records.map((r) => {
    const p = r.payload ?? {};
    const model = readNumber(p["model_probability"]) ?? readNumber(p["p_model"]);
    const market = readNumber(p["market_price"]) ?? readNumber(p["p_market"]);
    const sigma = readNumber(p["uncertainty"]) ?? readNumber(p["sigma"]);
    let bandLow: number | null = null;
    let bandHigh: number | null = null;
    if (model !== null && sigma !== null) {
      bandLow = Math.max(0, model - sigma);
      bandHigh = Math.min(1, model + sigma);
    }
    return { ts: r.ts, model, market, bandLow, bandHigh };
  });

  const latestEvidence = records
    .slice()
    .reverse()
    .find((r) => Array.isArray(r.payload?.["sources"]) || Array.isArray(r.payload?.["evidence"]));
  const sources =
    ((latestEvidence?.payload?.["sources"] as unknown[]) ?? (latestEvidence?.payload?.["evidence"] as unknown[]) ?? [])
      .filter(Boolean)
      .map((s) => (typeof s === "string" ? s : JSON.stringify(s)));

  const latestModel = [...series].reverse().find((p) => p.model !== null);
  const calibration = getCalibrationBuckets();
  const bucket = latestModel?.model !== undefined && latestModel?.model !== null
    ? calibrationBucketFor(latestModel.model)
    : null;
  const bucketStats = bucket !== null ? calibration.find((c) => Math.abs(c.bucket - bucket) < 1e-6) : null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Probability Lab</h1>
        <p className="text-sm text-muted">PRD §19.3 — model probability vs market price for one market.</p>
      </header>

      <section className="panel space-y-1">
        <div className="font-mono text-xs text-muted">{market.id}</div>
        <div className="text-base">{market.question}</div>
        <div className="text-xs text-muted">
          category {market.category ?? "—"} · status {market.status} · close {fmtTs(market.close_time)}
        </div>
        {yes ? (
          <div className="font-mono text-xs text-muted">
            YES token {yes.token_id} · tick {fmtNum(yes.tick_size, 4)} · min {fmtNum(yes.min_order_size, 2)}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="label mb-2">Model probability vs market price</div>
        {series.length === 0 ? (
          <Empty message="No probability/price log entries for this market yet." />
        ) : (
          <ProbabilityChart data={series} />
        )}
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="panel">
          <div className="label mb-2">Source evidence (latest)</div>
          {sources.length === 0 ? (
            <div className="text-sm text-muted">No sources attached to recent entries.</div>
          ) : (
            <ul className="list-disc space-y-1 pl-4 text-xs text-muted">
              {sources.map((s, i) => (
                <li key={i} className="font-mono">{s}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel">
          <div className="label mb-2">Calibration bucket</div>
          {bucket === null || !bucketStats ? (
            <div className="text-sm text-muted">
              {bucket === null ? "No model probability yet." : `No observations in bucket ${bucket.toFixed(1)}.`}
            </div>
          ) : (
            <div className="space-y-1 text-sm">
              <div>bucket <span className="font-mono">{bucket.toFixed(1)}</span></div>
              <div>n <span className="font-mono">{bucketStats.n}</span></div>
              <div>mean predicted <span className="font-mono">{fmtNum(bucketStats.mean_predicted, 3)}</span></div>
              <div>empirical <span className="font-mono">{fmtNum(bucketStats.empirical, 3)}</span></div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
