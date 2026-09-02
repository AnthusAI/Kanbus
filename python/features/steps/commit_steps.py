"""Behave steps for kbs commit."""

from __future__ import annotations

import subprocess

from pathlib import Path

from behave import then

from features.steps.shared import load_project_directory


@then("project/issues should be committed to git")
def then_project_issues_committed_to_git(context: object) -> None:
    working_directory = Path(context.working_directory).resolve()
    project_dir = load_project_directory(context)
    issues_path = (project_dir / "issues").resolve()
    relative_issues_path = issues_path.relative_to(working_directory).as_posix()
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", relative_issues_path],
        cwd=working_directory,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert not result.stdout.strip(), result.stdout
