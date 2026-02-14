"""Behave steps for console snapshot."""

from __future__ import annotations

import yaml
from behave import given

from features.steps.shared import load_project_directory
from taskulus.config import DEFAULT_CONFIGURATION


@given("a Taskulus project with a console configuration file")
def given_taskulus_console_config(context: object) -> None:
    project_dir = load_project_directory(context)
    payload = _default_console_config()
    config_path = project_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _default_console_config() -> dict:
    priorities = {
        key: value["name"] for key, value in DEFAULT_CONFIGURATION["priorities"].items()
    }
    return {
        "prefix": DEFAULT_CONFIGURATION["project_key"],
        "hierarchy": DEFAULT_CONFIGURATION["hierarchy"],
        "types": DEFAULT_CONFIGURATION["types"],
        "workflows": DEFAULT_CONFIGURATION["workflows"],
        "initial_status": DEFAULT_CONFIGURATION["initial_status"],
        "priorities": priorities,
        "default_priority": DEFAULT_CONFIGURATION["default_priority"],
        "beads_compatibility": DEFAULT_CONFIGURATION.get("beads_compatibility", False),
    }
