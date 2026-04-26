import Link from "next/link";
import { Card } from "@/components/Card";
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
  // Reliability gap = mean |predicted - empirical| weighted by n. Lower is better.
  const reliabilityGap =
    totalN === 0
      ? null
      : buckets.reduce(
          (sum, b) =>
            sum + Math.abs(b.mean_predicted - b.empirical) * b.n,
          0,
        ) / totalN;
  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Probability Lab</h1>
        <span className="text-xs text-muted">PRD §19.3</span>
      </header>

      <Card title="Calibration reliability diagram">
        <CalibrationDiagram data={points} />
        <p className="mt-3 text-xs text-muted">
          {totalN} observation{totalN === 1 ? "" : "s"} ·{" "}
          {reliabilityGap === null
            ? "—"
            : `weighted reliability gap ${fmtPct(reliabilityGap, 1)}`}{" "}
          · diagonal = perfect calibration
        </p>
      </Card>

      <Card title="Pick a market">
        {markets.length === 0 ? (
          <p className="text-sm text-muted">
            No markets in the SQLite store yet.
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {markets.map((m) => (
              <li key={m.id} className="flex items-center justify-between">
                <Link
                  href={`/probability/${encodeURIComponent(m.id)}`}
                  className="text-accent hover:underline"
                >
                  {m.question}
                </Link>
                <span className="text-xs text-muted">
                  {shortId(m.id, 10)} · q={fmtNum(m.market_quality, 2)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
