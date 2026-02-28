# Video Upload Workflow - Quick Start

This document provides a step-by-step guide for uploading rendered Kanbus feature videos to AWS S3.

## Prerequisites

- AWS profile configured: `anthus` (or specify with `--profile`)
- Videos already rendered in `videos/out/`
- Node.js 18+ installed

## Quick Start (One-Liner)

```bash
# 1. Render videos
node scripts/render-videos.js

# 2. Upload to S3
node scripts/upload-videos.js

# 3. Copy the GATSBY_VIDEOS_BASE_URL from script output and set it
export GATSBY_VIDEOS_BASE_URL="https://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio.s3.amazonaws.com/kanbus-feature-videos"

# 4. Run the web app
cd apps/kanb.us && npm run develop
```

## Step-by-Step Instructions

### Step 1: Render Videos Locally

Generate MP4 and JPG files from VideoML sources:

```bash
node scripts/render-videos.js
```

**Output:**
- Videos saved to: `videos/out/`
- Assets copied to: `apps/kanb.us/static/videos/` (for local preview)
- Console output shows which videos were generated

**Time:** ~2-5 minutes depending on system

### Step 2: Upload to AWS S3

Upload the rendered files to your Amplify bucket:

```bash
node scripts/upload-videos.js
```

**What it does:**
1. Checks AWS credentials
2. Auto-discovers the Amplify videos bucket
3. Syncs MP4 and JPG files to S3
4. Sets cache headers (5 minutes)
5. Prints the S3 URL to use

**Output example:**
```
Kanbus Video Upload
===================

Videos to upload: 34 files
AWS Profile: anthus
S3 Prefix: kanbus-feature-videos

Found bucket: amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio

Uploading to: s3://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio/kanbus-feature-videos/

(uploads MP4 and JPG files...)

Upload complete!

Next steps:
1. Set environment variable for local preview:
   export GATSBY_VIDEOS_BASE_URL=https://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio.s3.amazonaws.com/kanbus-feature-videos
```

### Step 3: Set Environment Variable

Copy the URL from script output and set it:

```bash
export GATSBY_VIDEOS_BASE_URL="https://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio.s3.amazonaws.com/kanbus-feature-videos"
```

Or use the Amplify CloudFront distribution (faster, if available):

```bash
export GATSBY_VIDEOS_BASE_URL="https://d1234.cloudfront.net/kanbus-feature-videos"
```

### Step 4: Run the Web App

Start the development server:

```bash
cd apps/kanb.us
npm run develop
```

The web app will now load videos from S3. Visit:
- http://localhost:8000/features/ - See feature showcase pages
- http://localhost:8000/demo - See intro video

## Script Options

### Dry Run (Preview without uploading)

See what would be uploaded without actually uploading:

```bash
node scripts/upload-videos.js --dry-run
```

### Custom AWS Profile

Use a different AWS profile:

```bash
node scripts/upload-videos.js --profile=my-profile
```

### Bash Alternative

Use the bash script instead (optional):

```bash
./scripts/upload-videos-to-cdn.sh
./scripts/upload-videos-to-cdn.sh --profile=anthus
./scripts/upload-videos-to-cdn.sh --dry-run
```

## Troubleshooting

### "Access Denied" error

AWS authentication failed. Check your credentials:

```bash
aws sts get-caller-identity --profile anthus
```

If that fails, reconfigure:

```bash
aws configure --profile anthus
```

### "No Amplify videos buckets found"

The script couldn't find the bucket automatically. Specify it manually:

```bash
VIDEOS_BUCKET=your-bucket-name node scripts/upload-videos.js
```

Or set in environment permanently:

```bash
export VIDEOS_BUCKET="amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio"
node scripts/upload-videos.js
```

### Videos not appearing in web app

1. Verify `GATSBY_VIDEOS_BASE_URL` is set correctly:
   ```bash
   echo $GATSBY_VIDEOS_BASE_URL
   ```

2. Check that files exist in S3:
   ```bash
   aws s3 ls s3://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio/kanbus-feature-videos/ --profile anthus
   ```

3. Rebuild the web app:
   ```bash
   cd apps/kanb.us && npm run build
   ```

4. Clear Gatsby cache:
   ```bash
   cd apps/kanb.us && rm -rf .cache && npm run develop
   ```

### S3 bucket is private

Videos need to be publicly readable. Check bucket policy or permissions.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AWS_PROFILE` | `anthus` | AWS profile to use |
| `VIDEOS_BUCKET` | auto-detect | S3 bucket name |
| `VIDEOS_PREFIX` | `kanbus-feature-videos` | S3 folder prefix |
| `VIDEOS_CACHE_CONTROL` | `public,max-age=300` | Cache control header |
| `GATSBY_VIDEOS_BASE_URL` | (required) | Base URL for videos in web app |

## Local Development (Without Upload)

If you want to iterate locally without uploading:

```bash
# 1. Render videos
node scripts/render-videos.js

# 2. Videos are copied to static directory
# apps/kanb.us/static/videos/

# 3. Set local path
export GATSBY_VIDEOS_BASE_URL="/videos"

# 4. Run dev server
cd apps/kanb.us && npm run develop
```

Videos will load from local static files instead of S3.

## Performance Notes

- **First run:** 2-5 minutes (video rendering)
- **Subsequent runs:** 1-2 minutes (incremental upload)
- **Cache TTL:** 5 minutes (configurable)

## Automation

To automate video uploads in CI/CD:

```bash
#!/bin/bash
set -e

# Render videos
node scripts/render-videos.js

# Upload with CI credentials
AWS_PROFILE=anthus node scripts/upload-videos.js

# Update environment
export GATSBY_VIDEOS_BASE_URL="https://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio.s3.amazonaws.com/kanbus-feature-videos"

# Deploy web app
cd apps/kanb.us && npm run build && npm run deploy
```

## References

- Full guide: [VIDEOS_UPLOAD_GUIDE.md](VIDEOS_UPLOAD_GUIDE.md)
- Video definitions: [apps/kanb.us/src/content/videos.ts](apps/kanb.us/src/content/videos.ts)
- VideoML sources: [videos/content/](videos/content/)
