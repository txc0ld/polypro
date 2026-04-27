import { Card } from "@/components/Card";
import { dbAvailable, listAllMarkets, type MarketRow } from "@/lib/db";
import { tailLog } from "@/lib/log";
import { fmtNum, fmtPct, fmtUsd, shortId, timeAgo } from "@/lib/format";

type ClassifyPayload = {
  approved: boolean;
  manual_only: boolean;
  reasons: string[];
};

function buildSkipReasons(records: { payload: unknown }[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const r of records) {
    const p = r.payload as ClassifyPayload;
    if (!p || p.approved) continue;
    for (const reason of p.reasons ?? []) {
      counts.set(reason, (counts.get(reason) ?? 0) + 1);
    }
  }
  return counts;
}

function bucketize(markets: MarketRow[]) {
  const buckets = new Map<string, number>([
    ["0.0–0.2", 0],
    ["0.2–0.4", 0],
    ["0.4–0.6", 0],
    ["0.6–0.8", 0],
    ["0.8–1.0", 0],
  ]);
  for (const m of markets) {
    const q = m.market_quality ?? 0;
    if (q < 0.2) buckets.set("0.0–0.2", (buckets.get("0.0–0.2") ?? 0) + 1);
    else if (q < 0.4) buckets.set("0.2–0.4", (buckets.get("0.2–0.4") ?? 0) + 1);
    else if (q < 0.6) buckets.set("0.4–0.6", (buckets.get("0.4–0.6") ?? 0) + 1);
    else if (q < 0.8) buckets.set("0.6–0.8", (buckets.get("0.6–0.8") ?? 0) + 1);
    else buckets.set("0.8–1.0", (buckets.get("0.8–1.0") ?? 0) + 1);
  }
  return buckets;
}

function MarketTable({ markets }: { markets: MarketRow[] }) {
  if (markets.length === 0) {
    return <p className="text-sm text-muted">No markets in this status.</p>;
  }
  return (
    <table className="w-full text-xs">
      <thead className="text-muted">
        <tr className="text-left">
          <th className="pb-2 pr-4 font-normal">id</th>
          <th className="pb-2 pr-4 font-normal">question</th>
          <th className="pb-2 pr-4 font-normal">category</th>
          <th className="pb-2 pr-4 font-normal text-right">liquidity</th>
          <th className="pb-2 pr-4 font-normal text-right">spread</th>
          <th className="pb-2 pr-4 font-normal text-right">quality</th>
          <th className="pb-2 pr-4 font-normal">created</th>
        </tr>
      </thead>
      <tbody>
        {markets.map((m) => (
          <tr key={m.id} className="border-t border-border align-top">
            <td className="py-2 pr-4 text-muted">{shortId(m.id, 10)}</td>
            <td className="py-2 pr-4">{m.question}</td>
            <td className="py-2 pr-4 text-muted">{m.category ?? "—"}</td>
            <td className="py-2 pr-4 text-right">
              {fmtUsd(m.liquidity_usd, 0)}
            </td>
            <td className="py-2 pr-4 text-right">
              {fmtPct((m.spread_pct ?? 0) / 100, 2)}
            </td>
            <td className="py-2 pr-4 text-right">
              {fmtNum(m.market_quality, 2)}
            </td>
            <td className="py-2 pr-4 text-muted">{timeAgo(m.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function ScannerBoard() {
  const markets = listAllMarkets();
  const watching = markets.filter((m) => m.status === "watching");
  const skipped = markets.filter((m) => m.status === "skipped");
  const manual = markets.filter((m) => m.status === "manual_only");

  const classifyEntries = await tailLog(1000, {
    actor: "market_scanner",
    action: "classify",
  });
  const skipReasons = buildSkipReasons(classifyEntries);
  const sortedReasons = [...skipReasons.entries()].sort((a, b) => b[1] - a[1]);

  const buckets = bucketize(markets);
  const maxBucket = Math.max(1, ...buckets.values());

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Market Scanner Board</h1>
        <span className="text-xs text-muted">PRD §19.2</span>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card title="Skip-reason histogram">
          {!dbAvailable() && classifyEntries.length === 0 ? (
            <p className="text-sm text-muted">
              No scanner classify entries in the log yet.
            </p>
          ) : sortedReasons.length === 0 ? (
            <p className="text-sm text-muted">No skips recorded.</p>
          ) : (
            <ul className="space-y-2 text-xs">
              {sortedReasons.map(([reason, count]) => {
                const pct =
                  count / Math.max(1, sortedReasons[0]?.[1] ?? 1);
                return (
                  <li key={reason}>
                    <div className="flex justify-between">
                      <span>{reason}</span>
                      <span className="text-muted">{count}</span>
                    </div>
                    <div className="h-1 rounded bg-border">
                      <div
                        className="h-1 rounded bg-warn"
                        style={{ width: `${Math.max(2, pct * 100)}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Quality-score distribution">
          <ul className="space-y-2 text-xs">
            {[...buckets.entries()].map(([label, count]) => {
              const pct = count / maxBucket;
              return (
                <li key={label}>
                  <div className="flex justify-between">
                    <span>{label}</span>
                    <span className="text-muted">{count}</span>
                  </div>
                  <div className="h-1 rounded bg-border">
                    <div
                      className="h-1 rounded bg-accent"
                      style={{ width: `${Math.max(2, pct * 100)}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      <Card title={`Watching (${watching.length})`}>
        <MarketTable markets={watching} />
      </Card>
      <Card title={`Manual-only review (${manual.length})`}>
        <MarketTable markets={manual} />
      </Card>
      <Card title={`Skipped (${skipped.length})`}>
        <MarketTable markets={skipped} />
      </Card>
    </div>
  );
}
