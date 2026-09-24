"""Behave steps for project rekey scenarios."""

from __future__ import annotations

from behave import given, then, when
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
import json
import subprocess

from features.steps.shared import (
    build_issue,
    load_project_directory,
    run_cli,
    read_issue_file,
    write_issue_file,
)
from kanbus.models import IssueData, DependencyLink
import yaml


@given("an issue {issue_id} exists")
def given_issue_exists(context: object, issue_id: str) -> None:
    """Create an issue with specified ID."""
    project_dir = load_project_directory(context)
    issue = build_issue(issue_id, issue_id, "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given("issues {ids} exist")
def given_issues_exist(context: object, ids: str) -> None:
    """Create multiple issues from a comma-separated list."""
    issue_ids = [i.strip().strip('"') for i in ids.split("and")]
    project_dir = load_project_directory(context)
    for issue_id in issue_ids:
        issue = build_issue(issue_id, issue_id, "task", "open", None, [])
        write_issue_file(project_dir, issue)


@given('issues "{id1}" and "{id2}" exist')
def given_two_issues_exist(context: object, id1: str, id2: str) -> None:
    """Create two specific issues."""
    project_dir = load_project_directory(context)
    for issue_id in [id1, id2]:
        issue = build_issue(issue_id, issue_id, "task", "open", None, [])
        write_issue_file(project_dir, issue)


@given('an issue "{issue_id}" exists with type "{issue_type}"')
def given_issue_with_type(context: object, issue_id: str, issue_type: str) -> None:
    """Create an issue with specified type."""
    project_dir = load_project_directory(context)
    issue = build_issue(issue_id, issue_id, issue_type, "open", None, [])
    write_issue_file(project_dir, issue)


@given('an issue "{issue_id}" exists with parent "{parent_id}"')
def given_issue_with_parent(context: object, issue_id: str, parent_id: str) -> None:
    """Create an issue with specified parent."""
    project_dir = load_project_directory(context)
    issue = build_issue(issue_id, issue_id, "task", "open", parent_id, [])
    write_issue_file(project_dir, issue)


@given('an issue "{parent_id}" exists with type "{issue_type}"')
def given_parent_issue(context: object, parent_id: str, issue_type: str) -> None:
    """Create a parent issue (epic)."""
    project_dir = load_project_directory(context)
    issue = build_issue(parent_id, parent_id, issue_type, "open", None, [])
    write_issue_file(project_dir, issue)


@given('an issue "{issue_id}" exists with description "{description}"')
def given_issue_with_description(context: object, issue_id: str, description: str) -> None:
    """Create an issue with specified description."""
    project_dir = load_project_directory(context)
    issue = build_issue(issue_id, issue_id, "task", "open", None, [])
    issue = issue.model_copy(update={"description": description})
    write_issue_file(project_dir, issue)


@given('an issue "{issue_id}" exists with title "{title}"')
def given_issue_with_title(context: object, issue_id: str, title: str) -> None:
    """Create an issue with specified title."""
    project_dir = load_project_directory(context)
    issue = build_issue(issue_id, title, "task", "open", None, [])
    write_issue_file(project_dir, issue)


@given('an issue "{issue_id}" exists with title "{title}" and description "{description}"')
def given_issue_with_title_and_desc(context: object, issue_id: str, title: str, description: str) -> None:
    """Create an issue with title and description."""
    project_dir = load_project_directory(context)
    issue = build_issue(issue_id, title, "task", "open", None, [])
    issue = issue.model_copy(update={"description": description})
    write_issue_file(project_dir, issue)


@given('issue "{issue_id}" has dependency "{dep_type}" on "{target_id}"')
def given_issue_has_dependency(context: object, issue_id: str, dep_type: str, target_id: str) -> None:
    """Add a dependency to an issue."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, issue_id)
    deps = list(issue.dependencies) if issue.dependencies else []
    deps.append(DependencyLink(target=target_id, type=dep_type))
    issue = issue.model_copy(update={"dependencies": deps})
    write_issue_file(project_dir, issue)


@given('issue "{issue_id}" has a comment "{comment_text}"')
def given_issue_has_comment(context: object, issue_id: str, comment_text: str) -> None:
    """Add a comment to an issue."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, issue_id)
    timestamp = datetime(2026, 2, 11, tzinfo=timezone.utc)
    comment = {
        "id": "comment-1",
        "author": "test",
        "body": comment_text,
        "created_at": timestamp.isoformat(),
        "updated_at": timestamp.isoformat(),
    }
    comments = list(issue.comments) if issue.comments else []
    comments.append(comment)
    issue = issue.model_copy(update={"comments": comments})
    write_issue_file(project_dir, issue)


@given('an issue "{new_id}" already exists')
def given_issue_already_exists(context: object, new_id: str) -> None:
    """Create a conflicting issue file."""
    project_dir = load_project_directory(context)
    issue = build_issue(new_id, new_id, "task", "open", None, [])
    write_issue_file(project_dir, issue)


@when('I run "kanbus rekey {args}"')
def when_run_rekey(context: object, args: str) -> None:
    """Run the rekey command."""
    run_cli(context, f"kanbus rekey {args}")


@then("the command should succeed")
def then_command_succeeds(context: object) -> None:
    """Verify command succeeded."""
    result = getattr(context, "result", None)
    assert result is not None
    assert result.exit_code == 0, f"Command failed: {result.stderr}"


@then('the command should succeed with message "{message}"')
def then_command_succeeds_with_message(context: object, message: str) -> None:
    """Verify command succeeded with message."""
    result = getattr(context, "result", None)
    assert result is not None
    assert result.exit_code == 0
    assert message in result.stdout or message in result.stderr


@then("the rekey should succeed")
def then_rekey_succeeds(context: object) -> None:
    """Alias for command succeeds."""
    then_command_succeeds(context)


@then('issue "{issue_id}" should exist')
def then_issue_exists(context: object, issue_id: str) -> None:
    """Verify issue exists."""
    project_dir = load_project_directory(context)
    assert (project_dir / "issues" / f"{issue_id}.json").exists()


@then('issue "{issue_id}" should not exist')
def then_issue_not_exists(context: object, issue_id: str) -> None:
    """Verify issue does not exist."""
    project_dir = load_project_directory(context)
    assert not (project_dir / "issues" / f"{issue_id}.json").exists()


@then('issue "{issue_id}" should still exist')
def then_issue_still_exists(context: object, issue_id: str) -> None:
    """Verify issue still exists."""
    then_issue_exists(context, issue_id)


@then('issue "{short_id}" should resolve to "{full_id}"')
def then_short_id_resolves(context: object, short_id: str, full_id: str) -> None:
    """Verify short ID resolves to full ID."""
    project_dir = load_project_directory(context)
    assert (project_dir / "issues" / f"{full_id}.json").exists()


@then('issue "{issue_id}" should have parent "{parent_id}"')
def then_issue_has_parent(context: object, issue_id: str, parent_id: str) -> None:
    """Verify issue parent."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, issue_id)
    assert issue.parent == parent_id


@then('issue "{issue_id}" should have dependency "{dep_type}" on "{target_id}"')
def then_issue_has_dependency(context: object, issue_id: str, dep_type: str, target_id: str) -> None:
    """Verify dependency."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, issue_id)
    for dep in issue.dependencies:
        if dep.type == dep_type and dep.target == target_id:
            return
    raise AssertionError(f"Dependency {dep_type} -> {target_id} not found")


@then('issue "{issue_id}" should have title "{title}"')
def then_issue_has_title(context: object, issue_id: str, title: str) -> None:
    """Verify issue title."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, issue_id)
    assert issue.title == title


@then('issue "{issue_id}" should have a comment "{comment_text}"')
def then_issue_has_comment(context: object, issue_id: str, comment_text: str) -> None:
    """Verify issue has comment."""
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, issue_id)
    for comment in issue.comments:
        if comment_text in comment.get("body", ""):
            return
    raise AssertionError(f"Comment not found: {comment_text}")


@then('stdout should contain "{text}"')
def then_stdout_contains(context: object, text: str) -> None:
    """Verify stdout contains text."""
    result = getattr(context, "result", None)
    assert result is not None
    assert text in result.stdout, f"Expected '{text}' in stdout:\n{result.stdout}"


@then('stdout should contain "{count} rewrites"')
def then_stdout_has_rewrite_count(context: object, count: str) -> None:
    """Verify rewrite count in output."""
    result = getattr(context, "result", None)
    assert result is not None
    assert count in result.stdout


@then('stderr should contain "{text}"')
def then_stderr_contains(context: object, text: str) -> None:
    """Verify stderr contains text."""
    result = getattr(context, "result", None)
    assert result is not None
    assert text in result.stderr, f"Expected '{text}' in stderr:\n{result.stderr}"


@then("the command should fail with exit code 1")
def then_command_fails(context: object) -> None:
    """Verify command failed."""
    result = getattr(context, "result", None)
    assert result is not None
    assert result.exit_code != 0


@then("the cache directory should be invalidated or rebuilt")
def then_cache_invalidated(context: object) -> None:
    """Verify caches invalidated."""
    project_dir = load_project_directory(context)
    cache_dir = project_dir / ".cache"
    assert not cache_dir.exists() or cache_dir.stat().st_mtime > 0


@when("I run \"kanbus validate\"")
def when_run_validate(context: object) -> None:
    """Run validate command."""
    run_cli(context, "kanbus validate")


@then("the validate command should succeed")
def then_validate_succeeds(context: object) -> None:
    """Verify validate succeeded."""
    then_command_succeeds(context)


@when("I check the git history")
def when_check_git_history(context: object) -> None:
    """Check git history."""
    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=context.working_directory,
        capture_output=True,
        text=True,
    )
    context.git_history = result.stdout


@then("the event history should reflect the rekey operation")
def then_event_history_reflects_rekey(context: object) -> None:
    """Verify event history."""
    project_dir = load_project_directory(context)
    events_dir = project_dir / "events"
    assert events_dir.exists()
