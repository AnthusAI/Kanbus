# Kanbus Videos (VideoML)

This folder contains the VideoML-first pipeline for Kanbus marketing videos. The canonical sources live in `content/*.vml`.

## Quick Start

```bash
# From this folder:

# Install Node deps
npm install

# Set required environment variables
export VIDEOML_CLI="/path/to/videoml/cli/bin/vml.js"
export BABULUS_BUNDLE="/path/to/babulus-standard.js"

# Generate timelines + scripts from VML
npm run vml:generate

# Bundle custom browser components
npm run bundle:components

# Render the intro video
npm run vml:render:intro
```

## Recommended Render Flow

From the repository root, run:

```bash
node scripts/render-videos.js
```

This script bundles browser components, generates the timeline and script JSON, renders the intro MP4, and copies MP4/JPG assets into `apps/kanb.us/static/videos` for local previews.

## Uploading to the CDN

The upload script uses the rendered assets and syncs them to the configured S3 bucket:

```bash
VIDEOS_BUCKET=<bucket-name> VIDEOS_PREFIX=videos node scripts/upload-videos.js
```

Both `VIDEOS_BUCKET` and `VIDEOS_PREFIX` are required. There is no fallback logic.

## Project Structure

```
videos/
├── content/                 # One .vml per video (canonical source)
├── scripts/                 # Browser component bundling scripts
├── src/
│   ├── components/          # Custom React components used by VML
│   └── videos/              # Generated script/timeline JSON outputs
├── public/
│   ├── browser-components.js  # Custom component bundle for renderer
│   └── videoml/               # Provider segment cache (tracked) + local artifacts (ignored)
├── out/                     # Rendered MP4s (git-ignored)
└── package.json
```

## Rendering Output

Rendered videos are written to `videos/out/`. The root script `node scripts/render-videos.js` copies MP4/JPG files into `apps/kanb.us/static/videos` for local preview.
