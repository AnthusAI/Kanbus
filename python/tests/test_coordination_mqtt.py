from __future__ import annotations

import copy
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from click.testing import CliRunner
from pydantic import ValidationError

from kanbus import coordination, coordination_mqtt, event_history, gossip
from kanbus.cli import _coordination_provider, cli
from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.gossip import CoordinationGossipEnvelope, DedupeSet
from kanbus.models import ProjectConfiguration


def _configuration(*, providers: list[str] | None = None) -> ProjectConfiguration:
    data = copy.deepcopy(DEFAULT_CONFIGURATION)
    if providers is not None:
        data["coordination"]["providers"] = providers
    data["realtime"].update(
        {
            "transport": "mqtt",
            "broker": "mqtt://broker.example:1883",
            "autostart": False,
        }
    )
    return ProjectConfiguration.model_validate(data)


def _stamp(value: datetime) -> str:
    return coordination.format_timestamp(value)


def _current_test_time() -> datetime:
    """Return a stable-in-test timestamp that remains inside overlay TTLs."""
    return coordination.utc_now().replace(microsecond=0)


def _durable_claim(
    events_dir: Path,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    event_id: str,
    occurred_at: datetime,
    ttl_s: int = 300,
    contention_window_s: int = 3,
) -> None:
    record = event_history.EventRecord(
        event_id=event_id,
        issue_id=resource,
        event_type="coordination.claim",
        occurred_at=_stamp(occurred_at),
        actor_id=owner,
        payload={
            "owner": owner,
            "claim_id": claim_id,
            "lease_expires_at": _stamp(occurred_at + timedelta(seconds=ttl_s)),
            "contention_window_s": contention_window_s,
            "ttl_s": ttl_s,
        },
    )
    event_history.write_events_batch(events_dir, [record])


def _claim_envelope(
    root: Path,
    project_dir: Path,
    config: ProjectConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    event_id: str,
    occurred_at: datetime,
    ttl_s: int = 300,
) -> CoordinationGossipEnvelope:
    return coordination_mqtt.make_claim_envelope(
        root,
        project_dir,
        config,
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        event_id=event_id,
        lease_ttl_s=ttl_s,
        occurred_at=occurred_at,
    )


def test_coordination_envelopes_have_type_specific_top_level_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gossip,
        "_resolve_project_label",
        lambda _root, _project, config: config.project_key,
    )
    root = tmp_path
    project_dir = root / "project"
    project_dir.mkdir()
    config = _configuration()
    timestamp = datetime(2026, 9, 16, 13, tzinfo=UTC)

    claim = _claim_envelope(
        root,
        project_dir,
        config,
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
        event_id="evt-claim",
        occurred_at=timestamp,
    )
    assert set(claim.model_dump(mode="json", exclude_none=True)) == {
        "id",
        "ts",
        "project",
        "type",
        "event_id",
        "producer_id",
        "resource",
        "owner",
        "claim_id",
        "lease_ttl_s",
    }

    lease = coordination_mqtt.make_lease_envelope(
        root,
        project_dir,
        config,
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
        event_id="evt-claim",
        lease_ttl_s=300,
        expires_at=timestamp + timedelta(seconds=300),
        occurred_at=timestamp + timedelta(seconds=3),
    )
    assert set(lease.model_dump(mode="json", exclude_none=True)) == {
        "id",
        "ts",
        "project",
        "type",
        "event_id",
        "producer_id",
        "resource",
        "owner",
        "claim_id",
        "lease_ttl_s",
        "expires_at",
    }

    release = coordination_mqtt.make_release_envelope(
        root,
        project_dir,
        config,
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
        event_id="evt-release",
        occurred_at=timestamp + timedelta(seconds=4),
    )
    assert set(release.model_dump(mode="json", exclude_none=True)) == {
        "id",
        "ts",
        "project",
        "type",
        "event_id",
        "producer_id",
        "resource",
        "owner",
        "claim_id",
    }

    with pytest.raises(
        ValidationError, match="coordination.claim requires lease_ttl_s"
    ):
        CoordinationGossipEnvelope.model_validate(
            {
                **claim.model_dump(mode="json", exclude_none=True),
                "lease_ttl_s": None,
            }
        )


