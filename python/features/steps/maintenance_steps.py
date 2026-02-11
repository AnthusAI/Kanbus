"""Behave steps for maintenance scenarios."""

from __future__ import annotations

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    run_cli,
    write_issue_file,
)


@given('issues "{first}" and "{second}" exist')
def given_issues_exist(context: object, first: str, second: str) -> None:
    project_dir = load_project_directory(context)
    for identifier in (first, second):
        issue = build_issue(identifier, "Title", "task", "open", None, [])
        write_issue_file(project_dir, issue)


@given('issue "{identifier}" has status "{status}"')
def given_issue_has_status(context: object, identifier: str, status: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", status, None, [])
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has type "{issue_type}"')
def given_issue_has_type(context: object, identifier: str, issue_type: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", issue_type, "open", None, [])
    write_issue_file(project_dir, issue)


@when('I run "tsk validate"')
def when_run_validate(context: object) -> None:
    run_cli(context, "tsk validate")


@when('I run "tsk stats"')
def when_run_stats(context: object) -> None:
    run_cli(context, "tsk stats")


@then('stdout should contain "{text}"')
def then_stdout_contains(context: object, text: str) -> None:
    assert text in context.result.stdout
