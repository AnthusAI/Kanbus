#!/usr/bin/env bash
set -euo pipefail

# End-to-end "smoke test" / demo for realtime gossip + overlay without manual multi-terminal work.
#
# What it does:
# - creates an isolated temp git repo
# - initializes a Kanbus project
# - starts a UDS gossip broker on a temp socket
# - starts a watcher that prints envelopes (NDJSON) and writes overlay snapshots
# - mutates an issue (create/update/delete)
# - asserts the watcher observed the events and overlay files were written
#
# Usage:
#   bash scripts/demo-realtime.sh
#   bash scripts/demo-realtime.sh --stay
#   KANBUS_DEMO_KEEP=0 bash scripts/demo-realtime.sh

STAY=0
for arg in "$@"; do
  case "$arg" in
    --stay)
      STAY=1
      ;;
    -h|--help)
      echo "Usage: scripts/demo-realtime.sh [--stay]"
      echo ""
      echo "  --stay   Keep broker + watcher running after the smoke test so you can"
      echo "           run additional mutations in the temp repo and watch the stream."
      exit 0
      ;;
    *)
      echo "error: unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v cargo >/dev/null 2>&1; then
  echo "error: cargo not found" >&2
  exit 1
fi

# Prefer rg for speed if available, otherwise use grep.
have_rg=0
if command -v rg >/dev/null 2>&1; then
  have_rg=1
fi

echo "[demo] building rust kbs (debug) ..."
cargo build --manifest-path rust/Cargo.toml --bin kbs -q
KBS_BIN="$ROOT_DIR/rust/target/debug/kbs"
if [[ ! -x "$KBS_BIN" ]]; then
  echo "error: expected $KBS_BIN to exist after build" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
KEEP_TMP="${KANBUS_DEMO_KEEP:-1}"
cleanup() {
  set +e
  # Best-effort shutdown of child processes.
  if [[ -n "${WATCH_PID:-}" ]]; then
    kill "$WATCH_PID" >/dev/null 2>&1 || true
    wait "$WATCH_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${BROKER_PID:-}" ]]; then
    kill "$BROKER_PID" >/dev/null 2>&1 || true
    wait "$BROKER_PID" >/dev/null 2>&1 || true
  fi
  if [[ "$KEEP_TMP" == "0" ]]; then
    rm -rf "$TMP_DIR" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[demo] temp repo: $TMP_DIR"
cd "$TMP_DIR"
git init -q

# Initialize Kanbus project in the temp repo.
"$KBS_BIN" init >/dev/null

# Use a repo-local socket so this demo doesn't conflict with any running broker.
mkdir -p "$TMP_DIR/.kanbus/run"
SOCKET_PATH="$TMP_DIR/.kanbus/run/bus.sock"

# Ensure all subprocesses use UDS and the socket path we chose.
export KANBUS_REALTIME_TRANSPORT="uds"
export KANBUS_REALTIME_UDS_SOCKET_PATH="$SOCKET_PATH"

WATCH_LOG="$TMP_DIR/watch.ndjson"

echo "[demo] starting broker (uds) ..."
"$KBS_BIN" gossip broker --socket "$SOCKET_PATH" >/dev/null 2>&1 &
BROKER_PID="$!"

echo "[demo] starting watcher (print + overlay writes) ..."
"$KBS_BIN" gossip watch --transport uds --print >"$WATCH_LOG" 2>"$TMP_DIR/watch.stderr" &
WATCH_PID="$!"

wait_for_file() {
  local path="$1"
  local seconds="$2"
  local start
  start="$(date +%s)"
  while true; do
    if [[ -S "$path" ]]; then
      return 0
    fi
    if [[ $(( $(date +%s) - start )) -ge "$seconds" ]]; then
      return 1
    fi
    sleep 0.05
  done
}

if ! wait_for_file "$SOCKET_PATH" 5; then
  echo "error: broker socket not created at $SOCKET_PATH" >&2
  exit 1
fi

echo "[demo] producing mutations ..."
CREATE_OUT="$("$KBS_BIN" create "Demo realtime task")"
# The CLI may print a shortened identifier. Derive the canonical id from the issue JSON file.
ISSUE_PATH="$(ls -t "$TMP_DIR/project/issues/"*.json 2>/dev/null | head -n 1 || true)"
if [[ -z "${ISSUE_PATH:-}" ]]; then
  echo "error: expected an issue file under project/issues after create" >&2
  echo "$CREATE_OUT" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 not found (needed to parse issue id from json)" >&2
  exit 1
