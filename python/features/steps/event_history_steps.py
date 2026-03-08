"""Behave steps for event history."""

from __future__ import annotations

import json
import re

from behave import then, when

from kanbus.issue_comment import delete_comment, update_comment

from features.steps.shared import (
    capture_issue_identifier,
    load_project_directory,
    read_issue_file,
    run_cli,
)


def _last_issue_id(context: object) -> str:
    identifier = getattr(context, "last_issue_id", None)
    if not identifier:
        raise AssertionError("last issue id not set")
    return identifier


def _load_issue_events(context: object, issue_id: str) -> list[tuple[str, dict]]:
    project_dir = load_project_directory(context)
    events_dirs = [project_dir / "events"]
    local_dir = project_dir.parent / "project-local" / "events"
    if local_dir.exists():
        events_dirs.append(local_dir)
    events: list[tuple[str, dict]] = []
    for events_dir in events_dirs:
        if not events_dir.exists():
            continue
        for path in events_dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("issue_id") == issue_id:
                events.append((path.name, payload))
    return events


def _capture_last_comment(context: object) -> tuple[str, str]:
    issue_id = _last_issue_id(context)
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, issue_id)
    if not issue.comments:
        raise AssertionError("expected a comment on the issue")
    comment = issue.comments[-1]
    if not comment.id:
        raise AssertionError("comment id not set")
    context.last_comment_id = comment.id
    context.last_comment_author = comment.author
    return comment.id, comment.author


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


@when('I update the last issue description to "{description}"')
def when_update_last_issue_description(context: object, description: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f'kanbus update {identifier} --description "{description}"')


@when("I localize the last issue")
def when_localize_last_issue(context: object) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f"kanbus localize {identifier}")


@when("I promote the last issue")
def when_promote_last_issue(context: object) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f"kanbus promote {identifier}")


@when('I update the last issue assignee to "{assignee}"')
def when_update_last_issue_assignee(context: object, assignee: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f"kanbus update {identifier} --assignee {assignee}")


@when("I update the last issue priority to {priority}")
def when_update_last_issue_priority(context: object, priority: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f"kanbus update {identifier} --priority {priority}")


@when('I set labels on the last issue to "{labels}"')
def when_set_labels_last_issue(context: object, labels: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f'kanbus update {identifier} --set-labels "{labels}"')


@when('I add a comment to the last issue with text "{text}"')
def when_add_comment_last_issue(context: object, text: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f'kanbus comment {identifier} "{text}"')
    _capture_last_comment(context)


@when('I update the last issue comment to "{text}"')
def when_update_last_issue_comment(context: object, text: str) -> None:
    identifier = _last_issue_id(context)
    comment_id = getattr(context, "last_comment_id", None)
    if not comment_id:
        comment_id, _ = _capture_last_comment(context)
    project_dir = load_project_directory(context)
    update_comment(project_dir, identifier, comment_id, text)


@when("I delete the last issue comment")
def when_delete_last_issue_comment(context: object) -> None:
    identifier = _last_issue_id(context)
    comment_id = getattr(context, "last_comment_id", None)
    if not comment_id:
        comment_id, _ = _capture_last_comment(context)
    project_dir = load_project_directory(context)
    delete_comment(project_dir, identifier, comment_id)


@when('I add a blocked-by dependency from the last issue to "{target}"')
def when_add_dependency(context: object, target: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f"kanbus dep {identifier} blocked-by {target}")


@when('I remove the blocked-by dependency from the last issue to "{target}"')
def when_remove_dependency(context: object, target: str) -> None:
    identifier = _last_issue_id(context)
    run_cli(context, f"kanbus dep {identifier} remove blocked-by {target}")


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
    "the event log for the last issue should include a priority update from {from_value} to {to_value}"
)
def then_event_log_priority_update(
    context: object, from_value: str, to_value: str
) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    expected_from = int(from_value)
    expected_to = int(to_value)
    found = False
    for _, event in events:
        if event.get("event_type") != "field_updated":
            continue
        changes = event.get("payload", {}).get("changes", {})
        change = changes.get("priority")
        if not change:
            continue
        if change.get("from") == expected_from and change.get("to") == expected_to:
            found = True
            break
    assert found, "expected priority field update"


@then(
    'the event log for the last issue should include a labels update from "{from_labels}" to "{to_labels}"'
)
def then_event_log_labels_update(
    context: object, from_labels: str, to_labels: str
) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    expected_from = [label.strip() for label in from_labels.split(",") if label.strip()]
    expected_to = [label.strip() for label in to_labels.split(",") if label.strip()]
    found = False
    for _, event in events:
        if event.get("event_type") != "field_updated":
            continue
        changes = event.get("payload", {}).get("changes", {})
        change = changes.get("labels")
        if not change:
            continue
        if change.get("from") == expected_from and change.get("to") == expected_to:
            found = True
            break
    assert found, "expected labels field update"


@then(
    'the event log for the last issue should include a transfer event "{event_type}" from "{from_location}" to "{to_location}"'
)
def then_event_log_transfer_event(
    context: object, event_type: str, from_location: str, to_location: str
) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    found = False
    for _, event in events:
        if event.get("event_type") != event_type:
            continue
        payload = event.get("payload", {})
        if (
            payload.get("from_location") == from_location
            and payload.get("to_location") == to_location
        ):
            found = True
            break
    assert found, f"expected transfer event {event_type}"


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


@then(
    'the event log for the last issue should include a comment_updated event by "{author}" with the last comment id'
)
def then_event_log_comment_updated(context: object, author: str) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    expected_id = getattr(context, "last_comment_id", None)
    found = False
    for _, event in events:
        if event.get("event_type") != "comment_updated":
            continue
        payload = event.get("payload", {})
        if payload.get("comment_author") != author:
            continue
        comment_id = payload.get("comment_id")
        if expected_id is not None and comment_id != expected_id:
            continue
        if not comment_id:
            continue
        found = True
        break
    assert found, f"expected comment_updated event for {author}"


@then(
    'the event log for the last issue should include a comment_deleted event by "{author}" with the last comment id'
)
def then_event_log_comment_deleted(context: object, author: str) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    expected_id = getattr(context, "last_comment_id", None)
    found = False
    for _, event in events:
        if event.get("event_type") != "comment_deleted":
            continue
        payload = event.get("payload", {})
        if payload.get("comment_author") != author:
            continue
        comment_id = payload.get("comment_id")
        if expected_id is not None and comment_id != expected_id:
            continue
        if not comment_id:
            continue
        found = True
        break
    assert found, f"expected comment_deleted event for {author}"


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


@then(
    'the event log for the last issue should include a dependency_removed "{dependency_type}" on "{target}"'
)
def then_event_log_dependency_removed(
    context: object, dependency_type: str, target: str
) -> None:
    identifier = _last_issue_id(context)
    events = _load_issue_events(context, identifier)
    found = False
    for _, event in events:
        if event.get("event_type") != "dependency_removed":
            continue
        payload = event.get("payload", {})
        if (
            payload.get("dependency_type") == dependency_type
            and payload.get("target_id") == target
        ):
            found = True
            break
    assert found, f"expected dependency_removed event for {dependency_type} -> {target}"
