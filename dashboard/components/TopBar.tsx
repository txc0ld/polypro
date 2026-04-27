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
    <header className="sticky top-0 z-40 border-b border-border bg-bg/85 backdrop-blur-xl">
      {/* Row 1 — brand, nav, runtime status pills */}
      <div className="flex items-center justify-between gap-6 px-6 py-3.5">
        <div className="flex items-center gap-8">
          <Link
            href="/"
            className="group flex items-center gap-2.5"
          >
            {/* Logo glyph */}
            <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-md bg-gradient-violet text-[10px] font-bold tracking-tight text-bg shadow-glow transition-transform group-hover:scale-105">
              <span className="relative z-10">PF</span>
              <span className="absolute inset-0 rounded-md bg-gradient-violet opacity-50 blur-md" />
            </span>
            <span className="text-[13px] font-semibold tracking-[0.22em] gradient-text">
              POLYFLOW
            </span>
          </Link>
          <nav className="flex items-center gap-0.5 text-xs">
            {TABS.map((t) => (
              <Link
                key={t.href}
                href={t.href}
                className="rounded px-3 py-1.5 font-medium text-muted transition-colors hover:bg-accent/10 hover:text-accent-glow"
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

      {/* Shimmering accent line */}
      <div className="h-px shimmer-bar" />

      {/* Row 2 — at-a-glance numerics */}
      <div className="grid grid-cols-2 gap-px border-t border-hairline bg-border/40 md:grid-cols-5">
        <Tile
          label="wallet"
          value={
            wallet ? fmtUsd(wallet.totalUsd, 2) : status.walletAddress ? "—" : "no funder"
          }
          hint={shortAddr(status.walletAddress)}
          highlight
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
                  ? "text-good"
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
  highlight = false,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={
        highlight
          ? "relative bg-bg px-5 py-3.5 transition-colors hover:bg-accent/[0.04]"
          : "bg-bg px-5 py-3.5 transition-colors hover:bg-accent/[0.04]"
      }
    >
      {highlight ? (
        <span className="absolute inset-y-0 left-0 w-px bg-gradient-violet" />
      ) : null}
      <div className="text-caption uppercase tracking-wider text-subtle">
        {label}
      </div>
      <div
        className={
          highlight
            ? "tabular mt-1 text-lg font-semibold gradient-text"
            : "tabular mt-1 text-base font-medium text-ink"
        }
      >
        {value}
      </div>
      {hint ? (
        <div className="mt-0.5 text-[11px] text-subtle">{hint}</div>
      ) : null}
    </div>
  );
}
