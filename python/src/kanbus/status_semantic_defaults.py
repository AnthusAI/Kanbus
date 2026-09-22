"""Derive a semantic category for a status that does not declare one.

Older project configurations predate ``semantic_category``. Rather than refuse to
load them, infer a category from the status key and name. An explicit value in
the configuration always wins; this only fills the gap.
"""

from __future__ import annotations

import re

_DONE_WORDS = frozenset(
    {
        "closed",
        "done",
        "complete",
        "completed",
        "resolved",
        "published",
        "shipped",
        "released",
        "archived",
        "cancelled",
        "canceled",
        "rejected",
        "accepted",
        "wontfix",
    }
)
_TODO_WORDS = frozenset(
    {
        "open",
        "backlog",
        "todo",
        "new",
        "idea",
        "ideas",
        "proposed",
        "planned",
        "inbox",
        "queued",
        "queue",
        "ready",
        "discovery",
        "triage",
    }
)


def derive_semantic_category(key: str, name: str = "") -> str:
    """Infer ``todo``, ``in_progress`` or ``done`` from a status key and name.

    Any word of the key or name that reads as a finished state gives ``done``,
    then any that reads as not started gives ``todo``; every other status
    (including ``blocked``) is treated as work in progress.
    """
    words = {word for word in re.split(r"[^a-z0-9]+", f"{key} {name}".lower()) if word}
    if words & _DONE_WORDS:
        return "done"
    if words & _TODO_WORDS:
        return "todo"
    return "in_progress"
