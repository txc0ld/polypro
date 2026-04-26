import Stat from "@/components/Stat";
import { getOpenPositions } from "@/lib/db";
import { fmtAge, fmtTs, fmtUsd } from "@/lib/format";
import { readHeartbeat } from "@/lib/heartbeat";
import { readLogTail, readLatest, type LogRecord } from "@/lib/log";
import { readPolicy } from "@/lib/policy";
import { readSystemState } from "@/lib/state";

function dailyPnl(records: LogRecord[]): number | null {
  const now = Date.now();
  let pnl: number | null = null;
  for (const r of records) {
    const ts = Date.parse(r.ts);
    if (Number.isNaN(ts) || now - ts > 24 * 3600 * 1000) continue;
    const candidate = r.payload?.["pnl_usdc"] ?? r.payload?.["realized_pnl_usdc"];
    if (typeof candidate === "number") pnl = (pnl ?? 0) + candidate;
  }
  return pnl;
}

export default async function LiveDesk() {
  const policy = readPolicy();
  const heartbeat = readHeartbeat();
  const positions = getOpenPositions();
  const tail = await readLogTail(10);
  const allRecent = await readLogTail(2000);
  const pnl = dailyPnl(allRecent);
  const openOrders = await readLatest({ actor: "portfolio_sentinel", action: "open_orders_snapshot" });
  const openOrderCount =
    typeof openOrders?.payload?.["count"] === "number"
      ? (openOrders.payload["count"] as number)
      : allRecent.filter(
          (r) => r.action === "order_placed" && now24h(r.ts),
        ).length;
  const killSwitch = await readLatest({ actor: "kill_switch" });
  const { state } = await readSystemState();

  const heartbeatTone = heartbeat.ageSeconds === null
    ? "warn"
    : heartbeat.ageSeconds < 90
    ? "good"
    : heartbeat.ageSeconds < 300
    ? "warn"
    : "bad";

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold">Live Desk</h1>
          <p className="text-sm text-muted">PRD §19.1 — autonomous runtime snapshot.</p>
        </div>
        <span className="pill">policy mode: <span className="ml-1 font-mono">{policy.mode}</span></span>
      </header>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <Stat label="Mode" value={policy.mode} />
        <Stat label="System State" value={state} tone={state === "HEALTHY" ? "good" : state === "UNKNOWN" ? "neutral" : "warn"} />
        <Stat label="Heartbeat" value={fmtAge(heartbeat.ageSeconds)} hint={fmtTs(heartbeat.ts)} tone={heartbeatTone} />
        <Stat label="Bankroll" value={fmtUsd(policy.bankrollUsdc)} />
        <Stat label="Open positions" value={String(positions.length)} />
        <Stat
          label="Open orders"
          value={String(openOrderCount)}
          hint={openOrders ? `as of ${fmtTs(openOrders.ts)}` : "no snapshot yet"}
        />
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Stat
          label="Daily PnL (USDC)"
          value={pnl === null ? "—" : fmtUsd(pnl)}
          tone={pnl === null ? "neutral" : pnl >= 0 ? "good" : "bad"}
          hint="sum of pnl_usdc payloads in the last 24h"
        />
        <Stat
          label="Kill switch"
          value={killSwitch ? String(killSwitch.payload?.["state"] ?? killSwitch.action) : "armed"}
          hint={killSwitch ? `last event ${fmtTs(killSwitch.ts)}` : "no kill_switch entries"}
          tone={killSwitch && /trip|engage|killed/i.test(String(killSwitch.action)) ? "bad" : "neutral"}
        />
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted">
          Latest immutable log entries
        </h2>
        <div className="panel overflow-x-auto p-0">
          <table className="table">
            <thead>
              <tr>
                <th className="w-48">ts</th>
                <th>actor</th>
                <th>action</th>
                <th>market</th>
                <th>payload</th>
              </tr>
            </thead>
            <tbody>
              {tail.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-muted">
                    No immutable log entries yet. Start the runtime with{" "}
                    <code className="font-mono">polyflow run</code>.
                  </td>
                </tr>
              ) : (
                tail
                  .slice()
                  .reverse()
                  .map((r) => (
                    <tr key={r.id}>
                      <td className="font-mono text-xs">{fmtTs(r.ts)}</td>
                      <td className="font-mono text-xs">{r.actor}</td>
                      <td className="font-mono text-xs">{r.action}</td>
                      <td className="font-mono text-xs">{r.market_id ?? "—"}</td>
                      <td className="max-w-md truncate font-mono text-xs text-muted">
                        {JSON.stringify(r.payload).slice(0, 220)}
                      </td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function now24h(ts: string): boolean {
  const t = Date.parse(ts);
  return !Number.isNaN(t) && Date.now() - t < 24 * 3600 * 1000;
}