def test_python_reads_and_writes_the_shared_plain_envelope_fixture(
    tmp_path: Path,
) -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "testdata"
        / "coordination_gossip_envelope.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    envelope = CoordinationGossipEnvelope.model_validate(fixture)
    evaluation_time = coordination.parse_timestamp(envelope.ts) + timedelta(seconds=2)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    coordination_mqtt.record_envelope(project_dir, envelope, ttl_s=1)

    expected_path = (
        project_dir
        / ".overlay"
        / "coordination"
        / coordination_mqtt._sha256_hex(envelope.resource or "")
        / f"{coordination_mqtt._sha256_hex(envelope.id)}.json"
    )
    assert expected_path.exists()
    assert envelope.resource not in expected_path.parts
    assert envelope.id not in expected_path.parts
    assert json.loads(expected_path.read_text(encoding="utf-8")) == fixture
    assert coordination_mqtt.load_envelopes(
        project_dir, ttl_s=1, now=evaluation_time
    ) == [envelope]
    assert (
        coordination_mqtt.overlay_events(
            project_dir,
            envelope.resource or "",
            contention_window_s=3,
            now=evaluation_time,
            ttl_s=1,
        )[0]["event_id"]
        == envelope.event_id
    )


def test_python_overlay_ignores_invalid_records_and_prunes_by_envelope_ts(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    resource = "job:overlay-expiry"
    directory = coordination_mqtt._resource_overlay_dir(project_dir, resource)
    directory.mkdir(parents=True)
    (directory / "invalid.json").write_text("not json", encoding="utf-8")
    (directory / "wrapped.json").write_text(
        json.dumps(
            {
                "overlay_expires_at": "2099-01-02T03:04:05Z",
                "envelope": {},
            }
        ),
        encoding="utf-8",
    )
    now = datetime(2026, 9, 16, 13, tzinfo=UTC)
    expired = CoordinationGossipEnvelope(
        id="expired-message",
        ts=_stamp(now - timedelta(seconds=10)),
        project="kanbus",
        type="coordination.release",
        event_id="release-event",
        producer_id="producer",
        resource=resource,
        owner="worker",
        claim_id="claim",
    )
    expired_path = directory / f"{coordination_mqtt._sha256_hex(expired.id)}.json"
    expired_path.write_text(
        expired.model_dump_json(exclude_none=True), encoding="utf-8"
    )

    assert (
        coordination_mqtt.overlay_events(
            project_dir,
            resource,
            contention_window_s=3,
            now=now,
            ttl_s=1,
        )
        == []
    )
    assert not expired_path.exists()
    assert (directory / "invalid.json").exists()


def test_provider_availability_does_not_start_a_local_broker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    monkeypatch.setattr(
        gossip,
        "resolve_broker_endpoint",
        lambda _broker: gossip.BrokerEndpoint(
            scheme="mqtt",
            host="127.0.0.1",
            port=1883,
            url="mqtt://127.0.0.1:1883",
        ),
    )
    monkeypatch.setattr(gossip, "broker_is_reachable", lambda _endpoint: False)
    monkeypatch.setattr(
        gossip,
        "ensure_mosquitto",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not autostart")),
    )
    monkeypatch.setattr(
        coordination_mqtt,
        "provider_available",
        lambda *_args: (_ for _ in ()).throw(AssertionError("Git must not probe MQTT")),
    )

    assert _coordination_provider(tmp_path, _configuration(providers=["git"])) == "git"
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: False)
    assert not coordination_mqtt.provider_available(tmp_path, config)
    assert not coordination_mqtt.provider_available(
        tmp_path, _configuration(providers=["git"])
    )


