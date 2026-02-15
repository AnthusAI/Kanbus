import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const vitePort = Number(process.env.VITE_PORT ?? "5173");
const consolePort = Number(process.env.CONSOLE_PORT ?? "5174");

export default defineConfig({
  plugins: [react()],
  server: {
    port: vitePort,
    watch: {
      ignored: [
        "**/project/issues/**"
      ]
    },
    proxy: {
      "^/[^/]+/[^/]+/api": {
        target: `http://localhost:${consolePort}`,
        changeOrigin: true
      }
    }
  }
});
