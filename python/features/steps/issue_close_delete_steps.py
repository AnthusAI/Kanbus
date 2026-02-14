"""Behave steps for issue close and delete."""

from __future__ import annotations

from behave import then, when

from features.steps.shared import load_project_directory, run_cli


@when('I run "kanbus close kanbus-aaa"')
def when_run_close(context: object) -> None:
    run_cli(context, "kanbus close kanbus-aaa")


@when('I run "kanbus close kanbus-missing"')
def when_run_close_missing(context: object) -> None:
    run_cli(context, "kanbus close kanbus-missing")


@when('I run "kanbus delete kanbus-aaa"')
def when_run_delete(context: object) -> None:
    run_cli(context, "kanbus delete kanbus-aaa")


@when('I run "kanbus delete kanbus-missing"')
def when_run_delete_missing(context: object) -> None:
    run_cli(context, "kanbus delete kanbus-missing")


@then('issue "kanbus-aaa" should not exist')
def then_issue_not_exists(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "kanbus-aaa.json"
    assert not issue_path.exists()
