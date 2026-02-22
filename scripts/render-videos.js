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

  mkdirSync(siteStaticVideosDir, { recursive: true });

  if (!existsSync(path.join(videosDir, "node_modules"))) {
    run("npm ci", { cwd: videosDir });
  }

  run("npm run bundle:components", { cwd: videosDir });
  run("npm run vml:generate", { cwd: videosDir });
  run("npm run vml:render:intro", { cwd: videosDir });

  const outFiles = existsSync(outDir) ? readdirSync(outDir) : [];
  const toCopy = outFiles.filter(
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
