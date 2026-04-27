import { strategyLabel, strategyPalette, type StrategyKey } from "@/lib/strategy";

export function StrategyBadge({
  strategy,
  size = "md",
}: {
  strategy: StrategyKey | null | undefined;
  size?: "sm" | "md";
}) {
  const palette = strategyPalette(strategy);
  const sz =
    size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-[11px] px-2 py-0.5";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border ${palette.border} ${palette.tint} ${palette.text} ${sz} font-medium`}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: palette.solid }}
      />
      {strategyLabel(strategy)}
    </span>
  );
}