def test_custom_authorizer_provider_probe_uses_effective_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    config.realtime.mqtt_custom_authorizer_name = "kanbus-auth"
    config.realtime.mqtt_api_token = "api-token"
    endpoint = gossip.BrokerEndpoint(
        scheme="mqtts",
        host="iot.example.test",
        port=8883,
        url="mqtts://iot.example.test:8883",
    )
    monkeypatch.setitem(sys.modules, "paho", SimpleNamespace(mqtt=None))
    monkeypatch.setitem(sys.modules, "paho.mqtt", SimpleNamespace(client=None))
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", SimpleNamespace())
    monkeypatch.setattr(gossip, "resolve_broker_endpoint", lambda _broker: endpoint)
    probed: list[int] = []
    monkeypatch.setattr(
        gossip,
        "broker_is_reachable",
        lambda target: probed.append(target.port) or True,
    )

    assert coordination_mqtt.provider_available(tmp_path, config)
    assert probed == [443]


def test_mqtt_overlay_claims_choose_stable_winner_then_publish_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gossip,
        "_resolve_project_label",
        lambda _root, _project, config: config.project_key,
    )
    root = tmp_path
    project_dir = root / "project"
    project_dir.mkdir()
    events_dir = project_dir / "events"
    config = _configuration(providers=["mqtt", "git"])
    start = _current_test_time()
    _durable_claim(
        events_dir,
        resource="job:collision",
        owner="worker-z",
        claim_id="claim-z",
        event_id="evt-z",
        occurred_at=start,
    )
    remote_claim = _claim_envelope(
        root,
        project_dir,
        config,
        resource="job:collision",
        owner="worker-a",
        claim_id="claim-a",
        event_id="evt-a",
        occurred_at=start + timedelta(seconds=1),
        ttl_s=600,
    )
    coordination_mqtt.record_envelope(project_dir, remote_claim)

    early_state, early_lease = coordination_mqtt.select_lease_envelope(
        root,
        project_dir,
        events_dir,
        "job:collision",
        config,
        now=start + timedelta(seconds=2),
    )
    assert early_state.owner == "worker-a"
    assert early_lease is None

    state, lease = coordination_mqtt.select_lease_envelope(
        root,
        project_dir,
        events_dir,
        "job:collision",
        config,
        now=start + timedelta(seconds=4),
    )
    assert lease is not None
    assert (state.owner, state.claim_id, state.event_id) == (
        "worker-a",
        "claim-a",
        "evt-a",
    )
    assert lease.event_id == "evt-a"
    assert lease.expires_at == _stamp(start + timedelta(seconds=601))
    assert coordination.parse_timestamp(lease.expires_at) == start + timedelta(
        seconds=lease.lease_ttl_s or 0
    ) + timedelta(seconds=1)


def test_overlay_deduplicates_durable_event_ids_and_release_clears_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gossip,
        "_resolve_project_label",
        lambda _root, _project, config: config.project_key,
    )
    root = tmp_path
    project_dir = root / "project"
    project_dir.mkdir()
    events_dir = project_dir / "events"
    config = _configuration(providers=["mqtt", "git"])
    start = _current_test_time()
    _durable_claim(
        events_dir,
        resource="job:release",
        owner="durable-owner",
        claim_id="durable-claim",
        event_id="shared-event-id",
        occurred_at=start,
    )

    duplicate = _claim_envelope(
        root,
        project_dir,
        config,
        resource="job:release",
        owner="wrong-owner",
        claim_id="wrong-claim",
        event_id="shared-event-id",
        occurred_at=start + timedelta(seconds=1),
    )
    coordination_mqtt.record_envelope(project_dir, duplicate)
    before_release = coordination_mqtt.inspect_lease(
        events_dir,
        project_dir,
        "job:release",
        config,
        now=start + timedelta(seconds=2),
    )
    assert (before_release.owner, before_release.claim_id) == (
        "durable-owner",
        "durable-claim",
    )

    release = coordination_mqtt.make_release_envelope(
        root,
        project_dir,
        config,
        resource="job:release",
        owner="durable-owner",
        claim_id="durable-claim",
        event_id="evt-release",
        occurred_at=start + timedelta(seconds=2),
    )
    coordination_mqtt.record_envelope(project_dir, release)
    after_release = coordination_mqtt.inspect_lease(
        events_dir,
        project_dir,
        "job:release",
        config,
        now=start + timedelta(seconds=3),
    )
    assert not after_release.active
    assert not [
        event
        for path in events_dir.glob("*.json")
        if (event := json.loads(path.read_text(encoding="utf-8")))["event_type"]
        == "coordination.release"
    ]


