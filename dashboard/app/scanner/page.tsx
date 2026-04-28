import Link from "next/link";
import { Card, EmptyState } from "@/components/Card";
import { Pill } from "@/components/Pill";
import { StrategyBadge } from "@/components/StrategyBadge";
import { listAllMarkets, type MarketRow } from "@/lib/db";
import { tailLog } from "@/lib/log";
import { fmtUsd, shortId } from "@/lib/format";

const CATEGORY_GROUPS: Array<{
  label: string;
  match: (cat: string) => boolean;
}> = [
  {
    label: "sports",
    match: (c) =>
      /sport|nba|nfl|mlb|nhl|soccer|tennis|ufc|boxing|hockey|football|baseball|basketball/i.test(
        c,
      ),
  },
  {
    label: "esports",
    match: (c) =>
      /esport|csgo|cs:?go|cs2|counter[\s-]?strike|league of legends|\blol\b|dota|valorant/i.test(
        c,
      ),
  },
  {
    label: "crypto",
    match: (c) => /crypto|btc|bitcoin|eth|ether|solana|sol|defi/i.test(c),
  },
  {
    label: "commodities",
    match: (c) =>
      /commodit|wti|crude|oil|gold|silver|copper|gas|xau|xag/i.test(c),
  },
  {
    label: "macro",
    match: (c) =>
      /macro|cpi|pce|fed|fomc|rates|inflation|treasury|gdp|nfp|jobs|unemploy/i.test(
        c,
      ),
  },
  {
    label: "political",
    match: (c) =>
      /politic|election|president|senate|house|congress|geopolit|policy/i.test(
        c,
      ),
  },
];

function groupOf(market: MarketRow): string {
  const text = `${market.category ?? ""} ${market.question}`;
  for (const g of CATEGORY_GROUPS) {
    if (g.match(text)) return g.label;
  }
  return "other";
}

function timeToClose(closeIso: string | null): string {
  if (!closeIso) return "—";
  const d = new Date(closeIso);
  if (Number.isNaN(d.getTime())) return "—";
  const ms = d.getTime() - Date.now();
  if (ms <= 0) return "closed";
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  if (h >= 24) {
    const d_ = Math.floor(h / 24);
    const h_ = h % 24;
    return `${d_}d ${h_}h`;
  }
  return `${h}h ${m.toString().padStart(2, "0")}m`;
}

function bidAskCell(m: MarketRow): string {
  const bid = m.best_bid;
  const ask = m.best_ask;
  if (bid !== null && ask !== null && bid !== undefined && ask !== undefined) {
    return `${(bid * 100).toFixed(1)}/${(ask * 100).toFixed(1)}c`;
  }
  return "—";
}

function spreadCents(m: MarketRow): string {
  if (m.spread_pct === null || m.spread_pct === undefined) return "—";
  return `${m.spread_pct.toFixed(2)}c`;
}

