#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TARGETS_CONFIG="${VIDEO_DEPLOY_TARGETS_CONFIG:-${ROOT_DIR}/config/video-deploy.targets.json}"
VIDEO_DEPLOY_TARGET="${VIDEO_DEPLOY_TARGET:-production}"
CONFIRM_LOCAL_PREVIEW="${CONFIRM_LOCAL_PREVIEW:-0}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/videos/out}"

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --confirm-local-preview)
        CONFIRM_LOCAL_PREVIEW=1
        shift
        ;;
      --target)
        if [ "$#" -lt 2 ]; then
          echo "PUBLISH_FAILED: --target requires a value" >&2
          exit 1
        fi
        VIDEO_DEPLOY_TARGET="$2"
        shift 2
        ;;
      --target=*)
        VIDEO_DEPLOY_TARGET="${1#--target=}"
        shift
        ;;
      *)
        echo "PUBLISH_FAILED: unknown option '$1'" >&2
        exit 1
        ;;
    esac
  done
}

parse_args "$@"

if [ ! -f "$TARGETS_CONFIG" ]; then
  echo "PUBLISH_FAILED: missing target config ${TARGETS_CONFIG}" >&2
  exit 1
fi

TARGET_AWS_PROFILE="$(jq -r --arg t "$VIDEO_DEPLOY_TARGET" '.[$t].awsProfile // empty' "$TARGETS_CONFIG")"
TARGET_BUCKET="$(jq -r --arg t "$VIDEO_DEPLOY_TARGET" '.[$t].bucket // empty' "$TARGETS_CONFIG")"
TARGET_PRIMARY_PREFIX="$(jq -r --arg t "$VIDEO_DEPLOY_TARGET" '.[$t].primaryPrefix // empty' "$TARGETS_CONFIG")"
TARGET_MIRROR_PREFIX="$(jq -r --arg t "$VIDEO_DEPLOY_TARGET" '.[$t].mirrorPrefix // empty' "$TARGETS_CONFIG")"
TARGET_CLOUDFRONT_DOMAIN="$(jq -r --arg t "$VIDEO_DEPLOY_TARGET" '.[$t].cloudfrontDomain // empty' "$TARGETS_CONFIG")"
TARGET_CLOUDFRONT_DISTRIBUTION_ID="$(jq -r --arg t "$VIDEO_DEPLOY_TARGET" '.[$t].cloudfrontDistributionId // empty' "$TARGETS_CONFIG")"

if [ -z "$TARGET_AWS_PROFILE" ] || [ -z "$TARGET_BUCKET" ] || [ -z "$TARGET_PRIMARY_PREFIX" ] || [ -z "$TARGET_MIRROR_PREFIX" ] || [ -z "$TARGET_CLOUDFRONT_DOMAIN" ] || [ -z "$TARGET_CLOUDFRONT_DISTRIBUTION_ID" ]; then
  echo "PUBLISH_FAILED: target '${VIDEO_DEPLOY_TARGET}' in ${TARGETS_CONFIG} is missing required fields" >&2
  exit 1
fi

AWS_PROFILE="${AWS_PROFILE:-$TARGET_AWS_PROFILE}"
VIDEOS_BUCKET="${VIDEOS_BUCKET:-$TARGET_BUCKET}"
PRIMARY_PREFIX="${PRIMARY_PREFIX:-$TARGET_PRIMARY_PREFIX}"
MIRROR_PREFIX="${MIRROR_PREFIX:-$TARGET_MIRROR_PREFIX}"
VIDEOS_CDN_BASE="${VIDEOS_CDN_BASE:-https://${TARGET_CLOUDFRONT_DOMAIN}}"
CLOUDFRONT_DISTRIBUTION_ID="${CLOUDFRONT_DISTRIBUTION_ID:-$TARGET_CLOUDFRONT_DISTRIBUTION_ID}"

