module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
    "../../packages/ui/dist/**/*.{js,jsx,ts,tsx}"
  ],
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
        selected: "var(--text-selected)",
        border: "var(--border)"
      },
      fontFamily: {
        sans: ["Inter", "SF Pro Text", "Helvetica Neue", "Arial", "sans-serif"],
        display: ["Inter", "SF Pro Text", "Helvetica Neue", "Arial", "sans-serif"]
      },
      boxShadow: {
        card: "0 10px 40px -18px rgba(0, 0, 0, 0.2)"
      }
    },
  },
  plugins: [],
};
