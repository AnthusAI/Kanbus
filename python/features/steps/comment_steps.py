"""Behave steps for issue comments."""

from __future__ import annotations

from behave import given, then, when

from features.steps.shared import load_project_directory, read_issue_file, run_cli


@given('the current user is "dev@example.com"')
def given_current_user(context: object) -> None:
    context.environment_overrides = {"TASKULUS_USER": "dev@example.com"}


@when('I run "tsk comment tsk-aaa \\"First comment\\""')
def when_comment_first(context: object) -> None:
    run_cli(context, 'tsk comment tsk-aaa "First comment"')


@when('I run "tsk comment tsk-aaa \\"Second comment\\""')
def when_comment_second(context: object) -> None:
    run_cli(context, 'tsk comment tsk-aaa "Second comment"')


@when('I run "tsk comment tsk-missing \\"Missing issue note\\""')
def when_comment_missing(context: object) -> None:
    run_cli(context, 'tsk comment tsk-missing "Missing issue note"')


@then('issue "tsk-aaa" should have 1 comment')
def then_issue_has_one_comment(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    assert len(issue.comments) == 1


@then('the latest comment should have author "dev@example.com"')
def then_latest_author(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    assert issue.comments[-1].author == "dev@example.com"


@then('the latest comment should have text "First comment"')
def then_latest_text(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    assert issue.comments[-1].text == "First comment"


@then("the latest comment should have a created_at timestamp")
def then_latest_timestamp(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    assert issue.comments[-1].created_at is not None


@then(
    'issue "tsk-aaa" should have comments in order "First comment", "Second comment"'
)
def then_comments_order(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "tsk-aaa")
    texts = [comment.text for comment in issue.comments]
    assert texts == ["First comment", "Second comment"]
