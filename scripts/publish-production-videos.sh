#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

AWS_PROFILE="${AWS_PROFILE:-anthus}"
PRIMARY_PREFIX="${PRIMARY_PREFIX:-videos}"
MIRROR_PREFIX="${MIRROR_PREFIX:-kanbus-feature-videos}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/videos/out}"

ensure_alias_asset() {
  local target="$1"
  local source="$2"
  if [ -f "$target" ]; then
    return 0
  fi
  if [ ! -f "$source" ]; then
    echo "PUBLISH_FAILED: missing source alias asset: $source" >&2
    exit 1
  fi
  cp -f "$source" "$target"
  echo "Created alias asset: ${target##*/} <- ${source##*/}"
}

echo "Publishing production videos"
echo "==========================="
echo "AWS_PROFILE: ${AWS_PROFILE}"
echo "PRIMARY_PREFIX: ${PRIMARY_PREFIX}"
echo "MIRROR_PREFIX: ${MIRROR_PREFIX}"
echo

echo "[0/4] Ensure compatibility alias assets"
ensure_alias_asset "${OUT_DIR}/intro-poster.jpg" "${OUT_DIR}/intro.jpg"
ensure_alias_asset "${OUT_DIR}/kanban-board.mp4" "${OUT_DIR}/core-management.mp4"
ensure_alias_asset "${OUT_DIR}/kanban-board.jpg" "${OUT_DIR}/core-management.jpg"
echo

echo "[1/4] Ensure production rewrite rule"
AWS_PROFILE="${AWS_PROFILE}" VIDEOS_PREFIX="${PRIMARY_PREFIX}" \
  scripts/configure-video-rewrite.sh
echo

echo "[2/4] Upload primary prefix (${PRIMARY_PREFIX})"
AWS_PROFILE="${AWS_PROFILE}" VIDEOS_PREFIX="${PRIMARY_PREFIX}" \
  node scripts/upload-videos.js --profile="${AWS_PROFILE}"
echo

echo "[3/4] Upload mirror prefix (${MIRROR_PREFIX})"
AWS_PROFILE="${AWS_PROFILE}" VIDEOS_PREFIX="${MIRROR_PREFIX}" \
  node scripts/upload-videos.js --profile="${AWS_PROFILE}"
echo

echo "[4/4] Verify production URLs + S3 keys + MP4 audio"
AWS_PROFILE="${AWS_PROFILE}" VIDEOS_PREFIX="${PRIMARY_PREFIX}" \
  scripts/verify-production-videos.sh
echo

echo "PUBLISH_AND_VERIFY_OK"