function parseStrategies(json: string | null): string[] {
  if (!json) return [];
  try {
    const v = JSON.parse(json);
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

type ClassifyPayload = {
  approved: boolean;
  manual_only: boolean;
  reasons: string[];
};

function buildSkipReasons(records: { payload: unknown }[]): Array<[string, number]> {
  const counts = new Map<string, number>();
  for (const r of records) {
    const p = r.payload as ClassifyPayload;
    if (!p || p.approved) continue;
    for (const reason of p.reasons ?? []) {
      counts.set(reason, (counts.get(reason) ?? 0) + 1);
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]);
}

function MarketRowView({ m }: { m: MarketRow }) {
  const strategies = parseStrategies(m.strategy_candidates);
  const qfScore = m.quickfire_score ?? 0;
  return (
    <Link
      href={`/probability/${encodeURIComponent(m.id)}`}
      className="row-hover block border-t border-border"
    >
      <div className="grid grid-cols-12 items-center gap-3 px-4 py-2 text-xs">
        <div className="col-span-5 truncate text-ink" title={m.question}>
          {m.question}
        </div>
        <div className="col-span-1 text-right tabular text-muted">
          {bidAskCell(m)}
        </div>
        <div className="col-span-1 text-right tabular text-subtle">
          {spreadCents(m)}
        </div>
        <div className="col-span-1 text-right tabular text-muted">
          {timeToClose(m.close_time)}
        </div>
        <div className="col-span-1">
          <div className="flex items-center gap-1.5">
            <div className="h-1 flex-1 rounded bg-border">
              <div
                className="h-1 rounded bg-accent"
                style={{
                  width: `${Math.min(100, Math.max(2, qfScore * 100))}%`,
                }}
              />
            </div>
            <span className="tabular text-[10px] text-faint">
              {qfScore.toFixed(2)}
            </span>
          </div>
        </div>
        <div className="col-span-2 flex flex-wrap items-center gap-1">
          {strategies.length > 0 ? (
            strategies
              .slice(0, 3)
              .map((s) => <StrategyBadge key={s} strategy={s} size="sm" />)
          ) : (
            <span className="text-[10px] text-faint">—</span>
          )}
          {strategies.length > 3 ? (
            <span className="text-[10px] text-faint">
              +{strategies.length - 3}
            </span>
          ) : null}
        </div>
        <div className="col-span-1 text-right font-mono text-[10px] text-faint">
          {shortId(m.id, 8)}
        </div>
      </div>
    </Link>
  );
}

function MarketGroup({
  label,
  markets,
}: {
  label: string;
  markets: MarketRow[];
}) {
  if (markets.length === 0) return null;
  return (
    <Card
      padded={false}
      title={label}
      action={<span>{markets.length} markets</span>}
    >
      <div className="grid grid-cols-12 gap-3 px-4 py-2 text-caption uppercase tracking-wider text-faint">
        <div className="col-span-5">question</div>
        <div className="col-span-1 text-right">bid/ask</div>
        <div className="col-span-1 text-right">spread</div>
        <div className="col-span-1 text-right">close in</div>
        <div className="col-span-1">quickfire</div>
        <div className="col-span-2">strategies</div>
        <div className="col-span-1 text-right">id</div>
      </div>
      {markets.map((m) => (
        <MarketRowView key={m.id} m={m} />
      ))}
    </Card>
  );
}

export default async function ScannerBoard() {
  const allMarkets = listAllMarkets();
  const watching = allMarkets.filter((m) => m.status === "watching");
  const skipped = allMarkets.filter((m) => m.status === "skipped");
  const manual = allMarkets.filter((m) => m.status === "manual_only");

  // Group watching markets by category
  const groups = new Map<string, MarketRow[]>();
  for (const m of watching) {
    const k = groupOf(m);
    const arr = groups.get(k) ?? [];
    arr.push(m);
    groups.set(k, arr);
  }
  // Sort within each group by quickfire score desc
  for (const arr of groups.values()) {
    arr.sort((a, b) => (b.quickfire_score ?? 0) - (a.quickfire_score ?? 0));
  }

  const orderedGroups: Array<[string, MarketRow[]]> = [
    ...CATEGORY_GROUPS.map((g) => [g.label, groups.get(g.label) ?? []]),
    ["other", groups.get("other") ?? []],
  ] as Array<[string, MarketRow[]]>;

  const classifyEntries = await tailLog(2000, {
    actor: "market_scanner",
    action: "classify",
  });
  const skipReasons = buildSkipReasons(classifyEntries);
  const maxSkip = skipReasons[0]?.[1] ?? 1;

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-display font-semibold tracking-tight text-ink">
            Scanner Board
          </h1>
          <p className="mt-1 text-xs text-subtle">
            {allMarkets.length} markets observed · {watching.length} watching ·{" "}
            {skipped.length} skipped · {manual.length} manual review
          </p>
        </div>
        <Pill tone="muted">PRD §19.2</Pill>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          {watching.length === 0 ? (
            <Card title="watching">
              <EmptyState
                title="no markets in watching state"
                hint="The scanner has not classified any markets as approved yet, or logs/polyflow.db is empty."
              />
            </Card>
          ) : (
            orderedGroups.map(([label, ms]) => (
              <MarketGroup key={label} label={label} markets={ms} />
            ))
          )}
        </div>

        <aside className="space-y-4">
          <Card title="skip reasons" action={<span>{skipReasons.length}</span>}>
            {skipReasons.length === 0 ? (
              <EmptyState
                title="no skips recorded"
                hint="Either the scanner approved everything, or the immutable log is empty."
              />
            ) : (
              <ul className="space-y-2 text-xs">
                {skipReasons.slice(0, 12).map(([reason, count]) => {
                  const pct = count / maxSkip;
                  return (
                    <li key={reason}>
                      <div className="flex items-baseline justify-between">
                        <span className="truncate text-ink" title={reason}>
                          {reason.toLowerCase().replace(/_/g, " ")}
                        </span>
                        <span className="tabular text-subtle">{count}</span>
                      </div>
                      <div className="mt-1 h-[3px] rounded bg-border">
                        <div
                          className="h-[3px] rounded bg-warn/70"
                          style={{
                            width: `${Math.max(2, pct * 100)}%`,
                          }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card title="status">
            <ul className="space-y-1.5 text-xs">
              <li className="flex justify-between">
                <span className="text-subtle">watching</span>
                <span className="tabular text-good">{watching.length}</span>
              </li>
              <li className="flex justify-between">
                <span className="text-subtle">manual_only</span>
                <span className="tabular text-warn">{manual.length}</span>
              </li>
              <li className="flex justify-between">
                <span className="text-subtle">skipped</span>
                <span className="tabular text-bad">{skipped.length}</span>
              </li>
              <li className="mt-1 flex justify-between border-t border-border pt-2">
                <span className="text-subtle">total observed</span>
                <span className="tabular text-ink">{allMarkets.length}</span>
              </li>
              <li className="flex justify-between">
                <span className="text-subtle">classify entries</span>
                <span className="tabular text-ink">
                  {classifyEntries.length}
                </span>
              </li>
            </ul>
          </Card>

          {manual.length > 0 ? (
            <Card title={`manual review (${manual.length})`} padded={false}>
              <ul className="divide-y divide-border">
                {manual.slice(0, 12).map((m) => (
                  <li key={m.id} className="px-4 py-2 text-xs">
                    <Link
                      href={`/probability/${encodeURIComponent(m.id)}`}
                      className="block truncate text-ink hover:text-accent-soft"
                      title={m.question}
                    >
                      {m.question}
                    </Link>
                    <span className="text-[10px] text-faint">
                      {m.category ?? "—"}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
