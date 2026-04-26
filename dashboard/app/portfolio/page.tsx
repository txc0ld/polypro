import Empty from "@/components/Empty";
import Stat from "@/components/Stat";
import { getMarket, getOpenPositions } from "@/lib/db";
import { fmtNum, fmtPct, fmtTs, fmtUsd } from "@/lib/format";
import { readAllMatching, readLatest } from "@/lib/log";
import { readPolicy } from "@/lib/policy";

type ExposureRow = {
  key: string;
  exposure: number;
  cap: number | null;
  capPct: number | null;
};

const KELLY_FRACTION_KEY = "kelly_fraction";

export default async function PortfolioPage() {
  const policy = readPolicy();
  const positions = getOpenPositions();
  const bankroll = policy.bankrollUsdc ?? null;

  const risk = (policy.raw["risk"] ?? {}) as Record<string, unknown>;
  const capMarketPct = numberOrNull(risk["max_single_market_position_pct"]);
  const capEventPct = numberOrNull(risk["max_single_event_exposure_pct"]);
  const capCategoryPct = numberOrNull(risk["max_category_exposure_pct"]);

  const marketMeta = new Map(positions.map((p) => [p.market_id, getMarket(p.market_id)]));

  const byMarket: Record<string, number> = {};
  const byEvent: Record<string, number> = {};
  const byCategory: Record<string, number> = {};
  let totalExposure = 0;
  for (const p of positions) {
    const exposure = (p.market_value ?? p.size * p.avg_price) || 0;
    totalExposure += exposure;
    byMarket[p.market_id] = (byMarket[p.market_id] ?? 0) + exposure;
    const meta = marketMeta.get(p.market_id);
    const eventKey = meta?.event_id ?? p.market_id;
    const categoryKey = meta?.category ?? "uncategorized";
    byEvent[eventKey] = (byEvent[eventKey] ?? 0) + exposure;
    byCategory[categoryKey] = (byCategory[categoryKey] ?? 0) + exposure;
  }

  const marketRows = toRows(byMarket, bankroll, capMarketPct);
  const eventRows = toRows(byEvent, bankroll, capEventPct);
  const categoryRows = toRows(byCategory, bankroll, capCategoryPct);

  const recent = await readAllMatching({});
  const drawdown = computeDrawdown(recent);
  const kellyUsage = lastKellyFraction(recent);

  const stuckOrders = await stuckOrdersFromLog(recent);
  const incidents = recent.filter(
    (r) => r.actor === "portfolio_sentinel" || r.actor === "kill_switch",
  ).slice(-25).reverse();

  const killSwitch = await readLatest({ actor: "kill_switch" });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Portfolio Sentinel</h1>
        <p className="text-sm text-muted">PRD §19.4 — exposure caps, Kelly usage, drawdown, stuck orders, incidents.</p>
      </header>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Bankroll" value={fmtUsd(bankroll)} />
        <Stat label="Total exposure" value={fmtUsd(totalExposure)} hint={bankroll ? fmtPct(totalExposure / bankroll) + " of bankroll" : undefined} />
        <Stat
          label="Kelly usage"
          value={kellyUsage === null ? "—" : fmtPct(kellyUsage)}
          hint={`policy.kelly.fraction = ${policy.raw["kelly"] && (policy.raw["kelly"] as Record<string, unknown>)["fraction"]}`}
        />
        <Stat
          label="Drawdown (24h)"
          value={drawdown === null ? "—" : fmtPct(drawdown)}
          tone={drawdown === null ? "neutral" : drawdown < -0.005 ? "bad" : "neutral"}
        />
      </section>

      <ExposureTable title="Per market" rows={marketRows} bankroll={bankroll} />
      <ExposureTable title="Per event" rows={eventRows} bankroll={bankroll} />
      <ExposureTable title="Per category" rows={categoryRows} bankroll={bankroll} />

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">
          Stuck orders <span className="text-muted/60">(open &gt; 5 min, no fill)</span>
        </h2>
        {stuckOrders.length === 0 ? (
          <Empty message="No stuck orders detected." />
        ) : (
          <div className="panel overflow-x-auto p-0">
            <table className="table">
              <thead>
                <tr>
                  <th>order id</th>
                  <th>market</th>
                  <th>side</th>
                  <th>price</th>
                  <th>size</th>
                  <th>placed</th>
                  <th>age</th>
                </tr>
              </thead>
              <tbody>
                {stuckOrders.map((o) => (
                  <tr key={o.id}>
                    <td className="font-mono text-xs">{o.id}</td>
                    <td className="font-mono text-xs">{o.marketId ?? "—"}</td>
                    <td className="font-mono text-xs">{o.side ?? "—"}</td>
                    <td className="font-mono text-xs">{fmtNum(o.price, 4)}</td>
                    <td className="font-mono text-xs">{fmtNum(o.size, 2)}</td>
                    <td className="font-mono text-xs">{fmtTs(o.placedAt)}</td>
                    <td className="font-mono text-xs">{Math.floor(o.ageSeconds / 60)}m</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">
          Incident queue
        </h2>
        <div className="panel overflow-x-auto p-0">
          <table className="table">
            <thead>
              <tr>
                <th className="w-48">ts</th>
                <th>actor</th>
                <th>action</th>
                <th>payload</th>
              </tr>
            </thead>
            <tbody>
              {incidents.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-muted">
                    No incident entries from portfolio_sentinel or kill_switch.
                  </td>
                </tr>
              ) : (
                incidents.map((r) => (
                  <tr key={r.id}>
                    <td className="font-mono text-xs">{fmtTs(r.ts)}</td>
                    <td className="font-mono text-xs">{r.actor}</td>
                    <td className="font-mono text-xs">{r.action}</td>
                    <td className="max-w-md truncate font-mono text-xs text-muted">
                      {JSON.stringify(r.payload).slice(0, 200)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {killSwitch ? (
          <p className="mt-2 text-xs text-muted">
            Last kill_switch entry: {fmtTs(killSwitch.ts)} · action <span className="font-mono">{killSwitch.action}</span>
          </p>
        ) : null}
      </section>
    </div>
  );
}

function ExposureTable({
  title,
  rows,
  bankroll,
}: {
  title: string;
  rows: ExposureRow[];
  bankroll: number | null;
}) {
  if (rows.length === 0) {
    return (
      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">{title}</h2>
        <Empty message="No open positions." />
      </section>
    );
  }
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">{title}</h2>
      <div className="panel space-y-2">
        {rows.map((r) => {
          const pct = bankroll && bankroll > 0 ? r.exposure / bankroll : null;
          const capRatio =
            r.cap !== null && r.cap > 0 ? Math.min(1, r.exposure / r.cap) : null;
          return (
            <div key={r.key} className="space-y-1 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-mono">{r.key}</span>
                <span className="font-mono text-muted">
                  {fmtUsd(r.exposure, 0)} · {pct === null ? "—" : fmtPct(pct)}
                  {r.capPct !== null ? ` · cap ${fmtNum(r.capPct, 2)}%` : ""}
                </span>
              </div>
              <div className="h-2 rounded bg-edge">
                <div
                  className={`h-2 rounded ${capRatio !== null && capRatio >= 1 ? "bg-bad" : capRatio !== null && capRatio >= 0.8 ? "bg-warn" : "bg-good/60"}`}
                  style={{ width: `${(capRatio ?? 0) * 100}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function toRows(
  acc: Record<string, number>,
  bankroll: number | null,
  capPct: number | null,
): ExposureRow[] {
  const cap = bankroll !== null && capPct !== null ? bankroll * (capPct / 100) : null;
  return Object.entries(acc)
    .map(([key, exposure]) => ({ key, exposure, cap, capPct }))
    .sort((a, b) => b.exposure - a.exposure);
}

function numberOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function lastKellyFraction(records: { payload: Record<string, unknown> }[]): number | null {
  for (let i = records.length - 1; i >= 0; i--) {
    const v = records[i].payload?.[KELLY_FRACTION_KEY];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

function computeDrawdown(records: { ts: string; payload: Record<string, unknown> }[]): number | null {
  const cutoff = Date.now() - 24 * 3600 * 1000;
  const equity = records
    .filter((r) => Date.parse(r.ts) >= cutoff)
    .map((r) => r.payload?.["bankroll_usdc"] ?? r.payload?.["equity_usdc"])
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (equity.length < 2) return null;
  let peak = equity[0];
  let maxDrop = 0;
  for (const v of equity) {
    if (v > peak) peak = v;
    const drop = (v - peak) / peak;
    if (drop < maxDrop) maxDrop = drop;
  }
  return maxDrop;
}

type StuckOrder = {
  id: string;
  marketId: string | null;
  side: string | null;
  price: number | null;
  size: number | null;
  placedAt: string;
  ageSeconds: number;
};

async function stuckOrdersFromLog(
  records: { ts: string; action: string; market_id: string | null; payload: Record<string, unknown> }[],
): Promise<StuckOrder[]> {
  const placed = new Map<string, StuckOrder>();
  for (const r of records) {
    const id = (r.payload?.["order_id"] as string | undefined) ?? (r.payload?.["id"] as string | undefined);
    if (!id) continue;
    if (r.action === "order_placed") {
      const ageSeconds = Math.floor((Date.now() - Date.parse(r.ts)) / 1000);
      placed.set(id, {
        id,
        marketId: r.market_id,
        side: (r.payload?.["side"] as string | undefined) ?? null,
        price: numberOrNull(r.payload?.["price"]),
        size: numberOrNull(r.payload?.["size"]),
        placedAt: r.ts,
        ageSeconds,
      });
    } else if (r.action === "order_filled" || r.action === "order_cancelled" || r.action === "order_canceled") {
      placed.delete(id);
    }
  }
  return Array.from(placed.values()).filter((o) => o.ageSeconds > 5 * 60);
}
