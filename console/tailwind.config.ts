import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "media",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        card: "var(--card)",
        "card-muted": "var(--card-muted)",
        frame: "var(--frame)",
        column: "var(--column)",
        foreground: "var(--text-foreground)",
        muted: "var(--text-muted)",
        border: "var(--border)"
      },
      fontFamily: {
        sans: ["Inter", "SF Pro Text", "Helvetica Neue", "Arial", "sans-serif"],
        display: ["Inter", "SF Pro Text", "Helvetica Neue", "Arial", "sans-serif"]
      },
      boxShadow: {
        card: "0 10px 40px -18px rgba(0, 0, 0, 0.2)"
      }
    }
  },
  plugins: []
};

export default config;
