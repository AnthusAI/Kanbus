#!/usr/bin/env bash
set -euo pipefail

# One-terminal interactive demo for realtime gossip + overlay.
#
# - Uses a stable workspace directory (default: .kanbus/demo/realtime) so you never
#   have to copy temp paths.
# - Starts a UDS broker + watcher (watcher prints envelopes as NDJSON with a prefix).
# - Provides a small REPL so you can run create/update/delete commands while
#   watching the gossip stream scroll.
#
# Usage:
#   bash scripts/realtime-demo.sh
#   bash scripts/realtime-demo.sh --autoplay
#   bash scripts/realtime-demo.sh --workspace /path/to/workdir
#
# Commands inside the prompt:
#   create <title...>
#   update <id> <status>
#   delete <id>
#   help
#   quit

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WORKSPACE="$ROOT_DIR/.kanbus/demo/realtime"
AUTOPLAY=0
for arg in "$@"; do
  case "$arg" in
    --workspace=*)
      WORKSPACE="${arg#--workspace=}"
      ;;
    --autoplay)
      AUTOPLAY=1
      ;;
    -h|--help)
      echo "Usage: scripts/realtime-demo.sh [--autoplay] [--workspace=/path]"
      exit 0
      ;;
    *)
      echo "error: unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

if ! command -v cargo >/dev/null 2>&1; then
  echo "error: cargo not found" >&2
  exit 1
fi

echo "[demo] building rust kbs (debug) ..."
cargo build --manifest-path rust/Cargo.toml --bin kbs -q
KBS_BIN="$ROOT_DIR/rust/target/debug/kbs"
if [[ ! -x "$KBS_BIN" ]]; then
  echo "error: expected $KBS_BIN to exist after build" >&2
  exit 1
fi

mkdir -p "$WORKSPACE"
cd "$WORKSPACE"

cleanup() {
  set +e
  if [[ -n "${WATCH_PID:-}" ]]; then
    kill "$WATCH_PID" >/dev/null 2>&1 || true
    wait "$WATCH_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${BROKER_PID:-}" ]]; then
    kill "$BROKER_PID" >/dev/null 2>&1 || true
    wait "$BROKER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ ! -d ".git" ]]; then
  git init -q
fi

if [[ ! -f ".kanbus.yml" ]]; then
  # Initialize a default Kanbus project structure (writes .kanbus.yml + project/).
  "$KBS_BIN" init >/dev/null
fi

mkdir -p ".kanbus/run"
SOCKET_PATH="$WORKSPACE/.kanbus/run/bus.sock"

export KANBUS_REALTIME_TRANSPORT="uds"
export KANBUS_REALTIME_UDS_SOCKET_PATH="$SOCKET_PATH"

echo "[demo] workspace: $WORKSPACE"
echo "[demo] socket: $SOCKET_PATH"
echo "[demo] starting broker ..."
"$KBS_BIN" gossip broker --socket "$SOCKET_PATH" >/dev/null 2>&1 &
BROKER_PID="$!"

echo "[demo] starting watcher (printing envelopes) ..."
# Prefix each line so it's visually distinct from prompt output.
"$KBS_BIN" gossip watch --transport uds --print 2>/dev/null | sed -u 's/^/[gossip] /' &
WATCH_PID="$!"

if [[ "$AUTOPLAY" == "1" ]]; then
  echo "[demo] autoplay mode: generating mutations every ~2s. Ctrl-C to stop." >&2

  if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 not found (needed for parsing ids in autoplay mode)" >&2
    exit 1
  fi

  i=1
  while true; do
    title="Autoplay task $i"
    "$KBS_BIN" create "$title" >/dev/null 2>&1 || true
    issue_path="$(ls -t "$WORKSPACE/project/issues/"*.json 2>/dev/null | head -n 1 || true)"
    if [[ -n "$issue_path" ]]; then
      issue_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], "r", encoding="utf-8"))["id"])' "$issue_path" 2>/dev/null || true)"
      if [[ -n "$issue_id" ]]; then
        "$KBS_BIN" update "$issue_id" --status in_progress >/dev/null 2>&1 || true
        "$KBS_BIN" delete "$issue_id" >/dev/null 2>&1 || true
      fi
    fi
    i=$((i + 1))
    sleep 2
  done
fi

echo "[demo] ready. Type 'help' for commands."

print_help() {
  cat <<'EOF'
Commands:
  create <title...>         Create a new issue (prints ID).
  update <id> <status>      Update status (e.g. in_progress, blocked, closed).
  delete <id>               Delete the issue.
  help                      Show this help.
  quit                      Stop broker + watcher and exit.
EOF
}

while true; do
  # Use stderr for prompt so gossip output (stdout) stays clean if piped.
  printf "> " >&2
  if ! IFS= read -r line; then
    echo "" >&2
    break
  fi
  line="${line#"${line%%[![:space:]]*}"}"  # ltrim
  if [[ -z "$line" ]]; then
    continue
  fi

  cmd="${line%% *}"
  rest="${line#"$cmd"}"
  rest="${rest#"${rest%%[![:space:]]*}"}"

  case "$cmd" in
    help)
      print_help >&2
      ;;
    quit|exit)
      break
      ;;
    create)
      if [[ -z "$rest" ]]; then
        echo "error: create requires a title" >&2
        continue
      fi
      out="$("$KBS_BIN" create "$rest")" || true
      echo "$out" >&2
      ;;
    update)
      id="${rest%% *}"
      status="${rest#"$id"}"
      status="${status#"${status%%[![:space:]]*}"}"
      if [[ -z "$id" || -z "$status" || "$id" == "$rest" ]]; then
        echo "error: update requires: update <id> <status>" >&2
        continue
      fi
      "$KBS_BIN" update "$id" --status "$status" >&2 || true
      ;;
    delete)
      if [[ -z "$rest" ]]; then
        echo "error: delete requires an id" >&2
        continue
      fi
      "$KBS_BIN" delete "$rest" >&2 || true
      ;;
    *)
      echo "error: unknown command: $cmd (type 'help')" >&2
      ;;
  esac
done

echo "[demo] stopping..." >&2
