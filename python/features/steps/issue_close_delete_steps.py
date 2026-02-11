"""Behave steps for issue close and delete."""

from __future__ import annotations

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)


@given('an issue "tsk-aaa" exists')
def given_issue_exists(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("tsk-aaa", "Title", "task", "open", None, [])
    write_issue_file(project_dir, issue)


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


@then('issue "tsk-aaa" should have status "closed"')
def then_issue_status_closed(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    assert issue.status == "closed"


@then('issue "tsk-aaa" should have a closed_at timestamp')
def then_issue_closed_at(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    assert issue.closed_at is not None


@then('issue "tsk-aaa" should not exist')
def then_issue_not_exists(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "tsk-aaa.json"
    assert not issue_path.exists()
