#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

AWS_PROFILE="${AWS_PROFILE:-anthus}"
AMPLIFY_APP_ID="${AMPLIFY_APP_ID:-d2h5foxy5ng19a}"
VIDEOS_PREFIX="${VIDEOS_PREFIX:-videos}"
AMPLIFY_OUTPUTS="${AMPLIFY_OUTPUTS:-${ROOT_DIR}/amplify_outputs.json}"

if [ ! -f "$AMPLIFY_OUTPUTS" ]; then
  echo "CONFIGURE_REWRITE_FAILED: missing ${AMPLIFY_OUTPUTS}" >&2
  exit 1
fi

VIDEOS_CDN_BASE="$(jq -r '.custom.videosCdnUrl // empty' "$AMPLIFY_OUTPUTS")"
if [ -z "$VIDEOS_CDN_BASE" ] || [ "$VIDEOS_CDN_BASE" = "null" ]; then
  echo "CONFIGURE_REWRITE_FAILED: missing custom.videosCdnUrl in ${AMPLIFY_OUTPUTS}" >&2
  exit 1
fi
VIDEOS_CDN_BASE="${VIDEOS_CDN_BASE%/}"
TARGET="${VIDEOS_CDN_BASE}/${VIDEOS_PREFIX}/<*>"

echo "Configure Amplify /videos rewrite"
echo "================================="
echo "AWS_PROFILE: ${AWS_PROFILE}"
echo "AMPLIFY_APP_ID: ${AMPLIFY_APP_ID}"
echo "VIDEOS_PREFIX: ${VIDEOS_PREFIX}"
echo "TARGET: ${TARGET}"
echo

AWS_PROFILE="$AWS_PROFILE" aws amplify update-app \
  --app-id "$AMPLIFY_APP_ID" \
  --custom-rules "[{\"source\":\"/videos/<*>\",\"target\":\"${TARGET}\",\"status\":\"302\"},{\"source\":\"/<*>\",\"target\":\"/index.html\",\"status\":\"404-200\"}]" \
  --query 'app.customRules' --output json >/tmp/configure-video-rewrite-rules.json

match_count="$(
  jq -r --arg src '/videos/<*>' --arg tgt "$TARGET" \
    'map(select(.source == $src and .target == $tgt and .status == "302")) | length' \
    /tmp/configure-video-rewrite-rules.json
)"
if [ "$match_count" -lt 1 ]; then
  echo "CONFIGURE_REWRITE_FAILED: rewrite rule not applied as expected" >&2
  cat /tmp/configure-video-rewrite-rules.json >&2
  exit 1
fi

echo "CONFIGURE_REWRITE_OK"
