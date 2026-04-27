import type { ReactNode } from "react";
import { fmtTime, timeAgo } from "@/lib/format";

export type TimelineStep = {
  ts: string | null;
  actor: string;
  action: string;
  status?: "ok" | "warn" | "bad" | "skip" | "pending";
  payload?: ReactNode;
  ref?: string | null;
};

const STATUS_DOT: Record<NonNullable<TimelineStep["status"]>, string> = {
  ok: "bg-accent",
  warn: "bg-warn",
  bad: "bg-bad",
  skip: "bg-subtle",
  pending: "bg-border",
};

export function Timeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <ol className="relative space-y-3 border-l border-hairline pl-6">
      {steps.map((step, idx) => {
        const dot = STATUS_DOT[step.status ?? "pending"];
        return (
          <li key={`${step.actor}-${step.action}-${idx}`} className="relative">
            <span
              className={`absolute -left-[27px] top-1.5 h-2 w-2 rounded-full ${dot} ring-2 ring-bg`}
            />
            <div className="rounded border border-hairline bg-surface p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex items-baseline gap-2">
                  <span className="text-[11px] font-medium text-ink">
                    {step.actor}
                  </span>
                  <span className="text-[11px] text-muted">{step.action}</span>
                  {step.ref ? (
                    <span className="font-mono text-[10px] text-subtle">
                      {step.ref}
                    </span>
                  ) : null}
                </div>
                <div className="text-[10px] text-subtle">
                  {step.ts ? (
                    <span title={fmtTime(step.ts)}>{timeAgo(step.ts)}</span>
                  ) : (
                    "pending"
                  )}
                </div>
              </div>
              {step.payload ? (
                <div className="mt-2 text-xs text-muted">{step.payload}</div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
