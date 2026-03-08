import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolvePortOrExit } from "./scripts/resolvePort";

const vitePort = Number(process.env.VITE_PORT ?? "5173");
const consolePort = Number(process.env.CONSOLE_PORT ?? "5174");
// Bind broadly by default; can override with VITE_HOST
const viteHost = process.env.VITE_HOST ?? "0.0.0.0";

export default defineConfig(async () => {
  const port = await resolvePortOrExit({
    desiredPort: vitePort,
    serviceName: "Vite dev server",
    envVariable: "VITE_PORT"
  });

  return {
    // Emit relative asset URLs so the embedded console works under staged and tenant-prefixed paths.
    base: process.env.VITE_ASSET_BASE ?? "./",
    plugins: [react()],
    server: {
      host: viteHost,
      port,
      allowedHosts: true,
      watch: {
        ignored: ["**/project/issues/**"]
      },
      proxy: {
        "/api": {
          target: `http://localhost:${consolePort}`,
          changeOrigin: true
        },
        "^/[^/]+/[^/]+/api": {
          target: `http://localhost:${consolePort}`,
          changeOrigin: true
        }
      }
    }
  };
});
