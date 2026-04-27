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
        // Deep black base with subtle violet tint
        bg: "#050007",
        surface: "#0a0512",
        panel: "#0f0820",
        border: "#2a1855",
        hairline: "#1a0f33",
        ink: "#f4f0ff",
        muted: "#a89cc9",
        subtle: "#7a6f9c",
        // Electric violet primary accent
        accent: "#a855f7",
        "accent-bright": "#d946ef",
        "accent-glow": "#c084fc",
        warn: "#fbbf24",
        bad: "#f87171",
        good: "#4ade80",
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
        caption: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.08em" }],
        display: ["2rem", { lineHeight: "2.25rem", letterSpacing: "-0.02em" }],
      },
      borderRadius: {
        DEFAULT: "6px",
        md: "8px",
        lg: "10px",
      },
      backgroundImage: {
        "grid-purple":
          "radial-gradient(circle at 1px 1px, rgba(168, 85, 247, 0.07) 1px, transparent 0)",
        "gradient-violet":
          "linear-gradient(135deg, #a855f7 0%, #d946ef 50%, #ec4899 100%)",
        "gradient-violet-soft":
          "linear-gradient(135deg, rgba(168, 85, 247, 0.18) 0%, rgba(217, 70, 239, 0.08) 100%)",
        "gradient-glow":
          "radial-gradient(circle at 50% 0%, rgba(168, 85, 247, 0.18) 0%, transparent 70%)",
      },
      boxShadow: {
        glow: "0 0 22px rgba(168, 85, 247, 0.28), 0 0 40px rgba(168, 85, 247, 0.1)",
        "glow-strong":
          "0 0 32px rgba(168, 85, 247, 0.5), 0 0 60px rgba(217, 70, 239, 0.22)",
        "glow-good": "0 0 16px rgba(74, 222, 128, 0.3)",
        "glow-bad": "0 0 16px rgba(248, 113, 113, 0.3)",
        panel:
          "0 1px 2px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(168, 85, 247, 0.07) inset",
      },
      animation: {
        "pulse-soft": "pulse-soft 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "pulse-glow": "pulse-glow 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fade-in 220ms ease-out",
        "slide-up": "slide-up 280ms cubic-bezier(0.16, 1, 0.3, 1)",
        shimmer: "shimmer 3s linear infinite",
      },
      keyframes: {
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
        "pulse-glow": {
          "0%, 100%": {
            boxShadow:
              "0 0 18px rgba(168, 85, 247, 0.35), 0 0 38px rgba(168, 85, 247, 0.12)",
          },
          "50%": {
            boxShadow:
              "0 0 28px rgba(168, 85, 247, 0.55), 0 0 56px rgba(217, 70, 239, 0.22)",
          },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(2px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
