"""
Project configuration defaults and writers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIGURATION: Dict[str, Any] = {
    "prefix": "tsk",
    "hierarchy": ["initiative", "epic", "task", "sub-task"],
    "types": ["bug", "story", "chore"],
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
        0: "critical",
        1: "high",
        2: "medium",
        3: "low",
        4: "trivial",
    },
    "default_priority": 2,
}


def write_default_configuration(path: Path) -> None:
    """Write the default configuration to the provided path.

    :param path: Path to the config.yaml file to write.
    :type path: Path
    """
    path.write_text(
        yaml.safe_dump(DEFAULT_CONFIGURATION, sort_keys=False),
        encoding="utf-8",
    )
