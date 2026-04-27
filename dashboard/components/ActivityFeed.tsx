import Link from "next/link";
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
  heartbeat: "text-subtle",
  trade_activity_analyzer: "text-orange",
  resolution_monitor: "text-emerald",
  order_sync: "text-amber",
  portfolio_sentinel: "text-violet",
};

function actorTone(actor: string): string {
  return ACTOR_TONE[actor] ?? "text-muted";
}

export function ActivityFeed({ records }: { records: LogRecord[] }) {
  if (records.length === 0) {
    return (
      <EmptyState
        title="activity feed empty"
        hint="logs/immutable.jsonl is missing or contains zero records."
      />
    );
  }
  const last = records.slice(-30).reverse();
  return (
    <ol className="space-y-0">
      {last.map((r) => {
        const sid = (r.payload as { signal_id?: string }).signal_id;
        const linkHref = sid
          ? `/trades/${encodeURIComponent(sid)}`
          : r.market_id
            ? `/probability/${encodeURIComponent(r.market_id)}`
            : null;
        const inner = (
          <div className="flex items-start gap-2 border-b border-hairline px-3 py-2 transition-colors last:border-0 hover:bg-white/[0.02]">
            <span className="w-12 shrink-0 text-[10px] tabular text-subtle">
              {timeAgo(r.ts).replace(" ago", "")}
            </span>
            <span
              className={`w-32 shrink-0 truncate text-[11px] font-medium ${actorTone(r.actor)}`}
              title={r.actor}
            >
              {r.actor}
            </span>
            <span className="flex-1 truncate text-[11px] text-ink" title={r.action}>
              {r.action}
            </span>
            <span
              className="w-20 shrink-0 truncate text-right font-mono text-[10px] text-subtle"
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
  );
}
