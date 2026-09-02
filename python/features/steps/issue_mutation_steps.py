"""Behave steps for issue mutation write-gate scenarios."""

from __future__ import annotations

from datetime import datetime, timezone

from behave import given, then

from features.steps.local_issue_steps import _local_project_directory
from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    write_issue_file,
)


def _parse_timestamp(timestamp: str) -> datetime:
    normalized = timestamp.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _read_issue_from_any_location(context: object, identifier: str):
    project_dir = load_project_directory(context)
    shared_path = project_dir / "issues" / f"{identifier}.json"
    if shared_path.exists():
        return read_issue_file(project_dir, identifier)
    local_dir = project_dir.parent / "project-local"
    return read_issue_file(local_dir, identifier)


@given('an issue "{identifier}" exists with updated_at "{updated_at}"')
def given_issue_exists_with_updated_at(
    context: object, identifier: str, updated_at: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    timestamp = _parse_timestamp(updated_at)
    issue = issue.model_copy(update={"updated_at": timestamp, "created_at": timestamp})
    write_issue_file(project_dir, issue)


@given('a local issue "{identifier}" exists with updated_at "{updated_at}"')
def given_local_issue_exists_with_updated_at(
    context: object, identifier: str, updated_at: str
) -> None:
    local_dir = _local_project_directory(context)
    issue = build_issue(identifier, "Local", "task", "open", None, [])
    timestamp = _parse_timestamp(updated_at)
    issue = issue.model_copy(update={"updated_at": timestamp, "created_at": timestamp})
    write_issue_file(local_dir, issue)


@given('issue "{identifier}" has updated_at "{updated_at}"')
def given_issue_has_updated_at(
    context: object, identifier: str, updated_at: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    timestamp = _parse_timestamp(updated_at)
    issue = issue.model_copy(update={"updated_at": timestamp})
    write_issue_file(project_dir, issue)


@then('issue "{identifier}" updated_at should be after "{updated_at}"')
def then_issue_updated_at_after(
    context: object, identifier: str, updated_at: str
) -> None:
    issue = _read_issue_from_any_location(context, identifier)
    threshold = _parse_timestamp(updated_at)
    actual = issue.updated_at
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    assert (
        actual > threshold
    ), f"expected updated_at after {updated_at}, got {issue.updated_at}"
