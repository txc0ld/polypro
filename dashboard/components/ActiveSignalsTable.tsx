import Link from "next/link";
import { StrategyBadge } from "./StrategyBadge";
import { EmptyState } from "./Card";
import type { ActiveSignal, SignalAction } from "@/lib/signals";
import { fmtUsd, shortId, timeAgo } from "@/lib/format";

const ACTION_LABEL: Record<SignalAction, { label: string; tone: string }> = {
  FILLED: { label: "FILLED", tone: "text-good" },
  PLACED: { label: "PLACED", tone: "text-good" },
  RISK_REJECTED: { label: "RISK", tone: "text-warn" },
  FORMATTER_REJECTED: { label: "FORMAT", tone: "text-warn" },
  INCIDENT_BLOCKED: { label: "BLOCKED", tone: "text-bad" },
  WATCH: { label: "WATCH", tone: "text-subtle" },
  REJECT: { label: "REJECT", tone: "text-faint" },
  PENDING: { label: "PENDING", tone: "text-muted" },
};

const ROW_LEFT_BAR: Record<SignalAction, string> = {
  FILLED: "border-l-2 border-good",
  PLACED: "border-l-2 border-good",
  RISK_REJECTED: "border-l-2 border-warn",
  FORMATTER_REJECTED: "border-l-2 border-warn",
  INCIDENT_BLOCKED: "border-l-2 border-bad",
  WATCH: "border-l-2 border-transparent",
  REJECT: "border-l-2 border-transparent",
  PENDING: "border-l-2 border-transparent",
};

function fmtProb(p: number | null): string {
  if (p === null || Number.isNaN(p)) return "—";
  return `${(p * 100).toFixed(1)}¢`;
}

function fmtBps(bps: number | null): string {
  if (bps === null) return "—";
  const sign = bps >= 0 ? "+" : "";
  return `${sign}${bps}bp`;
}

export function ActiveSignalsTable({ signals }: { signals: ActiveSignal[] }) {
  if (signals.length === 0) {
    return (
      <EmptyState
        title="no signals in last 30 minutes"
        hint="Strategies emit candidates each cycle. The runtime may be warming up, or every signal scored below the action threshold."
      />
    );
  }
  return (
    <div className="overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-caption uppercase tracking-wider text-faint">
            <th className="px-3 pb-2 pt-2.5 text-left font-normal">strategy</th>
            <th className="px-3 pb-2 pt-2.5 text-left font-normal">market</th>
            <th className="px-3 pb-2 pt-2.5 text-right font-normal">model</th>
            <th className="px-3 pb-2 pt-2.5 text-right font-normal">price</th>
            <th className="px-3 pb-2 pt-2.5 text-right font-normal">edge</th>
            <th className="px-3 pb-2 pt-2.5 text-right font-normal">size</th>
            <th className="px-3 pb-2 pt-2.5 text-right font-normal">action</th>
            <th className="px-3 pb-2 pt-2.5 text-right font-normal">age</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => {
            const action = ACTION_LABEL[s.action];
            const gap =
              s.modelProbability !== null && s.marketPrice !== null
                ? Math.abs(s.modelProbability - s.marketPrice)
                : null;
            return (
              <tr
                key={s.signalId}
                className={`row-hover border-t border-border ${ROW_LEFT_BAR[s.action]}`}
              >
                <td className="px-3 py-2 align-middle">
                  <StrategyBadge strategy={s.strategy} size="sm" />
                </td>
                <td className="px-3 py-2 align-middle">
                  <Link
                    href={`/probability/${encodeURIComponent(s.marketId)}`}
                    className="block max-w-[26ch] truncate text-ink hover:text-accent-soft"
                    title={s.marketQuestion ?? s.marketId}
                  >
                    {s.marketQuestion ?? shortId(s.marketId, 18)}
                  </Link>
                  <span className="text-[10px] uppercase tracking-wider text-faint">
                    {s.side}
                    {s.category ? ` · ${s.category}` : ""}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular text-ink">
                  {fmtProb(s.modelProbability)}
                </td>
                <td className="px-3 py-2 text-right tabular text-muted">
                  {fmtProb(s.marketPrice)}
                  {gap !== null ? (
                    <span className="ml-1 text-[10px] text-faint">
                      Δ{(gap * 100).toFixed(1)}
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-right tabular text-ink">
                  {fmtBps(s.effectiveEdgeBps)}
                </td>
                <td className="px-3 py-2 text-right tabular text-muted">
                  {s.approvedSizeUsdc !== null
                    ? fmtUsd(s.approvedSizeUsdc, 2)
                    : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  <Link
                    href={`/trades/${encodeURIComponent(s.signalId)}`}
                    className={`text-[11px] font-medium uppercase tracking-wider ${action.tone} hover:underline`}
                    title={s.reason ?? action.label}
                  >
                    {action.label}
                  </Link>
                </td>
                <td className="px-3 py-2 text-right text-faint">
                  {timeAgo(s.createdAt)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
