from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from pydantic import ValidationError

from kanbus import event_history
from kanbus.cli import cli
from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.coordination import (
    CoordinationError,
    claim,
    inspect_lease,
    parse_duration,
    release,
    renew,
)
from kanbus.models import CoordinationConfiguration


def _stamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _write_event(
    events_dir: Path,
    *,
    event_type: str,
    at: datetime,
    payload: dict[str, object],
    event_id: str,
    resource: str = "job:1",
) -> None:
    record = event_history.EventRecord(
        event_id=event_id,
        issue_id=resource,
        event_type=event_type,
        occurred_at=_stamp(at),
        actor_id=str(payload.get("owner", "worker")),
        payload=payload,
    )
    event_history.write_events_batch(events_dir, [record])


def _claim_payload(
    owner: str,
    claim_id: str,
    at: datetime,
    *,
    ttl_s: int = 300,
    contention_window_s: int = 5,
) -> dict[str, object]:
    return {
        "owner": owner,
        "claim_id": claim_id,
        "lease_expires_at": _stamp(at + timedelta(seconds=ttl_s)),
        "contention_window_s": contention_window_s,
        "ttl_s": ttl_s,
    }


def test_coordination_duration_parser_and_model_validation() -> None:
    assert [parse_duration(value) for value in ("2s", "3m", "1h")] == [
        2,
        180,
        3600,
    ]
    for value in ("0s", "-1s", "1.5s", "2d", "s"):
        with pytest.raises(CoordinationError, match="positive integer"):
            parse_duration(value)
        with pytest.raises(ValidationError, match="positive integer"):
            CoordinationConfiguration(contention_window=value)


def test_configuration_defaults_to_git_with_independent_durations() -> None:
    configuration = CoordinationConfiguration()
    assert configuration.providers == ["git"]
    assert configuration.contention_window == "5s"
    assert configuration.default_lease_ttl == "300s"
    with pytest.raises(
        ValidationError, match="coordination providers must be exactly git"
    ):
        CoordinationConfiguration(providers=["git", "mqtt"])


def test_claims_choose_stable_contender_and_closed_window_winner(
    tmp_path: Path,
) -> None:
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)
    _write_event(
        events_dir,
        event_type="coordination.claim",
        at=start,
        payload=_claim_payload("worker-z", "claim-z", start),
        event_id="evt-z",
    )
    _write_event(
        events_dir,
        event_type="coordination.claim",
        at=start + timedelta(seconds=2),
        payload=_claim_payload("worker-a", "claim-a", start + timedelta(seconds=2)),
        event_id="evt-a",
    )
    _write_event(
        events_dir,
        event_type="coordination.claim",
        at=start + timedelta(seconds=6),
        payload=_claim_payload("worker-0", "claim-0", start + timedelta(seconds=6)),
        event_id="evt-0",
    )

    state = inspect_lease(events_dir, "job:1", now=start + timedelta(seconds=10))

    assert state.active
    assert (state.owner, state.claim_id) == ("worker-a", "claim-a")
    assert state.expires_at == start + timedelta(seconds=302)


def test_event_id_breaks_duplicate_claim_ties_and_selects_matching_expiry(
    tmp_path: Path,
) -> None:
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)
    _write_event(
        events_dir,
        event_type="coordination.claim",
        at=start,
        payload=_claim_payload("worker", "same-claim", start, ttl_s=300),
        event_id="z-event",
    )
    second_claim_at = start + timedelta(seconds=1)
    _write_event(
        events_dir,
        event_type="coordination.claim",
        at=second_claim_at,
        payload=_claim_payload("worker", "same-claim", second_claim_at, ttl_s=600),
        event_id="a-event",
    )

    state = inspect_lease(events_dir, "job:1", now=start + timedelta(seconds=10))

    assert state.active
    assert state.expires_at == second_claim_at + timedelta(seconds=600)


def test_expired_winner_allows_a_new_epoch(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)
    _write_event(
        events_dir,
        event_type="coordination.claim",
        at=start,
        payload=_claim_payload("old-worker", "old-claim", start, ttl_s=10),
        event_id="evt-old",
    )
    _write_event(
        events_dir,
        event_type="coordination.claim",
        at=start + timedelta(seconds=11),
        payload=_claim_payload(
            "new-worker", "new-claim", start + timedelta(seconds=11)
        ),
        event_id="evt-new",
    )

    state = inspect_lease(events_dir, "job:1", now=start + timedelta(seconds=12))

    assert state.active
    assert (state.owner, state.claim_id) == ("new-worker", "new-claim")


