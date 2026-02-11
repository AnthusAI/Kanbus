"""User identification helpers."""

from __future__ import annotations

import getpass
import os


def get_current_user() -> str:
    """Return the current user identifier.

    :return: Current user identifier.
    :rtype: str
    """
    override = os.getenv("TASKULUS_USER")
    if override:
        return override
    return getpass.getuser()
