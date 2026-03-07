#!/usr/bin/env node

const { copyFileSync, existsSync, mkdirSync, statSync, watch } = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const sourceDir = path.join(repoRoot, "public", "videoml");
const targetDir = path.join(repoRoot, "apps", "kanb.us", "static", "videoml");

const VIDEO_IDS = [
  "intro",
  "core-management",
  "jira-sync",
  "local-tasks",
  "beads-compatibility",
  "virtual-projects",
  "vscode-plugin",
  "policy-as-code",
];

const hasFlag = (flag) => process.argv.includes(flag);
const watchMode = hasFlag("--watch");
const introOnly = hasFlag("--intro");
const allVideos = hasFlag("--all") || !introOnly;

const selectedIds = introOnly ? ["intro"] : (allVideos ? VIDEO_IDS : VIDEO_IDS);

const markerOk = (details) => {
  console.log(`PREVIEW_ASSET_SYNC_OK ${details}`);
};

const markerFailed = (details) => {
  console.error(`PREVIEW_ASSET_SYNC_FAILED ${details}`);
};

const syncOne = (videoId) => {
  const filename = `${videoId}.wav`;
  const src = path.join(sourceDir, filename);
  const dst = path.join(targetDir, filename);

  if (!existsSync(src)) {
    throw new Error(`missing-source ${src}`);
  }

  const srcStats = statSync(src);
  if (srcStats.size < 256) {
    throw new Error(`source-too-small ${src} size=${srcStats.size}`);
  }

  copyFileSync(src, dst);

  const dstStats = statSync(dst);
  if (dstStats.size !== srcStats.size) {
    throw new Error(`size-mismatch ${filename} src=${srcStats.size} dst=${dstStats.size}`);
  }

  // Ensure destination mtime is not older than source. Copy implementations can vary by fs.
  if (dstStats.mtimeMs + 1 < srcStats.mtimeMs) {
    throw new Error(`mtime-regressed ${filename} src=${srcStats.mtimeMs} dst=${dstStats.mtimeMs}`);
  }

  return { videoId, src, dst, bytes: srcStats.size };
};

const syncSelected = () => {
  mkdirSync(targetDir, { recursive: true });

  const results = [];
  for (const videoId of selectedIds) {
    results.push(syncOne(videoId));
  }
  markerOk(`mode=${introOnly ? "intro" : "all"} files=${results.length}`);
  return results;
};

const runWatch = () => {
  try {
    syncSelected();
  } catch (err) {
    markerFailed(String(err && err.message ? err.message : err));
  }

  const watchedSet = new Set(selectedIds.map((id) => `${id}.wav`));
  let debounceTimer = null;

  const scheduleSync = (filename) => {
    if (!filename || !watchedSet.has(filename)) return;
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      try {
        syncSelected();
      } catch (err) {
        markerFailed(String(err && err.message ? err.message : err));
      }
    }, 150);
  };

  const watcher = watch(sourceDir, { persistent: true }, (_eventType, file) => {
    const filename = typeof file === "string" ? file : file?.toString();
    scheduleSync(filename);
  });

  const shutdown = () => {
    watcher.close();
    process.exit(0);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
};

try {
  if (watchMode) {
    runWatch();
  } else {
    syncSelected();
  }
} catch (err) {
  markerFailed(String(err && err.message ? err.message : err));
  process.exit(1);
}
