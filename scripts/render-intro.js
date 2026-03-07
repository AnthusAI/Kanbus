const { execSync } = require("node:child_process");
const { copyFileSync, existsSync, mkdirSync, renameSync, unlinkSync } = require("node:fs");
const path = require("node:path");
const {
  AUDIO_MIN_ACTIVITY_RATIO,
  AUDIO_MIN_BYTES_MP4,
  AUDIO_MIN_BYTES_WAV,
  AUDIO_MIN_DURATION_SEC,
  assertAudioValidations,
  validateAudioFile,
} = require("./video-audio-validation");

const repoRoot = path.resolve(__dirname, "..");
const videosDir = path.join(repoRoot, "videos");
const outDir = path.join(videosDir, "out");
const publicVideomlDir = path.join(repoRoot, "public", "videoml");
const siteStaticVideosDir = path.join(repoRoot, "apps", "kanb.us", "static", "videos");

const run = (cmd, opts = {}) => execSync(cmd, { stdio: "inherit", ...opts });

const main = () => {
  if (!existsSync(videosDir)) {
    throw new Error(`Missing videos/ subproject at ${videosDir}`);
  }

  if (!process.env.VIDEOML_CLI) {
    process.env.VIDEOML_CLI = path.resolve(repoRoot, "..", "VideoML", "cli", "bin", "vml.js");
  }
  if (!process.env.BABULUS_BUNDLE) {
    process.env.BABULUS_BUNDLE = path.resolve(repoRoot, "..", "Babulus", "public", "babulus-standard.js");
  }

  if (!existsSync(process.env.VIDEOML_CLI)) {
    throw new Error(`VIDEOML_CLI not found at ${process.env.VIDEOML_CLI}`);
  }
  if (!existsSync(process.env.BABULUS_BUNDLE)) {
    throw new Error(`BABULUS_BUNDLE not found at ${process.env.BABULUS_BUNDLE}`);
  }

  mkdirSync(outDir, { recursive: true });
  mkdirSync(siteStaticVideosDir, { recursive: true });

  if (!existsSync(path.join(videosDir, "node_modules"))) {
    run("npm ci", { cwd: videosDir });
  }

  const introMp4 = path.join(outDir, "intro.mp4");
  const introPoster = path.join(outDir, "intro.jpg");
  const introPosterAlias = path.join(outDir, "intro-poster.jpg");
  [introMp4, introPoster, introPosterAlias].forEach((filePath) => {
    if (existsSync(filePath)) {
      unlinkSync(filePath);
    }
  });

  run("npm run bundle:components", { cwd: videosDir });
  run("npm run vml:generate:intro", { cwd: videosDir });
  run("node scripts/sync-vml-preview-assets.js --intro", { cwd: repoRoot });

  const introWav = path.join(publicVideomlDir, "intro.wav");
  assertAudioValidations("post-generate-wav", [
    {
      label: "source-wav:intro",
      validation: validateAudioFile(introWav, {
        requireAudioStream: true,
        minBytes: AUDIO_MIN_BYTES_WAV,
        minDurationSec: AUDIO_MIN_DURATION_SEC,
        probeSeconds: 6,
        sampleRateHz: 44100,
        minActivityRatio: AUDIO_MIN_ACTIVITY_RATIO,
        checkSilence: true,
      }),
    },
  ]);

  run("npm run vml:render:intro", { cwd: videosDir });

  assertAudioValidations("post-render-mp4", [
    {
      label: "render-mp4:intro.mp4",
      validation: validateAudioFile(introMp4, {
        requireAudioStream: true,
        minBytes: AUDIO_MIN_BYTES_MP4,
        minDurationSec: AUDIO_MIN_DURATION_SEC,
        probeSeconds: 6,
        sampleRateHz: 44100,
        minActivityRatio: AUDIO_MIN_ACTIVITY_RATIO,
        checkSilence: true,
      }),
    },
  ]);

  const tmpFaststart = path.join(outDir, "intro-faststart-tmp.mp4");
  run(`ffmpeg -y -i "${introMp4}" -c copy -movflags +faststart "${tmpFaststart}"`, { stdio: "ignore" });
  renameSync(tmpFaststart, introMp4);

  assertAudioValidations("post-remux-mp4", [
    {
      label: "remuxed-mp4:intro.mp4",
      validation: validateAudioFile(introMp4, {
        requireAudioStream: true,
        minBytes: AUDIO_MIN_BYTES_MP4,
        minDurationSec: AUDIO_MIN_DURATION_SEC,
        probeSeconds: 6,
        sampleRateHz: 44100,
        minActivityRatio: AUDIO_MIN_ACTIVITY_RATIO,
        checkSilence: true,
      }),
    },
  ]);

  run(`ffmpeg -y -ss 00:00:02.000 -i "${introMp4}" -vframes 1 -q:v 2 "${introPoster}"`, { stdio: "ignore" });
  copyFileSync(introPoster, introPosterAlias);
  copyFileSync(introMp4, path.join(siteStaticVideosDir, "intro.mp4"));
  copyFileSync(introPoster, path.join(siteStaticVideosDir, "intro.jpg"));
  copyFileSync(introPosterAlias, path.join(siteStaticVideosDir, "intro-poster.jpg"));

  console.log("INTRO_RENDER_OK");
};

main();
