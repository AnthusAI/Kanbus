#!/usr/bin/env bash
set -euo pipefail

echo "Running PyPI install smoke..."

WORK=/tmp/kanbus-smoke
rm -rf "$WORK"
mkdir -p "$WORK"
cd "$WORK"

echo "Initializing project with kanbus (PyPI)..."
git init >/dev/null
kanbus init

echo "Creating sample issues..."
kanbus create "Test issue A"
kanbus create "Test issue B"
kanbus create "Test issue C"

echo "Listing issues (kanbus / Python)..."
KANBUS_NO_DAEMON=1 kanbus list --status open --porcelain | tee /tmp/kanbus_python_list.txt

echo "Smoke test complete."
