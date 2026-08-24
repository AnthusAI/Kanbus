import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from behave import given

from kanbus.issue_lookup import load_issue_from_project
from kanbus.issue_files import write_issue_to_file
from kanbus.models import IssueComment


@given('the AI provider is configured as "litellm"')
def step_lifecycle_impl_1(context):
    config_path = Path(context.working_directory) / ".kanbus.yml"
    if config_path.exists():
        content = config_path.read_text()
    else:
        content = "project_directory: project\n"
    content += "\nai:\n  provider: litellm\n  model: gpt-5.6-luna\n"
    config_path.write_text(content)


@given("mock AI is enabled")
def step_lifecycle_impl_2(context):
    os.environ["KANBUS_TEST_AI_MOCK"] = "1"
    context.env_to_restore = (
        context.env_to_restore if hasattr(context, "env_to_restore") else {}
    )
    context.env_to_restore["KANBUS_TEST_AI_MOCK"] = "1"


@given('an issue "{issue_id}" of type "{issue_type}" in status "{status}"')
def step_lifecycle_impl_3(context, issue_id, issue_type, status):
    from kanbus.models import IssueData

    now = datetime.now(timezone.utc)
    issue = IssueData(
        id=issue_id,
        title=f"Test {issue_id}",
        description="Test description",
        type=issue_type,
        status=status,
        priority=1,
        created_at=now,
        updated_at=now,
    )
    issues_dir = Path(context.working_directory) / "project" / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    write_issue_to_file(issue, issues_dir / f"{issue_id}.json")


@given('issue "{issue_id}" was updated {days:d} days ago')
def step_lifecycle_impl_4(context, issue_id, days):
    lookup = load_issue_from_project(Path(context.working_directory), issue_id)
    issue = lookup.issue
    past_date = datetime.now(timezone.utc) - timedelta(days=days)
    issue.updated_at = past_date
    write_issue_to_file(issue, lookup.issue_path)


@given('issue "{issue_id}" has {count:d} comments')
def step_lifecycle_impl_5(context, issue_id, count):
    lookup = load_issue_from_project(Path(context.working_directory), issue_id)
    issue = lookup.issue
    for i in range(count):
        issue.comments.append(
            IssueComment(
                id=str(uuid.uuid4()),
                author="user",
                text=f"Comment {i}",
                created_at=issue.updated_at,
            )
        )
    write_issue_to_file(issue, lookup.issue_path)


@given('issue "{issue_id}" has a summary comment')
def step_lifecycle_impl_6(context, issue_id):
    lookup = load_issue_from_project(Path(context.working_directory), issue_id)
    issue = lookup.issue
    issue.comments.append(
        IssueComment(
            id=str(uuid.uuid4()),
            author="system:summary",
            created_at=issue.updated_at,
            comment_type="summary",
            data={
                "rewritten_description": "Summary",
                "activity_summary": "Summary",
            },
        )
    )
    write_issue_to_file(issue, lookup.issue_path)
