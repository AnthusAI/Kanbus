const defaultTheme = require("tailwindcss/defaultTheme");

module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Inter'", ...defaultTheme.fontFamily.sans],
        mono: ["'JetBrains Mono'", ...defaultTheme.fontFamily.mono]
      },
      colors: {
        taskulus: {
          primary: "#2563eb",
          accent: "#0ea5e9",
          surface: "#0b1024"
        }
      }
    }
  },
  plugins: []
};
