"""
Project configuration defaults and writers.
"""

from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_HIERARCHY: List[str] = ["initiative", "epic", "task", "sub-task"]
DEFAULT_TYPES: List[str] = ["bug", "story", "chore"]

DEFAULT_CONFIGURATION: Dict[str, Any] = {
    "project_directory": "project",
    "external_projects": [],
    "project_key": "kanbus",
    "hierarchy": DEFAULT_HIERARCHY,
    "types": DEFAULT_TYPES,
    "workflows": {
        "default": {
            "open": ["in_progress", "closed", "deferred"],
            "in_progress": ["open", "blocked", "closed"],
            "blocked": ["in_progress", "closed"],
            "closed": ["open"],
            "deferred": ["open", "closed"],
        },
        "epic": {
            "open": ["in_progress", "closed"],
            "in_progress": ["open", "closed"],
            "closed": ["open"],
        },
    },
    "initial_status": "open",
    "priorities": {
        0: {"name": "critical", "color": "red"},
        1: {"name": "high", "color": "bright_red"},
        2: {"name": "medium", "color": "yellow"},
        3: {"name": "low", "color": "blue"},
        4: {"name": "trivial", "color": "white"},
    },
    "default_priority": 2,
    "assignee": None,
    "time_zone": None,
    "status_colors": {
        "open": "cyan",
        "in_progress": "blue",
        "blocked": "red",
        "closed": "green",
        "deferred": "yellow",
    },
    "type_colors": {
        "initiative": "bright_blue",
        "epic": "magenta",
        "task": "cyan",
        "sub-task": "bright_cyan",
        "bug": "red",
        "story": "yellow",
        "chore": "green",
        "event": "bright_blue",
    },
    "beads_compatibility": False,
}
