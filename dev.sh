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

echo "═══════════════════════════════════════════════════════════════"
echo "Kanbus Development Server (Watch Mode)"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Starting:"
echo "  • UI styles watcher (packages/ui) → copies CSS changes to dist/"
echo "  • UI TypeScript watcher (packages/ui)"
echo "  • Console dev server (apps/console) → Vite + API"
echo ""
echo "The console will be available at: http://127.0.0.1:5173"
echo "Console API will be available at: http://127.0.0.1:5174"
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
done) > /tmp/kanbus-ui-watcher.log 2>&1 &
UI_WATCHER_PID=$!
echo "  UI Watcher PID: $UI_WATCHER_PID"

# Start UI TypeScript watcher in background
echo "Starting UI TypeScript watcher..."
cd "$UI_DIR" || exit 1
npm run dev > /tmp/kanbus-ui-tsc.log 2>&1 &
UI_TSC_PID=$!
echo "  UI TSC PID: $UI_TSC_PID"

# Start console dev server (Vite + API) in background
echo "Starting console dev server..."
cd "$CONSOLE_DIR" || exit 1
npm run dev > /tmp/kanbus-console-dev.log 2>&1 &
CONSOLE_DEV_PID=$!
echo "  Console Dev PID: $CONSOLE_DEV_PID"

echo ""
echo "✓ Development servers started"
echo ""

# Wait for all processes
wait $UI_WATCHER_PID $UI_TSC_PID $CONSOLE_DEV_PID 2>/dev/null || true
