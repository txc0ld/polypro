import Link from "next/link";
import { Card } from "@/components/Card";
import { getDb } from "@/lib/db";
import { fmtNum, fmtTime, shortId } from "@/lib/format";

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

export default function TradeCourtIndex() {
  const signals = listSignals();
  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Trade Court</h1>
        <span className="text-xs text-muted">PRD §19.5</span>
      </header>

      <Card title={`Signals (${signals.length})`}>
        {signals.length === 0 ? (
          <p className="text-sm text-muted">
            No signals recorded. Each signal becomes one trade page.
          </p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-muted">
              <tr className="text-left">
                <th className="pb-2 pr-4 font-normal">id</th>
                <th className="pb-2 pr-4 font-normal">market</th>
                <th className="pb-2 pr-4 font-normal">strategy</th>
                <th className="pb-2 pr-4 font-normal">side</th>
                <th className="pb-2 pr-4 font-normal">status</th>
                <th className="pb-2 pr-4 font-normal text-right">score</th>
                <th className="pb-2 pr-4 font-normal">created</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <tr key={s.id} className="border-t border-border">
                  <td className="py-2 pr-4">
                    <Link
                      href={`/trades/${encodeURIComponent(s.id)}`}
                      className="text-accent hover:underline"
                    >
                      {shortId(s.id, 8)}
                    </Link>
                  </td>
                  <td className="py-2 pr-4 text-muted">
                    {shortId(s.market_id, 10)}
                  </td>
                  <td className="py-2 pr-4">{s.strategy}</td>
                  <td className="py-2 pr-4">{s.side}</td>
                  <td className="py-2 pr-4">{s.status}</td>
                  <td className="py-2 pr-4 text-right">
                    {fmtNum(s.score, 2)}
                  </td>
                  <td className="py-2 pr-4 text-muted">
                    {fmtTime(s.created_at)}
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
