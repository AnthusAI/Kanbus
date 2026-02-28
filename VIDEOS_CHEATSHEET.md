# Video Upload - Command Reference Card

Quick reference for uploading Kanbus feature videos to AWS S3.

## Command Cheat Sheet

```bash
# Render videos locally
node scripts/render-videos.js

# Upload to S3 (auto-discovers bucket)
node scripts/upload-videos.js

# Upload with specific AWS profile
node scripts/upload-videos.js --profile=anthus

# Dry run (preview without uploading)
node scripts/upload-videos.js --dry-run

# Set environment variable for web app
export GATSBY_VIDEOS_BASE_URL="https://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio.s3.amazonaws.com/kanbus-feature-videos"

# Run web app
cd apps/kanb.us && npm run develop

# Verify videos in S3
aws s3 ls s3://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio/kanbus-feature-videos/ --profile anthus
```

## Environment Variables

```bash
# AWS profile to use
AWS_PROFILE=anthus

# S3 bucket name (auto-discovered if not set)
VIDEOS_BUCKET=amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio

# S3 prefix/folder
VIDEOS_PREFIX=kanbus-feature-videos

# Cache control header
VIDEOS_CACHE_CONTROL="public,max-age=300"

# Web app video base URL
GATSBY_VIDEOS_BASE_URL=https://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio.s3.amazonaws.com/kanbus-feature-videos
```

## Workflow

### One-Time Setup (5 min)

```bash
node scripts/render-videos.js
node scripts/upload-videos.js
```

Copy the `GATSBY_VIDEOS_BASE_URL` from the output.

### Local Development

```bash
export GATSBY_VIDEOS_BASE_URL="<URL from upload script>"
cd apps/kanb.us && npm run develop
```

Visit http://localhost:8000/features/

### CI/CD Integration

```bash
#!/bin/bash
set -e
node scripts/render-videos.js
AWS_PROFILE=anthus node scripts/upload-videos.js
export GATSBY_VIDEOS_BASE_URL="https://amplify-dfkbdffs2viq8-main-br-videosbucket75f673ed-2ylai9zpobio.s3.amazonaws.com/kanbus-feature-videos"
cd apps/kanb.us && npm run build
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Access Denied` | Run `aws sts get-caller-identity --profile anthus` to verify credentials |
| `No Amplify buckets found` | Set `VIDEOS_BUCKET` manually |
| Videos don't appear | Verify `GATSBY_VIDEOS_BASE_URL` is set; check S3 bucket permissions |
| Slow uploads | Reduce `VIDEOS_CACHE_CONTROL` TTL or check network speed |
| Out of sync videos | Delete `videos/out/` and re-render from scratch |

## Documentation

- **Quick Start:** [VIDEOS_QUICK_START.md](VIDEOS_QUICK_START.md)
- **Full Guide:** [VIDEOS_UPLOAD_GUIDE.md](VIDEOS_UPLOAD_GUIDE.md)
- **Video Definitions:** [apps/kanb.us/src/content/videos.ts](apps/kanb.us/src/content/videos.ts)
- **VideoML Sources:** [videos/content/](videos/content/)

## Scripts

- **Node.js:** `scripts/upload-videos.js` (recommended)
- **Bash:** `scripts/upload-videos-to-cdn.sh` (alternative)

## Contact

For issues or questions:
1. Check troubleshooting in VIDEOS_QUICK_START.md
2. Review logs from `node scripts/render-videos.js`
3. Run `node scripts/upload-videos.js --dry-run` to test