def test_lease_overlay_extends_expiry_and_dedupe_uses_producer_and_id() -> None:
    timestamp = _current_test_time()
    envelope = CoordinationGossipEnvelope(
        id="env-1",
        ts=_stamp(timestamp),
        project="kanbus",
        type="coordination.release",
        event_id="release-1",
        producer_id="producer-1",
        resource="job:1",
        owner="worker-a",
        claim_id="claim-a",
    )
    dedupe = DedupeSet(ttl_s=coordination_mqtt.DEDUPE_TTL_S)
    assert coordination_mqtt.DEDUPE_TTL_S == 3600
    assert coordination_mqtt.should_ignore_envelope(envelope, dedupe, "producer-1")
    remote = envelope.model_copy(update={"id": "env-2", "producer_id": "other"})
    assert not coordination_mqtt.should_ignore_envelope(remote, dedupe, "producer-1")
    assert coordination_mqtt.should_ignore_envelope(remote, dedupe, "producer-1")


def test_publish_uses_configured_project_topic_and_records_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gossip,
        "_resolve_project_label",
        lambda _root, _project, config: config.project_key,
    )
    root = tmp_path
    project_dir = root / "project"
    project_dir.mkdir()
    config = _configuration(providers=["mqtt", "git"])
    config.realtime.mqtt_custom_authorizer_name = "kanbus-auth"
    config.realtime.mqtt_api_token = "api-token"
    envelope = _claim_envelope(
        root,
        project_dir,
        config,
        resource="job:publish",
        owner="worker-a",
        claim_id="claim-a",
        event_id="evt-publish",
        occurred_at=_current_test_time(),
    )
    calls: list[tuple[str, str, str, object]] = []
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    monkeypatch.setattr(
        gossip,
        "resolve_broker_endpoint",
        lambda _broker: gossip.BrokerEndpoint(
            scheme="mqtt",
            host="broker.example",
            port=1883,
            url="mqtt://broker.example:1883",
        ),
    )
    monkeypatch.setattr(
        gossip,
        "_publish_mqtt",
        lambda _endpoint, topic, message, realtime: calls.append(
            (
                topic,
                message.type,
                str(message.model_dump(mode="json", exclude_none=True)["event_id"]),
                realtime,
            )
        ),
    )

    assert coordination_mqtt.publish_envelope(root, project_dir, config, envelope)
    assert calls == [
        (
            "projects/kanbus/events",
            "coordination.claim",
            "evt-publish",
            config.realtime,
        )
    ]
    assert coordination_mqtt.load_envelopes(project_dir) == [envelope]


