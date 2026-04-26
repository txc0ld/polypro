import Link from "next/link";
import { Card } from "@/components/Card";
import { listAllMarkets } from "@/lib/db";
import { fmtNum, shortId } from "@/lib/format";

export default function ProbabilityIndex() {
  const markets = listAllMarkets();
  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Probability Lab</h1>
        <span className="text-xs text-muted">PRD §19.3</span>
      </header>

      <Card title="Pick a market">
        {markets.length === 0 ? (
          <p className="text-sm text-muted">
            No markets in the SQLite store yet.
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {markets.map((m) => (
              <li key={m.id} className="flex items-center justify-between">
                <Link
                  href={`/probability/${encodeURIComponent(m.id)}`}
                  className="text-accent hover:underline"
                >
                  {m.question}
                </Link>
                <span className="text-xs text-muted">
                  {shortId(m.id, 10)} · q={fmtNum(m.market_quality, 2)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
