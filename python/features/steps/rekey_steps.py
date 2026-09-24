"""Behave steps for project rekey scenarios."""

from __future__ import annotations

import subprocess
from pathlib import Path
from behave import given, then, when
import yaml

from features.steps.shared import run_cli


@given("the project is committed to git")
def given_project_committed(context: object) -> None:
    """Commit the project to git."""
    root = Path(context.working_directory)
    try:
        # Configure git for tests
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=root,
            capture_output=True,
            check=False
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=root,
            capture_output=True,
            check=False
        )
        # Add and commit
        subprocess.run(
            ["git", "add", "-A"],
            cwd=root,
            capture_output=True,
            check=False
        )
        subprocess.run(
            ["git", "commit", "-m", "test setup"],
            cwd=root,
            capture_output=True,
            check=False
        )
    except Exception:
        pass


@given("the project directory has uncommitted changes")
def given_uncommitted_changes(context: object) -> None:
    """Create uncommitted changes in project/ directory."""
    from features.steps.shared import load_project_directory
    project_dir = load_project_directory(context)
    test_file = project_dir / "test-change.txt"
    test_file.write_text("uncommitted")


@when('I run "kanbus rekey {args}"')
def when_run_rekey(context: object, args: str) -> None:
    """Run the rekey command."""
    run_cli(context, f"kanbus rekey {args}")


@then('.kanbus.yml should have project_key "{key}"')
def then_project_key_in_file(context: object, key: str) -> None:
    """Verify project_key in .kanbus.yml file."""
    root = Path(context.working_directory)
    config_path = root / ".kanbus.yml"
    config_content = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config_content.get("project_key") == key, \
        f"Expected project_key '{key}' but got '{config_content.get('project_key')}'"
