const { execSync } = require("node:child_process");
const { existsSync, mkdirSync, copyFileSync, readdirSync, statSync, renameSync, unlinkSync, readFileSync } = require("node:fs");
const path = require("node:path");

const AUDIO_VALIDATION_PREFIX = "AUDIO_VALIDATION_FAILED";
const AUDIO_MIN_DURATION_SEC = 0.2;
const AUDIO_MIN_ACTIVITY_RATIO = 0.001;
const AUDIO_MIN_BYTES_WAV = 256;
const AUDIO_MIN_BYTES_MP4 = 1024;

const COMPOSITION_IDS = [
  "intro",
  "core-management",
  "jira-sync",
  "local-tasks",
  "beads-compatibility",
  "virtual-projects",
  "vscode-plugin",
  "policy-as-code",
  "lifecycle-hooks",
  "realtime-collaboration",
];

const repoRoot = path.resolve(__dirname, "..");
const videosDir = path.join(repoRoot, "videos");
const outDir = path.join(videosDir, "out");
const siteStaticVideosDir = path.join(repoRoot, "apps", "kanb.us", "static", "videos");
const publicVideomlDir = path.join(repoRoot, "public", "videoml");

const run = (cmd, opts = {}) => {
  execSync(cmd, { stdio: "inherit", ...opts });
};

const runCapture = (cmd, opts = {}) => {
  return execSync(cmd, { stdio: ["ignore", "pipe", "pipe"], ...opts });
};

const probeDurationSec = (assetPath) => {
  const output = runCapture(
    `ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "${assetPath}"`,
    { encoding: "utf8" }
  )
    .toString()
    .trim();
  const value = Number(output.split("\n")[0] || 0);
  return Number.isFinite(value) ? Math.max(0, value) : 0;
};

const probeAudioStreamCount = (assetPath) => {
  const output = runCapture(
    `ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "${assetPath}"`,
    { encoding: "utf8" }
  )
    .toString()
    .trim();
  if (!output) return 0;
  return output
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean).length;
};

const decodePcm = (assetPath, seconds = 6, sampleRateHz = 44100) => {
  return runCapture(
    `ffmpeg -v error -t ${seconds} -i "${assetPath}" -ac 1 -ar ${sampleRateHz} -f s16le pipe:1`,
    { encoding: "buffer", maxBuffer: 50 * 1024 * 1024 }
  );
};

const computeActivityRatio = (pcm, amplitudeThreshold = 200) => {
  if (!pcm || pcm.length < 2) {
    return { activityRatio: 0, isAllSilence: true };
  }
  const total = Math.floor(pcm.length / 2);
  let active = 0;
  for (let i = 0; i < total; i += 1) {
    const sample = pcm.readInt16LE(i * 2);
    if (sample >= amplitudeThreshold || sample <= -amplitudeThreshold) {
      active += 1;
    }
  }
  return {
    activityRatio: total ? active / total : 0,
    isAllSilence: active === 0,
  };
};

const validateAudioFile = (assetPath, options = {}) => {
  const {
    requireAudioStream = true,
    minBytes = AUDIO_MIN_BYTES_WAV,
    minDurationSec = AUDIO_MIN_DURATION_SEC,
    probeSeconds = 6,
    sampleRateHz = 44100,
    minActivityRatio = AUDIO_MIN_ACTIVITY_RATIO,
    checkSilence = true,
  } = options;

  const result = {
    path: assetPath,
    exists: false,
    bytes: 0,
    durationSec: 0,
    audioStreamCount: 0,
    activityRatio: 0,
    isAllSilence: null,
    valid: false,
    failures: [],
  };

  if (!existsSync(assetPath)) {
    result.failures.push("missing-file");
    return result;
  }
  result.exists = true;

  try {
    result.bytes = statSync(assetPath).size;
  } catch {
    result.failures.push("stat-failed");
  }
  if (result.bytes < minBytes) {
    result.failures.push(`bytes-below-min(${result.bytes}<${minBytes})`);
  }

  try {
    result.durationSec = probeDurationSec(assetPath);
  } catch {
    result.failures.push("probe-duration-failed");
  }
  if (result.durationSec < minDurationSec) {
    result.failures.push(`duration-below-min(${result.durationSec.toFixed(3)}<${minDurationSec})`);
  }

  try {
    result.audioStreamCount = probeAudioStreamCount(assetPath);
  } catch {
    result.failures.push("probe-streams-failed");
  }
  if (requireAudioStream && result.audioStreamCount < 1) {
    result.failures.push("missing-audio-stream");
  }

  const shouldInspectWaveform = checkSilence || minActivityRatio > 0;
  if (shouldInspectWaveform && (!requireAudioStream || result.audioStreamCount > 0)) {
    try {
      const secondsToProbe = Math.max(0.25, Math.min(probeSeconds, result.durationSec || probeSeconds));
      const pcm = decodePcm(assetPath, secondsToProbe, sampleRateHz);
      const { activityRatio, isAllSilence } = computeActivityRatio(pcm);
      result.activityRatio = activityRatio;
      result.isAllSilence = isAllSilence;
      if (checkSilence && isAllSilence) {
        result.failures.push("all-silence");
      }
      if (minActivityRatio > 0 && activityRatio < minActivityRatio) {
        result.failures.push(`activity-below-min(${activityRatio.toFixed(4)}<${minActivityRatio})`);
      }
    } catch {
      result.failures.push("waveform-check-failed");
    }
  }

  result.valid = result.failures.length === 0;
  return result;
};

