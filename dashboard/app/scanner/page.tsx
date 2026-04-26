import Link from "next/link";
import Empty from "@/components/Empty";
import { listMarkets, type MarketRow } from "@/lib/db";
import { fmtNum, fmtTs, fmtUsd } from "@/lib/format";
import { readAllMatching } from "@/lib/log";

const BUCKETS = [
  { lo: 0.0, hi: 0.2, label: "0.00–0.20" },
  { lo: 0.2, hi: 0.4, label: "0.20–0.40" },
  { lo: 0.4, hi: 0.6, label: "0.40–0.60" },
  { lo: 0.6, hi: 0.8, label: "0.60–0.80" },
  { lo: 0.8, hi: 1.001, label: "0.80–1.00" },
];

function bucketize(values: number[]): { label: string; n: number }[] {
  return BUCKETS.map((b) => ({
    label: b.label,
    n: values.filter((v) => v >= b.lo && v < b.hi).length,
  }));
}

export default async function ScannerBoard() {
  const markets = listMarkets();
  const grouped: Record<string, MarketRow[]> = {};
  for (const m of markets) {
    grouped[m.status] = grouped[m.status] ?? [];
    grouped[m.status].push(m);
  }

  const scannerLogs = await readAllMatching({ actor: "market_scanner" });
  const skipReasonCounts: Record<string, number> = {};
  for (const r of scannerLogs) {
    const reasons =
      (r.payload?.["skip_reasons"] as string[] | undefined) ??
      (r.payload?.["reasons"] as string[] | undefined) ??
      [];
    for (const code of reasons) {
      skipReasonCounts[code] = (skipReasonCounts[code] ?? 0) + 1;
    }
    const single = r.payload?.["skip_reason"];
    if (typeof single === "string") {
      skipReasonCounts[single] = (skipReasonCounts[single] ?? 0) + 1;
    }
  }
  const sortedReasons = Object.entries(skipReasonCounts).sort((a, b) => b[1] - a[1]);

  const qualityScores = markets
    .map((m) => m.market_quality)
    .filter((v): v is number => typeof v === "number");
  const qualityHist = bucketize(qualityScores);
  const maxBucket = Math.max(1, ...qualityHist.map((b) => b.n));

  const order = ["watching", "manual_only", "skipped"];
  const sortedStatuses = [
    ...order.filter((s) => grouped[s]?.length),
    ...Object.keys(grouped).filter((s) => !order.includes(s)),
  ];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Market Scanner Board</h1>
        <p className="text-sm text-muted">PRD §19.2 — markets table joined with scanner-log classifications.</p>
      </header>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="panel">
          <div className="label mb-2">Skip-reason histogram</div>
          {sortedReasons.length === 0 ? (
            <div className="text-sm text-muted">No scanner skip events logged yet.</div>
          ) : (
            <ul className="space-y-1 text-sm">
              {sortedReasons.map(([code, n]) => (
                <li key={code} className="flex items-center justify-between font-mono text-xs">
                  <span>{code}</span>
                  <span className="text-muted">{n}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel">
          <div className="label mb-2">Quality-score distribution</div>
          {qualityScores.length === 0 ? (
            <div className="text-sm text-muted">No quality scores recorded yet.</div>
          ) : (
            <div className="space-y-1">
              {qualityHist.map((b) => (
                <div key={b.label} className="flex items-center gap-2 text-xs">
                  <span className="w-20 font-mono text-muted">{b.label}</span>
                  <div className="h-3 flex-1 rounded bg-edge">
                    <div
                      className="h-3 rounded bg-good/60"
                      style={{ width: `${(b.n / maxBucket) * 100}%` }}
                    />
                  </div>
                  <span className="w-6 text-right font-mono text-muted">{b.n}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {sortedStatuses.length === 0 ? (
        <Empty message="No markets in the SQLite store yet. Run `polyflow scan-once` to populate." />
      ) : (
        sortedStatuses.map((status) => (
          <section key={status}>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">
              {status} <span className="text-muted/60">({grouped[status].length})</span>
            </h2>
            <div className="panel overflow-x-auto p-0">
              <table className="table">
                <thead>
                  <tr>
                    <th>id</th>
                    <th>question</th>
                    <th>category</th>
                    <th>liq</th>
                    <th>vol 24h</th>
                    <th>spread</th>
                    <th>quality</th>
                    <th>created</th>
                  </tr>
                </thead>
                <tbody>
                  {grouped[status].map((m) => (
                    <tr key={m.id}>
                      <td className="font-mono text-xs">
                        <Link className="underline-offset-2 hover:underline" href={`/probability/${m.id}`}>
                          {m.id}
                        </Link>
                      </td>
                      <td className="max-w-md truncate">{m.question}</td>
                      <td className="font-mono text-xs">{m.category ?? "—"}</td>
                      <td className="font-mono text-xs">{fmtUsd(m.liquidity_usd, 0)}</td>
                      <td className="font-mono text-xs">{fmtUsd(m.volume_24h_usd, 0)}</td>
                      <td className="font-mono text-xs">{fmtNum(m.spread_pct, 2)}%</td>
                      <td className="font-mono text-xs">{fmtNum(m.market_quality, 2)}</td>
                      <td className="font-mono text-xs text-muted">{fmtTs(m.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
    </div>
  );
}
