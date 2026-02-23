const { execSync } = require("node:child_process");
const { existsSync, readdirSync } = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const outDir = path.join(repoRoot, "videos", "out");

const bucket = process.env.VIDEOS_BUCKET;
const prefix = process.env.VIDEOS_PREFIX;
const cacheControl = process.env.VIDEOS_CACHE_CONTROL || "public,max-age=300";
const dryRun = process.argv.includes("--dry-run") ? "--dryrun" : "";

if (!bucket || !prefix) {
  throw new Error(
    "Missing required environment variables. Set VIDEOS_BUCKET and VIDEOS_PREFIX."
  );
}

const listAssets = (dir) => {
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((file) => file.toLowerCase().endsWith(".mp4") || file.toLowerCase().endsWith(".jpg"))
    .map((file) => path.join(dir, file));
};

const assets = listAssets(outDir);
if (assets.length === 0) {
  throw new Error(`No .mp4 or .jpg files found in ${outDir}`);
}

const destination = `s3://${bucket}/${prefix.replace(/\/$/, "")}/`;

console.log(`Uploading ${assets.length} asset(s) from ${outDir} -> ${destination}`);

execSync(
  [
    "aws s3 sync",
    `"${outDir}"`,
    `"${destination}"`,
    "--exclude \"*\"",
    "--include \"*.mp4\"",
    "--include \"*.jpg\"",
    `--cache-control \"${cacheControl}\"`,
    dryRun
  ]
    .filter(Boolean)
    .join(" "),
  { stdio: "inherit" }
);

console.log("Done.");
