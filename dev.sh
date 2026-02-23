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
CONFIG_FILE="$REPO_ROOT/.kanbus.yml"

resolve_console_port() {
  if [ -f "$CONFIG_FILE" ]; then
    port_line=$(awk -F: '/^console_port:/ { gsub(/[[:space:]]/, "", $2); print $2 }' "$CONFIG_FILE")
    if [ -n "$port_line" ]; then
      echo "$port_line"
      return
    fi
  fi
  echo ""
}

CONSOLE_PORT_RESOLVED="$(resolve_console_port)"

is_port_free() {
  port="$1"
  if command -v lsof >/dev/null 2>&1; then
    ! lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  if command -v nc >/dev/null 2>&1; then
    ! nc -z 127.0.0.1 "$port" >/dev/null 2>&1
    return $?
  fi
  return 0
}

wait_for_port() {
  port="$1"
  attempts="${2:-50}"
  while [ "$attempts" -gt 0 ]; do
    if command -v nc >/dev/null 2>&1; then
      if nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then
        return 0
      fi
    elif command -v lsof >/dev/null 2>&1; then
      if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
        return 0
      fi
    fi
    attempts=$((attempts - 1))
    sleep 0.2
  done
  return 1
}

find_free_port() {
  port="$1"
  while [ "$port" -lt 65535 ]; do
    if is_port_free "$port"; then
      echo "$port"
      return
    fi
    port=$((port + 1))
  done
  echo ""
}

# UI port: use project console_port unless VITE_PORT is explicitly set
if [ -z "${VITE_PORT:-}" ] && [ -n "$CONSOLE_PORT_RESOLVED" ]; then
  export VITE_PORT="$CONSOLE_PORT_RESOLVED"
fi
if [ -z "${VITE_HOST:-}" ]; then
  export VITE_HOST="127.0.0.1"
fi
if [ -n "${VITE_PORT:-}" ] && ! is_port_free "$VITE_PORT"; then
  bumped_port="$(find_free_port "$VITE_PORT")"
  if [ -n "$bumped_port" ]; then
    export VITE_PORT="$bumped_port"
  else
    echo "Error: UI port ${VITE_PORT} is already in use and no free port was found."
    exit 1
  fi
fi

resolve_python() {
  if [ -n "${KANBUS_PYTHON:-}" ]; then
    echo "$KANBUS_PYTHON"
    return
  fi
  if command -v conda >/dev/null 2>&1; then
    conda_py=$(conda run -n py311 python -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -n "$conda_py" ]; then
      echo "$conda_py"
      return
    fi
  fi
  if command -v python3.11 >/dev/null 2>&1; then
    echo "python3.11"
    return
  fi
  echo "python3"
}

# API port: allow override via CONSOLE_PORT; otherwise pick a free port starting at 5174
if [ -z "${CONSOLE_PORT:-}" ]; then
  free_port="$(find_free_port 5174)"
  if [ -n "$free_port" ]; then
    export CONSOLE_PORT="$free_port"
  else
    export CONSOLE_PORT="5174"
  fi
fi
if [ -n "${CONSOLE_PORT:-}" ] && ! is_port_free "$CONSOLE_PORT"; then
  bumped_api_port="$(find_free_port "$CONSOLE_PORT")"
  if [ -n "$bumped_api_port" ]; then
    export CONSOLE_PORT="$bumped_api_port"
  else
    echo "Error: Console API port ${CONSOLE_PORT} is already in use and no free port was found."
    exit 1
  fi
fi

# Ensure the console server uses a Python with the kanbus package available
export KANBUS_PYTHON="$(resolve_python)"

echo "═══════════════════════════════════════════════════════════════"
echo "Kanbus Development Server (Watch Mode)"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Starting:"
echo "  • UI styles watcher (packages/ui) → copies CSS changes to dist/"
echo "  • UI TypeScript watcher (packages/ui)"
echo "  • Console dev server (apps/console) → Vite + API"
echo ""
echo "The console will be available at: http://127.0.0.1:${VITE_PORT:-5173}"
echo "Console API will be available at: http://127.0.0.1:${CONSOLE_PORT}"
echo ""
echo "Press Ctrl+C to stop all services."
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Cleanup function to kill all background processes on exit
cleanup() {
  echo ""
  echo "Shutting down dev servers..."
  kill $UI_WATCHER_PID $UI_TSC_PID $FRONTEND_PID $BACKEND_PID $ASSET_SYNC_PID 2>/dev/null || true
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
done) > /tmp/kanbus-ui-watcher.log 2>&1 &
UI_WATCHER_PID=$!
echo "  UI Watcher PID: $UI_WATCHER_PID"

# Start UI TypeScript watcher in background
echo "Starting UI TypeScript watcher..."
cd "$UI_DIR" || exit 1
npm run dev > /tmp/kanbus-ui-tsc.log 2>&1 &
UI_TSC_PID=$!
echo "  UI TSC PID: $UI_TSC_PID"

# Start console Vite dev server (UI) in background
echo "Starting console dev server..."
cd "$CONSOLE_DIR" || exit 1
npm run dev:client > /tmp/kanbus-console-dev.log 2>&1 &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

# Keep embedded assets in sync with the watch build so the Rust server always
# serves the latest hashed files (prevents 404s for index-*.js/css).
# Runs in background; touches a stamp so cargo-watch notices updates.
echo "Starting embedded-asset sync..."
(
  set -e
  DIST_DIR="$CONSOLE_DIR/dist"
  TARGET_DIR="$RUST_DIR/embedded_assets/console"
  mkdir -p "$TARGET_DIR"
  while true; do
    if [ -d "$DIST_DIR" ]; then
      rsync -a --delete "$DIST_DIR/" "$TARGET_DIR/" >/tmp/kanbus-asset-sync.log 2>&1 || true
      touch "$TARGET_DIR/.stamp"
    fi
    sleep 2
  done
) &
ASSET_SYNC_PID=$!
echo "  Asset sync PID: $ASSET_SYNC_PID"

# Give frontend watcher a moment to start
sleep 2s

# Start Rust backend with cargo-watch from the rust directory
echo "Starting Rust backend with auto-restart..."
cd "$RUST_DIR" || exit 1
cargo watch -x "run --bin kbsc --features embed-assets" > /tmp/kanbus-backend.log 2>&1 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

if ! wait_for_port "${VITE_PORT:-5173}"; then
  echo ""
  echo "Vite dev server did not start on port ${VITE_PORT:-5173}."
  echo "Last 100 lines of /tmp/kanbus-console-dev.log:"
  tail -n 100 /tmp/kanbus-console-dev.log
  exit 1
fi

if ! wait_for_port "$CONSOLE_PORT"; then
  echo ""
  echo "Console API did not start on port ${CONSOLE_PORT}."
  echo "Last 100 lines of /tmp/kanbus-backend.log:"
  tail -n 100 /tmp/kanbus-backend.log
  exit 1
fi

echo ""
echo "✓ Development servers started"
echo ""

# Wait for all processes
wait $UI_WATCHER_PID $BACKEND_PID $FRONTEND_PID $ASSET_SYNC_PID 2>/dev/null || true
