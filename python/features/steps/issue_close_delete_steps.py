"""Behave steps for issue close and delete."""

from __future__ import annotations

from behave import then

from features.steps.shared import load_project_directory
from kanbus.project import find_project_local_directory


def _issue_path_for_identifier(context: object, identifier: str):
    project_dir = load_project_directory(context)
    path = project_dir / "issues" / f"{identifier}.json"
    if path.exists():
        return path
    local_dir = find_project_local_directory(project_dir)
    if local_dir is not None:
        local_path = local_dir / "issues" / f"{identifier}.json"
        if local_path.exists():
            return local_path
    return project_dir / "issues" / f"{identifier}.json"


@then('issue "{identifier}" should not exist')
def then_issue_not_exists(context: object, identifier: str) -> None:
    path = _issue_path_for_identifier(context, identifier)
    assert not path.exists(), f"Expected issue {identifier} to be deleted"


@then('issue "{identifier}" should exist')
def then_issue_exists(context: object, identifier: str) -> None:
    path = _issue_path_for_identifier(context, identifier)
    assert path.exists(), f"Expected issue {identifier} to exist"
