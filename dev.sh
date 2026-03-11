#!/bin/sh
# Kanbus Development Mode - Runs all necessary watchers for frontend and backend
# Usage: ./dev.sh
# This script will:
# 1. Run the console Vite dev server (apps/console)
# 2. Run the console dev API server (apps/console)
# 3. Exit cleanly when interrupted
# Works with any POSIX shell (sh, bash, zsh, etc.)

# Ensure we have a login shell environment with all tools available
export SHELL=/bin/zsh
if [ -f "$HOME/.zprofile" ]; then
  . "$HOME/.zprofile"
fi

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
CONSOLE_DIR="$REPO_ROOT/apps/console"
RUST_DIR="$REPO_ROOT/rust"
UI_DIR="$REPO_ROOT/packages/ui"
REPO_TAG="$(basename "$REPO_ROOT" | tr -cs 'A-Za-z0-9._-' '_')"
LOG_PREFIX="/tmp/kanbus-${REPO_TAG}-$$"
UI_WATCHER_LOG="${LOG_PREFIX}-ui-watcher.log"
UI_TSC_LOG="${LOG_PREFIX}-ui-tsc.log"
CONSOLE_DEV_LOG="${LOG_PREFIX}-console-dev.log"

CONFIG_PORT=""
CONFIG_HOST=""
if [ -f "$REPO_ROOT/.kanbus.yml" ]; then
  CONFIG_PORT=$(awk -F: '/^console_port:/ {gsub(/[[:space:]]/, "", $2); print $2; exit}' "$REPO_ROOT/.kanbus.yml")
  CONFIG_HOST=$(awk -F: '/^console_host:/ {gsub(/[[:space:]]/, "", $2); print $2; exit}' "$REPO_ROOT/.kanbus.yml")
fi

case "$CONFIG_PORT" in
  ''|*[!0-9]*)
    CONFIG_PORT=""
    ;;
esac

case "$CONFIG_HOST" in
  ''|*[^0-9A-Za-z\.\:\-]*)
    CONFIG_HOST=""
    ;;
esac

if [ -n "$CONFIG_PORT" ]; then
  DEFAULT_VITE_PORT="$CONFIG_PORT"
else
  DEFAULT_VITE_PORT="5173"
fi

DEFAULT_CONSOLE_PORT="5174"

VITE_PORT="${VITE_PORT:-$DEFAULT_VITE_PORT}"
CONSOLE_PORT="${CONSOLE_PORT:-$DEFAULT_CONSOLE_PORT}"
DEFAULT_HOST="${CONFIG_HOST:-0.0.0.0}"
CONSOLE_HOST="${CONSOLE_HOST:-$DEFAULT_HOST}"
VITE_HOST="${VITE_HOST:-$CONSOLE_HOST}"

CONSOLE_PROJECT_ROOT="${CONSOLE_PROJECT_ROOT:-$REPO_ROOT/project}"
KANBUS_PYTHONPATH="${KANBUS_PYTHONPATH:-$REPO_ROOT/python/src}"
KANBUS_PYTHON="${KANBUS_PYTHON:-conda}"
KANBUS_PYTHON_ARGS="${KANBUS_PYTHON_ARGS:-run -n py311 python}"

export VITE_PORT CONSOLE_PORT VITE_HOST CONSOLE_HOST CONSOLE_PROJECT_ROOT KANBUS_PYTHONPATH KANBUS_PYTHON KANBUS_PYTHON_ARGS

port_owner() {
  _port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$_port" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1 " (pid " $2 ")"}'
    return
  fi
  echo ""
}

find_free_port() {
  _start_port="$1"
  _label="$2"
  _port="$_start_port"
  while [ "$_port" -le 65535 ]; do
    _owner="$(port_owner "$_port")"
    if [ -z "$_owner" ]; then
      if [ "$_port" != "$_start_port" ]; then
        echo "NOTICE: ${_label} port ${_start_port} is in use; using ${_port} instead." >&2
      fi
      echo "$_port"
      return 0
    fi
    _port=$((_port + 1))
  done

  echo "ERROR: Could not find a free ${_label} port starting at ${_start_port}" >&2
  return 1
}

