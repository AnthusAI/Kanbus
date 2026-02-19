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
    "console_port": None,
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
    "categories": [
        {"name": "To do", "color": "gray"},
        {"name": "In progress", "color": "blue"},
        {"name": "Done", "color": "green"},
    ],
    "statuses": [
        {"key": "open", "name": "Open", "category": "To do", "collapsed": False},
        {
            "key": "in_progress",
            "name": "In Progress",
            "category": "In progress",
            "collapsed": False,
        },
        {
            "key": "blocked",
            "name": "Blocked",
            "category": "In progress",
            "collapsed": True,
        },
        {"key": "closed", "name": "Done", "category": "Done", "collapsed": True},
        {"key": "deferred", "name": "Deferred", "category": "To do", "collapsed": True},
    ],
    "transition_labels": {
        "default": {
            "open": {
                "in_progress": "Start progress",
                "closed": "Close",
                "deferred": "Defer",
            },
            "in_progress": {"open": "Stop progress", "blocked": "Block", "closed": "Complete"},
            "blocked": {"in_progress": "Unblock", "closed": "Close"},
            "closed": {"open": "Reopen"},
            "deferred": {"open": "Resume", "closed": "Close"},
        },
        "epic": {
            "open": {"in_progress": "Start", "closed": "Complete"},
            "in_progress": {"open": "Pause", "closed": "Complete"},
            "closed": {"open": "Reopen"},
        },
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