def test_renew_requires_winner_and_extends_existing_expiry(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)
    configuration = CoordinationConfiguration()
    _write_event(
        events_dir,
        event_type="coordination.claim",
        at=start,
        payload=_claim_payload("worker", "claim", start),
        event_id="evt-claim",
    )

    with pytest.raises(CoordinationError, match="lease owner mismatch"):
        renew(
            events_dir,
            configuration,
            resource="job:1",
            owner="other",
            claim_id="claim",
            now=start + timedelta(seconds=1),
        )

    renewed = renew(
        events_dir,
        configuration,
        resource="job:1",
        owner="worker",
        claim_id="claim",
        extend="120s",
        now=start + timedelta(seconds=6),
    )

    assert renewed.expires_at == start + timedelta(seconds=420)
    event_files = list(events_dir.glob("*.json"))
    renewal = next(
        json.loads(path.read_text(encoding="utf-8"))
        for path in event_files
        if json.loads(path.read_text(encoding="utf-8"))["event_type"]
        == "coordination.renew"
    )
    assert renewal["issue_id"] == "job:1"
    assert renewal["payload"]["lease_expires_at"] == _stamp(
        start + timedelta(seconds=420)
    )


def test_release_and_expiry_make_resource_eligible(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    start = datetime(2026, 9, 16, 12, tzinfo=UTC)
    configuration = CoordinationConfiguration()
    claim(
        events_dir,
        configuration,
        resource="job:1",
        owner="worker",
        claim_id="claim",
        now=start,
    )
    release(
        events_dir,
        resource="job:1",
        owner="worker",
        claim_id="claim",
        now=start + timedelta(seconds=6),
    )

    assert not inspect_lease(
        events_dir, "job:1", now=start + timedelta(seconds=7)
    ).active

    claim(
        events_dir,
        configuration,
        resource="job:1",
        owner="worker-2",
        claim_id="claim-2",
        now=start + timedelta(seconds=8),
    )
    assert (
        inspect_lease(events_dir, "job:1", now=start + timedelta(seconds=9)).owner
        == "worker-2"
    )
    assert not inspect_lease(
        events_dir, "job:1", now=start + timedelta(seconds=400)
    ).active


def test_cli_emits_locked_output_and_writes_resource_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config = copy.deepcopy(DEFAULT_CONFIGURATION)
    config["coordination"] = {
        "providers": ["git"],
        "contention_window": "5s",
        "default_lease_ttl": "300s",
    }
    (tmp_path / ".kanbus.yml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:cli",
            "--owner",
            "worker-cli",
            "--claim-id",
            "claim-cli",
        ],
    )

    assert result.exit_code == 0
    assert result.output.startswith(
        "provider: git\nresource: job:cli\nstate: active soft ownership\n"
        "owner: worker-cli\nclaim_id: claim-cli\nexpires_at: "
    )
    event = json.loads(next((project_dir / "events").glob("*.json")).read_text())
    assert event["issue_id"] == "job:cli"
    assert event["event_type"] == "coordination.claim"
    assert event["payload"]["owner"] == "worker-cli"
    assert event["payload"]["claim_id"] == "claim-cli"


def test_cli_rejects_mismatched_renewal_with_exact_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config = copy.deepcopy(DEFAULT_CONFIGURATION)
    (tmp_path / ".kanbus.yml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    claim_result = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:mismatch",
            "--owner",
            "worker-a",
            "--claim-id",
            "claim-a",
        ],
    )
    assert claim_result.exit_code == 0

    result = CliRunner().invoke(
        cli,
        [
            "coordination",
            "renew",
            "--resource",
            "job:mismatch",
            "--owner",
            "worker-b",
            "--claim-id",
            "claim-a",
        ],
    )

    assert result.exit_code == 1
    assert "lease owner mismatch" in result.stderr


def test_cli_rejects_non_git_provider_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config = copy.deepcopy(DEFAULT_CONFIGURATION)
    config["coordination"] = {
        "providers": ["git", "mqtt"],
        "contention_window": "5s",
        "default_lease_ttl": "300s",
    }
    (tmp_path / ".kanbus.yml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:provider",
            "--owner",
            "worker",
            "--claim-id",
            "claim",
        ],
    )

    assert result.exit_code == 1
    assert "coordination providers must be exactly git" in result.output


def test_configuration_loader_reports_field_qualified_duration_error(
    tmp_path: Path,
) -> None:
    config = copy.deepcopy(DEFAULT_CONFIGURATION)
    config["coordination"]["contention_window"] = "0s"
    config_path = tmp_path / ".kanbus.yml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfigurationError) as error:
        load_project_configuration(config_path)

    assert str(error.value) == (
        "coordination.contention_window: duration must be a positive integer "
        "followed by s, m, or h"
    )
