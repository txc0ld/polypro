import { notFound } from "next/navigation";
import { Card } from "@/components/Card";
import {
  ProbabilityChart,
  type ProbabilityPoint,
} from "@/components/ProbabilityChart";
import {
  calibrationBuckets,
  getMarket,
  listSignalsForMarket,
} from "@/lib/db";
import { tailLog, type LogRecord } from "@/lib/log";
import { fmtNum, fmtPct, fmtTime, shortId } from "@/lib/format";

type SignalPayload = {
  signal_id?: string;
  score?: number;
  status?: string;
};

function pointsFromLog(records: LogRecord[]): ProbabilityPoint[] {
  const pts: ProbabilityPoint[] = [];
  for (const r of records) {
    // signal_arbiter `score` action carries the full Signal in input_obj... but
    // we logged hashes only. The `output_obj` carries score/status; the
    // Signal's prob fields are echoed via input_obj when the runtime supplies
    // a dict. We sniff a few common shapes.
    const payload = r.payload as Record<string, unknown>;
    const mp = payload.model_probability;
    const px = payload.market_price;
    const unc = payload.uncertainty;
    if (typeof mp === "number" && typeof px === "number") {
      const u = typeof unc === "number" ? unc : 0;
      pts.push({
        ts: r.ts,
        modelProbability: mp,
        marketPrice: px,
        upper: Math.min(1, mp + u),
        lower: Math.max(0, mp - u),
      });
    }
  }
  return pts;
}

function calibrationBucketLabel(p: number | null): string {
  if (p === null || Number.isNaN(p)) return "—";
  const b = Math.round(p * 10) / 10;
  return b.toFixed(1);
}

export default async function ProbabilityLab({
  params,
}: {
  params: { market_id: string };
}) {
  const marketId = decodeURIComponent(params.market_id);
  const market = getMarket(marketId);
  if (!market) notFound();

  const signalRecords = await tailLog(2000, {
    actor: "signal_arbiter",
    marketId,
  });
  const points = pointsFromLog(signalRecords);
  const signals = listSignalsForMarket(marketId);
  const buckets = calibrationBuckets();
  const latest = points[points.length - 1];
  const bucketLabel = calibrationBucketLabel(latest?.modelProbability ?? null);
  const bucketStat = buckets.find(
    (b) => b.bucket.toFixed(1) === bucketLabel,
  );

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">{market.question}</h1>
        <span className="text-xs text-muted">PRD §19.3</span>
      </header>

      <Card title="Model probability vs market price">
        <ProbabilityChart data={points} />
        <p className="mt-3 text-xs text-muted">
          {points.length} estimates · band shows ±1σ uncertainty.
        </p>
      </Card>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card title="Source evidence">
          {signals.length === 0 ? (
            <p className="text-sm text-muted">No signals recorded for this market.</p>
          ) : (
            <ul className="space-y-2 text-xs">
              {signals.slice(0, 20).map((s) => {
                let refs: string[] = [];
                try {
                  refs = JSON.parse(s.evidence_refs) as string[];
                } catch {
                  /* noop */
                }
                let reasons: string[] = [];
                try {
                  reasons = JSON.parse(s.reason_codes) as string[];
                } catch {
                  /* noop */
                }
                return (
                  <li key={s.id} className="border-t border-border pt-2">
                    <div className="flex justify-between">
                      <span className="font-semibold">{s.strategy}</span>
                      <span className="text-muted">{fmtTime(s.created_at)}</span>
                    </div>
                    <div className="text-muted">
                      side {s.side} · score {fmtNum(s.score, 2)} · {s.status}
                    </div>
                    {refs.length > 0 ? (
                      <div className="text-muted">
                        evidence: {refs.join(", ")}
                      </div>
                    ) : null}
                    {reasons.length > 0 ? (
                      <div className="text-muted">
                        reasons: {reasons.join(", ")}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Calibration bucket">
          <p className="text-sm">
            Latest model probability falls in bucket{" "}
            <span className="text-accent">{bucketLabel}</span>.
          </p>
          {bucketStat ? (
            <ul className="mt-2 space-y-1 text-xs text-muted">
              <li>
                mean predicted: {fmtPct(bucketStat.mean_predicted, 1)}
              </li>
              <li>empirical: {fmtPct(bucketStat.empirical, 1)}</li>
              <li>n: {bucketStat.n}</li>
            </ul>
          ) : (
            <p className="mt-2 text-xs text-muted">
              No calibration observations recorded for this bucket yet.
            </p>
          )}
        </Card>

        <Card title="Market metadata">
          <ul className="space-y-1 text-xs">
            <li>id: {shortId(market.id, 16)}</li>
            <li>category: {market.category ?? "—"}</li>
            <li>liquidity: ${fmtNum(market.liquidity_usd, 0)}</li>
            <li>spread: {fmtPct((market.spread_pct ?? 0) / 100, 2)}</li>
            <li>quality: {fmtNum(market.market_quality, 2)}</li>
            <li>resolution risk: {fmtNum(market.resolution_risk, 2)}</li>
            <li>status: {market.status}</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
