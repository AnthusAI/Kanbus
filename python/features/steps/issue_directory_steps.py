"""Behave steps that place non-issue files beside issue JSON files."""

from __future__ import annotations

from behave import given

from features.steps.shared import load_project_directory


@given("a non-issue file exists in the issues directory")
def given_non_issue_file(context: object) -> None:
    """Write a plain-text file into the shared issues directory.

    :param context: Behave context object.
    :type context: object
    """
    project_dir = load_project_directory(context)
    notes_path = project_dir / "issues" / "notes.txt"
    notes_path.write_text("ignore", encoding="utf-8")


@given("a non-issue file exists in the local issues directory")
def given_non_issue_file_local(context: object) -> None:
    """Write a plain-text file into the project-local issues directory.

    :param context: Behave context object.
    :type context: object
    """
    project_dir = load_project_directory(context)
    local_dir = project_dir.parent / "project-local" / "issues"
    local_dir.mkdir(parents=True, exist_ok=True)
    notes_path = local_dir / "notes.txt"
    notes_path.write_text("ignore", encoding="utf-8")
