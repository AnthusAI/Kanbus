"""Behave steps for issue compaction feature."""

from pathlib import Path
import yaml
from behave import given, then
from kanbus.issue_lookup import load_issue_from_project
from kanbus.issue_files import write_issue_to_file
from kanbus.models import IssueComment
from datetime import datetime, timezone, timedelta
import uuid
import json


@given('the Kanbus configuration uses AI provider "{provider}" with model "{model}"')
def step_impl_ai_config(context, provider, model):
    root = Path(context.working_directory)
    config_path = root / ".kanbus.yml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["ai"] = {"provider": provider, "model": model}
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


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
    summary = next(
        (
            c
            for c in reversed(issue.comments)
            if getattr(c, "comment_type", "default") == "summary"
        ),
        None,
    )
    assert summary is not None, f"No summary comment found for {issue_id}"
    assert (
        text in summary.text
    ), f"Expected '{text}' in summary comment, got: {summary.text}"
