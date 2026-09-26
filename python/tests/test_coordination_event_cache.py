"""Test coordination event file caching behavior."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from kanbus import event_history
from kanbus.coordination import (
    _clear_event_file_cache,
    _load_coordination_events,
    inspect_lease,
)


def _stamp(value: datetime) -> str:
    """Format a datetime as RFC3339 for event payloads."""
    return (
        value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _write_claim_event(
    events_dir: Path,
    *,
    event_id: str,
    resource: str,
    owner: str,
    claim_id: str,
    at: datetime,
    ttl_s: int = 300,
    contention_window_s: int = 5,
) -> None:
    """Write a coordination.claim event to the events directory."""
    record = event_history.EventRecord(
        event_id=event_id,
        issue_id=resource,
        event_type="coordination.claim",
        occurred_at=_stamp(at),
        actor_id=owner,
        payload={
            "owner": owner,
            "claim_id": claim_id,
            "lease_expires_at": _stamp(at + timedelta(seconds=ttl_s)),
            "contention_window_s": contention_window_s,
            "ttl_s": ttl_s,
            "operation_sequence": 1,
        },
    )
    event_history.write_events_batch(events_dir, [record])


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the event file cache before and after each test."""
    _clear_event_file_cache()
    yield
    _clear_event_file_cache()


def test_reading_twice_caches_files(tmp_path: Path) -> None:
    """Reading events twice should result in each file being read only once."""
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)

    for i in range(20):
        _write_claim_event(
            events_dir,
            event_id=f"evt-{i:02d}",
            resource=f"resource-{i % 3}",
            owner=f"owner-{i % 3}",
            claim_id=f"claim-{i % 3}",
            at=start + timedelta(seconds=i),
        )

    read_count = 0
    original_read_text = Path.read_text

    def counting_read_text(self: Path, encoding: str = "utf-8") -> str:
        nonlocal read_count
        if self.parent == events_dir:
            read_count += 1
        return original_read_text(self, encoding=encoding)

    with patch.object(Path, "read_text", counting_read_text):
        _load_coordination_events(events_dir, "resource-0")
        count_after_first = read_count
        _load_coordination_events(events_dir, "resource-0")
        count_after_second = read_count

        _load_coordination_events(events_dir, "resource-1")
        _load_coordination_events(events_dir, "resource-2")
        count_after_fourth = read_count

        _load_coordination_events(events_dir, "resource-0")
        count_after_fifth = read_count

    assert (
        count_after_second == count_after_first
    ), "Second call should not re-read files (cache hit)"
    assert count_after_fourth <= 20, "Total reads should be at most the number of files"
    assert (
        count_after_fifth == count_after_fourth
    ), "Fifth call should hit cache for all files"


def test_cache_invalidation_on_file_change(tmp_path: Path) -> None:
    """Modifying a file should invalidate its cache entry."""
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)

    _write_claim_event(
        events_dir,
        event_id="evt-1",
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
        at=start,
        ttl_s=300,
    )

    events = _load_coordination_events(events_dir, "job:1")
    assert len(events) == 1
    assert events[0]["payload"]["owner"] == "worker-a"

    event_file = list(events_dir.glob("*.json"))[0]
    new_content = {
        "event_id": "evt-1",
        "issue_id": "job:1",
        "event_type": "coordination.claim",
        "occurred_at": _stamp(start),
        "actor_id": "worker-b",
        "payload": {
            "owner": "worker-b",
            "claim_id": "claim-b",
            "lease_expires_at": _stamp(start + timedelta(seconds=300)),
            "contention_window_s": 5,
            "ttl_s": 300,
            "operation_sequence": 1,
        },
    }
    event_file.write_text(json.dumps(new_content), encoding="utf-8")

    events = _load_coordination_events(events_dir, "job:1")
    assert len(events) == 1
    assert events[0]["payload"]["owner"] == "worker-b"


