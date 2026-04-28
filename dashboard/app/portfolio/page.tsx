import Link from "next/link";
import { Card, EmptyState, KeyRow, Stat } from "@/components/Card";
import { Pill } from "@/components/Pill";
import { listOpenPositions, type PositionRow, getDb } from "@/lib/db";
import { tailLog, type LogRecord } from "@/lib/log";
import { aggregateByStrategy, computeClv } from "@/lib/clv";
import { fmtNum, fmtPct, fmtUsd, shortId, timeAgo } from "@/lib/format";
import { readPolicy } from "@/lib/policy";
import { fetchWalletPositions, fetchWalletValue, funderAddress } from "@/lib/wallet";
import { StrategyBadge } from "@/components/StrategyBadge";

const STUCK_MS = 5 * 60 * 1000;

type CategoryExposure = {
  key: string;
  used: number;
  cap: number;
};

function lookupCategories(marketIds: string[]): Map<string, string> {
  const db = getDb();
  const out = new Map<string, string>();
  if (!db || marketIds.length === 0) return out;
  const placeholders = marketIds.map(() => "?").join(",");
  const rows = db
    .prepare(
      `SELECT id, category FROM markets WHERE id IN (${placeholders})`,
    )
    .all(...marketIds) as Array<{ id: string; category: string | null }>;
  for (const r of rows) out.set(r.id, r.category ?? "uncategorised");
  return out;
}

function exposureByCategory(
  positions: PositionRow[],
  bankroll: number,
  capPct: number,
  categoryFor: (m: string) => string,
): CategoryExposure[] {
  const cap = (capPct / 100) * bankroll;
  const map = new Map<string, number>();
  for (const p of positions) {
    const v = p.market_value ?? p.size * p.avg_price;
    const k = categoryFor(p.market_id);
    map.set(k, (map.get(k) ?? 0) + v);
  }
  return [...map.entries()]
    .map(([key, used]) => ({ key, used, cap }))
    .sort((a, b) => b.used - a.used);
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
    if (r.action === "place_order")
      placed.set(id, { ts: r.ts, marketId: r.market_id });
    else if (r.action === "cancel_order" || r.action === "fill")
      placed.delete(id);
  }
  const out: StuckOrder[] = [];
  for (const [exchangeOrderId, v] of placed.entries()) {
    const age = Date.now() - new Date(v.ts).getTime();
    if (age > STUCK_MS) {
      out.push({ exchangeOrderId, marketId: v.marketId, ts: v.ts, ageMs: age });
    }
  }
  return out.sort((a, b) => b.ageMs - a.ageMs);
}

