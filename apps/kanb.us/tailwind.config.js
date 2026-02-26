module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
    "../../packages/ui/dist/**/*.{js,jsx,ts,tsx}"
  ],
  darkMode: 'class',
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
        border: "var(--border)",
        "slate-1": "var(--slate-1)",
        "slate-2": "var(--slate-2)",
        "slate-3": "var(--slate-3)",
        "slate-4": "var(--slate-4)",
        "slate-5": "var(--slate-5)",
        "slate-6": "var(--slate-6)",
        "slate-7": "var(--slate-7)",
        "slate-8": "var(--slate-8)",
        "slate-9": "var(--slate-9)",
        "slate-10": "var(--slate-10)",
        "slate-11": "var(--slate-11)",
        "slate-12": "var(--slate-12)",
        "slate-a1": "var(--slate-a1)",
        "slate-a2": "var(--slate-a2)",
        "slate-a3": "var(--slate-a3)",
        "slate-a4": "var(--slate-a4)",
        "slate-a5": "var(--slate-a5)",
        "slate-a6": "var(--slate-a6)",
        "slate-a7": "var(--slate-a7)",
        "slate-a8": "var(--slate-a8)",
        "slate-a9": "var(--slate-a9)",
        "slate-a10": "var(--slate-a10)",
        "slate-a11": "var(--slate-a11)",
        "slate-a12": "var(--slate-a12)",
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
