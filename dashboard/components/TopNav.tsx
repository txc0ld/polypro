import Link from "next/link";
import type { IncidentState } from "@/lib/log";

const TABS = [
  { href: "/", label: "Live Desk" },
  { href: "/scanner", label: "Scanner" },
  { href: "/probability", label: "Probability" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/trades", label: "Trade Court" },
];

const STATE_COLORS: Record<IncidentState, string> = {
  HEALTHY: "bg-accent text-bg",
  DEGRADED: "bg-warn text-bg",
  LOCKDOWN: "bg-bad text-bg",
  KILLED: "bg-bad text-ink",
};

export function TopNav({ state }: { state: IncidentState }) {
  return (
    <nav className="flex items-center justify-between border-b border-border bg-panel px-6 py-3">
      <div className="flex items-center gap-6">
        <span className="text-base font-bold tracking-wider text-accent">
          POLYFLOW
        </span>
        <ul className="flex gap-4 text-sm">
          {TABS.map((tab) => (
            <li key={tab.href}>
              <Link
                href={tab.href}
                className="text-muted transition hover:text-ink"
              >
                {tab.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex items-center gap-3 text-xs">
        <span className="text-muted">runtime state</span>
        <span
          className={`rounded px-2 py-1 font-bold ${STATE_COLORS[state]}`}
        >
          {state}
        </span>
      </div>
    </nav>
  );
}
