#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)

CODEQL_VERSION="2.24.2"
TOOLS_DIR="${HOME}/.codeql-tools"
CODEQL_BIN="${TOOLS_DIR}/codeql/codeql"
WORK_DIR="${REPO_ROOT}/.codeql"
REPORT_DIR="${WORK_DIR}/reports"
CONFIG_FILE="${REPO_ROOT}/.github/codeql/codeql-config.yml"

DEFAULT_LANGS="python,javascript-typescript"

usage() {
  cat <<'EOF'
Run CodeQL code-quality analysis locally (mirrors GitHub "Code Quality" check)

Usage: tools/run_codeql_local.sh [options]

Options:
  --lang "py,js"   Comma-separated languages (default: python,javascript-typescript)
  --keep-db         Reuse existing databases instead of recreating
  --keep-reports    Do not delete prior SARIF reports before running
  --no-fail         Exit 0 even if findings exist
  -h, --help        Show this help

Outputs:
  - Databases:   .codeql/db-<lang>/
  - SARIF:       .codeql/reports/<lang>-code-quality.sarif

CodeQL CLI is auto-downloaded to .codeql-tools/ if not on PATH.
EOF
}

log() { echo "[codeql-local] $*"; }

err() { echo "[codeql-local][error] $*" >&2; }

langs=$DEFAULT_LANGS
keep_db=false
keep_reports=false
no_fail=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lang)
      langs="$2"; shift 2 ;;
    --keep-db) keep_db=true; shift ;;
    --keep-reports) keep_reports=true; shift ;;
    --no-fail) no_fail=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) err "Unknown option: $1"; usage; exit 1 ;;
  esac
done

IFS=',' read -r -a LANG_ARR <<<"$langs"

mkdir -p "$TOOLS_DIR" "$WORK_DIR" "$REPORT_DIR"

fetch_codeql() {
  if command -v codeql >/dev/null 2>&1; then
    CODEQL="$(command -v codeql)"
    log "Using system CodeQL: $CODEQL"
    return
  fi

  if [[ -x "$CODEQL_BIN" ]]; then
    log "Using downloaded CodeQL: $CODEQL_BIN"
    CODEQL="$CODEQL_BIN"
    return
  fi

  log "Downloading CodeQL CLI $CODEQL_VERSION to $TOOLS_DIR"
  platform=""
  case "$(uname -s)" in
    Linux) platform="linux64" ;;
    Darwin) platform="osx64" ;;
    *) err "Unsupported platform for CodeQL auto-download"; exit 1 ;;
  esac

  archive="codeql-bundle-${platform}.tar.gz"
  url="https://github.com/github/codeql-action/releases/download/codeql-bundle-v${CODEQL_VERSION}/${archive}"
  tmp="${TOOLS_DIR}/${archive}"
  curl -sSL "$url" -o "$tmp"
  tar -xzf "$tmp" -C "$TOOLS_DIR"
  rm -f "$tmp"

  # Bundle extracts to "$TOOLS_DIR/codeql/codeql"
  EXTRACTED_BIN="$TOOLS_DIR"/codeql/codeql
  if [[ ! -x "$EXTRACTED_BIN" ]]; then
    err "Downloaded CodeQL bundle missing binary at $EXTRACTED_BIN"
    exit 1
  fi

  chmod +x "$EXTRACTED_BIN"
  CODEQL="$EXTRACTED_BIN"
  log "Downloaded CodeQL to $CODEQL"
}

cleanup_reports() {
  $keep_reports && return
  rm -rf "$REPORT_DIR"
  mkdir -p "$REPORT_DIR"
}

cleanup_db() {
  local lang=$1
  $keep_db && return
  rm -rf "$WORK_DIR/db-${lang}"
}

run_lang() {
  local lang=$1
  local db_dir="$WORK_DIR/db-${lang}"
  local sarif="$REPORT_DIR/${lang}-code-quality.sarif"
  local lang_arg="$lang"
  local suite="codeql/${lang}-queries:codeql-suites/${lang}-code-quality.qls"

  if [[ "$lang" == "javascript-typescript" ]]; then
    lang_arg="javascript"
    suite="codeql/javascript-queries:codeql-suites/javascript-code-quality.qls"
  fi

  cleanup_db "$lang"

  log "Creating DB for ${lang}"
  create_opts=(
    "$db_dir"
    --language="$lang_arg"
    --source-root "$REPO_ROOT"
    --overwrite
    --threads=0
    --no-run-unnecessary-builds
  )
  if [[ -f "$CONFIG_FILE" ]]; then
    create_opts+=(--codescanning-config "$CONFIG_FILE")
  fi

  "$CODEQL" database create "${create_opts[@]}"

  log "Analyzing ${lang}"
  "$CODEQL" database analyze "$db_dir" "$suite" \
    --format=sarif-latest \
    --output "$sarif" \
    --threads=0 \
    --ram=6144 \
    --search-path "$TOOLS_DIR/codeql"

  log "Summary for ${lang}:"
  python - <<'PY' "$sarif" || true
import json, sys
path = sys.argv[1]
try:
    with open(path) as f:
        data = json.load(f)
except Exception as exc:
    print(f"Could not read {path}: {exc}")
    sys.exit(0)
counts = {}
for run in data.get("runs", []):
    for res in run.get("results", []):
        level = res.get("level", "warning")
        counts[level] = counts.get(level, 0) + 1
total = sum(counts.values())
for level in sorted(counts):
    print(f"{level}: {counts[level]}")
print(f"Total: {total}")
PY

  echo "SARIF: $sarif"
}

fetch_codeql
cleanup_reports

overall_status=0

for lang in "${LANG_ARR[@]}"; do
  run_lang "$lang" || overall_status=$?
done

if $no_fail; then
  exit 0
fi

exit $overall_status
