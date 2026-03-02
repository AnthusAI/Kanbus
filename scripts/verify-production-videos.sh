#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

AWS_PROFILE="${AWS_PROFILE:-anthus}"
VIDEOS_PREFIX="${VIDEOS_PREFIX:-videos}"
MIRROR_PREFIX="${MIRROR_PREFIX:-kanbus-feature-videos}"
VERIFY_MIRROR="${VERIFY_MIRROR:-1}"
VERIFY_REWRITE="${VERIFY_REWRITE:-1}"
AMPLIFY_APP_ID="${AMPLIFY_APP_ID:-d2h5foxy5ng19a}"
PROD_BASE_URL="${PROD_BASE_URL:-https://kanb.us}"
AMPLIFY_OUTPUTS="${ROOT_DIR}/amplify_outputs.json"

if [ ! -f "$AMPLIFY_OUTPUTS" ]; then
  echo "VERIFY_FAILED: missing ${AMPLIFY_OUTPUTS}" >&2
  exit 1
fi

VIDEOS_BUCKET="${VIDEOS_BUCKET:-$(jq -r '.custom.videosBucketName // empty' "$AMPLIFY_OUTPUTS")}"
VIDEOS_CDN_BASE="${VIDEOS_CDN_BASE:-$(jq -r '.custom.videosCdnUrl // empty' "$AMPLIFY_OUTPUTS")}"

if [ -z "$VIDEOS_BUCKET" ] || [ "$VIDEOS_BUCKET" = "null" ]; then
  echo "VERIFY_FAILED: missing videos bucket (set VIDEOS_BUCKET or custom.videosBucketName)" >&2
  exit 1
fi

if [ -z "$VIDEOS_CDN_BASE" ] || [ "$VIDEOS_CDN_BASE" = "null" ]; then
  echo "VERIFY_FAILED: missing videos CDN base (set VIDEOS_CDN_BASE or custom.videosCdnUrl)" >&2
  exit 1
fi
VIDEOS_CDN_BASE="${VIDEOS_CDN_BASE%/}"

EXPECTED_ASSETS="$(node - <<'NODE'
const fs = require("fs");
const src = fs.readFileSync("apps/kanb.us/src/content/videos.ts", "utf8");
const names = [...src.matchAll(/filename:\s*"([^"]+)"/g)].map((m) => m[1]);
const posters = [...src.matchAll(/poster:\s*"([^"]+)"/g)].map((m) => m[1]);
const extras = ["intro-poster.jpg"];
const all = Array.from(new Set([...names, ...posters, ...extras])).sort();
process.stdout.write(all.join("\n"));
NODE
)"

if [ -z "$EXPECTED_ASSETS" ]; then
  echo "VERIFY_FAILED: no expected assets discovered" >&2
  exit 1
fi

FAIL=0

run_with_timeout() {
  local seconds="$1"
  shift
  perl -e 'my $t = shift @ARGV; alarm $t; exec @ARGV' "$seconds" "$@"
}

echo "Production Video Verification"
echo "============================="
echo "AWS_PROFILE: ${AWS_PROFILE}"
echo "VIDEOS_BUCKET: ${VIDEOS_BUCKET}"
echo "VIDEOS_PREFIX: ${VIDEOS_PREFIX}"
echo "MIRROR_PREFIX: ${MIRROR_PREFIX}"
echo "VERIFY_MIRROR: ${VERIFY_MIRROR}"
echo "VERIFY_REWRITE: ${VERIFY_REWRITE}"
echo "AMPLIFY_APP_ID: ${AMPLIFY_APP_ID}"
echo "VIDEOS_CDN_BASE: ${VIDEOS_CDN_BASE}"
echo "PROD_BASE_URL: ${PROD_BASE_URL}"
echo

if [ "$VERIFY_REWRITE" = "1" ]; then
  expected_rule_target="${VIDEOS_CDN_BASE}/${VIDEOS_PREFIX}/<*>"
  rewrite_count="$(
    AWS_PROFILE="$AWS_PROFILE" aws amplify get-app --app-id "$AMPLIFY_APP_ID" --query 'app.customRules' --output json \
      | jq -r --arg src '/videos/<*>' --arg tgt "$expected_rule_target" \
        'map(select(.source == $src and .target == $tgt and .status == "302")) | length'
  )"
  if [ "$rewrite_count" -lt 1 ]; then
    echo "VERIFY_FAILED: missing expected Amplify rewrite rule /videos/<*> -> ${expected_rule_target} (302)" >&2
    FAIL=1
  else
    echo "Amplify rewrite rule check: OK (/videos/<*> -> ${expected_rule_target}, status=302)"
  fi
  echo
