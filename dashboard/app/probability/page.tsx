import Link from "next/link";
import { Card, EmptyState } from "@/components/Card";
import { Pill } from "@/components/Pill";
import { CalibrationDiagram } from "@/components/CalibrationDiagram";
import { calibrationBuckets, listAllMarkets } from "@/lib/db";
import { fmtNum, fmtPct, shortId } from "@/lib/format";

export default function ProbabilityIndex() {
  const markets = listAllMarkets();
  const buckets = calibrationBuckets();
  const points = buckets.map((b) => ({
    bucket: b.bucket,
    meanPredicted: b.mean_predicted,
    empirical: b.empirical,
    n: b.n,
  }));
  const totalN = buckets.reduce((a, b) => a + b.n, 0);
  const reliabilityGap =
    totalN === 0
      ? null
      : buckets.reduce(
          (sum, b) => sum + Math.abs(b.mean_predicted - b.empirical) * b.n,
          0,
        ) / totalN;
  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-display font-semibold tracking-tight gradient-text">
            Probability Lab
          </h1>
          <p className="text-sm text-subtle">
            Calibration diagnostics + per-market drilldowns
          </p>
        </div>
        <Pill tone="muted">PRD §19.3</Pill>
      </header>

      <Card
        title="calibration reliability"
        action={
          <span>
            {totalN} obs ·{" "}
            {reliabilityGap === null
              ? "—"
              : `gap ${fmtPct(reliabilityGap, 1)}`}
          </span>
        }
      >
        <CalibrationDiagram data={points} />
      </Card>

      <Card title="markets" action={<span>{markets.length}</span>}>
        {markets.length === 0 ? (
          <EmptyState
            title="no markets in store"
            hint="Run the bot or seed logs/polyflow.db to populate."
          />
        ) : (
          <ul className="divide-y divide-hairline text-xs">
            {markets.slice(0, 100).map((m) => (
              <li key={m.id}>
                <Link
                  href={`/probability/${encodeURIComponent(m.id)}`}
                  className="flex items-center justify-between gap-3 px-2 py-2 transition-colors hover:bg-white/[0.02]"
                >
                  <span className="truncate text-ink" title={m.question}>
                    {m.question}
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-subtle">
                    {shortId(m.id, 10)} · q={fmtNum(m.market_quality, 2)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
