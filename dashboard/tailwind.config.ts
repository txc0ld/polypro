import type { Config } from "tailwindcss";

/**
 * Minimalist palette — Linear/Vercel/Stripe inspired.
 *
 * One accent (violet), neutral zinc surfaces, semantic green/amber/red.
 * No gradients, no glow, no rounded-larger-than-8px. Numbers are tabular,
 * IDs are mono, everything else is sans.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#09090b", // zinc-950
        surface: "#0c0c0f",
        panel: "#101014",
        border: "#1f1f23", // zinc-800
        hairline: "#161619",
        ink: "#fafafa", // zinc-50
        muted: "#a1a1aa", // zinc-400
        subtle: "#71717a", // zinc-500
        faint: "#52525b", // zinc-600
        accent: "#8b5cf6", // violet-500
        "accent-soft": "#a78bfa", // violet-400
        warn: "#f59e0b",
        bad: "#ef4444",
        good: "#10b981",
        emerald: "#10b981",
        sky: "#38bdf8",
        amber: "#f59e0b",
        orange: "#f97316",
        violet: "#a78bfa",
        fuchsia: "#e879f9",
        rose: "#fb7185",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        caption: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.06em" }],
        display: ["1.5rem", { lineHeight: "1.875rem", letterSpacing: "-0.015em" }],
        hero: ["2rem", { lineHeight: "2.25rem", letterSpacing: "-0.02em" }],
      },
      borderRadius: {
        none: "0",
        sm: "4px",
        DEFAULT: "6px",
        md: "6px",
        lg: "8px",
      },
      animation: {
        "pulse-soft": "pulse-soft 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fade-in 200ms ease-out",
      },
      keyframes: {
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