fi

printf "%-28s %-8s %-8s %-6s %-6s %-6s %-s\n" "FILE" "S3_KEY" "S3_MIR" "PROD" "CDN" "MIR" "REDIRECT"
while IFS= read -r asset; do
  [ -z "$asset" ] && continue

  if AWS_PROFILE="$AWS_PROFILE" aws s3api head-object --bucket "$VIDEOS_BUCKET" --key "${VIDEOS_PREFIX}/${asset}" >/dev/null 2>&1; then
    s3_key="YES"
  else
    s3_key="NO"
    FAIL=1
  fi

  if [ "$VERIFY_MIRROR" = "1" ]; then
    if AWS_PROFILE="$AWS_PROFILE" aws s3api head-object --bucket "$VIDEOS_BUCKET" --key "${MIRROR_PREFIX}/${asset}" >/dev/null 2>&1; then
      s3_mirror="YES"
    else
      s3_mirror="NO"
      FAIL=1
    fi
  else
    s3_mirror="SKIP"
  fi

  prod_status="$(curl -s -o /dev/null -w "%{http_code}" "${PROD_BASE_URL}/videos/${asset}")"
  cdn_status="$(curl -s -o /dev/null -w "%{http_code}" "${VIDEOS_CDN_BASE}/${VIDEOS_PREFIX}/${asset}")"
  if [ "$VERIFY_MIRROR" = "1" ]; then
    mirror_status="$(curl -s -o /dev/null -w "%{http_code}" "${VIDEOS_CDN_BASE}/${MIRROR_PREFIX}/${asset}")"
  else
    mirror_status="SKIP"
  fi
  redirect="$(curl -sI "${PROD_BASE_URL}/videos/${asset}" | sed -n 's/^location: //Ip' | tr -d '\r' | head -n1)"
  expected_redirect="${VIDEOS_CDN_BASE}/${VIDEOS_PREFIX}/${asset}"

  if [ "$prod_status" != "302" ] || [ "$cdn_status" != "200" ] || [ "$redirect" != "$expected_redirect" ]; then
    FAIL=1
  fi
  if [ "$VERIFY_MIRROR" = "1" ] && [ "$mirror_status" != "200" ]; then
    FAIL=1
  fi

  printf "%-28s %-8s %-8s %-6s %-6s %-6s %-s\n" \
    "$asset" "$s3_key" "$s3_mirror" "$prod_status" "$cdn_status" "$mirror_status" "${redirect:-none}"
done <<< "$EXPECTED_ASSETS"

echo
printf "%-28s %-8s %-10s %-12s\n" "MP4" "A_STREAM" "DUR_SEC" "MEAN_VOL_DB"
while IFS= read -r asset; do
  case "$asset" in
    *.mp4)
      url="${PROD_BASE_URL}/videos/${asset}"
      streams="ERR"
      duration="ERR"
      mean_volume="ERR"

      if stream_out="$(run_with_timeout 60 ffprobe -v error -select_streams a:0 -show_entries stream=codec_type -of csv=p=0 "$url" 2>/dev/null)"; then
        streams="$(printf "%s\n" "$stream_out" | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' ')"
      else
        FAIL=1
      fi

      if duration_out="$(run_with_timeout 60 ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$url" 2>/dev/null)"; then
        duration="$(printf "%s\n" "$duration_out" | awk '{printf "%.2f", $1}')"
      else
        FAIL=1
      fi

      if volume_out="$(run_with_timeout 75 ffmpeg -hide_banner -nostats -t 10 -i "$url" -vn -af volumedetect -f null /dev/null 2>&1)"; then
        mean_volume="$(printf "%s\n" "$volume_out" | sed -n 's/.*mean_volume: \([-0-9.]* dB\).*/\1/p' | tail -n1)"
        if [ -z "$mean_volume" ]; then
          mean_volume="N/A"
        fi
      else
        FAIL=1
      fi

      if [ "$streams" = "ERR" ] || [ "$streams" -lt 1 ]; then
        FAIL=1
      fi

      printf "%-28s %-8s %-10s %-12s\n" "$asset" "$streams" "$duration" "$mean_volume"
      ;;
  esac
done <<< "$EXPECTED_ASSETS"

if [ "$FAIL" -ne 0 ]; then
  echo
  echo "PRODUCTION_VIDEO_VERIFY_FAILED" >&2
  exit 1
fi

echo
echo "PRODUCTION_VIDEO_VERIFY_OK"
