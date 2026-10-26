"""Fail when a test-only environment switch is read outside the test-hook gates.

Rust code must read KANBUS_TEST_* switches through ``crate::test_hooks``, which
compiles to a constant "not present" unless ``cfg(test)`` or the ``test-hooks``
cargo feature is active. Python code must read them through
``kanbus.test_hooks.read_test_hook``, which honours them only when
``KANBUS_ENABLE_TEST_HOOKS`` is set. Neither runtime may key behaviour on
``PYTEST_CURRENT_TEST``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

RUST_SOURCE_DIRECTORY = REPOSITORY_ROOT / "rust" / "src"
PYTHON_SOURCE_DIRECTORY = REPOSITORY_ROOT / "python" / "src"

RUST_RAW_READ_PATTERN = re.compile(r"\benv::var(?:_os)?\s*\(")
PYTHON_RAW_READ_PATTERN = re.compile(
    r"\bos\.getenv\s*\(|\benviron\.get\s*\(|\benviron\["
)
TEST_SWITCH_PATTERN = re.compile(r"KANBUS_TEST_|\bTEST_[A-Z_]+_ENV\b")
PYTEST_MARKER_PATTERN = re.compile(r"PYTEST_CURRENT_TEST")

RUST_GATE_FILE = RUST_SOURCE_DIRECTORY / "test_hooks.rs"
PYTHON_GATE_FILE = PYTHON_SOURCE_DIRECTORY / "kanbus" / "test_hooks.py"


def _rust_test_module_start(lines: List[str]) -> int:
    """Return the index of the first ``#[cfg(test)]`` line, or ``len(lines)``."""
    for index, line in enumerate(lines):
        if line.strip() == "#[cfg(test)]":
            return index
    return len(lines)


def _python_assignment_target(line: str) -> bool:
    """Return whether the line only writes to the environment."""
    return bool(re.search(r"environ\[[^\]]+\]\s*=[^=]", line))


def find_rust_violations() -> List[str]:
    """Collect raw Rust reads of test switches outside the gate module."""
    violations: List[str] = []
    for path in sorted(RUST_SOURCE_DIRECTORY.rglob("*.rs")):
        if path == RUST_GATE_FILE:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        production_end = _rust_test_module_start(lines)
        for index, line in enumerate(lines[:production_end]):
            if PYTEST_MARKER_PATTERN.search(line):
                violations.append(f"{path}:{index + 1}: PYTEST_CURRENT_TEST")
            if RUST_RAW_READ_PATTERN.search(line) and TEST_SWITCH_PATTERN.search(line):
                violations.append(f"{path}:{index + 1}: raw read of a test switch")
    return violations


def find_python_violations() -> List[str]:
    """Collect raw Python reads of test switches outside the gate module."""
    violations: List[str] = []
    for path in sorted(PYTHON_SOURCE_DIRECTORY.rglob("*.py")):
        if path == PYTHON_GATE_FILE:
            continue
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if PYTEST_MARKER_PATTERN.search(line):
                violations.append(f"{path}:{index + 1}: PYTEST_CURRENT_TEST")
            if _python_assignment_target(line):
                continue
            if PYTHON_RAW_READ_PATTERN.search(line) and TEST_SWITCH_PATTERN.search(
                line
            ):
                violations.append(f"{path}:{index + 1}: raw read of a test switch")
    return violations


def main() -> int:
    """Run the check and return the process exit code."""
    violations = find_rust_violations() + find_python_violations()
    if violations:
        print("Test switches must be read through the test-hook gates:")
        for violation in violations:
            print(f"  {violation}")
        return 1
    print("All test switches are read through the test-hook gates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
