#!/usr/bin/env bash
set -euo pipefail

echo "Running crates.io install smoke..."

WORK=/tmp/kanbus-smoke
rm -rf "$WORK"
mkdir -p "$WORK"
cd "$WORK"

echo "Initializing project with kanbus (Python CLI from PyPI) for fixture..."
python3.11 -m pip install --no-cache-dir --upgrade pip
python3.11 -m pip install --no-cache-dir kanbus
git init >/dev/null
kanbus init
kanbus create "Test issue A"
kanbus create "Test issue B"
kanbus create "Test issue C"

echo "Listing issues with Rust binary (kbs)..."
KANBUS_NO_DAEMON=1 kbs list --status open --porcelain | tee /tmp/kanbus_rust_list.txt

echo "Listing issues with Python binary (kanbus) for comparison..."
KANBUS_NO_DAEMON=1 kanbus list --status open --porcelain | tee /tmp/kanbus_python_list.txt

echo "Diffing outputs..."
if diff -u /tmp/kanbus_python_list.txt /tmp/kanbus_rust_list.txt; then
  echo "OK: Rust and Python outputs match."
else
  echo "FAIL: Outputs differ." >&2
  exit 1
fi

echo "Smoke test complete."
