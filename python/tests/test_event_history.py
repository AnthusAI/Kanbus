from datetime import datetime, timezone

from kanbus.event_history import (
    build_update_events,
    create_event,
    event_filename,
    write_events_batch,
)
from kanbus.models import IssueData


def _issue(identifier: str, status: str = "open", title: str = "Title") -> IssueData:
    now = datetime(2026, 2, 21, 0, 0, 0, tzinfo=timezone.utc)
    return IssueData(
        id=identifier,
        title=title,
        description="",
        type="task",
        status=status,
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=now,
        updated_at=now,
        closed_at=None,
        custom={},
    )


def test_event_filename_sorts_by_timestamp() -> None:
    a = event_filename("2026-02-21T06:09:40.100Z", "a")
    b = event_filename("2026-02-21T06:09:40.200Z", "b")
    assert a < b


def test_write_events_batch_creates_file(tmp_path) -> None:
    event = create_event(
        issue_id="kanbus-aaa",
        event_type="issue_created",
        actor_id="actor",
        payload={"title": "Test"},
        occurred_at="2026-02-21T06:09:40.180Z",
    )
    paths = write_events_batch(tmp_path / "events", [event])
    assert len(paths) == 1
    assert paths[0].exists()


def test_build_update_events_includes_transition_and_fields() -> None:
    before = _issue("kanbus-aaa", status="open", title="Old")
    after = _issue("kanbus-aaa", status="closed", title="New")
    events = build_update_events(before, after, "actor", "2026-02-21T06:09:40.180Z")
    types = {event.event_type for event in events}
    assert "state_transition" in types
    assert "field_updated" in types
