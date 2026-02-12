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
from taskulus.issue_display import format_issue_for_display


@given('an issue "tsk-aaa" exists with title "Implement OAuth2 flow"')
def given_issue_exists_with_title(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("tsk-aaa", "Implement OAuth2 flow", "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('an issue "tsk-desc" exists with title "Describe me"')
def given_issue_desc_exists(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("tsk-desc", "Describe me", "task", "open", None, [])
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


@when('I run "tsk show tsk-desc"')
def when_run_show_desc(context: object) -> None:
    run_cli(context, "tsk show tsk-desc")


@when('I run "tsk show tsk-aaa --json"')
def when_run_show_json(context: object) -> None:
    run_cli(context, "tsk show tsk-aaa --json")


@when('I run "tsk show tsk-labels"')
def when_run_show_labels(context: object) -> None:
    run_cli(context, "tsk show tsk-labels")


@when('I run "tsk show tsk-missing"')
def when_run_show_missing(context: object) -> None:
    run_cli(context, "tsk show tsk-missing")


@when('I format issue "tsk-labels" for display')
def when_format_issue_for_display(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-labels")
    context.formatted_output = format_issue_for_display(issue)


@then('the formatted output should contain "Labels: auth, urgent"')
def then_formatted_output_contains_labels(context: object) -> None:
    output = getattr(context, "formatted_output", "")
    assert "Labels: auth, urgent" in output
