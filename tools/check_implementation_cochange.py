#!/usr/bin/env python3
"""
Fail when a change touches only one of the two Kanbus implementations.

Rust (rust/src) and Python (python/src) are full, independent ports that must
stay in step. A pull request that changes one without the other needs the
'parity-exempt' label, which states that the change is intentionally
one-sided (tests, tooling, or a runtime-specific concern).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List

RUST_SOURCE_PREFIX = "rust/src/"
PYTHON_SOURCE_PREFIX = "python/src/"
EXEMPTION_LABEL = "parity-exempt"


def changed_files(base_reference: str) -> List[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{base_reference}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base ref, e.g. origin/develop")
    parser.add_argument(
        "--labels", default="", help="comma-separated pull request labels"
    )
    arguments = parser.parse_args()

    labels = {label.strip() for label in arguments.labels.split(",") if label.strip()}
    files = changed_files(arguments.base)
    rust_changed = [path for path in files if path.startswith(RUST_SOURCE_PREFIX)]
    python_changed = [path for path in files if path.startswith(PYTHON_SOURCE_PREFIX)]

    if bool(rust_changed) == bool(python_changed):
        print("implementation co-change: both implementations or neither changed")
        return 0
    if EXEMPTION_LABEL in labels:
        print(f"implementation co-change: one-sided change allowed by '{EXEMPTION_LABEL}'")
        return 0

    changed_side = "Rust" if rust_changed else "Python"
    missing_side = "Python" if rust_changed else "Rust"
    print(
        f"This change touches only the {changed_side} implementation. Port it to "
        f"{missing_side}, or add the '{EXEMPTION_LABEL}' label if it is intentionally one-sided."
    )
    for path in rust_changed or python_changed:
        print(f"  {path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
