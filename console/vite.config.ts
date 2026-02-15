import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

const vitePort = Number(process.env.VITE_PORT ?? "5173");
const consolePort = Number(process.env.CONSOLE_PORT ?? "5174");

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      {
        find: "@kanbus/ui/styles",
        replacement: path.resolve(__dirname, "../packages/ui/src/styles")
      },
      {
        find: "@kanbus/ui",
        replacement: path.resolve(__dirname, "../packages/ui/src")
      }
    ]
  },
  server: {
    port: vitePort,
    watch: {
      ignored: [
        "**/project/issues/**"
      ]
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
});
