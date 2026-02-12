"""Behave steps for issue update."""

from __future__ import annotations

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)


@given('an issue "tsk-aaa" exists with title "Old Title"')
def given_issue_with_title(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("tsk-aaa", "Old Title", "task", "open", None, [])
    write_issue_file(project_dir, issue)



@when(
    'I run "tsk update tsk-aaa --title \\"New Title\\" --description \\"Updated description\\""'
)
def when_run_update_title(context: object) -> None:
    run_cli(
        context,
        'tsk update tsk-aaa --title "New Title" --description "Updated description"',
    )


@when('I run "tsk update tsk-aaa --status in_progress"')
def when_run_update_status(context: object) -> None:
    run_cli(context, "tsk update tsk-aaa --status in_progress")


@when('I run "tsk update tsk-aaa --status blocked"')
def when_run_update_invalid_status(context: object) -> None:
    run_cli(context, "tsk update tsk-aaa --status blocked")


@when('I run "tsk update tsk-test01 --status {status}"')
def when_run_update_status_test01(context: object, status: str) -> None:
    run_cli(context, f"tsk update tsk-test01 --status {status}")


@when('I run "tsk update tsk-epic01 --status deferred"')
def when_run_update_status_epic01(context: object) -> None:
    run_cli(context, "tsk update tsk-epic01 --status deferred")


@when('I run "tsk update tsk-test01 --claim"')
def when_run_update_claim_test01(context: object) -> None:
    run_cli(context, "tsk update tsk-test01 --claim")


@when('I run "tsk update tsk-missing --title \\"New Title\\""')
def when_run_update_missing(context: object) -> None:
    run_cli(context, 'tsk update tsk-missing --title "New Title"')


@when('I run "tsk update tsk-aaa --title \\"New Title\\""')
def when_run_update_title_only(context: object) -> None:
    run_cli(context, 'tsk update tsk-aaa --title "New Title"')


@then('issue "tsk-aaa" should have title "New Title"')
def then_issue_has_title(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    assert issue.title == "New Title"


@then('issue "tsk-aaa" should have description "Updated description"')
def then_issue_has_description(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    assert issue.description == "Updated description"


@then('issue "tsk-aaa" should have an updated_at timestamp')
def then_issue_has_updated_at(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    assert issue.updated_at is not None
