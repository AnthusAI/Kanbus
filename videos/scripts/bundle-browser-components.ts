#!/usr/bin/env tsx

import * as esbuild from "esbuild";
import { resolve } from "path";
import { globalsPlugin } from "./esbuild-globals-plugin";

async function bundle() {
  console.error("Bundling browser components...");

  await esbuild.build({
    entryPoints: [resolve(__dirname, "browser-components.tsx")],
    bundle: true,
    format: "iife",
    globalName: "BabulusComponents",
    outfile: resolve(__dirname, "../public/browser-components.js"),
    platform: "browser",
    jsx: "automatic",
    plugins: [globalsPlugin],
    absWorkingDir: resolve(__dirname, ".."),
    loader: {
      ".tsx": "tsx",
      ".ts": "ts",
      ".jsx": "jsx",
      ".js": "js",
      ".png": "dataurl",
      ".jpg": "dataurl",
      ".jpeg": "dataurl",
      ".gif": "dataurl",
      ".svg": "dataurl",
      ".css": "text"
    },
    minify: false,
    sourcemap: true
  });

  console.error("Bundle created at public/browser-components.js");
}

bundle().catch((error) => {
  console.error("Bundle failed:", error);
  process.exit(1);
});
