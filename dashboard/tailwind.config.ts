import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#000000",
        surface: "#0a0a0b",
        panel: "#0e0e10",
        border: "#1f1f23",
        hairline: "#141417",
        ink: "#f4f4f5",
        muted: "#a1a1aa",
        subtle: "#71717a",
        accent: "#6ee7b7",
        warn: "#f59e0b",
        bad: "#f87171",
        // strategy palette — keep in sync with lib/strategy.ts
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
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        // Display + body + caption hierarchy
        caption: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.05em" }],
        display: ["1.875rem", { lineHeight: "2.25rem", letterSpacing: "-0.01em" }],
      },
      borderRadius: {
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
          "50%": { opacity: "0.55" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(2px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
