"""Behave steps for issue update."""

from __future__ import annotations

from behave import then, when

from features.steps.shared import load_project_directory, read_issue_file


@then('issue "kanbus-aaa" should have title "New Title"')
def then_issue_has_title(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    assert issue.title == "New Title"


@then('issue "kanbus-aaa" should have description "Updated description"')
def then_issue_has_description(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    assert issue.description == "Updated description"


@then('issue "kanbus-aaa" should have an updated_at timestamp')
def then_issue_has_updated_at(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    assert issue.updated_at is not None


@then('issue "{identifier}" should have parent "{parent_identifier}"')
def then_issue_has_parent(
    context: object, identifier: str, parent_identifier: str
) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.parent == parent_identifier
