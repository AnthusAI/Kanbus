"""Behave steps for query scenarios."""

from __future__ import annotations

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
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


@given('issue "{identifier}" has assignee "{assignee}"')
def given_issue_has_assignee(context: object, identifier: str, assignee: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    issue = issue.model_copy(update={"assignee": assignee})
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has labels "{label_text}"')
def given_issue_has_labels(context: object, identifier: str, label_text: str) -> None:
    project_dir = load_project_directory(context)
    labels = [item.strip() for item in label_text.split(",") if item.strip()]
    issue = build_issue(identifier, "Title", "task", "open", None, labels)
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has priority {priority:d}')
def given_issue_has_priority(context: object, identifier: str, priority: int) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    issue = issue.model_copy(update={"priority": priority})
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has title "{title}"')
def given_issue_has_title(context: object, identifier: str, title: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, title, "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('issue "{identifier}" has description "{description}"')
def given_issue_has_description(
    context: object, identifier: str, description: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Title", "task", "open", None, [])
    issue = issue.model_copy(update={"description": description})
    write_issue_file(project_dir, issue)


@when('I run "tsk list --status open"')
def when_run_list_status(context: object) -> None:
    run_cli(context, "tsk list --status open")


@when('I run "tsk list --type task"')
def when_run_list_type(context: object) -> None:
    run_cli(context, "tsk list --type task")


@when('I run "tsk list --assignee dev@example.com"')
def when_run_list_assignee(context: object) -> None:
    run_cli(context, "tsk list --assignee dev@example.com")


@when('I run "tsk list --label auth"')
def when_run_list_label(context: object) -> None:
    run_cli(context, "tsk list --label auth")


@when('I run "tsk list --sort priority"')
def when_run_list_sort(context: object) -> None:
    run_cli(context, "tsk list --sort priority")


@when('I run "tsk list --search login"')
def when_run_list_search(context: object) -> None:
    run_cli(context, "tsk list --search login")


@then('stdout should contain "tsk-open"')
def then_stdout_contains_open(context: object) -> None:
    assert "tsk-open" in context.result.stdout


@then('stdout should not contain "tsk-closed"')
def then_stdout_not_contains_closed(context: object) -> None:
    assert "tsk-closed" not in context.result.stdout


@then('stdout should contain "tsk-task"')
def then_stdout_contains_task_issue(context: object) -> None:
    assert "tsk-task" in context.result.stdout


@then('stdout should not contain "tsk-bug"')
def then_stdout_not_contains_bug(context: object) -> None:
    assert "tsk-bug" not in context.result.stdout


@then('stdout should contain "tsk-a"')
def then_stdout_contains_a(context: object) -> None:
    assert "tsk-a" in context.result.stdout


@then('stdout should not contain "tsk-b"')
def then_stdout_not_contains_b(context: object) -> None:
    assert "tsk-b" not in context.result.stdout


@then('stdout should list "tsk-high" before "tsk-low"')
def then_stdout_lists_high_before_low(context: object) -> None:
    output = context.result.stdout
    assert output.index("tsk-high") < output.index("tsk-low")


@then('stdout should contain "tsk-ui"')
def then_stdout_contains_ui(context: object) -> None:
    assert "tsk-ui" in context.result.stdout


@then('stdout should not contain "tsk-auth"')
def then_stdout_not_contains_auth(context: object) -> None:
    assert "tsk-auth" not in context.result.stdout
