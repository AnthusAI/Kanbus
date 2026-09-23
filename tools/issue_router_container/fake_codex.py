#!/usr/bin/env python3
"""Deterministic stand-in for ``codex exec --json`` used by the container harness.

The router calls it as ``<command> <args> exec --json ... <prompt>`` with the prompt
as the last argument. It reads the disposable test issue with ``kbs show`` exactly as
a real agent would, then reports one router result comment.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid

MARKER_RE = re.compile(r"KANBUS-ROUTER-TEST:[0-9a-f]+")
ISSUE_ID_RE = re.compile(
    r"kbs-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
MODES = ("complete", "hang")


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload), flush=True)


def _read_marker(issue_id: str) -> str | None:
    shown = subprocess.run(
        ["kbs", "show", issue_id], capture_output=True, text=True, check=False
    )
    match = MARKER_RE.search(shown.stdout)
    return match.group(0) if match else None


def _comment_text(marker: str) -> str:
    return (
        f"{marker} Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt.\n\n"
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco.\n\n"
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Duis aute irure dolor in reprehenderit in voluptate velit esse."
    )


def main() -> int:
    """Run the fake agent in the mode named by ``FAKE_CODEX_MODE``.

    :return: Process exit status.
    :rtype: int
    """
    mode = os.environ.get("FAKE_CODEX_MODE", "complete").strip()
    if mode not in MODES:
        print(f"FAKE_CODEX_MODE must be one of {MODES}, got {mode!r}", file=sys.stderr)
        return 2
    _emit({"type": "thread.started", "thread_id": f"fake-{uuid.uuid4().hex}"})
    if mode == "hang":
        while True:
            time.sleep(3600)
    prompt = sys.argv[-1]
    issue_ids = sorted(set(ISSUE_ID_RE.findall(prompt)))
    if len(issue_ids) != 1:
        print(
            "expected exactly one distinct package issue id in the prompt",
            file=sys.stderr,
        )
        return 3
    marker = _read_marker(issue_ids[0])
    if marker is None:
        print("test marker not found on the package issue", file=sys.stderr)
        return 3
    result = {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "Fake agent completed the disposable task.",
        "issue_updates": [],
        "issue_comments": [{"issue_id": issue_ids[0], "text": _comment_text(marker)}],
        "checkpoint": None,
        "artifacts": [],
    }
    _emit(
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "agent_message",
                "text": json.dumps(result),
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