const logValidationFailure = (label, validation) => {
  console.error(
    `${AUDIO_VALIDATION_PREFIX} label=${label} file=${validation.path} ` +
      `failures=${validation.failures.join("|")} bytes=${validation.bytes} ` +
      `duration_sec=${validation.durationSec.toFixed(3)} streams=${validation.audioStreamCount} ` +
      `activity_ratio=${(validation.activityRatio || 0).toFixed(4)}`
  );
};

const assertAudioValidations = (stage, checks) => {
  const failures = [];
  for (const check of checks) {
    if (!check.validation.valid) {
      failures.push(check);
      logValidationFailure(check.label, check.validation);
    }
  }
  if (failures.length > 0) {
    console.error(
      `${AUDIO_VALIDATION_PREFIX} stage=${stage} total_failures=${failures.length} status=abort`
    );
    throw new Error(`Audio validation failed during ${stage}`);
  }
};

const removeStaleVideoAssets = () => {
  if (!existsSync(outDir)) return;
  for (const file of readdirSync(outDir)) {
    if (file.toLowerCase().endsWith(".mp4") || file.toLowerCase().endsWith(".jpg")) {
      unlinkSync(path.join(outDir, file));
    }
  }
};

const ensureAliasAsset = (targetPath, sourcePath) => {
  if (existsSync(targetPath)) return;
  if (!existsSync(sourcePath)) {
    throw new Error(`Missing source alias asset: ${sourcePath}`);
  }
  copyFileSync(sourcePath, targetPath);
  console.log(`Created alias asset: ${path.basename(targetPath)} <- ${path.basename(sourcePath)}`);
};

function getTimelineDurationSec(compositionId) {
  const timelinePath = path.join(repoRoot, "src", "videos", compositionId, `${compositionId}.timeline.json`);
  if (!existsSync(timelinePath)) return 30;
  const data = JSON.parse(readFileSync(timelinePath, "utf8"));
  const items = data.items || [];
  let maxEnd = 0;
  for (const item of items) {
    if (item.endSec != null && item.endSec > maxEnd) maxEnd = item.endSec;
  }
  return maxEnd > 0 ? Math.ceil(maxEnd) + 1 : 30;
}

function ensureSilentWav(compositionId) {
  const wavPath = path.join(publicVideomlDir, `${compositionId}.wav`);
  if (existsSync(wavPath)) return;
  mkdirSync(publicVideomlDir, { recursive: true });
  const durationSec = getTimelineDurationSec(compositionId);
  console.log(`Creating silent WAV for ${compositionId} (${durationSec}s) at ${wavPath}`);
  execSync(
    `ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=mono -t ${durationSec} -acodec pcm_s16le "${wavPath}"`,
    { stdio: "ignore" }
  );
}

function mixLifecycleHooksFromSegments() {
  const segmentsDir = path.join(repoRoot, "src", "videos", "lifecycle-hooks", "env", "development", "segments");
  const outPath = path.join(publicVideomlDir, "lifecycle-hooks.wav");
  const segs = [
    path.join(segmentsDir, "hook--hook_voice--tts--4142a228b2e5--1.wav"),
    path.join(segmentsDir, "deep_dive--before_hooks--tts--778764518869--1.wav"),
    path.join(segmentsDir, "deep_dive--after_hooks--tts--d547a4671b79--1.wav"),
    path.join(segmentsDir, "deep_dive--policy_alignment--tts--e393da64fb40--1.wav"),
  ];
  if (!segs.every((p) => existsSync(p))) return false;
  mkdirSync(publicVideomlDir, { recursive: true });
  const silencePath = path.join(segmentsDir, "silence-819a032561bf.wav");
  if (!existsSync(silencePath)) return false;
  const list = segs.flatMap((p, i) => (i > 0 ? [silencePath, p] : [p])).map((p) => `file '${p}'`);
  const listPath = path.join(repoRoot, "tmp-lifecycle-hooks-concat.txt");
  require("fs").writeFileSync(listPath, list.join("\n"));
  try {
    execSync(`ffmpeg -y -f concat -safe 0 -i "${listPath}" -acodec pcm_s16le -ar 44100 -ac 1 "${outPath}"`, { stdio: "ignore" });
    return true;
  } finally {
    if (existsSync(listPath)) unlinkSync(listPath);
  }
}

