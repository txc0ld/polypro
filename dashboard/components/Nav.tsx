import Link from "next/link";
import { readSystemState, type SystemState } from "@/lib/state";

const links = [
  { href: "/", label: "Live Desk" },
  { href: "/scanner", label: "Scanner" },
  { href: "/portfolio", label: "Portfolio" },
];

const stateColor: Record<SystemState, string> = {
  HEALTHY: "bg-good/20 text-good border-good/40",
  DEGRADED: "bg-warn/20 text-warn border-warn/40",
  LOCKDOWN: "bg-bad/20 text-bad border-bad/40",
  KILLED: "bg-bad/30 text-bad border-bad/60",
  UNKNOWN: "bg-muted/20 text-muted border-muted/40",
};

export default async function Nav() {
  const { state } = await readSystemState();
  return (
    <nav className="border-b border-edge bg-panel">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        <div className="flex items-center gap-6">
          <Link href="/" className="font-mono text-sm font-semibold tracking-tight">
            POLYFLOW
          </Link>
          <ul className="flex items-center gap-4 text-sm">
            {links.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className="text-muted transition hover:text-white">
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <span className={`pill border ${stateColor[state]}`}>{state}</span>
      </div>
    </nav>
  );
}
