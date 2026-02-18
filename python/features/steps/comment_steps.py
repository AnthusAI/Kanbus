"""Behave steps for issue comments."""

from __future__ import annotations

from datetime import datetime, timezone

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)
from kanbus.issue_comment import (
    IssueCommentError,
    delete_comment,
    ensure_issue_comment_ids,
    update_comment,
)
from kanbus.models import IssueComment


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


@then(
    'issue "kanbus-aaa" should have comments in order "First comment", "Second comment"'
)
def then_comments_order(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-aaa")
    texts = [comment.text for comment in issue.comments]
    assert texts == ["First comment", "Second comment"]


@given('an issue "{identifier}" exists with a comment missing an id')
def given_issue_with_missing_comment_id(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Legacy comments", "task", "open", None, [])
    comment = IssueComment(
        id=None,
        author="dev@example.com",
        text="Legacy note",
        created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
    )
    issue = issue.model_copy(update={"comments": [comment]})
    write_issue_file(project_dir, issue)


@given(
    'an issue "{identifier}" exists with comment id "{comment_id}" and text "{text}"'
)
def given_issue_with_comment_id(
    context: object, identifier: str, comment_id: str, text: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Commented issue", "task", "open", None, [])
    comment = IssueComment(
        id=comment_id,
        author="dev@example.com",
        text=text,
        created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
    )
    issue = issue.model_copy(update={"comments": [comment]})
    write_issue_file(project_dir, issue)


@given('an issue "{identifier}" exists with comment ids "{first_id}" and "{second_id}"')
def given_issue_with_comment_ids(
    context: object, identifier: str, first_id: str, second_id: str
) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue(identifier, "Ambiguous comments", "task", "open", None, [])
    comments = [
        IssueComment(
            id=first_id,
            author="dev@example.com",
            text="First",
            created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
        ),
        IssueComment(
            id=second_id,
            author="dev@example.com",
            text="Second",
            created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
        ),
    ]
    issue = issue.model_copy(update={"comments": comments})
    write_issue_file(project_dir, issue)


@when('I ensure comment ids for "{identifier}"')
def when_ensure_comment_ids(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    context.updated_issue = ensure_issue_comment_ids(project_dir, identifier)


@when('I update comment "{comment_id}" on "{identifier}" to "{text}"')
def when_update_comment(
    context: object, comment_id: str, identifier: str, text: str
) -> None:
    project_dir = load_project_directory(context)
    context.updated_issue = update_comment(project_dir, identifier, comment_id, text)


@when('I delete comment "{comment_id}" on "{identifier}"')
def when_delete_comment(context: object, comment_id: str, identifier: str) -> None:
    project_dir = load_project_directory(context)
    context.updated_issue = delete_comment(project_dir, identifier, comment_id)


@when('I attempt to update comment "{comment_id}" on "{identifier}" to "{text}"')
def when_attempt_update_comment(
    context: object, comment_id: str, identifier: str, text: str
) -> None:
    project_dir = load_project_directory(context)
    if comment_id == "<empty>":
        comment_id = ""
    try:
        context.updated_issue = update_comment(
            project_dir, identifier, comment_id, text
        )
        context.last_error = None
    except IssueCommentError as error:
        context.last_error = error


@when('I attempt to delete comment "{comment_id}" on "{identifier}"')
def when_attempt_delete_comment(
    context: object, comment_id: str, identifier: str
) -> None:
    project_dir = load_project_directory(context)
    if comment_id == "<empty>":
        comment_id = ""
    try:
        context.updated_issue = delete_comment(project_dir, identifier, comment_id)
        context.last_error = None
    except IssueCommentError as error:
        context.last_error = error


@when('I attempt to ensure comment ids for "{identifier}"')
def when_attempt_ensure_comment_ids(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    try:
        context.updated_issue = ensure_issue_comment_ids(project_dir, identifier)
        context.last_error = None
    except IssueCommentError as error:
        context.last_error = error


@then('issue "{identifier}" should have comment ids assigned')
def then_issue_comment_ids_assigned(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.comments, "expected at least one comment"
    assert all(comment.id for comment in issue.comments)


@then('issue "{identifier}" should have comment text "{text}"')
def then_issue_comment_text(context: object, identifier: str, text: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert issue.comments, "expected at least one comment"
    assert issue.comments[0].text == text


@then('issue "{identifier}" should have {count:d} comments')
def then_issue_comment_count(context: object, identifier: str, count: int) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    assert len(issue.comments) == count


@then('the last comment operation should fail with "{message}"')
def then_comment_operation_failed(context: object, message: str) -> None:
    error = getattr(context, "last_error", None)
    assert error is not None, "expected an error"
    assert message in str(error)
