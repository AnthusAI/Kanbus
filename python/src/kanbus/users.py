"""User identification helpers."""

from __future__ import annotations

import os


def get_current_user() -> str:
    """Return the current user identifier.

    :return: Current user identifier.
    :rtype: str
    """
    override = os.getenv("KANBUS_USER")
    if override is not None and override.strip():
        return override
    user = os.getenv("USER")
    if user:
        return user
    return "unknown"
