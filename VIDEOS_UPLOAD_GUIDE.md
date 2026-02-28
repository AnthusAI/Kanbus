# Video Upload Guide

This guide explains how to render and upload Kanbus feature videos to AWS S3.

## Quick Start

### 1. Render Videos Locally

Generate video files from VideoML sources:

```bash
node scripts/render-videos.js
```

This creates:
- MP4 video files in `videos/out/`
- JPG poster images in `videos/out/`
- Assets copied to `apps/kanb.us/static/videos/` for local preview

### 2. Upload to S3

Upload the rendered videos to AWS:

```bash
# Using the default AWS profile (anthus)
node scripts/upload-videos.js

# Using a specific AWS profile
node scripts/upload-videos.js --profile=your-profile

# Dry run to preview what would be uploaded
node scripts/upload-videos.js --dry-run
```

### 3. Configure the Web App

After upload, the script provides the S3 URL. Set the environment variable:

```bash
# For direct S3 access
export GATSBY_VIDEOS_BASE_URL=https://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio.s3.amazonaws.com/kanbus-feature-videos

# Or use the Amplify CloudFront distribution (if available)
export GATSBY_VIDEOS_BASE_URL=https://d1234.cloudfront.net/kanbus-feature-videos
```

### 4. Run the Web App

Start the development server:

```bash
cd apps/kanb.us
npm run develop
```

Videos will load from S3 and display on feature pages.

## Script Options

### Node.js Script: `scripts/upload-videos.js`

```bash
node scripts/upload-videos.js [OPTIONS]
```

**Options:**
- `--profile=NAME` - AWS profile to use (default: `anthus`)
- `--dry-run` - Preview changes without uploading

**Environment Variables:**
- `AWS_PROFILE` - AWS profile (overridden by `--profile` flag)
- `VIDEOS_BUCKET` - S3 bucket name (auto-discovered if not set)
- `VIDEOS_PREFIX` - S3 prefix/folder (default: `kanbus-feature-videos`)
- `VIDEOS_CACHE_CONTROL` - Cache control header (default: `public,max-age=300`)

### Bash Script: `scripts/upload-videos-to-cdn.sh`

Alternative bash script with similar options:

```bash
./scripts/upload-videos-to-cdn.sh [OPTIONS]
```

**Options:**
- `--profile PROFILE` - AWS profile to use (default: `anthus`)
- `--dry-run` - Preview changes without uploading

## Architecture

### Video Files

Videos are defined in `apps/kanb.us/src/content/videos.ts`:

```typescript
export type VideoEntry = {
  id: string;                // Unique identifier
  title: string;             // Display title
  description: string;       // Feature description
  filename: string;          // MP4 filename in S3
  poster?: string;           // JPG poster image filename
};
```

Each video must have:
1. A corresponding `.babulus.xml` file in `videos/content/`
2. An entry in `VIDEOS` array in `videos.ts`
3. Rendered MP4 and JPG files in `videos/out/`

### Video URLs

The web app constructs video URLs using:

```typescript
const baseUrl = process.env.GATSBY_VIDEOS_BASE_URL;
const videoUrl = `${baseUrl}/${video.filename}`;
const posterUrl = `${baseUrl}/${video.poster}`;
```

## Local Development

### Preview Without Upload

To develop locally without uploading to S3:

```bash
# Render videos
node scripts/render-videos.js

# Set local path (Gatsby copies to static/)
export GATSBY_VIDEOS_BASE_URL=/videos

# Run dev server
cd apps/kanb.us && npm run develop
```

Videos will load from `apps/kanb.us/static/videos/`.

### Full Workflow

```bash
# 1. Render videos
node scripts/render-videos.js

# 2. Upload to S3
node scripts/upload-videos.js

# 3. Set S3 URL (from script output)
export GATSBY_VIDEOS_BASE_URL=...

# 4. Run web app
cd apps/kanb.us && npm run develop

# 5. Visit http://localhost:8000
```

## Troubleshooting

### Upload fails with "Access Denied"

Check AWS credentials:

```bash
aws sts get-caller-identity --profile anthus
```

If this fails, reconfigure AWS:

```bash
aws configure --profile anthus
```

### Bucket not found

The script searches for Amplify buckets with "videosbucket" in the name. Specify manually:

```bash
VIDEOS_BUCKET=your-bucket-name node scripts/upload-videos.js
```

### Videos don't appear in web app

1. Verify `GATSBY_VIDEOS_BASE_URL` is set
2. Check S3 bucket permissions (should be public)
3. Verify file names match in `videos.ts`
4. Rebuild web app: `cd apps/kanb.us && npm run build`

## Cache Control

Videos are uploaded with 5-minute cache control:

```
Cache-Control: public,max-age=300
```

To change:

```bash
VIDEOS_CACHE_CONTROL="public,max-age=3600" node scripts/upload-videos.js
```

## Video Formats

- **MP4**: H.264 video codec, for browsers
- **JPG**: 1920x1080 poster images for hero sections

All files are uploaded with public read permissions.
