"""Behave steps for event history."""

from __future__ import annotations

import json
import re
from pathlib import Path

from behave import then, when

from features.steps.shared import (
    capture_issue_identifier,
    load_project_directory,
    run_cli,
)


def _last_issue_id(context: object) -> str:
    identifier = getattr(context, "last_issue_id", None)
    if not identifier:
        raise AssertionError("last issue id not set")
    return identifier


def _load_issue_events(context: object, issue_id: str) -> list[tuple[str, dict]]:
    project_dir = load_project_directory(context)
    events_dir = project_dir / "events"
    if not events_dir.exists():
        return []
    events: list[tuple[str, dict]] = []
    for path in events_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("issue_id") == issue_id:
            events.append((path.name, payload))
    return events


@when('I run the command "{command}"')
def when_run_command(context: object, command: str) -> None:
    run_cli(context, command)


@when("I capture the issue identifier")
def when_capture_issue_identifier(context: object) -> None:
    capture_issue_identifier(context)


@when('I update the last issue status to "{status}"')
def when_update_last_issue_status(context: object, status: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f"kanbus update {identifier} --status {status}")


@when('I update the last issue title to "{title}"')
def when_update_last_issue_title(context: object, title: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f'kanbus update {identifier} --title "{title}"')


@when('I add a comment to the last issue with text "{text}"')
def when_add_comment_last_issue(context: object, text: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f'kanbus comment {identifier} "{text}"')


@when('I add a blocked-by dependency from the last issue to "{target}"')
def when_add_dependency(context: object, target: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f"kanbus dep add {identifier} --blocked-by {target}")


@when("I delete the last issue")
def when_delete_last_issue(context: object) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f"kanbus delete {identifier}")


@then('the event log for the last issue should include event type "{event_type}"')
def then_event_log_includes_type(context: object, event_type: str) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    assert any(event.get("event_type") == event_type for _, event in events)


@then("the event log filenames for the last issue should be ISO timestamped")
def then_event_filenames_iso(context: object) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z__.+\.json$")
    assert events, "expected events for issue"
    for filename, _ in events:
        assert pattern.match(filename), f"unexpected event filename: {filename}"


@then(
    'the event log for the last issue should include a state transition from "{from_status}" to "{to_status}"'
)
def then_event_log_state_transition(
    context: object, from_status: str, to_status: str
) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    found = False
    for _, event in events:
        if event.get("event_type") != "state_transition":
            continue
        payload = event.get("payload", {})
        if (
            payload.get("from_status") == from_status
            and payload.get("to_status") == to_status
        ):
            found = True
            break
    assert found, f"expected state transition {from_status} -> {to_status}"


@then(
    'the event log for the last issue should include a field update for "{field}" from "{from_value}" to "{to_value}"'
)
def then_event_log_field_update(
    context: object, field: str, from_value: str, to_value: str
) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    found = False
    for _, event in events:
        if event.get("event_type") != "field_updated":
            continue
        changes = event.get("payload", {}).get("changes", {})
        change = changes.get(field)
        if not change:
            continue
        if change.get("from") == from_value and change.get("to") == to_value:
            found = True
            break
    assert found, f"expected field update for {field}"


@then(
    'the event log for the last issue should include a comment_added event by "{author}" with a comment id'
)
def then_event_log_comment_added(context: object, author: str) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    found = False
    for _, event in events:
        if event.get("event_type") != "comment_added":
            continue
        payload = event.get("payload", {})
        if payload.get("comment_author") == author and payload.get("comment_id"):
            found = True
            break
    assert found, f"expected comment_added event for {author}"


@then("the event log for the last issue should not include comment text")
def then_event_log_no_comment_text(context: object) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    for _, event in events:
        event_type = event.get("event_type", "")
        if not event_type.startswith("comment_"):
            continue
        payload = event.get("payload", {})
        assert "text" not in payload, "comment text should not be stored in events"


@then(
    'the event log for the last issue should include a dependency "{dependency_type}" on "{target}"'
)
def then_event_log_dependency(
    context: object, dependency_type: str, target: str
) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    found = False
    for _, event in events:
        if event.get("event_type") != "dependency_added":
            continue
        payload = event.get("payload", {})
        if (
            payload.get("dependency_type") == dependency_type
            and payload.get("target_id") == target
        ):
            found = True
            break
    assert found, f"expected dependency event for {dependency_type} -> {target}"
