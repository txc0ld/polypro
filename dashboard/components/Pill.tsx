import type { ReactNode } from "react";

export type PillTone =
  | "neutral"
  | "good"
  | "warn"
  | "bad"
  | "info"
  | "muted";

const TONE: Record<PillTone, string> = {
  neutral: "border-border bg-white/5 text-ink",
  good: "border-accent/40 bg-accent/10 text-accent",
  warn: "border-warn/40 bg-warn/10 text-warn",
  bad: "border-bad/40 bg-bad/10 text-bad",
  info: "border-sky/40 bg-sky/10 text-sky",
  muted: "border-border bg-transparent text-subtle",
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
          className={`h-1.5 w-1.5 rounded-full ${
            tone === "good"
              ? "bg-accent"
              : tone === "warn"
                ? "bg-warn"
                : tone === "bad"
                  ? "bg-bad"
                  : tone === "info"
                    ? "bg-sky"
                    : "bg-subtle"
          } ${pulse ? "animate-pulse-soft" : ""}`}
        />
      ) : null}
      {children}
    </span>
  );
}
