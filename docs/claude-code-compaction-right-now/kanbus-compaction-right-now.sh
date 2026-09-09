#!/usr/bin/env bash
# Example: reinject Kanbus WIP after Claude Code context compaction.
# Copy to .claude/hooks/ in your Kanbus repo. See README.md in this directory.

set -uo pipefail

KBS="${KBS:-kbs}"
TIMEOUT_SECONDS="${KANBUS_COMPACTION_HOOK_TIMEOUT_SECONDS:-5}"
PLACEHOLDER="(no right-now summary)"

run_with_timeout() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "${TIMEOUT_SECONDS}s" "$@"
  else
    "$@"
  fi
}

json_output=""
if ! json_output="$(run_with_timeout "$KBS" now --json --list 2>/dev/null)"; then
  exit 0
fi

if [[ -z "${json_output//[[:space:]]/}" ]]; then
  exit 0
fi

printf '%s' "$json_output" | python3 -c '
import json
import sys

placeholder = sys.argv[1]
raw = sys.stdin.read()
try:
    items = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(0)

if not isinstance(items, list) or not items:
    sys.exit(0)

print("Kanbus WIP (whole project, capped):")
print()

for item in items:
    if not isinstance(item, dict):
        continue
    issue_id = item.get("id", "?")
    title = item.get("title", "")
    status = item.get("status", "?")
    priority = item.get("priority", "?")
    summary = item.get("right_now_summary")
    if summary is None or summary == "":
        summary = placeholder
    print(f"- [P{priority}][{status}] {issue_id}: {title} — {summary}")
' "$PLACEHOLDER" || exit 0

exit 0
