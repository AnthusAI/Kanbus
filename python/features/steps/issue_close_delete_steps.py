"""Behave steps for issue close and delete."""

from __future__ import annotations

from behave import then

from features.steps.shared import load_project_directory


@then('issue "kanbus-aaa" should not exist')
def then_issue_not_exists(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "kanbus-aaa.json"
    assert not issue_path.exists()
