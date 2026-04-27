import Link from "next/link";
import { Card, EmptyState } from "@/components/Card";
import { Pill } from "@/components/Pill";
import { StrategyBadge } from "@/components/StrategyBadge";
import { getDb } from "@/lib/db";
import { fmtNum, shortId, timeAgo } from "@/lib/format";

type SignalRow = {
  id: string;
  market_id: string;
  strategy: string;
  side: string;
  status: string;
  score: number;
  created_at: string;
};

function listSignals(): SignalRow[] {
  const db = getDb();
  if (!db) return [];
  return db
    .prepare<[], SignalRow>(
      `SELECT id, market_id, strategy, side, status, score, created_at
       FROM signals ORDER BY created_at DESC LIMIT 500`,
    )
    .all();
}

const STATUS_TONE: Record<string, "good" | "warn" | "bad" | "muted"> = {
  PLACE: "good",
  WATCH: "warn",
  REJECT: "bad",
};

export default function TradeCourtIndex() {
  const signals = listSignals();
  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-display font-semibold tracking-tight gradient-text">
            Trade Court
          </h1>
          <p className="text-sm text-subtle">
            Every signal becomes a chronological trade page
          </p>
        </div>
        <Pill tone="muted">PRD §19.5</Pill>
      </header>

      <Card padded={false} title="signals" action={<span>{signals.length}</span>}>
        {signals.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="no signals recorded"
              hint="Each signal gets a court page. The arbiter has not produced any signals yet."
            />
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-caption uppercase tracking-wider text-subtle">
              <tr className="text-left">
                <th className="px-4 pb-2 pt-3 font-normal">id</th>
                <th className="px-4 pb-2 pt-3 font-normal">market</th>
                <th className="px-4 pb-2 pt-3 font-normal">strategy</th>
                <th className="px-4 pb-2 pt-3 font-normal">side</th>
                <th className="px-4 pb-2 pt-3 font-normal">status</th>
                <th className="px-4 pb-2 pt-3 text-right font-normal">score</th>
                <th className="px-4 pb-2 pt-3 text-right font-normal">when</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <tr
                  key={s.id}
                  className="border-t border-hairline transition-colors hover:bg-white/[0.02]"
                >
                  <td className="px-4 py-2">
                    <Link
                      href={`/trades/${encodeURIComponent(s.id)}`}
                      className="font-mono text-ink hover:text-accent"
                    >
                      {shortId(s.id, 10)}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <Link
                      href={`/probability/${encodeURIComponent(s.market_id)}`}
                      className="font-mono text-muted hover:text-accent"
                    >
                      {shortId(s.market_id, 10)}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <StrategyBadge strategy={s.strategy} size="sm" />
                  </td>
                  <td className="px-4 py-2 text-muted">{s.side}</td>
                  <td className="px-4 py-2">
                    <Pill tone={STATUS_TONE[s.status] ?? "muted"}>
                      {s.status}
                    </Pill>
                  </td>
                  <td className="px-4 py-2 text-right tabular">
                    {fmtNum(s.score, 2)}
                  </td>
                  <td className="px-4 py-2 text-right text-subtle">
                    {timeAgo(s.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