const main = () => {
  if (!existsSync(videosDir)) {
    throw new Error(`Missing videos/ subproject at ${videosDir}`);
  }

  // Set default env vars if missing
  if (!process.env.VIDEOML_CLI) {
    process.env.VIDEOML_CLI = path.resolve(repoRoot, "..", "VideoML", "cli", "bin", "vml.js");
  }
  if (!process.env.BABULUS_BUNDLE) {
    process.env.BABULUS_BUNDLE = path.resolve(repoRoot, "..", "Babulus", "public", "babulus-standard.js");
  }

  console.log(`Using VIDEOML_CLI: ${process.env.VIDEOML_CLI}`);
  console.log(`Using BABULUS_BUNDLE: ${process.env.BABULUS_BUNDLE}`);

  if (!existsSync(process.env.VIDEOML_CLI)) {
    throw new Error(
      `VIDEOML_CLI not found at: ${process.env.VIDEOML_CLI}\n` +
        `Set the VIDEOML_CLI environment variable to the path of the VideoML CLI entry point.`
    );
  }

  if (!existsSync(process.env.BABULUS_BUNDLE)) {
    throw new Error(
      `BABULUS_BUNDLE not found at: ${process.env.BABULUS_BUNDLE}\n` +
        `Set the BABULUS_BUNDLE environment variable to the path of babulus-standard.js.\n` +
        `Example: export BABULUS_BUNDLE=/path/to/Babulus/public/babulus-standard.js`
    );
  }

  mkdirSync(siteStaticVideosDir, { recursive: true });

  if (!existsSync(path.join(videosDir, "node_modules"))) {
    run("npm ci", { cwd: videosDir });
  }
  const babulusBundle = path.join(videosDir, "node_modules", "babulus", "public", "babulus-standard.js");
  if (!existsSync(babulusBundle)) {
    run("npm install", { cwd: videosDir });
  }

  const singleId = process.env.COMPOSITION_ID || null;
  const compositionIds = singleId ? [singleId] : COMPOSITION_IDS;
  let usedSilentFallback = false;
  if (singleId && !COMPOSITION_IDS.includes(singleId)) {
    throw new Error(`Unknown COMPOSITION_ID=${singleId}. Must be one of: ${COMPOSITION_IDS.join(", ")}`);
  }

  if (!singleId) {
    removeStaleVideoAssets();
  }

  run("npm run bundle:components", { cwd: videosDir });
  const pathEnv = path.join(repoRoot, "scripts") + path.delimiter + (process.env.PATH || "");
  const envWithVml = { ...process.env, PATH: pathEnv };

  if (singleId) {
    const dslPath = path.join(videosDir, "content", `${singleId}.babulus.xml`);
    if (!existsSync(dslPath)) {
      throw new Error(`Missing DSL for ${singleId}: ${dslPath}`);
    }
    const wavPath = path.join(publicVideomlDir, `${singleId}.wav`);
    if (singleId === "lifecycle-hooks" && mixLifecycleHooksFromSegments()) {
      console.log(`Mixed lifecycle-hooks.wav from committed segments`);
      run("npm run sync:public", { cwd: videosDir, env: envWithVml });
      usedSilentFallback = false;
    } else {
      const existingValidation = existsSync(wavPath)
        ? validateAudioFile(wavPath, {
            requireAudioStream: true,
            minBytes: AUDIO_MIN_BYTES_WAV,
            minDurationSec: AUDIO_MIN_DURATION_SEC,
            minActivityRatio: AUDIO_MIN_ACTIVITY_RATIO,
            checkSilence: true,
          })
        : null;
      if (existingValidation?.valid) {
        console.log(`Using existing WAV for ${singleId}`);
        run("npm run sync:public", { cwd: videosDir, env: envWithVml });
        usedSilentFallback = false;
      } else {
        let generateOk = false;
        try {
          run(`vml generate "${dslPath}"`, { cwd: videosDir, env: envWithVml });
          run("npm run sync:public", { cwd: videosDir, env: envWithVml });
          generateOk = true;
        } catch (err) {
          console.error("Generate failed (TTS may need API keys). Using silent-audio fallback for render.");
          ensureSilentWav(singleId);
          run("npm run sync:public", { cwd: videosDir, env: envWithVml });
        }
        usedSilentFallback = !generateOk;
      }
    }
  } else {
    run("npm run generate", { cwd: videosDir, env: envWithVml });
  }

  const wavChecks = compositionIds.map((id) => {
    const wavPath = path.join(publicVideomlDir, `${id}.wav`);
    const isSilentFallback = usedSilentFallback && id === singleId;
    return {
      label: `source-wav:${id}`,
      validation: validateAudioFile(wavPath, {
        requireAudioStream: true,
        minBytes: AUDIO_MIN_BYTES_WAV,
        minDurationSec: AUDIO_MIN_DURATION_SEC,
        probeSeconds: 6,
        sampleRateHz: 44100,
        minActivityRatio: isSilentFallback ? 0 : AUDIO_MIN_ACTIVITY_RATIO,
        checkSilence: !isSilentFallback,
      }),
    };
  });
  assertAudioValidations("post-generate-wav", wavChecks);

  if (singleId) {
    run(`npm run vml:render:${singleId}`, { cwd: videosDir, env: envWithVml });
  } else {
    run("npm run render", { cwd: videosDir, env: envWithVml });
  }

  const outFiles = existsSync(outDir) ? readdirSync(outDir) : [];
  const allMp4 = outFiles.filter((file) => file.toLowerCase().endsWith(".mp4"));
  const mp4Files = singleId
    ? allMp4.filter((file) => compositionIds.includes(file.replace(/\.mp4$/i, "")))
    : allMp4;

  const preRemuxChecks = mp4Files.map((filename) => {
    const mp4Path = path.join(outDir, filename);
    return {
      label: `render-mp4:${filename}`,
      validation: validateAudioFile(mp4Path, {
        requireAudioStream: true,
        minBytes: AUDIO_MIN_BYTES_MP4,
        minDurationSec: AUDIO_MIN_DURATION_SEC,
        probeSeconds: 6,
        sampleRateHz: 44100,
        minActivityRatio: AUDIO_MIN_ACTIVITY_RATIO,
        checkSilence: true,
      }),
    };
  });
  assertAudioValidations("post-render-mp4", preRemuxChecks);

  // Remux with faststart so browsers can play without downloading the full file.
  // The moov atom must appear before mdat for instant playback and correct duration display.
  for (const filename of mp4Files) {
    const src = path.join(outDir, filename);
    const tmp = src.replace(".mp4", "-faststart-tmp.mp4");
    console.log(`Applying faststart to ${filename}...`);
    try {
      run(`ffmpeg -y -i "${src}" -c copy -movflags +faststart "${tmp}"`, { stdio: "ignore" });
      renameSync(tmp, src);
    } catch {
      console.error(`Failed to apply faststart to ${filename}`);
      if (existsSync(tmp)) unlinkSync(tmp);
      throw new Error(`Failed to apply faststart to ${filename}`);
    }
  }

  const postRemuxChecks = mp4Files.map((filename) => {
    const mp4Path = path.join(outDir, filename);
    return {
      label: `remuxed-mp4:${filename}`,
      validation: validateAudioFile(mp4Path, {
        requireAudioStream: true,
        minBytes: AUDIO_MIN_BYTES_MP4,
        minDurationSec: AUDIO_MIN_DURATION_SEC,
        probeSeconds: 6,
        sampleRateHz: 44100,
        minActivityRatio: AUDIO_MIN_ACTIVITY_RATIO,
        checkSilence: true,
      }),
    };
  });
  assertAudioValidations("post-remux-mp4", postRemuxChecks);

  for (const filename of mp4Files) {
    const src = path.join(outDir, filename);
    const posterSrc = path.join(outDir, filename.replace(".mp4", ".jpg"));
    console.log(`Extracting poster for ${filename}...`);
    try {
      run(`ffmpeg -y -ss 00:00:02.000 -i "${src}" -vframes 1 -q:v 2 "${posterSrc}"`, { stdio: "ignore" });
    } catch {
      console.error(`Failed to extract poster for ${filename}`);
      throw new Error(`Failed to extract poster for ${filename}`);
    }
  }

  if (!singleId) {
  ensureAliasAsset(path.join(outDir, "intro-poster.jpg"), path.join(outDir, "intro.jpg"));
  ensureAliasAsset(path.join(outDir, "kanban-board.mp4"), path.join(outDir, "core-management.mp4"));
  ensureAliasAsset(path.join(outDir, "kanban-board.jpg"), path.join(outDir, "core-management.jpg"));
  }

  const updatedOutFiles = existsSync(outDir) ? readdirSync(outDir) : [];
  const toCopy = (singleId ? updatedOutFiles.filter((f) => f === `${singleId}.mp4` || f === `${singleId}.jpg`) : updatedOutFiles).filter(
    (file) => file.toLowerCase().endsWith(".mp4") || file.toLowerCase().endsWith(".jpg")
  );

  for (const filename of toCopy) {
    const src = path.join(outDir, filename);
    const dst = path.join(siteStaticVideosDir, filename);
    copyFileSync(src, dst);
    console.log(`Copied ${src} -> ${dst}`);
  }
};

main();
