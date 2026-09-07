import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import { resolvePortOrExit } from "./scripts/resolvePort";

const vitePort = Number(process.env.VITE_PORT ?? "5173");
const consolePort = Number(process.env.CONSOLE_PORT ?? "5174");
// Bind broadly by default; can override with VITE_HOST
const viteHost = process.env.VITE_HOST ?? "0.0.0.0";

function writeProxyError(res: { writeHead?: (code: number, headers: Record<string, string>) => void; headersSent?: boolean; end: (body?: string) => void }): void {
  if (res.writeHead && !res.headersSent) {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "api proxy error" }));
  }
}

function jsonApiProxyOptions(): ProxyOptions {
  return {
    target: `http://localhost:${consolePort}`,
    changeOrigin: true,
    timeout: 15000,
    proxyTimeout: 15000,
    configure: (proxy) => {
      proxy.on("error", (_error, _req, res) => {
        writeProxyError(res);
      });
    }
  };
}

function sseProxyOptions(): ProxyOptions {
  return {
    target: `http://localhost:${consolePort}`,
    changeOrigin: true,
    timeout: 0,
    proxyTimeout: 0,
    configure: (proxy) => {
      proxy.on("proxyReq", (proxyReq) => {
        proxyReq.setTimeout(0);
      });
      proxy.on("proxyRes", (proxyRes, _req, res) => {
        res.on("close", () => {
          if (!proxyRes.destroyed) {
            proxyRes.destroy();
          }
        });
      });
      proxy.on("error", (_error, _req, res) => {
        writeProxyError(res);
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
        "/api/events": sseProxyOptions(),
        "/api/telemetry/console/events": sseProxyOptions(),
        "/api": jsonApiProxyOptions(),
        "^/[^/]+/[^/]+/api/events": sseProxyOptions(),
        "^/[^/]+/[^/]+/api/telemetry/console/events": sseProxyOptions(),
        "^/[^/]+/[^/]+/api": jsonApiProxyOptions()
      }
    }
  };
});
