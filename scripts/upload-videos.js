const { execSync } = require("node:child_process");
const { existsSync, readdirSync, readFileSync, statSync } = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const outDir = path.join(repoRoot, "videos", "out");
const amplifyOutputsPath = path.join(repoRoot, "amplify_outputs.json");

// Parse arguments
let awsProfile = process.env.AWS_PROFILE || "anthus";
let bucket = process.env.VIDEOS_BUCKET;
const prefix = process.env.VIDEOS_PREFIX || "videos";
const cacheControl = process.env.VIDEOS_CACHE_CONTROL || "public,max-age=300";
let dryRun = "";
const AUDIO_VALIDATION_PREFIX = "AUDIO_VALIDATION_FAILED";

const loadAmplifyVideoOutputs = () => {
  if (!existsSync(amplifyOutputsPath)) return null;
  try {
    const outputs = JSON.parse(readFileSync(amplifyOutputsPath, "utf8"));
    const bucketName = outputs?.custom?.videosBucketName;
    const cdnUrl = outputs?.custom?.videosCdnUrl;
    if (!bucketName && !cdnUrl) return null;
    return { bucketName, cdnUrl };
  } catch {
    return null;
  }
};

const amplifyVideoOutputs = loadAmplifyVideoOutputs();

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

const probeAudioStreamCount = (assetPath) => {
  const output = execSync(
    `ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 \"${assetPath}\"`,
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }
  ).trim();
  if (!output) return 0;
  return output
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean).length;
};

const probeDurationSec = (assetPath) => {
  const output = execSync(
    `ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 \"${assetPath}\"`,
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }
  ).trim();
  const value = Number((output.split("\n")[0] || "0").trim());
  return Number.isFinite(value) ? Math.max(0, value) : 0;
};

const validateMp4Audio = (assetPath) => {
  const failures = [];
  let bytes = 0;
  let streams = 0;
  let durationSec = 0;
  let activityRatio = 0;

  try {
    bytes = statSync(assetPath).size;
  } catch {
    failures.push("stat-failed");
  }
  if (bytes < 1024) {
    failures.push(`bytes-below-min(${bytes}<1024)`);
  }

  try {
    streams = probeAudioStreamCount(assetPath);
  } catch {
    failures.push("probe-streams-failed");
  }
  if (streams < 1) {
    failures.push("missing-audio-stream");
  }

  try {
    durationSec = probeDurationSec(assetPath);
  } catch {
    failures.push("probe-duration-failed");
  }
  if (durationSec < 0.2) {
    failures.push(`duration-below-min(${durationSec.toFixed(3)}<0.2)`);
  }

  if (streams > 0) {
    try {
      const probeFor = Math.max(0.25, Math.min(6, durationSec || 6));
      const pcm = execSync(
        `ffmpeg -v error -t ${probeFor} -i \"${assetPath}\" -ac 1 -ar 44100 -f s16le pipe:1`,
        { encoding: "buffer", maxBuffer: 50 * 1024 * 1024, stdio: ["ignore", "pipe", "pipe"] }
      );
      if (!pcm || pcm.length < 2) {
        failures.push("waveform-empty");
      } else {
        const total = Math.floor(pcm.length / 2);
        let active = 0;
        for (let i = 0; i < total; i += 1) {
          const sample = pcm.readInt16LE(i * 2);
          if (sample >= 200 || sample <= -200) {
            active += 1;
          }
        }
        activityRatio = total ? active / total : 0;
        if (active === 0) {
          failures.push("all-silence");
        }
        if (activityRatio < 0.001) {
          failures.push(`activity-below-min(${activityRatio.toFixed(4)}<0.001)`);
        }
      }
    } catch {
      failures.push("waveform-check-failed");
    }
  }

  return {
    valid: failures.length === 0,
    failures,
    bytes,
    streams,
    durationSec,
    activityRatio,
  };
};

// Validate videos directory
const assets = listAssets(outDir);
if (assets.length === 0) {
  console.error(`Error: No .mp4 or .jpg files found in ${outDir}`);
  console.error("Run 'node scripts/render-videos.js' first to generate videos.");
  process.exit(1);
}

const mp4Assets = assets.filter((assetPath) => assetPath.toLowerCase().endsWith(".mp4"));
for (const mp4Path of mp4Assets) {
  const validation = validateMp4Audio(mp4Path);
  if (!validation.valid) {
    console.error(
      `${AUDIO_VALIDATION_PREFIX} file=${mp4Path} failures=${validation.failures.join("|")} ` +
      `bytes=${validation.bytes} duration_sec=${validation.durationSec.toFixed(3)} ` +
      `streams=${validation.streams} activity_ratio=${validation.activityRatio.toFixed(4)}`
    );
    console.error(`${AUDIO_VALIDATION_PREFIX} upload_aborted=true`);
    process.exit(1);
  }
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
  if (amplifyVideoOutputs?.bucketName) {
    bucket = amplifyVideoOutputs.bucketName;
    console.log(`Using Amplify outputs bucket: ${bucket}`);
  } else {
    console.log("Searching for Amplify videos bucket...");
    try {
      const bucketsOutput = execSync(`aws s3 ls --profile ${awsProfile} | grep -i videosbucket`, { encoding: "utf8" });
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
      console.warn(`Warning: auto-discovered bucket via list fallback: ${bucket}`);
      console.warn(`Warning: ${amplifyOutputsPath} not found or missing custom.videosBucketName`);
    } catch (error) {
      console.error("Error: Could not find Amplify videos bucket");
      console.error("Tip: Set VIDEOS_BUCKET environment variable to specify a bucket explicitly");
      process.exit(1);
    }
  }
}

try {
  execSync(`aws s3api head-bucket --bucket ${bucket} --profile ${awsProfile}`, { stdio: "pipe" });
} catch (error) {
  console.error(`Error: Cannot access bucket '${bucket}' using profile '${awsProfile}'`);
  process.exit(1);
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
const normalizedPrefix = prefix.replace(/^\/+|\/+$/g, "");
console.log("1. Set environment variable for local preview:");
console.log(`   export GATSBY_VIDEOS_BASE_URL=https://${bucket}.s3.amazonaws.com/${normalizedPrefix}`);
console.log("");
console.log("2. Recommended: use the Amplify CDN URL:");
if (amplifyVideoOutputs?.cdnUrl) {
  const baseCdn = amplifyVideoOutputs.cdnUrl.replace(/\/+$/g, "");
  console.log(`   export GATSBY_VIDEOS_BASE_URL=${baseCdn}/${normalizedPrefix}`);
} else {
  console.log(`   export GATSBY_VIDEOS_BASE_URL=https://<cloudfront-domain>/${normalizedPrefix}`);
}
console.log("");
console.log("3. Run the web app:");
console.log("   cd apps/kanb.us && npm run develop");