function ExposureBars({
  rows,
  emptyHint,
}: {
  rows: CategoryExposure[];
  emptyHint?: string;
}) {
  if (rows.length === 0)
    return (
      <EmptyState
        title="no exposure"
        hint={emptyHint ?? "No open positions match this grouping."}
      />
    );
  return (
    <ul className="space-y-3">
      {rows.map((r) => {
        const pct = Math.min(1, r.used / Math.max(r.cap, 0.01));
        const tone =
          pct < 0.7 ? "bg-accent" : pct < 0.95 ? "bg-warn" : "bg-bad";
        return (
          <li key={r.key}>
            <div className="flex items-baseline justify-between text-xs">
              <span className="truncate text-ink" title={r.key}>
                {r.key}
              </span>
              <span className="tabular text-subtle">
                {fmtUsd(r.used, 2)}{" "}
                <span className="text-[10px] text-faint">
                  / {fmtUsd(r.cap, 0)}
                </span>
              </span>
            </div>
            <div className="mt-1 h-[3px] rounded bg-border">
              <div
                className={`h-[3px] rounded ${tone}`}
                style={{ width: `${Math.max(2, pct * 100)}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default async function PortfolioSentinel() {
  const policy = readPolicy();
  const bankroll = policy.bankrollUsdc ?? 0;
  const positions = listOpenPositions();
  const records = await tailLog(3000);
  const clvAll = await computeClv();
  const clvWithValue = clvAll.filter((c) => c.clv !== null);
  const clvByStrategy = aggregateByStrategy(clvAll);
  const clvOverallMean =
    clvWithValue.length === 0
      ? null
      : clvWithValue.reduce((a, b) => a + (b.clv ?? 0), 0) /
        clvWithValue.length;

  const stuck = stuckOrders(records);
  const dailyPnl = records
    .filter((r) => Date.now() - new Date(r.ts).getTime() < 86400000)
    .map((r) => (r.payload as { realized_pnl_usdc?: number }).realized_pnl_usdc)
    .filter((v): v is number => typeof v === "number")
    .reduce((a, b) => a + b, 0);

  const lastRisk = [...records]
    .reverse()
    .find((r) => r.actor === "risk_governor" && r.action === "evaluate");
  const kellyUsed = lastRisk
    ? (lastRisk.payload as { fractional_kelly?: number }).fractional_kelly ?? 0
    : 0;

  // Live wallet positions (server-side fetch)
  const address = funderAddress();
  const [walletValue, walletPositions] = await Promise.all([
    address ? fetchWalletValue(address) : Promise.resolve(null),
    address ? fetchWalletPositions(address) : Promise.resolve([]),
  ]);

  const cats = lookupCategories([...new Set(positions.map((p) => p.market_id))]);
  const byCategory = exposureByCategory(
    positions,
    bankroll,
    25,
    (m) => cats.get(m) ?? "uncategorised",
  );
  const byMarket = exposureByCategory(
    positions,
    bankroll,
    8,
    (m) => m,
  );

  const incidents = records
    .filter(
      (r) =>
        r.actor === "portfolio_sentinel" ||
        r.actor === "kill_switch" ||
        r.actor === "circuit_breakers" ||
        r.action === "kill_switch" ||
        r.action.startsWith("incident_") ||
        r.action.startsWith("frozen_") ||
        r.action.startsWith("final_blackout"),
    )
    .slice(-12)
    .reverse();

  // Cross-reference position with most recent CLV record (per market).
  const clvByMarket = new Map<string, (typeof clvWithValue)[number]>();
  for (const c of clvWithValue) clvByMarket.set(c.marketId, c);

  // Cross-reference SQLite positions with wallet positions for current price.
  const walletByMarket = new Map<string, (typeof walletPositions)[number]>();
  for (const w of walletPositions) walletByMarket.set(w.conditionId, w);

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-display font-semibold tracking-tight text-ink">
            Portfolio Sentinel
          </h1>
          <p className="mt-1 text-xs text-subtle">
            {positions.length} open position{positions.length === 1 ? "" : "s"}{" "}
            · {clvWithValue.length} resolved trade
            {clvWithValue.length === 1 ? "" : "s"} with CLV
          </p>
        </div>
        <Pill tone="muted">PRD §19.4</Pill>
      </header>

      <div className="grid grid-cols-2 overflow-hidden rounded-md border border-border md:grid-cols-4">
        <div className="border-b border-r border-border bg-surface p-4 md:border-b-0">
          <Stat
            label="open positions"
            value={positions.length}
            hint="from positions table"
          />
        </div>
        <div className="border-b border-border bg-surface p-4 md:border-b-0 md:border-r">
          <Stat
            label="daily pnl"
            value={
              <span
                className={
                  dailyPnl > 0
                    ? "text-good"
                    : dailyPnl < 0
                      ? "text-bad"
                      : "text-ink"
                }
              >
                {dailyPnl > 0 ? "+" : ""}
                {fmtUsd(dailyPnl, 2)}
              </span>
            }
            hint="last 24h · from log"
          />
        </div>
        <div className="border-r border-border bg-surface p-4">
          <Stat
            label="kelly used"
            value={fmtPct(kellyUsed, 2)}
            hint="last evaluate"
          />
        </div>
        <div className="bg-surface p-4">
          <Stat
            label="stuck orders"
            value={stuck.length}
            tone={stuck.length > 0 ? "warn" : "good"}
            hint="open > 5m"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
        {/* LEFT — positions table */}
        <Card padded={false} title="positions" action={
          <span>
            {positions.length} on book
            {walletPositions.length > 0
              ? ` · ${walletPositions.length} on chain`
              : ""}
          </span>
        }>
          {positions.length === 0 && walletPositions.length === 0 ? (
            <EmptyState
              title="no open positions"
              hint="The bot has not placed any fills, or the SQLite store is empty."
            />
          ) : positions.length === 0 ? (
            // Fallback to on-chain positions if SQLite has none.
            <table className="w-full text-xs">
              <thead className="text-caption uppercase tracking-wider text-subtle">
                <tr className="text-left">
                  <th className="px-4 pb-2 pt-3 font-normal">market</th>
                  <th className="px-4 pb-2 pt-3 font-normal">outcome</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">size</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">avg</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">px</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">pnl</th>
                </tr>
              </thead>
              <tbody>
                {walletPositions.map((w) => (
                  <tr
                    key={`${w.conditionId}-${w.outcome}`}
                    className="border-t border-border"
                  >
                    <td className="max-w-[28ch] truncate px-4 py-2 text-ink">
                      {w.market || shortId(w.conditionId, 12)}
                    </td>
                    <td className="px-4 py-2 text-muted">{w.outcome}</td>
                    <td className="px-4 py-2 text-right tabular">{fmtNum(w.size, 2)}</td>
                    <td className="px-4 py-2 text-right tabular">
                      {fmtPct(w.avgPrice, 1)}
                    </td>
                    <td className="px-4 py-2 text-right tabular">
                      {fmtPct(w.currentPrice, 1)}
                    </td>
                    <td
                      className={`px-4 py-2 text-right tabular ${
                        w.cashPnl > 0
                          ? "text-good"
                          : w.cashPnl < 0
                            ? "text-bad"
                            : "text-muted"
                      }`}
                    >
                      {w.cashPnl > 0 ? "+" : ""}
                      {fmtUsd(w.cashPnl, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-caption uppercase tracking-wider text-subtle">
                <tr className="text-left">
                  <th className="px-4 pb-2 pt-3 font-normal">market</th>
                  <th className="px-4 pb-2 pt-3 font-normal">outcome</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">size</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">avg</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">cur</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">unrealized</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">clv</th>
                  <th className="px-4 pb-2 pt-3 text-right font-normal">updated</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const wallet = walletByMarket.get(p.market_id);
                  const cur = wallet?.currentPrice ?? null;
                  const unrealized =
                    cur !== null
                      ? p.size * (cur - p.avg_price)
                      : (p.market_value ?? p.size * p.avg_price) -
                        p.size * p.avg_price;
                  const clv = clvByMarket.get(p.market_id);
                  return (
                    <tr
                      key={`${p.market_id}-${p.token_id}`}
                      className="border-t border-border"
                    >
                      <td className="max-w-[28ch] truncate px-4 py-2 text-ink">
                        <Link
                          href={`/probability/${encodeURIComponent(p.market_id)}`}
                          className="hover:text-accent-soft"
                        >
                          {shortId(p.market_id, 12)}
                        </Link>
                      </td>
                      <td className="px-4 py-2 text-muted">{p.outcome}</td>
                      <td className="px-4 py-2 text-right tabular">
                        {fmtNum(p.size, 2)}
                      </td>
                      <td className="px-4 py-2 text-right tabular">
                        {fmtPct(p.avg_price, 1)}
                      </td>
                      <td className="px-4 py-2 text-right tabular text-muted">
                        {cur === null ? "—" : fmtPct(cur, 1)}
                      </td>
                      <td
                        className={`px-4 py-2 text-right tabular ${
                          unrealized > 0
                            ? "text-good"
                            : unrealized < 0
                              ? "text-bad"
                              : "text-muted"
                        }`}
                      >
                        {unrealized > 0 ? "+" : ""}
                        {fmtUsd(unrealized, 2)}
                      </td>
                      <td
                        className={`px-4 py-2 text-right tabular ${
                          clv === undefined || clv.clv === null
                            ? "text-faint"
                            : clv.clv > 0
                              ? "text-good"
                              : "text-bad"
                        }`}
                      >
                        {clv === undefined || clv.clv === null
                          ? "—"
                          : `${clv.clv > 0 ? "+" : ""}${(clv.clv * 10000).toFixed(0)}bp`}
                      </td>
                      <td className="px-4 py-2 text-right text-subtle">
                        {timeAgo(p.updated_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>

        {/* RIGHT — exposure + kill switch + breakers + CLV strategy */}
        <div className="space-y-4">
          <Card title="wallet · live">
            {walletValue ? (
              <div className="space-y-2">
                <div>
                  <div className="text-caption uppercase tracking-wider text-subtle">
                    on-chain value
                  </div>
                  <div className="tabular text-hero font-medium text-ink">
                    {fmtUsd(walletValue.totalUsd, 2)}
                  </div>
                </div>
                <KeyRow
                  k="bankroll target"
                  v={fmtUsd(bankroll, 0)}
                />
                <KeyRow
                  k="positions"
                  v={walletPositions.length}
                />
              </div>
            ) : (
              <EmptyState
                title="wallet unavailable"
                hint={
                  address
                    ? "Polymarket Data API returned no value."
                    : "Set POLY_FUNDER_ADDRESS to enable."
                }
              />
            )}
          </Card>

          <Card title="exposure by category" action={<span>cap 25%</span>}>
            <ExposureBars rows={byCategory} />
          </Card>

          <Card title="exposure by market" action={<span>cap 8%</span>}>
            <ExposureBars rows={byMarket.slice(0, 8)} />
          </Card>

          <Card title="kill switch">
            <KeyRow
              k="state"
              v={
                <Pill
                  tone={
                    incidents.some((i) => i.action === "kill_switch")
                      ? "bad"
                      : "good"
                  }
                  dot
                >
                  {incidents.some((i) => i.action === "kill_switch")
                    ? "tripped"
                    : "armed"}
                </Pill>
              }
            />
            <KeyRow
              k="daily loss cap"
              v={`${policy.bankrollUsdc !== null ? fmtUsd(policy.bankrollUsdc * 0.2, 2) : "—"}`}
            />
            <KeyRow k="circuit breaker events" v={incidents.length} />
          </Card>
        </div>
      </div>

      {/* CLV by strategy */}
      <Card
        title="closing-line value"
        action={
          clvWithValue.length === 0 ? (
            <span>n=0</span>
          ) : (
            <span>
              n={clvWithValue.length} · mean{" "}
              <span
                className={
                  (clvOverallMean ?? 0) > 0
                    ? "text-good"
                    : (clvOverallMean ?? 0) < 0
                      ? "text-bad"
                      : ""
                }
              >
                {clvOverallMean === null
                  ? "—"
                  : `${clvOverallMean > 0 ? "+" : ""}${(clvOverallMean * 100).toFixed(2)}c`}
              </span>
            </span>
          )
        }
      >
        {clvByStrategy.length === 0 ? (
          <EmptyState
            title="no clv yet"
            hint="No resolved trades with both an execution price and a closing line."
          />
        ) : (
          <ul className="space-y-3">
            {clvByStrategy.map((s) => {
              const magnitude = Math.min(1, Math.abs(s.mean) / 0.05);
              const tone =
                s.mean > 0 ? "bg-good" : s.mean < 0 ? "bg-bad" : "bg-faint";
              return (
                <li key={s.strategy}>
                  <div className="flex items-baseline justify-between gap-2">
                    <StrategyBadge strategy={s.strategy} size="sm" />
                    <span className="text-xs text-subtle">
                      n={s.n} · win {fmtPct(s.positive / s.n, 0)} · mean{" "}
                      <span
                        className={
                          s.mean > 0
                            ? "text-good"
                            : s.mean < 0
                              ? "text-bad"
                              : "text-muted"
                        }
                      >
                        {s.mean > 0 ? "+" : ""}
                        {(s.mean * 100).toFixed(2)}c
                      </span>
                    </span>
                  </div>
                  <div className="mt-1 h-[3px] rounded bg-border">
                    <div
                      className={`h-[3px] rounded ${tone}`}
                      style={{
                        width: `${Math.max(2, magnitude * 100)}%`,
                      }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {/* Incident queue */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card title="stuck orders" action={<span>open &gt; 5m</span>}>
          {stuck.length === 0 ? (
            <EmptyState title="none" />
          ) : (
            <ul className="divide-y divide-border text-xs">
              {stuck.map((s) => (
                <li
                  key={s.exchangeOrderId}
                  className="flex items-baseline justify-between py-2"
                >
                  <span className="font-mono text-muted">
                    {shortId(s.exchangeOrderId, 14)}
                  </span>
                  <span className="text-subtle">
                    {shortId(s.marketId, 10)} ·{" "}
                    <span className="text-warn">
                      {Math.round(s.ageMs / 60000)}m
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="incident queue">
          {incidents.length === 0 ? (
            <EmptyState title="no incidents" />
          ) : (
            <ul className="divide-y divide-border text-xs">
              {incidents.map((r) => {
                const detail =
                  (r.payload as { detail?: string; reason?: string }).detail ??
                  (r.payload as { reason?: string }).reason ??
                  "";
                return (
                  <li
                    key={r.id}
                    className="flex items-baseline justify-between gap-3 py-2"
                  >
                    <span className="text-subtle">{timeAgo(r.ts)}</span>
                    <span className="text-ink">{r.actor}</span>
                    <span className="text-warn">{r.action}</span>
                    <span className="truncate text-muted" title={detail}>
                      {detail}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
