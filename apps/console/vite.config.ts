import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolvePortOrExit } from "./scripts/resolvePort";

const vitePort = Number(process.env.VITE_PORT ?? "5173");
const consolePort = Number(process.env.CONSOLE_PORT ?? "5174");
const viteHost = process.env.VITE_HOST ?? "127.0.0.1";

export default defineConfig(async () => {
  const port = await resolvePortOrExit({
    desiredPort: vitePort,
    serviceName: "Vite dev server",
    envVariable: "VITE_PORT"
  });

  return {
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
