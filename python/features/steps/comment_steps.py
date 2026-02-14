"""Behave steps for issue comments."""

from __future__ import annotations

from behave import given, then, when

from features.steps.shared import load_project_directory, read_issue_file, run_cli


@given('the current user is "dev@example.com"')
def given_current_user(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_USER"] = "dev@example.com"
    context.environment_overrides = overrides


@when('I run "kanbus comment kanbus-aaa \\"First comment\\""')
def when_comment_first(context: object) -> None:
    run_cli(context, 'kanbus comment kanbus-aaa "First comment"')


@when('I run "kanbus comment kanbus-aaa \\"Second comment\\""')
def when_comment_second(context: object) -> None:
    run_cli(context, 'kanbus comment kanbus-aaa "Second comment"')


@when('I run "kanbus comment kanbus-missing \\"Missing issue note\\""')
def when_comment_missing(context: object) -> None:
    run_cli(context, 'kanbus comment kanbus-missing "Missing issue note"')


@when('I run "kanbus comment kanbus-note \\"Searchable comment\\""')
def when_comment_note(context: object) -> None:
    run_cli(context, 'kanbus comment kanbus-note "Searchable comment"')


@when('I run "kanbus comment kanbus-dup \\"Dup keyword\\""')
def when_comment_dup(context: object) -> None:
    run_cli(context, 'kanbus comment kanbus-dup "Dup keyword"')


@then('issue "kanbus-aaa" should have 1 comment')
def then_issue_has_one_comment(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    assert len(issue.comments) == 1


@then('the latest comment should have author "dev@example.com"')
def then_latest_author(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    assert issue.comments[-1].author == "dev@example.com"


@then('the latest comment should have text "First comment"')
def then_latest_text(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    assert issue.comments[-1].text == "First comment"


@then("the latest comment should have a created_at timestamp")
def then_latest_timestamp(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    assert issue.comments[-1].created_at is not None


@then('issue "kanbus-aaa" should have comments in order "First comment", "Second comment"')
def then_comments_order(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    texts = [comment.text for comment in issue.comments]
    assert texts == ["First comment", "Second comment"]
