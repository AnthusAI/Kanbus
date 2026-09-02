"""Behave steps for issue compaction feature."""

from pathlib import Path
from behave import given, then
from kanbus.issue_lookup import load_issue_from_project
from kanbus.issue_files import write_issue_to_file
from kanbus.models import IssueComment
from datetime import datetime, timezone, timedelta
import json
import uuid
from kanbus.comment_summary import (
    SUMMARY_ACTIVITY_SUMMARY_KEY,
    SUMMARY_REWRITTEN_DESCRIPTION_KEY,
    get_latest_summary_comment,
    get_summary_activity_summary,
    get_summary_rewritten_description,
)


@given('the issue "{issue_id}" has a comment with text "{text}"')
def step_impl_comment(context, issue_id, text):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    comment = IssueComment(
        id=str(uuid.uuid4()),
        author="testuser",
        text=text,
        created_at=datetime.now(timezone.utc),
        comment_type="default",
    )
    issue.comments.append(comment)
    write_issue_to_file(issue, lookup.issue_path)


@given(
    'the issue "{issue_id}" has a summary comment with rewritten description "{rewritten}" and activity summary "{activity}"'
)
def step_impl_structured_summary_comment(context, issue_id, rewritten, activity):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    comment = IssueComment(
        id=str(uuid.uuid4()),
        author="system:summary",
        created_at=datetime.now(timezone.utc),
        comment_type="summary",
        data={
            SUMMARY_REWRITTEN_DESCRIPTION_KEY: rewritten,
            SUMMARY_ACTIVITY_SUMMARY_KEY: activity,
        },
    )
    issue.comments.append(comment)
    write_issue_to_file(issue, lookup.issue_path)


@given('the issue "{issue_id}" has a summary comment containing "{text}"')
def step_impl_summary_comment(context, issue_id, text):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    comment = IssueComment(
        id=str(uuid.uuid4()),
        author="system:summary",
        text=text,
        created_at=datetime.now(timezone.utc),
        comment_type="summary",
    )
    issue.comments.append(comment)
    write_issue_to_file(issue, lookup.issue_path)


@given('the issue "{issue_id}" has a summary comment containing:')
def step_impl_summary_comment_multiline(context, issue_id):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    comment = IssueComment(
        id=str(uuid.uuid4()),
        author="system:summary",
        text=context.text.strip(),
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
        comment_type="summary",
    )
    issue.comments.append(comment)
    write_issue_to_file(issue, lookup.issue_path)


@then('the issue "{issue_id}" should have a summary comment')
def step_impl_check_summary(context, issue_id):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    assert any(
        getattr(c, "comment_type", "default") == "summary" for c in issue.comments
    )


@then("the system records a structured log entry for the LLM usage")
def step_impl_check_log(context):
    root = Path(context.working_directory)
    log_path = root / "project" / "events" / "llm_usage.jsonl"
    assert log_path.exists()
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) > 0
        entry = json.loads(lines[-1])
        assert "tokens" in entry
        assert "cost" in entry


@given('the issue "{issue_id}" has status "{status}"')
def step_impl_issue_status(context, issue_id, status):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    issue.status = status
    write_issue_to_file(issue, lookup.issue_path)


@given('the issue "{issue_id}" was updated {days:d} days ago')
def step_impl_issue_updated(context, issue_id, days):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    issue.updated_at = datetime.now(timezone.utc) - timedelta(days=days)
    write_issue_to_file(issue, lookup.issue_path)


@then('the summary comment for issue "{issue_id}" should contain "{text}"')
def step_impl_summary_contain(context, issue_id, text):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    summary = get_latest_summary_comment(issue)
    assert summary is not None, f"No summary comment found for {issue_id}"
    activity_summary = get_summary_activity_summary(summary)
    assert (
        text in activity_summary
    ), f"Expected '{text}' in summary comment, got: {activity_summary!r}"


@then(
    'the summary rewritten description for issue "{issue_id}" should be shorter than the original description'
)
def step_impl_summary_rewritten_shorter_than_original(context, issue_id):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    summary = get_latest_summary_comment(issue)
    assert summary is not None, f"No summary comment found for {issue_id}"
    rewritten_description = get_summary_rewritten_description(summary)
    assert rewritten_description is not None
    assert len(rewritten_description) < len(issue.description), (
        f"Expected rewritten description to be shorter than original. "
        f"Original length={len(issue.description)}, "
        f"rewritten length={len(rewritten_description)}"
    )


@then(
    'the summary comment for issue "{issue_id}" should have rewritten description "{text}"'
)
def step_impl_summary_rewritten_description(context, issue_id, text):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    summary = get_latest_summary_comment(issue)
    assert summary is not None, f"No summary comment found for {issue_id}"
    rewritten_description = get_summary_rewritten_description(summary)
    assert (
        rewritten_description == text
    ), f"Expected rewritten description {text!r}, got {rewritten_description!r}"


@then('the summary comment for issue "{issue_id}" should not contain "{text}"')
def step_impl_summary_not_contain(context, issue_id, text):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    summary = get_latest_summary_comment(issue)
    assert summary is not None, f"No summary comment found for {issue_id}"
    activity_summary = get_summary_activity_summary(summary)
    assert (
        text not in activity_summary
    ), f"Did not expect '{text}' in summary comment, got: {activity_summary!r}"


@then('issue "{issue_id}" description should equal "{description}"')
def step_impl_issue_description(context, issue_id, description):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    assert (
        issue.description == description
    ), f"Expected description {description!r}, got {issue.description!r}"


@then('issue "{issue_id}" should have custom field "{field_name}"')
def step_impl_issue_custom_field(context, issue_id, field_name):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    assert (
        field_name in issue.custom
    ), f"Expected custom field {field_name!r}, got {issue.custom!r}"


@given('issue "{issue_id}" has custom field "{field_name}" with value "{value}"')
def step_impl_issue_custom_field_value(context, issue_id, field_name, value):
    root = Path(context.working_directory)
    lookup = load_issue_from_project(root, issue_id)
    issue = lookup.issue
    issue.custom[field_name] = value
    write_issue_to_file(issue, lookup.issue_path)
