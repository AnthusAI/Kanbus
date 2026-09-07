import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolvePortOrExit } from "./scripts/resolvePort";

const vitePort = Number(process.env.VITE_PORT ?? "5173");
const consolePort = Number(process.env.CONSOLE_PORT ?? "5174");
// Bind broadly by default; can override with VITE_HOST
const viteHost = process.env.VITE_HOST ?? "0.0.0.0";

function consoleApiProxy() {
  return {
    target: `http://localhost:${consolePort}`,
    changeOrigin: true,
    timeout: 0,
    proxyTimeout: 0,
    configure: (proxy) => {
      proxy.on("proxyRes", (proxyRes, req) => {
        const url = req.url ?? "";
        if (!url.includes("/events")) {
          return;
        }
        proxyRes.headers["cache-control"] = "no-cache, no-transform";
        proxyRes.headers["x-accel-buffering"] = "no";
        delete proxyRes.headers["content-length"];
      });
    }
  };
}

export default defineConfig(async () => {
  const port = await resolvePortOrExit({
    desiredPort: vitePort,
    serviceName: "Vite dev server",
    envVariable: "VITE_PORT"
  });

  return {
    // Root-absolute asset URLs keep JS/CSS loading from /assets/ on deep-link reloads.
    base: process.env.VITE_ASSET_BASE ?? "/",
    plugins: [react()],
    server: {
      host: viteHost,
      port,
      allowedHosts: true,
      watch: {
        ignored: ["**/project/issues/**"]
      },
      proxy: {
        "/api": consoleApiProxy(),
        "^/[^/]+/[^/]+/api": consoleApiProxy()
      }
    }
  };
});
