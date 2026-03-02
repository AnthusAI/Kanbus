#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-${ROOT_DIR}/videos/out}"
STATIC_VIDEOS_DIR="${STATIC_VIDEOS_DIR:-${ROOT_DIR}/apps/kanb.us/static/videos}"

EXPECTED_ASSETS="$(node - <<'NODE'
const fs = require("fs");
const src = fs.readFileSync("apps/kanb.us/src/content/videos.ts", "utf8");
const names = [...src.matchAll(/filename:\s*"([^"]+)"/g)].map((m) => m[1]);
const posters = [...src.matchAll(/poster:\s*"([^"]+)"/g)].map((m) => m[1]);
const all = Array.from(new Set([...names, ...posters])).sort();
process.stdout.write(all.join("\n"));
NODE
)"

if [ -z "$EXPECTED_ASSETS" ]; then
  echo "LOCAL_VIDEO_VERIFY_FAILED: no expected assets discovered from apps/kanb.us/src/content/videos.ts" >&2
  exit 1
fi

check_asset_set() {
  local label="$1"
  local dir="$2"
  local missing=0

  if [ ! -d "$dir" ]; then
    echo "LOCAL_VIDEO_VERIFY_FAILED: missing directory for ${label}: ${dir}" >&2
    return 1
  fi

  while IFS= read -r asset; do
    [ -z "$asset" ] && continue
    if [ ! -f "${dir}/${asset}" ]; then
      echo "LOCAL_VIDEO_VERIFY_FAILED: missing ${label} asset ${dir}/${asset}" >&2
      missing=1
    fi
  done <<< "$EXPECTED_ASSETS"

  if [ "$missing" -ne 0 ]; then
    return 1
  fi

  return 0
}

echo "Local Video Verification"
echo "========================"
echo "OUT_DIR: ${OUT_DIR}"
echo "STATIC_VIDEOS_DIR: ${STATIC_VIDEOS_DIR}"
echo

echo "[1/3] Verify rendered assets in videos/out"
check_asset_set "videos/out" "$OUT_DIR"
echo "OK"
echo

echo "[2/3] Verify copied assets in apps/kanb.us/static/videos"
check_asset_set "static/videos" "$STATIC_VIDEOS_DIR"
echo "OK"
echo

echo "[3/3] Verify Gatsby production build against /videos"
(
  cd apps/kanb.us
  GATSBY_VIDEOS_BASE_URL=/videos npm run build
)
echo "OK"
echo

echo "LOCAL_VIDEO_VERIFY_OK"