def test_new_files_are_seen(tmp_path: Path) -> None:
    """New event files added after a first call should be seen in subsequent calls."""
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)

    _write_claim_event(
        events_dir,
        event_id="evt-1",
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
        at=start,
    )

    events = _load_coordination_events(events_dir, "job:1")
    assert len(events) == 1

    _write_claim_event(
        events_dir,
        event_id="evt-2",
        resource="job:1",
        owner="worker-b",
        claim_id="claim-b",
        at=start + timedelta(seconds=1),
    )

    events = _load_coordination_events(events_dir, "job:1")
    assert len(events) == 2


def test_cache_is_not_polluted_by_mutations(tmp_path: Path) -> None:
    """Mutating a returned record should not affect cached data."""
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)

    _write_claim_event(
        events_dir,
        event_id="evt-1",
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
        at=start,
    )

    records_1 = _load_coordination_events(events_dir, "job:1")
    assert len(records_1) == 1
    original_owner = records_1[0]["payload"]["owner"]

    records_1[0]["payload"]["owner"] = "mutated-worker"

    records_2 = _load_coordination_events(events_dir, "job:1")
    assert len(records_2) == 1
    assert (
        records_2[0]["payload"]["owner"] == original_owner
    ), "Cached data should not be polluted by mutations to returned records"


def test_unreadable_file_is_skipped(tmp_path: Path) -> None:
    """A file that cannot be read should be skipped without raising."""
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)

    _write_claim_event(
        events_dir,
        event_id="evt-1",
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
        at=start,
    )

    bad_file = events_dir / "bad.json"
    bad_file.write_text("not json", encoding="utf-8")

    events = _load_coordination_events(events_dir, "job:1")
    assert len(events) == 1
    assert events[0]["event_id"] == "evt-1"


def test_invalid_json_file_is_skipped(tmp_path: Path) -> None:
    """A file with invalid JSON should be skipped without raising."""
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)

    _write_claim_event(
        events_dir,
        event_id="evt-1",
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
        at=start,
    )

    bad_file = events_dir / "malformed.json"
    bad_file.write_text("{invalid json}", encoding="utf-8")

    events = _load_coordination_events(events_dir, "job:1")
    assert len(events) == 1
    assert events[0]["event_id"] == "evt-1"


def test_deleted_file_is_removed_from_results(tmp_path: Path) -> None:
    """A file deleted between calls should not appear in subsequent results."""
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)

    _write_claim_event(
        events_dir,
        event_id="evt-1",
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
        at=start,
    )
    _write_claim_event(
        events_dir,
        event_id="evt-2",
        resource="job:1",
        owner="worker-b",
        claim_id="claim-b",
        at=start + timedelta(seconds=1),
    )

    events = _load_coordination_events(events_dir, "job:1")
    assert len(events) == 2

    event_files = list(events_dir.glob("*.json"))
    event_files[0].unlink()

    events = _load_coordination_events(events_dir, "job:1")
    assert len(events) == 1


def test_cache_with_inspect_lease_caching(tmp_path: Path) -> None:
    """Cache should reduce file reads when inspect_lease is called multiple times."""
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)

    for i in range(10):
        _write_claim_event(
            events_dir,
            event_id=f"evt-{i:02d}",
            resource="job:1",
            owner="worker-a",
            claim_id="claim-a",
            at=start + timedelta(seconds=i),
        )

    read_count = 0
    original_read_text = Path.read_text

    def counting_read_text(self: Path, encoding: str = "utf-8") -> str:
        nonlocal read_count
        if self.parent == events_dir:
            read_count += 1
        return original_read_text(self, encoding=encoding)

    with patch.object(Path, "read_text", counting_read_text):
        lease_1 = inspect_lease(events_dir, "job:1", now=start + timedelta(seconds=5))
        count_after_first = read_count

        lease_2 = inspect_lease(events_dir, "job:1", now=start + timedelta(seconds=6))
        count_after_second = read_count

    assert lease_1.active
    assert lease_2.active
    assert (
        count_after_second == count_after_first
    ), "Second inspect_lease should hit cache and not re-read files"
