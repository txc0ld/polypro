"use client";

import Link from "next/link";
import { useState, useMemo } from "react";
import type { LogRecord } from "@/lib/log";
import { shortId, timeAgo } from "@/lib/format";
import { EmptyState } from "./Card";

const ACTOR_TONE: Record<string, string> = {
  market_scanner: "text-sky",
  signal_arbiter: "text-emerald",
  risk_governor: "text-violet",
  clob_order_formatter: "text-fuchsia",
  clob_adapter: "text-amber",
  post_order_kelly_guard: "text-rose",
  btc_feed: "text-amber",
  commodities_feed: "text-orange",
  news_analyzer: "text-sky",
  strategy_automation: "text-violet",
  intra_market_arbitrage: "text-fuchsia",
  near_expiry_certainty: "text-rose",
  circuit_breakers: "text-bad",
  macro_calendar: "text-sky",
  runtime: "text-warn",
  heartbeat: "text-faint",
  trade_activity_analyzer: "text-orange",
  resolution_monitor: "text-emerald",
  order_sync: "text-amber",
  portfolio_sentinel: "text-violet",
};

function actorTone(actor: string): string {
  return ACTOR_TONE[actor] ?? "text-muted";
}

const FILTERS: Array<{ key: string; label: string; actors: string[] }> = [
  { key: "all", label: "all", actors: [] },
  {
    key: "trade",
    label: "trade",
    actors: ["clob_adapter", "clob_order_formatter", "risk_governor"],
  },
  {
    key: "strategy",
    label: "strategy",
    actors: [
      "signal_arbiter",
      "strategy_automation",
      "intra_market_arbitrage",
      "near_expiry_certainty",
    ],
  },
  {
    key: "feed",
    label: "feed",
    actors: ["btc_feed", "commodities_feed", "news_analyzer"],
  },
  {
    key: "runtime",
    label: "runtime",
    actors: ["runtime", "heartbeat", "circuit_breakers", "portfolio_sentinel"],
  },
];

export function ActivityFeed({ records }: { records: LogRecord[] }) {
  const [filter, setFilter] = useState("all");

  const filtered = useMemo(() => {
    const f = FILTERS.find((x) => x.key === filter);
    if (!f || f.actors.length === 0) return records;
    return records.filter((r) => f.actors.includes(r.actor));
  }, [records, filter]);

  if (records.length === 0) {
    return (
      <EmptyState
        title="activity feed empty"
        hint="logs/immutable.jsonl is missing or contains zero records."
      />
    );
  }
  const last = filtered.slice(-30).reverse();
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1 border-b border-border px-3 py-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded px-2 py-0.5 text-[10px] uppercase tracking-wider transition-colors ${
              filter === f.key
                ? "bg-panel text-ink"
                : "text-subtle hover:text-muted"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {last.length === 0 ? (
        <EmptyState
          title="no entries match this filter"
          hint="Try switching to 'all'."
        />
      ) : (
        <ol className="space-y-0">
          {last.map((r) => {
            const sid = (r.payload as { signal_id?: string }).signal_id;
            const linkHref = sid
              ? `/trades/${encodeURIComponent(sid)}`
              : r.market_id
                ? `/probability/${encodeURIComponent(r.market_id)}`
                : null;
            const inner = (
              <div className="row-hover flex items-start gap-2 border-b border-border px-3 py-1.5 last:border-0">
                <span className="w-12 shrink-0 text-[10px] tabular text-faint">
                  {timeAgo(r.ts).replace(" ago", "")}
                </span>
                <span
                  className={`w-32 shrink-0 truncate text-[11px] font-medium ${actorTone(r.actor)}`}
                  title={r.actor}
                >
                  {r.actor}
                </span>
                <span
                  className="flex-1 truncate text-[11px] text-ink"
                  title={r.action}
                >
                  {r.action}
                </span>
                <span
                  className="w-20 shrink-0 truncate text-right font-mono text-[10px] text-faint"
                  title={r.market_id ?? ""}
                >
                  {r.market_id ? shortId(r.market_id, 8) : ""}
                </span>
              </div>
            );
            return (
              <li key={r.id}>
                {linkHref ? (
                  <Link href={linkHref} className="block">
                    {inner}
                  </Link>
                ) : (
                  inner
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
