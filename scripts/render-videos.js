const { execSync } = require("node:child_process");
const { existsSync, mkdirSync, copyFileSync, readdirSync } = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..");
const videosDir = path.join(repoRoot, "videos");
const outDir = path.join(videosDir, "out");
const siteStaticVideosDir = path.join(repoRoot, "apps", "kanb.us", "static", "videos");

const run = (cmd, opts = {}) => {
  execSync(cmd, { stdio: "inherit", ...opts });
};

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

  run("npm run bundle:components", { cwd: videosDir });
  run("npm run vml:generate", { cwd: videosDir });
  run("npm run vml:render:all", { cwd: videosDir });

  const outFiles = existsSync(outDir) ? readdirSync(outDir) : [];
  const mp4Files = outFiles.filter((file) => file.toLowerCase().endsWith(".mp4"));

  // Remux with faststart so browsers can play without downloading the full file.
  // The moov atom must appear before mdat for instant playback and correct duration display.
  for (const filename of mp4Files) {
    const src = path.join(outDir, filename);
    const tmp = src.replace(".mp4", "-faststart-tmp.mp4");
    console.log(`Applying faststart to ${filename}...`);
    try {
      run(`ffmpeg -y -i "${src}" -c copy -movflags +faststart "${tmp}"`, { stdio: "ignore" });
      require("node:fs").renameSync(tmp, src);
    } catch (e) {
      console.error(`Failed to apply faststart to ${filename}`);
      if (existsSync(tmp)) require("node:fs").unlinkSync(tmp);
    }
  }

  for (const filename of mp4Files) {
    const src = path.join(outDir, filename);
    const posterSrc = path.join(outDir, filename.replace(".mp4", ".jpg"));
    console.log(`Extracting poster for ${filename}...`);
    try {
      run(`ffmpeg -y -ss 00:00:02.000 -i "${src}" -vframes 1 -q:v 2 "${posterSrc}"`, { stdio: "ignore" });
    } catch (e) {
      console.error(`Failed to extract poster for ${filename}`);
    }
  }

  const updatedOutFiles = existsSync(outDir) ? readdirSync(outDir) : [];
  const toCopy = updatedOutFiles.filter(
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
