#!/usr/bin/env node

const { spawn } = require("node:child_process");
const { existsSync } = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const videosDir = path.join(repoRoot, "videos");
const homeDir = process.env.HOME || "";

const resolveFirstExisting = (candidates) => {
  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) {
      return candidate;
    }
  }
  return "";
};

const resolvedVideomlCli = process.env.VIDEOML_CLI || resolveFirstExisting([
  path.resolve(repoRoot, "..", "VideoML", "cli", "bin", "vml.js"),
  path.resolve(homeDir, "Projects", "VideoML", "cli", "bin", "vml.js"),
]);

const resolvedBabulusBundle = process.env.BABULUS_BUNDLE || resolveFirstExisting([
  path.resolve(repoRoot, "..", "Babulus", "public", "babulus-standard.js"),
  path.resolve(homeDir, "Projects", "Babulus", "public", "babulus-standard.js"),
]);

if (!resolvedVideomlCli) {
  console.error("INTRO_PREVIEW_WATCH_FAILED missing_VIDEOML_CLI export VIDEOML_CLI=/path/to/VideoML/cli/bin/vml.js");
  process.exit(1);
}
process.env.VIDEOML_CLI = resolvedVideomlCli;

if (resolvedBabulusBundle) {
  process.env.BABULUS_BUNDLE = resolvedBabulusBundle;
}

const children = [];
let shuttingDown = false;

const spawnProc = (name, cmd, args, cwd) => {
  const child = spawn(cmd, args, {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
    env: process.env,
  });

  child.stdout.on("data", (chunk) => {
    process.stdout.write(`[${name}] ${chunk}`);
  });
  child.stderr.on("data", (chunk) => {
    process.stderr.write(`[${name}] ${chunk}`);
  });

  child.on("exit", (code, signal) => {
    if (shuttingDown) return;
    if (code === 0 || signal === "SIGTERM" || signal === "SIGINT") return;
    console.error(`INTRO_PREVIEW_WATCH_FAILED process=${name} code=${code ?? "null"} signal=${signal ?? "null"}`);
    shutdown(1);
  });

  children.push(child);
};

const shutdown = (code = 0) => {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) {
      child.kill("SIGTERM");
    }
  }
  setTimeout(() => {
    for (const child of children) {
      if (!child.killed) child.kill("SIGKILL");
    }
    process.exit(code);
  }, 500);
};

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

spawnProc("bundle", "npm", ["run", "bundle:components:watch"], videosDir);
spawnProc("generate", "npm", ["run", "vml:watch:intro"], videosDir);
spawnProc("sync", "node", ["scripts/sync-vml-preview-assets.js", "--intro", "--watch"], repoRoot);

console.log("INTRO_PREVIEW_WATCH_READY");
