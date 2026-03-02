# Production Video Publish Runbook

This runbook publishes website videos to production S3/CDN and verifies that
live `kanb.us` URLs resolve and contain non-silent audio.

## One command (recommended)

```bash
AWS_PROFILE=anthus scripts/publish-production-videos.sh
```

What this does:

1. Ensures compatibility aliases in `videos/out`:
   - `intro-poster.jpg` from `intro.jpg` (if missing)
   - `kanban-board.mp4/.jpg` from `core-management.mp4/.jpg` (if missing)
2. Ensures Amplify rewrite is configured:
   - `/videos/<*> -> <videosCdnUrl>/videos/<*>` (`302`)
3. Uploads to primary prefix: `videos/`
4. Uploads to mirror prefix: `kanbus-feature-videos/`
5. Runs strict production verification.

Success marker:

```text
PUBLISH_AND_VERIFY_OK
```

## Verify only

```bash
AWS_PROFILE=anthus scripts/verify-production-videos.sh
```

Checks:

- S3 key existence in `videos/` and (by default) `kanbus-feature-videos/`
- Amplify rewrite rule correctness
- `https://kanb.us/videos/<asset>` returns `302`
- CDN targets return `200`
- MP4 audio stream present and active (not silent)

Success marker:

```text
PRODUCTION_VIDEO_VERIFY_OK
```

## Configure rewrite only

```bash
AWS_PROFILE=anthus VIDEOS_PREFIX=videos scripts/configure-video-rewrite.sh
```

Success marker:

```text
CONFIGURE_REWRITE_OK
```
