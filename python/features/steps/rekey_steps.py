"""Behave steps for project rekey scenarios."""

from __future__ import annotations

from behave import when
from pathlib import Path
import yaml

from features.steps.shared import load_project_directory, run_cli


@when('I run "kanbus rekey {args}"')
def when_run_rekey(context: object, args: str) -> None:
    """Run the rekey command."""
    run_cli(context, f"kanbus rekey {args}")
