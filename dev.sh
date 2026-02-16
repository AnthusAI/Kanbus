#!/bin/sh
# Kanbus Development Mode - Runs all necessary watchers for frontend and backend
# Usage: ./dev.sh
# This script will:
# 1. Watch and rebuild the console frontend (React/Vite)
# 2. Watch and rebuild/restart the Rust console backend
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

echo "═══════════════════════════════════════════════════════════════"
echo "Kanbus Development Server (Watch Mode)"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Starting:"
echo "  • UI styles watcher (packages/ui) → copies CSS changes to dist/"
echo "  • Frontend watcher (apps/console) → rebuilds to dist/"
echo "  • Rust backend (console_local) → auto-restarts on Rust changes"
echo ""
echo "The console will be available at: http://127.0.0.1:5174"
echo ""
echo "Press Ctrl+C to stop all services."
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Cleanup function to kill all background processes on exit
cleanup() {
  echo ""
  echo "Shutting down dev servers..."
  kill $UI_WATCHER_PID $FRONTEND_PID $BACKEND_PID 2>/dev/null || true
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

# Start frontend watcher in background
echo "Starting frontend watcher..."
cd "$CONSOLE_DIR" || exit 1
npm run build -- --watch > /tmp/kanbus-frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

# Give frontend watcher a moment to start
sleep 2s

# Start Rust backend with cargo-watch from the rust directory
echo "Starting Rust backend with auto-restart..."
cd "$RUST_DIR" || exit 1
cargo watch -x "run --bin console_local" &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

echo ""
echo "✓ Development servers started"
echo ""

# Wait for all processes
wait $UI_WATCHER_PID $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
