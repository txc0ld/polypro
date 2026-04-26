import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#0b0d10",
        panel: "#11151b",
        edge: "#1d242d",
        muted: "#7d8794",
        good: "#3ddc97",
        warn: "#f5b14a",
        bad: "#ff6b6b",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
