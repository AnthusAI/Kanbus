"""Behave steps for Beads/Kanbus interoperability testing."""

from __future__ import annotations

import json


from behave import given, then, when, use_step_matcher

from features.steps.shared import run_cli, run_cli_with_input

# Use parse matcher for complex command patterns
use_step_matcher("re")


@given('a kanbus issue "(?P<identifier>[^"]+)" exists')
def given_kanbus_issue_exists(context: object, identifier: str) -> None:
    """Create a basic Kanbus/Beads issue for testing with specific ID."""
    # For beads compatibility testing, create the issue in beads format with exact ID
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    issue_record = {
        "id": identifier,
        "title": f"Test issue {identifier}",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with open(issues_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(issue_record) + "\n")


@given('a beads issue "(?P<identifier>[^"]+)" exists')
def given_beads_issue_exists(context: object, identifier: str) -> None:
    """Create a Beads issue in the .beads/issues.jsonl file."""
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    issue_record = {
        "id": identifier,
        "title": f"Test issue {identifier}",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with open(issues_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(issue_record) + "\n")


@given(
    'a kanbus issue "(?P<identifier>[^"]+)" exists with dependency "(?P<dependency>[^"]+)"'
)
def given_kanbus_issue_with_dependency(
    context: object, identifier: str, dependency: str
) -> None:
    """Create a Kanbus issue with a dependency."""
    dep_parts = dependency.split()
    dep_type = dep_parts[0]
    dep_target = dep_parts[1]
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    issue_record = {
        "id": identifier,
        "title": f"Test issue {identifier}",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "dependencies": [{"type": dep_type, "depends_on_id": dep_target}],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with open(issues_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(issue_record) + "\n")


@given('a kanbus issue "(?P<identifier>[^"]+)" exists with labels "(?P<labels>[^"]+)"')
def given_kanbus_issue_with_labels(
    context: object, identifier: str, labels: str
) -> None:
    """Create a Kanbus issue with labels."""
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    issue_record = {
        "id": identifier,
        "title": f"Test issue {identifier}",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "labels": [label.strip() for label in labels.split(",")],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with open(issues_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(issue_record) + "\n")


@given('a kanbus issue "(?P<identifier>[^"]+)" exists with title "(?P<title>[^"]+)"')
def given_kanbus_issue_with_title(context: object, identifier: str, title: str) -> None:
    """Create a Kanbus issue with specific title."""
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    issue_record = {
        "id": identifier,
        "title": title,
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with open(issues_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(issue_record) + "\n")


@given('a kanbus issue "(?P<identifier>[^"]+)" exists with status "(?P<status>[^"]+)"')
def given_kanbus_issue_with_status(
    context: object, identifier: str, status: str
) -> None:
    """Create a Kanbus issue with specific status."""
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    issue_record = {
        "id": identifier,
        "title": f"Test issue {identifier}",
        "status": status,
        "priority": 2,
        "issue_type": "task",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with open(issues_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(issue_record) + "\n")


@given('a kanbus issue "(?P<identifier>[^"]+)" exists with priority (?P<priority>\\d+)')
def given_kanbus_issue_with_priority(
    context: object, identifier: str, priority: str
) -> None:
    """Create a Kanbus issue with specific priority."""
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    issue_record = {
        "id": identifier,
        "title": f"Test issue {identifier}",
        "status": "open",
        "priority": int(priority),
        "issue_type": "task",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with open(issues_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(issue_record) + "\n")


@given('a kanbus-only issue "(?P<identifier>[^"]+)" exists')
def given_kanbus_only_issue_exists(context: object, identifier: str) -> None:
    """Create an issue that only exists in Kanbus, not in Beads."""
    run_cli(context, f"kanbus create Kanbus-only test issue for {identifier}")


@given('a beads issue "(?P<child>[^"]+)" exists with parent "(?P<parent_id>[^"]+)"')
def given_beads_issue_with_parent(context: object, child: str, parent_id: str) -> None:
    """Create a Beads issue with a parent relationship."""
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    issue_record = {
        "id": child,
        "title": "Child subtask for testing",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "parent": parent_id,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "dependencies": [{"type": "parent-child", "depends_on_id": parent_id}],
    }
    with open(issues_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(issue_record) + "\n")


@given('a kanbus issue "(?P<child>[^"]+)" exists with parent "(?P<parent_id>[^"]+)"')
def given_kanbus_issue_with_parent(context: object, child: str, parent_id: str) -> None:
    """Create a Beads issue with a parent relationship for interoperability testing."""
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    issue_record = {
        "id": child,
        "title": f"Child issue {child}",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "parent": parent_id,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with open(issues_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(issue_record) + "\n")


# Use a generic pattern for all command variants
@when('I run "(?P<command>[^"]+)" with stdin "(?P<stdin_text>[^"]+)"')
def when_run_command_with_stdin(context: object, command: str, stdin_text: str) -> None:
    """Generic step to run any kanbus command with stdin input."""
    # Decode escaped newlines
    stdin_content = stdin_text.replace("\\n", "\n")
    run_cli_with_input(context, command, stdin_content)


@when('I run "(?P<command>[^"]+)"')
def when_run_command(context: object, command: str) -> None:
    """Generic step to run any kanbus command."""
    run_cli(context, command)


@then('beads issues\\.jsonl should not contain "(?P<identifier>[^"]+)"')
def then_beads_jsonl_not_contains(context: object, identifier: str) -> None:
    """Verify identifier is not in beads issues.jsonl."""
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    contents = issues_path.read_text(encoding="utf-8")
    assert identifier not in contents, f"Found {identifier} in beads issues.jsonl"


@then('beads issues\\.jsonl should contain "(?P<identifier>[^"]+)"')
def then_beads_jsonl_contains(context: object, identifier: str) -> None:
    """Verify identifier is in beads issues.jsonl."""
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    contents = issues_path.read_text(encoding="utf-8")
    assert identifier in contents, f"Did not find {identifier} in beads issues.jsonl"


@then("stdout should contain parent reference")
def then_stdout_contains_parent_reference(context: object) -> None:
    """Verify stdout contains a parent reference."""
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    assert (
        "parent" in result.stdout.lower() or "parent-child" in result.stdout.lower()
    ), "No parent reference found in stdout"


@then(
    'the comments should appear in order: "(?P<comment1>[^"]+)", "(?P<comment2>[^"]+)", "(?P<comment3>[^"]+)"'
)
def then_comments_in_order(
    context: object, comment1: str, comment2: str, comment3: str
) -> None:
    """Verify comments appear in specified order."""
    result = getattr(context, "result", None)
    assert result is not None, "command result missing"
    stdout = result.stdout
    idx1 = stdout.find(comment1)
    idx2 = stdout.find(comment2)
    idx3 = stdout.find(comment3)
    assert (
        idx1 >= 0 and idx2 >= 0 and idx3 >= 0
    ), f"Not all comments found: {comment1}, {comment2}, {comment3}"
    assert idx1 < idx2 < idx3, f"Comments not in order: {idx1}, {idx2}, {idx3}"


# Reset step matcher back to parse for other files
use_step_matcher("parse")
