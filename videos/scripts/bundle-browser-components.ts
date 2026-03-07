#!/usr/bin/env tsx

import * as esbuild from "esbuild";
import { resolve } from "path";
import { globalsPlugin } from "./esbuild-globals-plugin";

async function bundle() {
  const watchMode = process.argv.includes("--watch");
  console.error("Bundling browser components...");
  const buildOptions: esbuild.BuildOptions = {
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
      ".css": "text",
    },
    minify: false,
    sourcemap: true,
  };

  if (watchMode) {
    const ctx = await esbuild.context(buildOptions);
    await ctx.watch();
    console.error("Bundle watch active at videos/public/browser-components.js");
    return;
  }

  await esbuild.build(buildOptions);
  console.error("Bundle created at public/browser-components.js");
}

bundle().catch((error) => {
  console.error("Bundle failed:", error);
  process.exit(1);
});
