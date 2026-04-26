import { Card, Stat } from "@/components/Card";
import {
  dbAvailable,
  listOpenPositions,
} from "@/lib/db";
import {
  currentIncidentState,
  loadHeartbeat,
  logExists,
  tailLog,
  type LogRecord,
} from "@/lib/log";
import { fmtTime, fmtUsd, shortId, timeAgo } from "@/lib/format";
import { heartbeatPath } from "@/lib/paths";
import { readPolicy } from "@/lib/policy";

const FIVE_MINUTES = 5 * 60 * 1000;

function pnlFromLog(records: LogRecord[]): number {
  // Best-effort daily PnL: sum payload.realized_pnl_usdc on post_order_kelly_guard
  // and clob_adapter records emitted in the last 24h. Falls back to 0 when the
  // runtime hasn't emitted any.
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  let total = 0;
  for (const r of records) {
    const t = new Date(r.ts).getTime();
    if (Number.isNaN(t) || t < cutoff) continue;
    const pnl = (r.payload as { realized_pnl_usdc?: number }).realized_pnl_usdc;
    if (typeof pnl === "number") total += pnl;
  }
  return total;
}

function openOrdersFromLog(records: LogRecord[]): number {
  const placed = new Set<string>();
  for (const r of records) {
    if (r.actor === "clob_adapter" && r.action === "place_order") {
      const id = (r.payload as { exchange_order_id?: string }).exchange_order_id;
      if (id) placed.add(id);
    }
    if (r.actor === "clob_adapter" && r.action === "cancel_order") {
      const id = (r.payload as { exchange_order_id?: string }).exchange_order_id;
      if (id) placed.delete(id);
    }
  }
  return placed.size;
}

export default async function LiveDesk() {
  const policy = readPolicy();
  const state = await currentIncidentState();
  const hb = await loadHeartbeat(heartbeatPath);
  const positions = listOpenPositions();
  const recent = await tailLog(500);
  const latest10 = recent.slice(-10).reverse();

  const heartbeatFresh = hb
    ? Date.now() - new Date(hb.ts).getTime() < FIVE_MINUTES
    : false;

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Live Desk</h1>
        <span className="text-xs text-muted">PRD §19.1</span>
      </header>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card>
          <Stat
            label="mode"
            value={policy.mode ?? "—"}
            hint={policy.exists ? "from configs/policy.yaml" : "policy missing"}
          />
        </Card>
        <Card>
          <Stat
            label="bankroll"
            value={fmtUsd(policy.bankrollUsdc, 0)}
            hint="configured"
          />
        </Card>
        <Card>
          <Stat
            label="open positions"
            value={positions.length}
            hint={dbAvailable() ? "from positions table" : "no DB found"}
          />
        </Card>
        <Card>
          <Stat
            label="open orders"
            value={openOrdersFromLog(recent)}
            hint={logExists() ? "derived from log" : "no log found"}
          />
        </Card>
        <Card>
          <Stat
            label="daily PnL"
            value={fmtUsd(pnlFromLog(recent))}
            hint="last 24h, from log"
          />
        </Card>
        <Card>
          <Stat
            label="heartbeat"
            value={
              <span
                className={heartbeatFresh ? "text-accent" : "text-bad"}
              >
                {hb ? timeAgo(hb.ts) : "missing"}
              </span>
            }
            hint={hb ? `pid ${hb.pid}` : "logs/heartbeat.json"}
          />
        </Card>
        <Card>
          <Stat
            label="runtime state"
            value={state}
            hint="reconstructed from log"
          />
        </Card>
        <Card>
          <Stat
            label="kill switch"
            value={state === "KILLED" ? "TRIPPED" : "armed"}
            hint={state === "KILLED" ? "redeploy required" : "fail-closed"}
          />
        </Card>
      </div>

      <Card title="Latest 10 immutable-log entries">
        {latest10.length === 0 ? (
          <p className="text-sm text-muted">
            No entries in {logExists() ? "logs/immutable.jsonl" : "logs/ (file missing)"}.
          </p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-muted">
              <tr className="text-left">
                <th className="pb-2 pr-4 font-normal">ts</th>
                <th className="pb-2 pr-4 font-normal">actor</th>
                <th className="pb-2 pr-4 font-normal">action</th>
                <th className="pb-2 pr-4 font-normal">market</th>
                <th className="pb-2 pr-4 font-normal">id</th>
              </tr>
            </thead>
            <tbody>
              {latest10.map((r) => (
                <tr key={r.id} className="border-t border-border">
                  <td className="py-2 pr-4 text-muted">{fmtTime(r.ts)}</td>
                  <td className="py-2 pr-4">{r.actor}</td>
                  <td className="py-2 pr-4">{r.action}</td>
                  <td className="py-2 pr-4 text-muted">
                    {shortId(r.market_id, 12)}
                  </td>
                  <td className="py-2 pr-4 text-muted">{shortId(r.id, 8)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Source health">
        <ul className="grid grid-cols-1 gap-2 text-xs md:grid-cols-3">
          <li>
            SQLite store: {dbAvailable() ? (
              <span className="text-accent">online</span>
            ) : (
              <span className="text-warn">missing</span>
            )}
          </li>
          <li>
            Immutable log: {logExists() ? (
              <span className="text-accent">online</span>
            ) : (
              <span className="text-warn">missing</span>
            )}
          </li>
          <li>
            Policy file: {policy.exists ? (
              <span className="text-accent">loaded</span>
            ) : (
              <span className="text-warn">missing</span>
            )}
          </li>
        </ul>
      </Card>
    </div>
  );
}
