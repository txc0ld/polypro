/**
 * Strategy badge palette. The dashboard surfaces every strategy in the
 * runtime by name; the operator-facing PRD assigns a stable colour to each
 * one so badges, sparklines, and filter chips read consistently across
 * pages. Keep this map in sync with src/polyflow/types.py::Strategy.
 */

export type StrategyKey =
  | "external_odds_divergence"
  | "news_repricing"
  | "btc_threshold"
  | "crypto_momentum"
  | "four_layer_alignment"
  | "intra_market_arbitrage"
  | "near_expiry_certainty"
  | "passive_fair_value_quoting"
  | "new_market_opening"
  | "spread_capture"
  | "negative_risk_basket"
  | string;

type Palette = {
  /** Solid hex for sparklines, dots, charts. */
  solid: string;
  /** Tailwind class fragment for border. */
  border: string;
  /** Tailwind class fragment for text. */
  text: string;
  /** Tailwind class fragment for tinted background (10% alpha-ish). */
  tint: string;
};

const PALETTES: Record<string, Palette> = {
  external_odds_divergence: {
    solid: "#10b981",
    border: "border-emerald/40",
    text: "text-emerald",
    tint: "bg-emerald/10",
  },
  news_repricing: {
    solid: "#38bdf8",
    border: "border-sky/40",
    text: "text-sky",
    tint: "bg-sky/10",
  },
  btc_threshold: {
    solid: "#f59e0b",
    border: "border-amber/40",
    text: "text-amber",
    tint: "bg-amber/10",
  },
  crypto_momentum: {
    solid: "#f97316",
    border: "border-orange/40",
    text: "text-orange",
    tint: "bg-orange/10",
  },
  four_layer_alignment: {
    solid: "#a78bfa",
    border: "border-violet/40",
    text: "text-violet",
    tint: "bg-violet/10",
  },
  intra_market_arbitrage: {
    solid: "#e879f9",
    border: "border-fuchsia/40",
    text: "text-fuchsia",
    tint: "bg-fuchsia/10",
  },
  near_expiry_certainty: {
    solid: "#fb7185",
    border: "border-rose/40",
    text: "text-rose",
    tint: "bg-rose/10",
  },
};

const FALLBACK: Palette = {
  solid: "#a1a1aa",
  border: "border-border",
  text: "text-muted",
  tint: "bg-white/5",
};

export function strategyPalette(key: StrategyKey | null | undefined): Palette {
  if (!key) return FALLBACK;
  return PALETTES[key] ?? FALLBACK;
}

export function strategyLabel(key: StrategyKey | null | undefined): string {
  if (!key) return "—";
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
