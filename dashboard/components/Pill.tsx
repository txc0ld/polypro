import type { ReactNode } from "react";

export type PillTone =
  | "neutral"
  | "good"
  | "warn"
  | "bad"
  | "info"
  | "accent"
  | "muted";

const TONE: Record<PillTone, string> = {
  neutral: "border-border bg-panel text-muted",
  good: "border-good/40 bg-good/[0.08] text-good",
  warn: "border-warn/40 bg-warn/[0.08] text-warn",
  bad: "border-bad/40 bg-bad/[0.08] text-bad",
  info: "border-sky/40 bg-sky/[0.08] text-sky",
  accent: "border-accent/40 bg-accent/[0.08] text-accent-soft",
  muted: "border-border bg-transparent text-subtle",
};

const DOT: Record<PillTone, string> = {
  neutral: "bg-muted",
  good: "bg-good",
  warn: "bg-warn",
  bad: "bg-bad",
  info: "bg-sky",
  accent: "bg-accent",
  muted: "bg-subtle",
};

export function Pill({
  children,
  tone = "neutral",
  dot = false,
  pulse = false,
  className = "",
}: {
  children: ReactNode;
  tone?: PillTone;
  dot?: boolean;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${TONE[tone]} ${className}`}
    >
      {dot ? (
        <span
          className={`h-1.5 w-1.5 rounded-full ${DOT[tone]} ${pulse ? "animate-pulse-soft" : ""}`}
        />
      ) : null}
      {children}
    </span>
  );
}
