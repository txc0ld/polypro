import type { ReactNode } from "react";

export type PillTone =
  | "neutral"
  | "good"
  | "warn"
  | "bad"
  | "info"
  | "muted";

const TONE: Record<PillTone, string> = {
  neutral: "border-accent/30 bg-accent/[0.06] text-ink",
  good: "border-good/50 bg-good/10 text-good shadow-glow-good",
  warn: "border-warn/50 bg-warn/10 text-warn",
  bad: "border-bad/50 bg-bad/10 text-bad shadow-glow-bad",
  info: "border-sky/50 bg-sky/10 text-sky",
  muted: "border-border/60 bg-transparent text-subtle",
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
              ? "bg-good"
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
