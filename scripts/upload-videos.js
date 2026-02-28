const { execSync } = require("node:child_process");
const { existsSync, readdirSync } = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const outDir = path.join(repoRoot, "videos", "out");

// Parse arguments
let awsProfile = process.env.AWS_PROFILE || "anthus";
let bucket = process.env.VIDEOS_BUCKET;
const prefix = process.env.VIDEOS_PREFIX || "kanbus-feature-videos";
const cacheControl = process.env.VIDEOS_CACHE_CONTROL || "public,max-age=300";
let dryRun = "";

for (const arg of process.argv.slice(2)) {
  if (arg.startsWith("--profile=")) {
    awsProfile = arg.split("=")[1];
  } else if (arg === "--profile" && process.argv.indexOf(arg) + 1 < process.argv.length) {
    awsProfile = process.argv[process.argv.indexOf(arg) + 1];
  } else if (arg === "--dry-run") {
    dryRun = "--dryrun";
  }
}

// Helper to list assets
const listAssets = (dir) => {
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((file) => file.toLowerCase().endsWith(".mp4") || file.toLowerCase().endsWith(".jpg"))
    .map((file) => path.join(dir, file));
};

// Validate videos directory
const assets = listAssets(outDir);
if (assets.length === 0) {
  console.error(`Error: No .mp4 or .jpg files found in ${outDir}`);
  console.error("Run 'node scripts/render-videos.js' first to generate videos.");
  process.exit(1);
}

console.log("Kanbus Video Upload");
console.log("===================");
console.log("");
console.log(`Videos to upload: ${assets.length} files`);
console.log(`AWS Profile: ${awsProfile}`);
console.log(`S3 Prefix: ${prefix}`);
console.log("");

// Verify AWS credentials
try {
  execSync(`aws sts get-caller-identity --profile ${awsProfile}`, { stdio: "pipe" });
} catch (error) {
  console.error(`Error: Cannot authenticate with AWS profile '${awsProfile}'`);
  console.error("Check your AWS configuration and try again.");
  process.exit(1);
}

// Auto-discover bucket if not specified
if (!bucket) {
  console.log("Searching for Amplify videos bucket...");
  try {
    const bucketsOutput = execSync(`aws s3 ls --profile ${awsProfile} | grep -i video`, { encoding: "utf8" });
    const buckets = bucketsOutput
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => line.split(/\s+/).pop())
      .filter(Boolean);
    
    if (buckets.length === 0) {
      console.error("Error: No Amplify videos buckets found");
      console.error("Tip: Set VIDEOS_BUCKET environment variable to specify a bucket explicitly");
      process.exit(1);
    }
    
    bucket = buckets[0];
    console.log(`Found bucket: ${bucket}`);
  } catch (error) {
    console.error("Error: Could not find Amplify videos bucket");
    console.error("Tip: Set VIDEOS_BUCKET environment variable to specify a bucket explicitly");
    process.exit(1);
  }
}

console.log("");

const destination = `s3://${bucket}/${prefix.replace(/\/$/, "")}/`;

if (dryRun) {
  console.log("DRY RUN: Showing what would be uploaded");
  console.log("");
}

console.log(`Uploading to: ${destination}`);
console.log("");

const cmd = [
  "aws s3 sync",
  `"${outDir}"`,
  `"${destination}"`,
  `--profile ${awsProfile}`,
  "--exclude \"*\"",
  "--include \"*.mp4\"",
  "--include \"*.jpg\"",
  `--cache-control \"${cacheControl}\"`,
  dryRun
]
  .filter(Boolean)
  .join(" ");

execSync(cmd, { stdio: "inherit" });

console.log("");
console.log("Upload complete!");
console.log("");
console.log("Next steps:");
console.log("1. Set environment variable for local preview:");
console.log(`   export GATSBY_VIDEOS_BASE_URL=https://${bucket}.s3.amazonaws.com/${prefix}`);
console.log("");
console.log("2. Or use the Amplify distribution URL if available:");
console.log(`   export GATSBY_VIDEOS_BASE_URL=https://d1234.cloudfront.net/${prefix}`);
console.log("");
console.log("3. Run the web app:");
console.log("   cd apps/kanb.us && npm run develop");