warn_existing_processes() {
  _warned=0

  if command -v pgrep >/dev/null 2>&1; then
    _kbsc_pids="$(pgrep -x kbsc 2>/dev/null | tr '\n' ' ' | awk '{$1=$1; print}')"
    if [ -n "$_kbsc_pids" ]; then
      echo "WARNING: Existing kbsc process(es): $_kbsc_pids"
      _warned=1
    fi
  fi

  _dev_candidates="$(ps -Ao pid=,command= | awk '$0 ~ /(^|[[:space:]])([.][/]|.*[/])dev[.]sh([[:space:]]|$)/ {print $1}')"
  _other_dev_pids=""
  for _pid in $_dev_candidates; do
    if [ "$_pid" != "$$" ] && [ "$_pid" != "$PPID" ]; then
      _other_dev_pids="${_other_dev_pids} ${_pid}"
    fi
  done
  _other_dev_pids="$(echo "$_other_dev_pids" | awk '{$1=$1; print}')"
  if [ -n "$_other_dev_pids" ]; then
    echo "WARNING: Existing dev.sh process(es): $_other_dev_pids"
    _warned=1
  fi

  if command -v lsof >/dev/null 2>&1; then
    _listeners="$(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk 'NR>1 && ($1 == "kbsc" || ($1 == "node" && $9 ~ /:(424[0-9]|517[0-9])$/)) {print $9 " (" $1 " pid " $2 ")"}')"
    if [ -n "$_listeners" ]; then
      echo "WARNING: Existing Kanbus listener(s):"
      echo "$_listeners" | sed 's/^/  - /'
      _warned=1
    fi
  fi

  if [ "$_warned" -eq 1 ]; then
    echo "WARNING: Continuing startup (warn + continue policy)."
    echo ""
  fi
}

warn_existing_processes

# Auto-select free ports up front so we don't boot partially and confuse API routing.
VITE_PORT="$(find_free_port "$VITE_PORT" "Vite")" || exit 1
if [ "$CONSOLE_PORT" = "$VITE_PORT" ]; then
  CONSOLE_PORT=$((CONSOLE_PORT + 1))
fi
CONSOLE_PORT="$(find_free_port "$CONSOLE_PORT" "Console API")" || exit 1
export VITE_PORT CONSOLE_PORT

ACCESS_HOST="$VITE_HOST"
if [ "$ACCESS_HOST" = "0.0.0.0" ]; then
  ACCESS_HOST="127.0.0.1"
fi

echo "═══════════════════════════════════════════════════════════════"
echo "Kanbus Development Server (Watch Mode)"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Starting:"
echo "  • UI styles watcher (packages/ui) → copies CSS changes to dist/"
echo "  • UI TypeScript watcher (packages/ui)"
echo "  • Console dev server (apps/console) → Vite + API"
echo ""
echo "The console will be available at: http://${VITE_HOST}:$VITE_PORT"
if [ "$VITE_HOST" = "0.0.0.0" ]; then
  echo "  (Use your LAN IP for other devices, e.g. \`ipconfig getifaddr en0\`)"
fi
echo "USE THIS URL NOW: http://${ACCESS_HOST}:$VITE_PORT"
echo "Console API will be available at: http://127.0.0.1:$CONSOLE_PORT"
echo "Logs:"
echo "  • $UI_WATCHER_LOG"
echo "  • $UI_TSC_LOG"
echo "  • $CONSOLE_DEV_LOG"
echo ""
echo "Press Ctrl+C to stop all services."
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Cleanup function to kill all background processes on exit
cleanup() {
  echo ""
  echo "Shutting down dev servers..."
  kill $UI_WATCHER_PID $UI_TSC_PID $CONSOLE_DEV_PID 2>/dev/null || true
  wait 2>/dev/null || true
  echo "Dev servers stopped."
}

trap cleanup EXIT INT TERM

# Start UI styles watcher in background
echo "Starting UI styles watcher..."
cd "$UI_DIR" || exit 1
(while true; do
  if [ -d "src/styles" ]; then
    cp -R src/styles dist/styles 2>/dev/null || mkdir -p dist && cp -R src/styles dist/styles
  fi
  sleep 2
done) > "$UI_WATCHER_LOG" 2>&1 &
UI_WATCHER_PID=$!
echo "  UI Watcher PID: $UI_WATCHER_PID"

# Start UI TypeScript watcher in background
echo "Starting UI TypeScript watcher..."
cd "$UI_DIR" || exit 1
npm run dev > "$UI_TSC_LOG" 2>&1 &
UI_TSC_PID=$!
echo "  UI TSC PID: $UI_TSC_PID"

# Start console dev server (Vite + API) in background
echo "Starting console dev server..."
cd "$CONSOLE_DIR" || exit 1
npm run dev > "$CONSOLE_DEV_LOG" 2>&1 &
CONSOLE_DEV_PID=$!
echo "  Console Dev PID: $CONSOLE_DEV_PID"

echo ""
echo "✓ Development servers started"
echo ""

# Wait for all processes
wait $UI_WATCHER_PID $UI_TSC_PID $CONSOLE_DEV_PID 2>/dev/null || true