def test_cli_selects_mqtt_and_inspect_reconciles_after_window_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    project_dir.mkdir()
    data = copy.deepcopy(DEFAULT_CONFIGURATION)
    data["coordination"] = {
        "providers": ["mqtt", "git"],
        "contention_window": "1s",
        "default_lease_ttl": "300s",
    }
    data["realtime"].update(
        {
            "transport": "mqtt",
            "broker": "mqtt://broker.example:1883",
            "autostart": False,
        }
    )
    (root / ".kanbus.yml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setattr(
        gossip,
        "_resolve_project_label",
        lambda _root, _project, config: config.project_key,
    )
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    published: list[CoordinationGossipEnvelope] = []

    def fake_publish(root_path, target_project, config, envelope):
        published.append(envelope)
        coordination_mqtt.record_envelope(
            target_project, envelope, ttl_s=config.overlay.ttl_s
        )
        return True

    monkeypatch.setattr(coordination_mqtt, "publish_envelope", fake_publish)
    monkeypatch.chdir(root)
    runner = CliRunner()
    claimed = runner.invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:cli",
            "--owner",
            "worker-a",
            "--claim-id",
            "claim-a",
        ],
    )
    assert claimed.exit_code == 0, claimed.output
    assert "provider: mqtt" in claimed.output
    assert [envelope.type for envelope in published] == ["coordination.claim"]

    claim_event = next(
        json.loads(path.read_text(encoding="utf-8"))
        for path in (project_dir / "events").glob("*.json")
        if json.loads(path.read_text(encoding="utf-8"))["event_type"]
        == "coordination.claim"
    )
    claim_time = coordination.parse_timestamp(claim_event["occurred_at"])
    monkeypatch.setattr(
        coordination,
        "utc_now",
        lambda: claim_time + timedelta(seconds=2),
    )
    inspected = runner.invoke(
        cli,
        ["coordination", "inspect", "--resource", "job:cli"],
    )
    assert inspected.exit_code == 0, inspected.output
    assert "provider: mqtt" in inspected.output
    assert [envelope.type for envelope in published] == [
        "coordination.claim",
        "coordination.lease",
    ]
    lease = published[-1]
    assert lease.event_id == published[0].event_id
    assert coordination.parse_timestamp(
        lease.expires_at or ""
    ) == claim_time + timedelta(seconds=lease.lease_ttl_s or 0)

    inspected_again = runner.invoke(
        cli,
        ["coordination", "inspect", "--resource", "job:cli"],
    )
    assert inspected_again.exit_code == 0
    assert len(published) == 2


def test_cli_renew_before_window_close_does_not_publish_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    project_dir.mkdir()
    data = copy.deepcopy(DEFAULT_CONFIGURATION)
    data["coordination"] = {
        "providers": ["mqtt", "git"],
        "contention_window": "3s",
        "default_lease_ttl": "300s",
    }
    data["realtime"].update(
        {
            "transport": "mqtt",
            "broker": "mqtt://broker.example:1883",
            "autostart": False,
        }
    )
    (root / ".kanbus.yml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    monkeypatch.setattr(
        gossip,
        "_resolve_project_label",
        lambda _root, _project, config: config.project_key,
    )
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    published: list[CoordinationGossipEnvelope] = []

    def fake_publish(root_path, target_project, config, envelope):
        published.append(envelope)
        coordination_mqtt.record_envelope(
            target_project, envelope, ttl_s=config.overlay.ttl_s
        )
        return True

    monkeypatch.setattr(coordination_mqtt, "publish_envelope", fake_publish)
    start = datetime(2026, 9, 16, 13, tzinfo=UTC)
    monkeypatch.setattr("kanbus.cli.utc_now", lambda: start)
    monkeypatch.chdir(root)
    runner = CliRunner()
    claimed = runner.invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:renew-before-close",
            "--owner",
            "worker-a",
            "--claim-id",
            "claim-a",
        ],
    )
    assert claimed.exit_code == 0, claimed.output
    assert [envelope.type for envelope in published] == ["coordination.claim"]

    monkeypatch.setattr("kanbus.cli.utc_now", lambda: start + timedelta(seconds=2))
    renewed = runner.invoke(
        cli,
        [
            "coordination",
            "renew",
            "--resource",
            "job:renew-before-close",
            "--owner",
            "worker-a",
            "--claim-id",
            "claim-a",
        ],
    )
    assert renewed.exit_code == 0, renewed.output
    assert "provider: mqtt" in renewed.output
    assert [envelope.type for envelope in published] == ["coordination.claim"]
    durable_types = {
        json.loads(path.read_text(encoding="utf-8"))["event_type"]
        for path in (project_dir / "events").glob("*.json")
    }
    assert "coordination.renew" in durable_types
