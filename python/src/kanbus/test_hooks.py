from __future__ import annotations

import os
from typing import Optional

TEST_HOOKS_ENABLE_VARIABLE = "KANBUS_ENABLE_TEST_HOOKS"


def are_test_hooks_enabled() -> bool:
    """Return whether test-only environment switches are honoured.

    Test switches change behaviour in ways no real user wants, so they are
    ignored unless the test runner explicitly opted in.
    """
    return os.environ.get(TEST_HOOKS_ENABLE_VARIABLE) == "1"


def read_test_hook(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return a test switch's value, or ``default`` when hooks are disabled."""
    if not are_test_hooks_enabled():
        return default
    return os.environ.get(name, default)