if [ "$CONFIRM_LOCAL_PREVIEW" != "1" ]; then
  echo "PUBLISH_FAILED: local preview confirmation required" >&2
  echo "Run with --confirm-local-preview (or set CONFIRM_LOCAL_PREVIEW=1) after reviewing local /videos output." >&2
  exit 1
fi

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
echo "TARGET: ${VIDEO_DEPLOY_TARGET}"
echo "AWS_PROFILE: ${AWS_PROFILE}"
echo "VIDEOS_BUCKET: ${VIDEOS_BUCKET}"
echo "PRIMARY_PREFIX: ${PRIMARY_PREFIX}"
echo "MIRROR_PREFIX: ${MIRROR_PREFIX}"
echo "VIDEOS_CDN_BASE: ${VIDEOS_CDN_BASE}"
echo "CLOUDFRONT_DISTRIBUTION_ID: ${CLOUDFRONT_DISTRIBUTION_ID}"
echo

echo "[0/5] Verify local assets and local /videos build"
scripts/verify-local-videos.sh
echo

echo "[1/5] Ensure compatibility alias assets"
ensure_alias_asset "${OUT_DIR}/intro-poster.jpg" "${OUT_DIR}/intro.jpg"
ensure_alias_asset "${OUT_DIR}/kanban-board.mp4" "${OUT_DIR}/core-management.mp4"
ensure_alias_asset "${OUT_DIR}/kanban-board.jpg" "${OUT_DIR}/core-management.jpg"
echo

echo "[2/5] Upload primary prefix (${PRIMARY_PREFIX})"
AWS_PROFILE="${AWS_PROFILE}" \
  VIDEOS_BUCKET="${VIDEOS_BUCKET}" \
  VIDEOS_PREFIX="${PRIMARY_PREFIX}" \
  node scripts/upload-videos.js --target="${VIDEO_DEPLOY_TARGET}" --profile="${AWS_PROFILE}"
echo

echo "[3/5] Upload mirror prefix (${MIRROR_PREFIX})"
AWS_PROFILE="${AWS_PROFILE}" \
  VIDEOS_BUCKET="${VIDEOS_BUCKET}" \
  VIDEOS_PREFIX="${MIRROR_PREFIX}" \
  node scripts/upload-videos.js --target="${VIDEO_DEPLOY_TARGET}" --profile="${AWS_PROFILE}"
echo

echo "[4/5] Invalidate CloudFront cache"
if [ "${PRIMARY_PREFIX}" = "${MIRROR_PREFIX}" ]; then
  INVALIDATION_PATHS=("/${PRIMARY_PREFIX}/*")
else
  INVALIDATION_PATHS=("/${PRIMARY_PREFIX}/*" "/${MIRROR_PREFIX}/*")
fi
AWS_PROFILE="${AWS_PROFILE}" aws cloudfront create-invalidation \
  --distribution-id "${CLOUDFRONT_DISTRIBUTION_ID}" \
  --paths "${INVALIDATION_PATHS[@]}" >/tmp/kanbus-video-invalidation.json
INVALIDATION_ID="$(jq -r '.Invalidation.Id // empty' /tmp/kanbus-video-invalidation.json)"
INVALIDATION_STATUS="$(jq -r '.Invalidation.Status // empty' /tmp/kanbus-video-invalidation.json)"
echo "CloudFront invalidation requested: ${INVALIDATION_ID} (${INVALIDATION_STATUS})"
echo

echo "[5/5] Verify production URLs + S3 keys + MP4 audio"
AWS_PROFILE="${AWS_PROFILE}" \
  VIDEOS_BUCKET="${VIDEOS_BUCKET}" \
  VIDEOS_CDN_BASE="${VIDEOS_CDN_BASE}" \
  VIDEOS_PREFIX="${PRIMARY_PREFIX}" \
  MIRROR_PREFIX="${MIRROR_PREFIX}" \
  scripts/verify-production-videos.sh
echo

echo "PUBLISH_AND_VERIFY_OK"
