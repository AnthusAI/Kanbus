"""Behave steps for issue display."""

from __future__ import annotations

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)


@given('an issue "tsk-aaa" exists with title "Implement OAuth2 flow"')
def given_issue_exists_with_title(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("tsk-aaa", "Implement OAuth2 flow", "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('issue "tsk-aaa" has status "open" and type "task"')
def given_issue_status_and_type(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    issue = issue.model_copy(update={"status": "open", "issue_type": "task"})
    write_issue_file(project_dir, issue)


@when('I run "tsk show tsk-aaa"')
def when_run_show(context: object) -> None:
    run_cli(context, "tsk show tsk-aaa")


@when('I run "tsk show tsk-aaa --json"')
def when_run_show_json(context: object) -> None:
    run_cli(context, "tsk show tsk-aaa --json")


@when('I run "tsk show tsk-missing"')
def when_run_show_missing(context: object) -> None:
    run_cli(context, "tsk show tsk-missing")


@then('stdout should contain "Implement OAuth2 flow"')
def then_stdout_contains_title(context: object) -> None:
    assert "Implement OAuth2 flow" in context.result.stdout


@then('stdout should contain "open"')
def then_stdout_contains_status(context: object) -> None:
    assert "open" in context.result.stdout


@then('stdout should contain "task"')
def then_stdout_contains_type(context: object) -> None:
    assert "task" in context.result.stdout


@then('stdout should contain "\\"id\\": \\"tsk-aaa\\""')
def then_stdout_contains_json_id(context: object) -> None:
    assert '"id": "tsk-aaa"' in context.result.stdout


@then('stdout should contain "\\"title\\": \\"Implement OAuth2 flow\\""')
def then_stdout_contains_json_title(context: object) -> None:
    assert '"title": "Implement OAuth2 flow"' in context.result.stdout
