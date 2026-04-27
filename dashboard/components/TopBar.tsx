import Link from "next/link";
import { Pill, type PillTone } from "./Pill";
import { fmtUsd, timeAgo } from "@/lib/format";
import type { RuntimeStatus } from "@/lib/runtime";
import type { IncidentState } from "@/lib/log";

const TABS = [
  { href: "/", label: "Live Desk" },
  { href: "/scanner", label: "Scanner" },
  { href: "/portfolio", label: "Portfolio" },
];

const STATE_TONE: Record<IncidentState, PillTone> = {
  HEALTHY: "good",
  DEGRADED: "warn",
  LOCKDOWN: "bad",
  KILLED: "bad",
};

const MODE_TONE: Record<string, PillTone> = {
  observe: "muted",
  paper: "info",
  live_tiny: "good",
  live_standard: "good",
  lockdown: "bad",
};

function modeTone(mode: string | null): PillTone {
  if (!mode) return "muted";
  return MODE_TONE[mode] ?? "neutral";
}

function pnlTone(v: number): "good" | "bad" | "muted" {
  if (v > 0.005) return "good";
  if (v < -0.005) return "bad";
  return "muted";
}

function shortAddr(addr: string | null): string {
  if (!addr) return "no funder";
  if (addr.length < 12) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export function TopBar({ status }: { status: RuntimeStatus }) {
  const pnl = status.dailyPnlUsdc;
  const tone = pnlTone(pnl);
  const wallet = status.wallet;
  const heartbeatTone: PillTone =
    status.heartbeat.status === "fresh"
      ? "good"
      : status.heartbeat.status === "stale"
        ? "warn"
        : "bad";

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur">
      {/* Row 1 — brand, nav, runtime status pills */}
      <div className="flex items-center justify-between gap-6 px-6 py-3">
        <div className="flex items-center gap-7">
          <Link
            href="/"
            className="text-sm font-semibold tracking-[0.2em] text-ink"
          >
            POLYFLOW
          </Link>
          <nav className="flex items-center gap-1 text-xs">
            {TABS.map((t) => (
              <Link
                key={t.href}
                href={t.href}
                className="rounded px-2.5 py-1 text-muted transition-colors hover:bg-white/5 hover:text-ink"
              >
                {t.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <Pill tone={STATE_TONE[status.incident]} dot pulse={status.incident === "HEALTHY"}>
            {status.incident}
          </Pill>
          <Pill tone={modeTone(status.mode)}>{status.mode ?? "no mode"}</Pill>
          <Pill tone={heartbeatTone} dot pulse={status.heartbeat.status === "fresh"}>
            {status.heartbeat.ts ? timeAgo(status.heartbeat.ts) : "no heartbeat"}
          </Pill>
        </div>
      </div>

      {/* Row 2 — at-a-glance numerics */}
      <div className="grid grid-cols-2 gap-px border-t border-hairline bg-border/40 md:grid-cols-5">
        <Tile
          label="wallet"
          value={
            wallet ? fmtUsd(wallet.totalUsd, 2) : status.walletAddress ? "—" : "no funder"
          }
          hint={shortAddr(status.walletAddress)}
        />
        <Tile
          label="bankroll"
          value={fmtUsd(status.policy.bankrollUsdc, 0)}
          hint="configured"
        />
        <Tile
          label="daily pnl"
          value={
            <span
              className={
                tone === "good"
                  ? "text-accent"
                  : tone === "bad"
                    ? "text-bad"
                    : "text-ink"
              }
            >
              {pnl > 0 ? "+" : ""}
              {fmtUsd(pnl, 2)}
            </span>
          }
          hint="realized · last 24h"
        />
        <Tile
          label="open orders"
          value={status.openOrders}
          hint="from log"
        />
        <Tile
          label="active markets"
          value={status.activeMarkets}
          hint="status = watching"
        />
      </div>
    </header>
  );
}

function Tile({
  label,
  value,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="bg-bg px-5 py-3">
      <div className="text-caption uppercase tracking-wider text-subtle">
        {label}
      </div>
      <div className="tabular mt-0.5 text-base font-medium text-ink">{value}</div>
      {hint ? (
        <div className="mt-0.5 text-[11px] text-subtle">{hint}</div>
      ) : null}
    </div>
  );
}
