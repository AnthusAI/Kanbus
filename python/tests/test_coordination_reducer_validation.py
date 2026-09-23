"""Malformed history, gossip merge, and append-failure reducer tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kanbus import coordination
from kanbus.coordination import CoordinationError, inspect_lease
from kanbus.event_history import EventRecord, write_events_batch
from kanbus.models import CoordinationConfiguration


def _stamp(value: datetime) -> str:
    return coordination.format_timestamp(value)


def _claim_record(
    *,
    event_id: str,
    resource: str,
    owner: str,
    claim_id: str,
    at: datetime,
    sequence: int | None = None,
) -> dict:
    payload = {
        "owner": owner,
        "claim_id": claim_id,
        "lease_expires_at": _stamp(at + timedelta(seconds=300)),
        "contention_window_s": 5,
        "ttl_s": 300,
    }
    if sequence is not None:
        payload["operation_sequence"] = sequence
    return {
        "event_id": event_id,
        "issue_id": resource,
        "event_type": "coordination.claim",
        "occurred_at": _stamp(at),
        "actor_id": owner,
        "payload": payload,
    }


def test_reducer_normalizes_legacy_naive_timestamps_and_skips_corrupt_history(
    tmp_path: Path,
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    at = datetime(2026, 9, 17, 12, tzinfo=UTC)
    record = _claim_record(
        event_id="legacy-claim",
        resource="job:legacy",
        owner="worker",
        claim_id="claim",
        at=at,
    )
    record["occurred_at"] = "2026-09-17T12:00:00"
    (events_dir / "legacy.json").write_text(json.dumps(record), encoding="utf-8")
    (events_dir / "bad-json.json").write_text("{", encoding="utf-8")
    invalid_time = _claim_record(
        event_id="invalid-time",
        resource="job:legacy",
        owner="worker-x",
        claim_id="claim-x",
        at=at,
    )
    invalid_time["occurred_at"] = "tomorrow"
    (events_dir / "invalid-time.json").write_text(
        json.dumps(invalid_time), encoding="utf-8"
    )

    state = inspect_lease(events_dir, "job:legacy", now=at + timedelta(seconds=1))

    assert state.active
    assert state.claimed_at == at
    assert (state.owner, state.claim_id) == ("worker", "claim")


def test_gossip_merge_deduplicates_durable_ids_and_discards_invalid_candidates(
    tmp_path: Path,
) -> None:
    events_dir = tmp_path / "events"
    at = datetime(2026, 9, 17, 12, tzinfo=UTC)
    durable = _claim_record(
        event_id="shared-id",
        resource="job:gossip",
        owner="durable-worker",
        claim_id="z-durable",
        at=at,
    )
    (events_dir / "durable.json").parent.mkdir(parents=True)
    (events_dir / "durable.json").write_text(json.dumps(durable), encoding="utf-8")
    contender = _claim_record(
        event_id="remote-valid",
        resource="job:gossip",
        owner="peer",
        claim_id="a-peer",
        at=at + timedelta(seconds=1),
    )
    invalid_sequence = _claim_record(
        event_id="remote-invalid-sequence",
        resource="job:gossip",
        owner="bad-peer",
        claim_id="0-invalid",
        at=at,
        sequence=0,
    )
    invalid_time = _claim_record(
        event_id="remote-invalid-time",
        resource="job:gossip",
        owner="bad-peer",
        claim_id="0-invalid-time",
        at=at,
    )
    invalid_time["occurred_at"] = "not-a-time"
    additional = [
        None,
        {**contender, "issue_id": "another-resource"},
        {**contender, "event_type": "issue.updated"},
        {**contender, "payload": []},
        {**contender, "event_id": ""},
        invalid_sequence,
        invalid_time,
        _claim_record(
            event_id="shared-id",
            resource="job:gossip",
            owner="forged-peer",
            claim_id="0-forged",
            at=at,
        ),
        contender,
    ]

    state = inspect_lease(
        events_dir,
        "job:gossip",
        now=at + timedelta(seconds=3),
        additional_events=additional,
    )

    assert state.active
    assert (state.owner, state.claim_id, state.event_id) == (
        "peer",
        "a-peer",
        "remote-valid",
    )


def test_reducer_append_failure_is_reported_as_coordination_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_write(*_args, **_kwargs):
        raise OSError("read only filesystem")

    monkeypatch.setattr(coordination, "write_events_batch", fail_write)

    with pytest.raises(CoordinationError, match="read only filesystem"):
        coordination.claim(
            tmp_path / "events",
            CoordinationConfiguration(),
            resource="job:append-failure",
            owner="worker",
            claim_id="claim",
            now=datetime(2026, 9, 17, 12, tzinfo=UTC),
        )


def test_release_rejects_unknown_owner_and_claim_id(tmp_path: Path) -> None:
    at = datetime(2026, 9, 17, 12, tzinfo=UTC)
    event = EventRecord(
        event_id="claim-event",
        issue_id="job:release-mismatch",
        event_type="coordination.claim",
        occurred_at=_stamp(at),
        actor_id="worker",
        payload={
            "owner": "worker",
            "claim_id": "claim",
            "lease_expires_at": _stamp(at + timedelta(seconds=300)),
            "contention_window_s": 5,
            "ttl_s": 300,
        },
    )
    events_dir = tmp_path / "events"
    write_events_batch(events_dir, [event])

    for owner, claim_id in (("other", "claim"), ("worker", "other-claim")):
        with pytest.raises(CoordinationError, match="lease owner mismatch"):
            coordination.release(
                events_dir,
                resource="job:release-mismatch",
                owner=owner,
                claim_id=claim_id,
                now=at + timedelta(seconds=1),
            )
