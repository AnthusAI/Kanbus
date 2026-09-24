"""Behave steps for project rekey scenarios."""

from __future__ import annotations

import subprocess
from behave import given, when

from features.steps.shared import load_project_directory, run_cli


@given("the project directory has uncommitted changes")
def given_uncommitted_changes(context: object) -> None:
    """Create uncommitted changes in project/ directory."""
    project_dir = load_project_directory(context)
    test_file = project_dir / "test-change.txt"
    test_file.write_text("uncommitted")


@when('I run "kanbus rekey {args}"')
def when_run_rekey(context: object, args: str) -> None:
    """Run the rekey command."""
    # Commit any pending changes first (from issue creation)
    root = context.working_directory
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
        pass  # Ignore if not in git

    run_cli(context, f"kanbus rekey {args}")
