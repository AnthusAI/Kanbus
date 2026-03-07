# Kanbus Videos (VideoML)

This folder contains the VideoML-first pipeline for Kanbus marketing videos. The canonical sources live in `content/*.babulus.xml`.

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

## Intro Tuning Loop

For layout and motion iteration, do not render video. Use preview mode with one watch command.

```bash
# Terminal 1: run site dev server
cd apps/kanb.us
npm run develop

# Terminal 2: keep intro preview assets current
cd /path/to/Kanbus2
node scripts/watch-intro-preview.js
```

Preview on the site using VML mode:

```text
http://localhost:8000/?preview=1
```

`watch-intro-preview.js` supervises:
1. `videos` component bundle watch
2. intro VML generate watch (`vml:watch:intro`)
3. preview WAV sync (`scripts/sync-vml-preview-assets.js --intro --watch`)

Success marker:

```text
INTRO_PREVIEW_WATCH_READY
```

Failure marker:

```text
INTRO_PREVIEW_WATCH_FAILED
```

## No Render Needed for Layout Iteration

For design/layout work, use:
- `videos/content/*.babulus.xml` as canonical XML source
- `?preview=1` player for live inspection
- preview WAV sync script for voiceover playback

Only run render scripts when you need MP4 artifacts.

## Recommended Render Flow

From the repository root, run:

```bash
node scripts/render-videos.js
```

This script bundles browser components, generates the timeline and script JSON, renders the intro MP4, and copies MP4/JPG assets into `apps/kanb.us/static/videos` for local previews.

It also syncs preview WAV files into `apps/kanb.us/static/videoml`.

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

## Troubleshooting Preview

- Missing XML or WAV:
  - preview shows `PREVIEW_INPUTS_MISSING`
  - run `node scripts/sync-vml-preview-assets.js --intro` for intro
  - run `node scripts/sync-vml-preview-assets.js --all` for all videos
- Stale browser state:
  - hard refresh the preview page
  - restart `gatsby develop` if route/middleware changes were just applied
