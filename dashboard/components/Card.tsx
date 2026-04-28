import { ReactNode } from "react";

export function Card({
  title,
  action,
  children,
  className = "",
  padded = true,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section
      className={`overflow-hidden rounded-md border border-border bg-surface ${className}`}
    >
      {title || action ? (
        <header className="flex items-center justify-between border-b border-border px-4 py-2.5">
          {title ? (
            <h2 className="text-caption uppercase tracking-wider text-subtle">
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
            ? "text-accent"
            : "text-ink";
  return (
    <div className="flex flex-col gap-1">
      <span className="text-caption uppercase tracking-wider text-subtle">
        {label}
      </span>
      <span className={`tabular text-xl font-medium ${toneClass}`}>{value}</span>
      {hint ? <span className="text-[11px] text-subtle">{hint}</span> : null}
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
    <div className="flex items-baseline justify-between gap-3 py-1">
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
    <div className="flex flex-col items-start gap-1 py-6 text-xs">
      <span className="uppercase tracking-wider text-subtle">{title}</span>
      {hint ? <span className="text-faint">{hint}</span> : null}
    </div>
  );
}
