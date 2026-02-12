"""Behave steps for issue close and delete."""

from __future__ import annotations

from behave import then, when

from features.steps.shared import load_project_directory, run_cli


@when('I run "tsk close tsk-aaa"')
def when_run_close(context: object) -> None:
    run_cli(context, "tsk close tsk-aaa")


@when('I run "tsk close tsk-missing"')
def when_run_close_missing(context: object) -> None:
    run_cli(context, "tsk close tsk-missing")


@when('I run "tsk delete tsk-aaa"')
def when_run_delete(context: object) -> None:
    run_cli(context, "tsk delete tsk-aaa")


@when('I run "tsk delete tsk-missing"')
def when_run_delete_missing(context: object) -> None:
    run_cli(context, "tsk delete tsk-missing")


@then('issue "tsk-aaa" should not exist')
def then_issue_not_exists(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "tsk-aaa.json"
    assert not issue_path.exists()
