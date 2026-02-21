"""
Project configuration defaults and writers.
"""

from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_HIERARCHY: List[str] = ["initiative", "epic", "task", "sub-task"]
DEFAULT_TYPES: List[str] = ["bug", "story", "chore"]

DEFAULT_CONFIGURATION: Dict[str, Any] = {
    "project_directory": "project",
    "virtual_projects": {},
    "console_port": None,
    "project_key": "kanbus",
    "hierarchy": DEFAULT_HIERARCHY,
    "types": DEFAULT_TYPES,
    "workflows": {
        "default": {
            "backlog": ["open", "closed"],
            "open": ["in_progress", "closed", "backlog"],
            "in_progress": ["open", "blocked", "closed"],
            "blocked": ["in_progress", "closed"],
            "closed": ["open"],
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
        {"name": "To do", "color": "grey"},
        {"name": "In progress", "color": "blue"},
        {"name": "Done", "color": "green"},
    ],
    "statuses": [
        {"key": "backlog", "name": "Backlog", "category": "To do", "collapsed": True},
        {"key": "open", "name": "Discovery", "category": "To do", "collapsed": False},
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
    ],
    "transition_labels": {
        "default": {
            "backlog": {
                "open": "Start discovery",
                "closed": "Drop",
            },
            "open": {
                "in_progress": "Start work",
                "closed": "Drop",
                "backlog": "Back to backlog",
            },
            "in_progress": {
                "open": "Pause",
                "blocked": "Block",
                "closed": "Complete",
            },
            "blocked": {"in_progress": "Unblock", "closed": "Drop"},
            "closed": {"open": "Reopen"},
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
        "task": "blue",
        "sub-task": "bright_cyan",
        "bug": "red",
        "story": "yellow",
        "chore": "green",
        "event": "bright_blue",
    },
    "beads_compatibility": False,
}