fi
ISSUE_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], "r", encoding="utf-8"))["id"])' "$ISSUE_PATH")"
if [[ -z "${ISSUE_ID:-}" ]]; then
  echo "error: failed to derive issue id from $ISSUE_PATH" >&2
  exit 1
fi

"$KBS_BIN" update "$ISSUE_ID" --status in_progress >/dev/null
"$KBS_BIN" delete "$ISSUE_ID" >/dev/null

echo "[demo] waiting for watcher to observe envelopes ..."
deadline=$(( $(date +%s) + 5 ))
while [[ $(date +%s) -lt "$deadline" ]]; do
  if [[ "$have_rg" -eq 1 ]]; then
    if rg -q "\"issue_id\"\\s*:\\s*\"$ISSUE_ID\"" "$WATCH_LOG" && rg -q "\"type\"\\s*:\\s*\"issue\\.deleted\"" "$WATCH_LOG"; then
      break
    fi
  else
    if grep -q "\"issue_id\"[[:space:]]*:[[:space:]]*\"$ISSUE_ID\"" "$WATCH_LOG" && grep -q "\"type\"[[:space:]]*:[[:space:]]*\"issue.deleted\"" "$WATCH_LOG"; then
      break
    fi
  fi
  sleep 0.05
done

if [[ "$have_rg" -eq 1 ]]; then
  if ! rg -q "\"issue_id\"\\s*:\\s*\"$ISSUE_ID\"" "$WATCH_LOG"; then
    echo "error: watcher did not print any envelope for issue_id=$ISSUE_ID" >&2
    tail -n 20 "$WATCH_LOG" >&2 || true
    exit 1
  fi
else
  if ! grep -q "\"issue_id\"[[:space:]]*:[[:space:]]*\"$ISSUE_ID\"" "$WATCH_LOG"; then
    echo "error: watcher did not print any envelope for issue_id=$ISSUE_ID" >&2
    tail -n 20 "$WATCH_LOG" >&2 || true
    exit 1
  fi
fi

OVERLAY_PATH="$TMP_DIR/project/.overlay/issues/$ISSUE_ID.json"
if [[ ! -f "$OVERLAY_PATH" ]]; then
  echo "error: expected overlay snapshot at $OVERLAY_PATH" >&2
  echo "watch stderr:" >&2
  tail -n 50 "$TMP_DIR/watch.stderr" >&2 || true
  echo "watch log (tail):" >&2
  tail -n 20 "$WATCH_LOG" >&2 || true
  exit 1
fi

if [[ "$have_rg" -eq 1 ]]; then
  rg -q "\"id\"\\s*:\\s*\"$ISSUE_ID\"" "$OVERLAY_PATH" || {
    echo "error: overlay snapshot does not contain expected id=$ISSUE_ID" >&2
    exit 1
  }
else
  grep -q "\"id\"[[:space:]]*:[[:space:]]*\"$ISSUE_ID\"" "$OVERLAY_PATH" || {
    echo "error: overlay snapshot does not contain expected id=$ISSUE_ID" >&2
    exit 1
  }
fi

echo "[demo] OK"
echo "[demo] issue_id: $ISSUE_ID"
echo "[demo] watcher log: $WATCH_LOG"
echo "[demo] overlay snapshot: $OVERLAY_PATH"
echo "[demo] socket: $SOCKET_PATH"
if [[ "$KEEP_TMP" == "1" ]]; then
  echo "[demo] temp repo kept (set KANBUS_DEMO_KEEP=0 to auto-delete): $TMP_DIR"
fi

if [[ "$STAY" == "1" ]]; then
  echo ""
  echo "[demo] staying alive. In another terminal, try:"
  echo "  cd \"$TMP_DIR\""
  echo "  \"$KBS_BIN\" create \"Another task\""
  echo "  \"$KBS_BIN\" update <ISSUE_ID> --status in_progress"
  echo "  \"$KBS_BIN\" delete <ISSUE_ID>"
  echo ""
  echo "[demo] and watch the stream:"
  echo "  tail -f \"$WATCH_LOG\""
  echo ""
  echo "[demo] Ctrl-C to stop broker + watcher."
  while kill -0 "$WATCH_PID" >/dev/null 2>&1; do
    sleep 0.5
  done
fi
