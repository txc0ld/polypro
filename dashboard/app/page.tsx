import { Card, EmptyState, KeyRow, Stat } from "@/components/Card";
import { Pill } from "@/components/Pill";
import { ActiveSignalsTable } from "@/components/ActiveSignalsTable";
import { ActivityFeed } from "@/components/ActivityFeed";
import { loadActiveSignals } from "@/lib/signals";
import { loadRuntimeStatus } from "@/lib/runtime";
import { fmtUsd, timeAgo } from "@/lib/format";

export default async function LiveDesk() {
  const [status, signals] = await Promise.all([
    loadRuntimeStatus(),
    loadActiveSignals(),
  ]);

  const wallet = status.wallet;
  const heartbeatTone =
    status.heartbeat.status === "fresh"
      ? "good"
      : status.heartbeat.status === "stale"
        ? "warn"
        : "bad";
  const stateTone =
    status.incident === "HEALTHY"
      ? "good"
      : status.incident === "DEGRADED"
        ? "warn"
        : "bad";

  const placedCount = signals.filter(
    (s) => s.action === "PLACED" || s.action === "FILLED",
  ).length;
  const blockedCount = signals.filter((s) =>
    ["RISK_REJECTED", "FORMATTER_REJECTED", "INCIDENT_BLOCKED"].includes(s.action),
  ).length;

  return (
    <div className="space-y-6">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-display font-semibold tracking-tight">Live Desk</h1>
          <p className="text-sm text-subtle">
            Autonomous runtime · 7 strategies wired · read-only mirror
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-subtle">
          <Pill tone="muted">PRD §19.1</Pill>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* LEFT — runtime telemetry */}
        <div className="space-y-4 lg:col-span-1">
          <Card title="runtime">
            <div className="grid grid-cols-2 gap-4">
              <Stat
                label="state"
                value={status.incident}
                tone={stateTone}
                hint="reconstructed from incident logs"
              />
              <Stat
                label="mode"
                value={status.mode ?? "—"}
                hint={status.policy.exists ? "policy.yaml" : "policy missing"}
              />
              <Stat
                label="heartbeat"
                value={
                  status.heartbeat.ts ? timeAgo(status.heartbeat.ts) : "missing"
                }
                tone={heartbeatTone}
                hint={
                  status.heartbeat.pid !== null
                    ? `pid ${status.heartbeat.pid}`
                    : "logs/heartbeat.json"
                }
              />
              <Stat
                label="kill switch"
                value={status.incident === "KILLED" ? "TRIPPED" : "armed"}
                tone={status.incident === "KILLED" ? "bad" : "good"}
                hint={
                  status.incident === "KILLED"
                    ? "redeploy required"
                    : "fail-closed"
                }
              />
            </div>
          </Card>

          <Card title="wallet">
            {wallet ? (
              <div className="space-y-3">
                <div>
                  <div className="text-caption uppercase tracking-wider text-subtle">
                    total value
                  </div>
                  <div className="tabular text-3xl font-medium text-ink">
                    {fmtUsd(wallet.totalUsd, 2)}
                  </div>
                </div>
                <div className="space-y-1">
                  <KeyRow
                    k="bankroll target"
                    v={fmtUsd(status.policy.bankrollUsdc, 0)}
                  />
                  <KeyRow
                    k="funder"
                    v={
                      <span className="font-mono">
                        {status.walletAddress
                          ? `${status.walletAddress.slice(0, 6)}…${status.walletAddress.slice(-4)}`
                          : "—"}
                      </span>
                    }
                  />
                  <KeyRow k="data api" v="data-api.polymarket.com" />
                  <KeyRow k="fetched" v={timeAgo(wallet.fetchedAt)} />
                </div>
              </div>
            ) : status.walletAddress ? (
              <EmptyState
                title="wallet value unavailable"
                hint="Polymarket Data API did not return a value for this address."
              />
            ) : (
              <EmptyState
                title="no funder address"
                hint="Set POLY_FUNDER_ADDRESS in .env.local"
              />
            )}
          </Card>

          <Card title="cycle health">
            <div className="space-y-1">
              <KeyRow
                k="daily pnl"
                v={
                  <span
                    className={
                      status.dailyPnlUsdc > 0
                        ? "text-accent"
                        : status.dailyPnlUsdc < 0
                          ? "text-bad"
                          : "text-ink"
                    }
                  >
                    {status.dailyPnlUsdc > 0 ? "+" : ""}
                    {fmtUsd(status.dailyPnlUsdc, 2)}
                  </span>
                }
              />
              <KeyRow k="open orders" v={status.openOrders} />
              <KeyRow k="active markets" v={status.activeMarkets} />
              <KeyRow
                k="last trade"
                v={
                  status.lastTradeAt
                    ? timeAgo(status.lastTradeAt)
                    : "no trades yet"
                }
              />
              <KeyRow
                k="signals · 30m"
                v={
                  <span>
                    {signals.length}{" "}
                    <span className="text-subtle">
                      ({placedCount} placed · {blockedCount} blocked)
                    </span>
                  </span>
                }
              />
            </div>
          </Card>
        </div>

        {/* MIDDLE — active signals */}
        <Card
          className="lg:col-span-1"
          padded={false}
          title="active signals · last 30 minutes"
          action={
            <span>
              {signals.length} candidate{signals.length === 1 ? "" : "s"}
            </span>
          }
        >
          <ActiveSignalsTable signals={signals} />
        </Card>

        {/* RIGHT — activity feed */}
        <Card
          className="lg:col-span-1"
          padded={false}
          title="activity"
          action={
            <span>
              {status.recent.length === 0
                ? "no log entries"
                : `${status.recent.length} log entries`}
            </span>
          }
        >
          <ActivityFeed records={status.recent} />
        </Card>
      </div>
    </div>
  );
}
