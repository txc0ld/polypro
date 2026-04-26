import { Card, Stat } from "@/components/Card";
import { listOpenPositions, type PositionRow } from "@/lib/db";
import { tailLog, type LogRecord } from "@/lib/log";
import { fmtNum, fmtPct, fmtTime, fmtUsd, shortId } from "@/lib/format";
import { readPolicy } from "@/lib/policy";

const STUCK_MS = 5 * 60 * 1000;

type ExposureRow = {
  key: string;
  used: number;
  cap: number;
};

function aggregateExposure(
  positions: PositionRow[],
  bankroll: number,
  capPct: number,
  groupBy: (p: PositionRow) => string,
): ExposureRow[] {
  const cap = (capPct / 100) * bankroll;
  const map = new Map<string, number>();
  for (const p of positions) {
    const v = p.market_value ?? p.size * p.avg_price;
    map.set(groupBy(p), (map.get(groupBy(p)) ?? 0) + v);
  }
  return [...map.entries()]
    .map(([key, used]) => ({ key, used, cap }))
    .sort((a, b) => b.used - a.used);
}

function ExposureBars({ rows }: { rows: ExposureRow[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted">No exposure.</p>;
  }
  return (
    <ul className="space-y-2 text-xs">
      {rows.map((r) => {
        const pct = Math.min(1, r.used / Math.max(r.cap, 1));
        const colour =
          pct < 0.7 ? "bg-accent" : pct < 0.95 ? "bg-warn" : "bg-bad";
        return (
          <li key={r.key}>
            <div className="flex justify-between">
              <span>{r.key || "—"}</span>
              <span className="text-muted">
                {fmtUsd(r.used, 0)} / {fmtUsd(r.cap, 0)}
              </span>
            </div>
            <div className="h-1 rounded bg-border">
              <div
                className={`h-1 rounded ${colour}`}
                style={{ width: `${Math.max(2, pct * 100)}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

type StuckOrder = {
  exchangeOrderId: string;
  marketId: string | null;
  ts: string;
  ageMs: number;
};

function stuckOrders(records: LogRecord[]): StuckOrder[] {
  const placed = new Map<string, { ts: string; marketId: string | null }>();
  for (const r of records) {
    if (r.actor !== "clob_adapter") continue;
    const id = (r.payload as { exchange_order_id?: string }).exchange_order_id;
    if (!id) continue;
    if (r.action === "place_order") {
      placed.set(id, { ts: r.ts, marketId: r.market_id });
    } else if (r.action === "cancel_order" || r.action === "fill") {
      placed.delete(id);
    }
  }
  const out: StuckOrder[] = [];
  for (const [exchangeOrderId, v] of placed.entries()) {
    const age = Date.now() - new Date(v.ts).getTime();
    if (age > STUCK_MS) {
      out.push({
        exchangeOrderId,
        marketId: v.marketId,
        ts: v.ts,
        ageMs: age,
      });
    }
  }
  return out.sort((a, b) => b.ageMs - a.ageMs);
}

export default async function PortfolioSentinel() {
  const policy = readPolicy();
  const bankroll = policy.bankrollUsdc ?? 0;
  const positions = listOpenPositions();
  const records = await tailLog(2000);

  const market = aggregateExposure(positions, bankroll, 1, (p) => p.market_id);
  const event = aggregateExposure(positions, bankroll, 2.5, (p) => p.market_id);
  const category = aggregateExposure(positions, bankroll, 5, () => "all");

  const stuck = stuckOrders(records);

  const incidents = records
    .filter(
      (r) =>
        r.actor === "portfolio_sentinel" ||
        r.actor === "kill_switch" ||
        r.action === "kill_switch" ||
        r.action.startsWith("incident_"),
    )
    .slice(-30)
    .reverse();

  // Best-effort drawdown from log
  const dailyPnl = records
    .filter((r) => Date.now() - new Date(r.ts).getTime() < 86400000)
    .map((r) => (r.payload as { realized_pnl_usdc?: number }).realized_pnl_usdc)
    .filter((v): v is number => typeof v === "number")
    .reduce((a, b) => a + b, 0);

  // Best-effort Kelly usage from latest risk_governor decisions
  const lastRisk = [...records]
    .reverse()
    .find((r) => r.actor === "risk_governor" && r.action === "evaluate");
  const kellyUsed = lastRisk
    ? (lastRisk.payload as { fractional_kelly?: number }).fractional_kelly ?? 0
    : 0;

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Portfolio Sentinel</h1>
        <span className="text-xs text-muted">PRD §19.4</span>
      </header>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card>
          <Stat label="open positions" value={positions.length} />
        </Card>
        <Card>
          <Stat
            label="daily PnL"
            value={fmtUsd(dailyPnl)}
            hint="last 24h"
          />
        </Card>
        <Card>
          <Stat
            label="Kelly used"
            value={fmtPct(kellyUsed, 2)}
            hint="last evaluate"
          />
        </Card>
        <Card>
          <Stat
            label="stuck orders"
            value={stuck.length}
            hint="open > 5m"
          />
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card title="Per-market exposure (cap 1%)">
          <ExposureBars rows={market} />
        </Card>
        <Card title="Per-event exposure (cap 2.5%)">
          <ExposureBars rows={event} />
        </Card>
        <Card title="Category exposure (cap 5%)">
          <ExposureBars rows={category} />
        </Card>
      </div>

      <Card title="Open positions">
        {positions.length === 0 ? (
          <p className="text-sm text-muted">No open positions.</p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-muted">
              <tr className="text-left">
                <th className="pb-2 pr-4 font-normal">market</th>
                <th className="pb-2 pr-4 font-normal">outcome</th>
                <th className="pb-2 pr-4 font-normal text-right">size</th>
                <th className="pb-2 pr-4 font-normal text-right">avg px</th>
                <th className="pb-2 pr-4 font-normal text-right">value</th>
                <th className="pb-2 pr-4 font-normal">updated</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={`${p.market_id}-${p.token_id}`} className="border-t border-border">
                  <td className="py-2 pr-4 text-muted">
                    {shortId(p.market_id, 12)}
                  </td>
                  <td className="py-2 pr-4">{p.outcome}</td>
                  <td className="py-2 pr-4 text-right">
                    {fmtNum(p.size, 2)}
                  </td>
                  <td className="py-2 pr-4 text-right">
                    {fmtNum(p.avg_price, 3)}
                  </td>
                  <td className="py-2 pr-4 text-right">
                    {fmtUsd(p.market_value, 2)}
                  </td>
                  <td className="py-2 pr-4 text-muted">
                    {fmtTime(p.updated_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Stuck orders (open > 5m)">
        {stuck.length === 0 ? (
          <p className="text-sm text-muted">None.</p>
        ) : (
          <ul className="space-y-1 text-xs">
            {stuck.map((s) => (
              <li
                key={s.exchangeOrderId}
                className="flex justify-between border-t border-border pt-1"
              >
                <span>{shortId(s.exchangeOrderId, 14)}</span>
                <span className="text-muted">
                  {shortId(s.marketId, 10)} · {Math.round(s.ageMs / 60000)}m
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Incident queue">
        {incidents.length === 0 ? (
          <p className="text-sm text-muted">No incidents.</p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-muted">
              <tr className="text-left">
                <th className="pb-2 pr-4 font-normal">ts</th>
                <th className="pb-2 pr-4 font-normal">actor</th>
                <th className="pb-2 pr-4 font-normal">action</th>
                <th className="pb-2 pr-4 font-normal">detail</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((r) => {
                const detail =
                  (r.payload as { detail?: string; reason?: string }).detail ??
                  (r.payload as { reason?: string }).reason ??
                  "";
                return (
                  <tr key={r.id} className="border-t border-border">
                    <td className="py-2 pr-4 text-muted">{fmtTime(r.ts)}</td>
                    <td className="py-2 pr-4">{r.actor}</td>
                    <td className="py-2 pr-4">{r.action}</td>
                    <td className="py-2 pr-4 text-muted">{detail}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
