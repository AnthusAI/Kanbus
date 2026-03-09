from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from kanbus import event_history

from test_helpers import build_issue


def test_now_timestamp_and_event_filename_shapes() -> None:
    ts = event_history.now_timestamp()
    assert ts.endswith("Z")
    assert "T" in ts
    assert event_history.event_filename("2026-03-09T00:00:00.000Z", "evt-1").endswith(
        "__evt-1.json"
    )


def test_create_event_uses_given_or_generated_timestamp() -> None:
    explicit = event_history.create_event(
        issue_id="kanbus-1",
        event_type="field_updated",
        actor_id="agent",
        payload={"k": "v"},
        occurred_at="2026-03-09T00:00:00.000Z",
    )
    assert explicit.occurred_at == "2026-03-09T00:00:00.000Z"

    generated = event_history.create_event(
        issue_id="kanbus-1",
        event_type="field_updated",
        actor_id="agent",
        payload={"k": "v"},
    )
    assert generated.occurred_at.endswith("Z")
    assert generated.event_id


def test_events_dir_helpers_handle_project_and_local_paths(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    local_dir = tmp_path / "project-local"
    (local_dir / "issues").mkdir(parents=True, exist_ok=True)
    issue_path = local_dir / "issues" / "kanbus-1.json"
    issue_path.write_text("{}", encoding="utf-8")

    assert event_history.events_dir_for_project(project_dir) == project_dir / "events"
    assert event_history.events_dir_for_local(project_dir) == local_dir / "events"
    assert event_history.events_dir_for_issue_path(project_dir, issue_path) == local_dir / "events"
    assert (
        event_history.events_dir_for_issue_path(project_dir, project_dir / "issues" / "x.json")
        == project_dir / "events"
    )
    assert event_history.events_dir_for_issue(project_dir, "kanbus-1") == local_dir / "events"
    assert event_history.events_dir_for_issue(project_dir, "missing") == project_dir / "events"


def test_events_dir_for_local_raises_when_parent_missing() -> None:
    fake_path = SimpleNamespace(parent=None)
    try:
        event_history.events_dir_for_local(fake_path)  # type: ignore[arg-type]
    except RuntimeError as error:
        assert "project-local path unavailable" in str(error)
    else:
        raise AssertionError("expected RuntimeError")


def test_write_events_batch_and_rollback(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    event = event_history.create_event(
        issue_id="kanbus-1",
        event_type="created",
        actor_id="agent",
        payload={"x": 1},
        occurred_at="2026-03-09T00:00:00.000Z",
    )
    written = event_history.write_events_batch(events_dir, [event])
    assert len(written) == 1
    assert written[0].exists()

    event_history.rollback_event_files(written)
    assert not written[0].exists()

    assert event_history.write_events_batch(events_dir, []) == []


def test_write_events_batch_rolls_back_on_failure(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    first = event_history.create_event(
        issue_id="kanbus-1",
        event_type="created",
        actor_id="agent",
        payload={"x": 1},
        occurred_at="2026-03-09T00:00:00.000Z",
    )
    second = event_history.create_event(
        issue_id="kanbus-2",
        event_type="created",
        actor_id="agent",
        payload={"y": 2},
        occurred_at="2026-03-09T00:00:01.000Z",
    )

    original_replace = Path.replace
    calls = {"count": 0}

    def flaky_replace(self: Path, target: Path) -> Path:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("replace failed")
        return original_replace(self, target)

    with patch.object(Path, "replace", flaky_replace):
        try:
            event_history.write_events_batch(events_dir, [first, second])
        except RuntimeError as error:
            assert "replace failed" in str(error)
        else:
            raise AssertionError("expected RuntimeError")

    assert list(events_dir.glob("*.json")) == []


def test_delete_events_for_issues_handles_invalid_json_and_empty_inputs(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    keep = events_dir / "keep.json"
    drop = events_dir / "drop.json"
    bad = events_dir / "bad.json"
    keep.write_text(json.dumps({"issue_id": "kanbus-keep"}), encoding="utf-8")
    drop.write_text(json.dumps({"issue_id": "kanbus-drop"}), encoding="utf-8")
    bad.write_text("{", encoding="utf-8")

    event_history.delete_events_for_issues(events_dir, set())
    assert keep.exists()
    assert drop.exists()

    event_history.delete_events_for_issues(events_dir, {"kanbus-drop"})
    assert keep.exists()
    assert not drop.exists()
    assert bad.exists()


def test_payload_helpers_and_field_update_diff() -> None:
    before = build_issue(
        "kanbus-1",
        title="Before",
        status="open",
        labels=["a"],
        priority=2,
        parent=None,
    ).model_copy(update={"description": "old"})
    after = build_issue(
        "kanbus-1",
        title="After",
        status="in_progress",
        labels=["a", "b"],
        priority=1,
        parent="kanbus-parent",
    ).model_copy(update={"description": "new"})

    created = event_history.issue_created_payload(after)
    assert created["title"] == "After"
    assert created["status"] == "in_progress"
    assert event_history.issue_deleted_payload(after)["issue_type"] == after.issue_type
    assert event_history.state_transition_payload("open", "closed") == {
        "from_status": "open",
        "to_status": "closed",
    }
    assert event_history.comment_payload("c1", "ryan") == {
        "comment_id": "c1",
        "comment_author": "ryan",
    }
    assert event_history.comment_updated_payload("c1", "ryan")["changed_fields"] == ["text"]
    assert event_history.dependency_payload("blocks", "kanbus-2") == {
        "dependency_type": "blocks",
        "target_id": "kanbus-2",
    }
    assert event_history.transfer_payload("shared", "local") == {
        "from_location": "shared",
        "to_location": "local",
    }

    diff = event_history.field_update_payload(before, after)
    assert diff is not None
    assert "title" in diff["changes"]
    assert "priority" in diff["changes"]
    assert event_history.field_update_payload(after, after) is None


def test_build_update_events_emits_transition_and_field_updated() -> None:
    before = build_issue("kanbus-1", title="Before", status="open")
    after = build_issue("kanbus-1", title="After", status="in_progress")
    events = event_history.build_update_events(
        before=before,
        after=after,
        actor_id="agent",
        occurred_at="2026-03-09T00:00:00.000Z",
    )
    assert [event.event_type for event in events] == ["state_transition", "field_updated"]
    assert event_history.build_update_events(after, after, "agent", "2026-03-09T00:00:00.000Z") == []
