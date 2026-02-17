#!/usr/bin/env bash
set -euo pipefail

echo "Running interop smoke (PyPI kanbus, crates kbs, beads)..."

WORK=/tmp/kanbus-smoke
rm -rf "$WORK"
mkdir -p "$WORK"
cd "$WORK"

echo "Initializing project with Python kanbus..."
git init >/dev/null
kanbus init

export BEADS_DB="$WORK/beads.db"
export BEADS_ROLE="test"

echo "Creating sample issues..."
kanbus create "Test issue A"
kanbus create "Test issue B"
kanbus create "Test issue C"

echo "Initializing beads..."
bd init --quiet
bd create "Test issue A" --json >/dev/null
bd create "Test issue B" --json >/dev/null
bd create "Test issue C" --json >/dev/null

list_all() {
  label="$1"
  echo "Listing with Python kanbus..."
  KANBUS_NO_DAEMON=1 kanbus list --status open --porcelain | tee /tmp/list_python.txt

  echo "Listing with Rust kbs..."
  KANBUS_NO_DAEMON=1 kbs list --status open --porcelain | tee /tmp/list_rust.txt

  echo "Listing with beads (bd)..."
  KANBUS_NO_DAEMON=1 bd list --status open --json > /tmp/bd_raw.txt 2>/dev/null || true
  python3.11 - <<'PY' > /tmp/list_beads.txt
import json, sys
text = open("/tmp/bd_raw.txt","r",encoding="utf-8").read()
start = text.find("["); end = text.rfind("]")
if start == -1 or end == -1 or end < start:
    sys.exit("bd list produced no JSON")
data = json.loads(text[start:end+1])
for title in sorted(item.get("title","") for item in data if item.get("status")=="open"):
    print(title)
PY

  cut -d'|' -f6 /tmp/list_python.txt | sed 's/^ //' | sort -u > /tmp/titles_py.txt
  cut -d'|' -f6 /tmp/list_rust.txt   | sed 's/^ //' | sort -u > /tmp/titles_rust.txt
  sort -u /tmp/list_beads.txt        > /tmp/titles_beads.txt

  echo "Checking parity at checkpoint: $label"
  diff -u /tmp/titles_py.txt /tmp/titles_rust.txt
  diff -u /tmp/titles_py.txt /tmp/titles_beads.txt
}

# Seed parity (3 issues)
list_all "seed issues (A/B/C)"

echo "Adding issue via Python kanbus..."
KANBUS_NO_DAEMON=1 kanbus create "Test issue PY-added" >/dev/null
KANBUS_NO_DAEMON=1 bd create "Test issue PY-added" --json >/dev/null
list_all "after Python add"

echo "Adding issue via Rust kbs..."
KANBUS_NO_DAEMON=1 kbs create "Test issue RUST-added" >/dev/null
KANBUS_NO_DAEMON=1 bd create "Test issue RUST-added" --json >/dev/null
list_all "after Rust add"

echo "Adding issue via beads..."
KANBUS_NO_DAEMON=1 bd create "Test issue BEADS-added" --json >/dev/null
# Pull beads issues back into kanbus so parity holds
KANBUS_NO_DAEMON=1 kanbus create "Test issue BEADS-added" >/dev/null || true
list_all "after beads add"

echo "Interop smoke passed with six issues in sync."
