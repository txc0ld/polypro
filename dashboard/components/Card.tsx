import { ReactNode } from "react";

export function Card({
  title,
  action,
  children,
  className = "",
  padded = true,
  glow = false,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
  glow?: boolean;
}) {
  return (
    <section
      className={`relative overflow-hidden rounded-lg border border-border/70 bg-panel/70 backdrop-blur-sm ${
        glow ? "card-glow-strong" : "card-glow"
      } ${className}`}
    >
      {/* top accent gradient line */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent"
      />
      {title || action ? (
        <header className="flex items-center justify-between border-b border-hairline px-4 py-3">
          {title ? (
            <h2 className="text-caption uppercase tracking-wider text-muted">
              {title}
            </h2>
          ) : (
            <span />
          )}
          {action ? <div className="text-xs text-subtle">{action}</div> : null}
        </header>
      ) : null}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "good" | "warn" | "bad" | "accent";
}) {
  const toneClass =
    tone === "good"
      ? "text-good"
      : tone === "warn"
        ? "text-warn"
        : tone === "bad"
          ? "text-bad"
          : tone === "accent"
            ? "gradient-text"
            : "text-ink";
  return (
    <div className="flex flex-col gap-1">
      <span className="text-caption uppercase tracking-wider text-subtle">
        {label}
      </span>
      <span className={`tabular text-2xl font-semibold ${toneClass}`}>
        {value}
      </span>
      {hint ? <span className="text-xs text-muted">{hint}</span> : null}
    </div>
  );
}

export function KeyRow({
  k,
  v,
  mono = false,
}: {
  k: ReactNode;
  v: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-hairline py-1.5 last:border-0">
      <span className="text-xs text-subtle">{k}</span>
      <span className={`text-xs ${mono ? "font-mono text-muted" : "text-ink"}`}>
        {v}
      </span>
    </div>
  );
}

export function EmptyState({
  title = "no data yet",
  hint,
}: {
  title?: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-start gap-1 py-6 text-xs text-subtle">
      <span className="uppercase tracking-wider">{title}</span>
      {hint ? <span className="text-muted">{hint}</span> : null}
    </div>
  );
}
