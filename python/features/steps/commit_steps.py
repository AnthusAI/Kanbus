"""Behave steps for kbs commit."""

from __future__ import annotations

import subprocess

from pathlib import Path

from behave import given, then

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


@then("the events directory should be committed to git")
def then_project_events_committed_to_git(context: object) -> None:
    working_directory = Path(context.working_directory).resolve()
    project_dir = load_project_directory(context)
    events_path = (project_dir / "events").resolve()
    relative_events_path = events_path.relative_to(working_directory).as_posix()
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", relative_events_path],
        cwd=working_directory,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert not result.stdout.strip(), result.stdout


@then('the last commit message should be "{expected}"')
def then_last_commit_message_should_be(context: object, expected: str) -> None:
    working_directory = Path(context.working_directory).resolve()
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=working_directory,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == expected, result.stdout


def _event_files_under_project_events(context: object) -> list[Path]:
    events_dir = load_project_directory(context) / "events"
    if not events_dir.is_dir():
        return []
    return sorted(
        path
        for path in events_dir.iterdir()
        if path.suffix in {".json", ".jsonl"} and not path.name.startswith(".")
    )


@then("the events directory should contain event files")
def then_project_events_contain_event_files(context: object) -> None:
    assert _event_files_under_project_events(context), "expected event files"


@then("the events directory should contain no event files")
def then_project_events_contain_no_event_files(context: object) -> None:
    event_files = _event_files_under_project_events(context)
    assert not event_files, f"unexpected event files: {event_files}"


@given('the repository .gitignore contains "{rule}"')
def given_repository_gitignore_contains(context: object, rule: str) -> None:
    gitignore_path = Path(context.working_directory) / ".gitignore"
    existing = (
        gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    )
    separator = "" if not existing or existing.endswith("\n") else "\n"
    gitignore_path.write_text(f"{existing}{separator}{rule}\n", encoding="utf-8")
