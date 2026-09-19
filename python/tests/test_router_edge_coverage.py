"""Focused regression tests for remaining router and coordination edge paths."""

from __future__ import annotations

import builtins
import copy
import json
import subprocess
import sys
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from kanbus import coordination, coordination_mqtt, coordination_mutex_api
from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.coordination import CoordinationError
from kanbus.coordination_mutex_api import MutexApiError, MutexApiUnavailable
from kanbus.event_history import create_event, write_events_batch
from kanbus.gossip import CoordinationGossipEnvelope
from kanbus.issue_router import IssueRouterError
from kanbus.models import (
    CoordinationConfiguration,
    IssueRouterConfiguration,
    ProjectConfiguration,
    RouterForgeConfiguration,
)
from kanbus.router_adapters import (
    CodexExecAdapter,
    _find_result_payload,
    _process_identity,
)
from kanbus.router_forge import (
    FakeForge,
    GitHubForge,
    _apply_forge_transition,
    record_github_check_run_event,
    record_github_pull_request_event,
)
from kanbus import router_adapters, router_forge, router_state


def _configuration(*, providers: list[str] | None = None) -> ProjectConfiguration:
    values = copy.deepcopy(DEFAULT_CONFIGURATION)
    if providers is not None:
        values["coordination"]["providers"] = providers
    values["realtime"].update(
        transport="mqtt",
        broker="mqtt://broker.example:1883",
        autostart=False,
        mqtt_custom_authorizer_name=None,
        mqtt_api_token=None,
    )
    return ProjectConfiguration.model_validate(values)


def _install_fake_paho(monkeypatch, client_class) -> None:
    paho_module = ModuleType("paho")
    mqtt_module = ModuleType("paho.mqtt")
    client_module = ModuleType("paho.mqtt.client")
    client_module.Client = client_class
    client_module.MQTT_ERR_SUCCESS = 0
    paho_module.mqtt = mqtt_module
    mqtt_module.client = client_module
    monkeypatch.setitem(sys.modules, "paho", paho_module)
    monkeypatch.setitem(sys.modules, "paho.mqtt", mqtt_module)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", client_module)


def _router_configuration() -> IssueRouterConfiguration:
    return IssueRouterConfiguration(
        enabled=False,
        forge=RouterForgeConfiguration(repository="owner/repo"),
    )


def _pr_event(action: str = "synchronize", **overrides):
    return {
        "schema_version": 1,
        "event_id": "forge-event-1",
        "kind": "pull_request",
        "action": action,
        "repository": "owner/repo",
        "number": 7,
        "head_sha": "head-7",
        "merged": False,
        **overrides,
    }


def _owned_pull_request(*, head_sha: str = "head-7") -> dict[str, object]:
    return {
        "event_type": "router_pull_request_opened",
        "issue_id": "router:kbs-7",
        "event_id": "opened-1",
        "payload": {"number": 7, "head_sha": head_sha},
    }


def test_coordination_ignores_invalid_speculation_and_reports_missing_sequences(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 9, 17, tzinfo=UTC)
    extras = [
        None,
        {"issue_id": "another-resource", "event_type": "coordination.claim"},
        {
            "event_id": "invalid-sequence",
            "issue_id": "job:edge",
            "event_type": "coordination.claim",
            "occurred_at": coordination.format_timestamp(start),
            "payload": {
                "operation_sequence": True,
                "owner": "worker",
                "claim_id": "claim",
            },
        },
        {
            "event_id": "invalid-date",
            "issue_id": "job:edge",
            "event_type": "coordination.claim",
            "occurred_at": "not-a-time",
            "payload": {"owner": "worker", "claim_id": "claim"},
        },
    ]
    state = coordination.inspect_lease(
        tmp_path / "missing-events", "job:edge", now=start, additional_events=extras
    )
    assert not state.active
    assert (
        coordination.operation_sequence_for_event(
            tmp_path / "missing-events", "job:edge", "not-present"
        )
        is None
    )

    with pytest.raises(CoordinationError, match="revision must be a positive integer"):
        coordination.claim(
            tmp_path / "events",
            CoordinationConfiguration(),
            resource="job:edge",
            owner="worker",
            claim_id="claim",
            revision=True,
            now=start,
        )

    for resource, owner, claim_id, message in (
        (" ", "worker", "claim", "resource must not be empty"),
        ("job:edge", " ", "claim", "owner must not be empty"),
        ("job:edge", "worker", " ", "claim id must not be empty"),
    ):
        with pytest.raises(CoordinationError, match=message):
            coordination.claim(
                tmp_path / "events",
                CoordinationConfiguration(),
                resource=resource,
                owner=owner,
                claim_id=claim_id,
                now=start,
            )


def test_coordination_reducer_ignores_non_winner_renewal_and_release(
    tmp_path: Path,
) -> None:
    events = tmp_path / "events"
    start = datetime(2026, 9, 17, tzinfo=UTC)
    configuration = CoordinationConfiguration(default_lease_ttl="1h")
    coordination.claim(
        events,
        configuration,
        resource="job:reduce",
        owner="winner",
        claim_id="claim-winner",
        now=start,
    )
    timestamp = coordination.format_timestamp(start + timedelta(seconds=2))
    forged_operations = [
        create_event(
            issue_id="job:reduce",
            event_type="coordination.renew",
            actor_id="other",
            payload={
                "owner": "other",
                "claim_id": "claim-other",
                "lease_expires_at": coordination.format_timestamp(
                    start + timedelta(hours=2)
                ),
                "operation_sequence": 2,
            },
            occurred_at=timestamp,
        ),
        create_event(
            issue_id="job:reduce",
            event_type="coordination.release",
            actor_id="other",
            payload={
                "owner": "other",
                "claim_id": "claim-other",
                "operation_sequence": 3,
            },
            occurred_at=timestamp,
        ),
    ]
    write_events_batch(events, forged_operations)

    state = coordination.inspect_lease(
        events, "job:reduce", now=start + timedelta(seconds=3)
    )
    assert state.active
    assert (state.owner, state.claim_id) == ("winner", "claim-winner")

    expired_renewal = create_event(
        issue_id="job:reduce",
        event_type="coordination.renew",
        actor_id="winner",
        payload={
            "owner": "winner",
            "claim_id": "claim-winner",
            "lease_expires_at": coordination.format_timestamp(
                start + timedelta(hours=4)
            ),
            "operation_sequence": 4,
        },
        occurred_at=coordination.format_timestamp(start + timedelta(hours=2)),
    )
    write_events_batch(events, [expired_renewal])
    expired_state = coordination.inspect_lease(
        events, "job:reduce", now=start + timedelta(hours=3)
    )
    assert not expired_state.active


def test_published_result_validation_idempotency_and_write_failure(
    monkeypatch, tmp_path: Path
) -> None:
    events = tmp_path / "events"
    assert coordination.inspect_published_result(events, "job:result") is None
    events.mkdir()
    (events / "malformed.json").write_text("[]", encoding="utf-8")
    assert coordination.inspect_published_result(events, "job:result") is None

    start = datetime(2026, 9, 17, tzinfo=UTC)
    published = coordination.publish_result(
        events,
        resource="job:result",
        revision=2,
        artifact="artifact://v2",
        actor_id="worker",
        occurred_at=start,
    )
    assert (
        coordination.publish_result(
            events,
            resource="job:result",
            revision=2,
            artifact="artifact://v2",
            actor_id="worker",
            occurred_at=start + timedelta(seconds=1),
        )
        == published
    )
    with pytest.raises(CoordinationError, match="stale revision"):
        coordination.publish_result(
            events,
            resource="job:result",
            revision=2,
            artifact="artifact://different",
            actor_id="worker",
            occurred_at=start,
        )
    with pytest.raises(CoordinationError, match="positive integer"):
        coordination.publish_result(
            events,
            resource="job:result",
            revision=True,
            artifact="artifact://v3",
            actor_id="worker",
        )
    with pytest.raises(CoordinationError, match="artifact must not be empty"):
        coordination.publish_result(
            events,
            resource="job:result",
            revision=3,
            artifact="   ",
            actor_id="worker",
        )

    monkeypatch.setattr(
        coordination,
        "write_events_batch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(CoordinationError, match="disk full"):
        coordination.publish_result(
            events,
            resource="job:result",
            revision=3,
            artifact="artifact://v3",
            actor_id="worker",
        )


def test_mutex_api_http_errors_and_non_string_lease_fields(monkeypatch) -> None:
    config = coordination_mutex_api.MutexApiConfiguration()
    with pytest.raises(MutexApiUnavailable, match="not configured"):
        coordination_mutex_api.inspect(config, resource="job:1")

    config = coordination_mutex_api.MutexApiConfiguration(
        endpoint="https://mutex.example.test", bearer_token="token"
    )

    def not_found(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://mutex.example.test", 404, "missing", None, None
        )

    monkeypatch.setattr(coordination_mutex_api, "_urlopen", not_found)
    assert coordination_mutex_api.inspect(config, resource="job:404") is None

    malformed = {
        "resource": "job:1",
        "owner": 7,
        "claim_id": "claim",
        "revision": 1,
        "claimed_at": 100,
        "expires_at": 200,
    }
    monkeypatch.setattr(
        coordination_mutex_api,
        "_urlopen",
        lambda *_args, **_kwargs: _JsonResponse(200, json.dumps(malformed).encode()),
    )
    with pytest.raises(MutexApiError, match="invalid lease response"):
        coordination_mutex_api.inspect(config, resource="job:1")


class _JsonResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_process_identity_and_jsonl_result_selection(
    monkeypatch, tmp_path: Path
) -> None:
    original_is_file = Path.is_file
    monkeypatch.setattr(router_adapters.os, "name", "posix")
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=b"started command"),
    )
    assert _process_identity(42).startswith("ps:")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, "ps")
        ),
    )
    assert _process_identity(42) is None

    payload = {"schema_version": 1, "outcome": "completed"}
    assert _find_result_payload("[]\n{}\n" + json.dumps({"result": payload})) == payload
    assert _find_result_payload("progress\n" + json.dumps(payload)) == payload

    record = tmp_path / "process.json"
    record.write_text(json.dumps({"claim_id": "another"}), encoding="utf-8")
    adapter = CodexExecAdapter.__new__(CodexExecAdapter)
    adapter.process_record_path = record
    monkeypatch.setattr(Path, "is_file", original_is_file)
    adapter._remove_process_record("claim-1")
    assert record.exists()
    record.write_text("not-json", encoding="utf-8")
    adapter._remove_process_record("claim-1")
    assert record.exists()


def test_linux_process_identity_uses_proc_start_time(monkeypatch) -> None:
    monkeypatch.setattr(router_adapters.os, "name", "posix")
    original_is_file = Path.is_file

    def is_file(path: Path) -> bool:
        if str(path) == "/proc/42/stat":
            return True
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", is_file)

    def read_text(path: Path, *, encoding=None):
        if str(path) == "/proc/42/stat":
            return "42 (worker name) " + " ".join(str(index) for index in range(25))
        if str(path) == "/proc/sys/kernel/random/boot_id":
            return "boot-uuid\n"
        raise AssertionError(path)

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(Path, "read_bytes", lambda _path: b"codex\0exec")
    monkeypatch.setattr(router_adapters.os, "readlink", lambda _path: "/bin/codex")
    identity = _process_identity(42)
    assert identity is not None
    assert identity.startswith("linux:boot-uuid:19:/bin/codex:")


def test_process_identity_and_result_parser_reject_unusable_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    original_is_file = Path.is_file
    monkeypatch.setattr(router_adapters.os, "name", "nt")
    assert _process_identity(42) is None

    monkeypatch.setattr(router_adapters.os, "name", "posix")
    monkeypatch.setattr(Path, "is_file", lambda path: str(path) == "/proc/42/stat")
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: "42 (worker) 1 2")
    assert _process_identity(42) is None

    def fail_boot_id(path: Path, *, encoding=None):
        if str(path) == "/proc/42/stat":
            return "42 (worker) " + " ".join(str(index) for index in range(25))
        raise OSError("proc unavailable")

    monkeypatch.setattr(Path, "read_text", fail_boot_id)
    assert _process_identity(42) is None

    monkeypatch.setattr(Path, "is_file", lambda _path: False)
    monkeypatch.setattr(
        subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout=b"")
    )
    assert _process_identity(42) is None
    with pytest.raises(IssueRouterError, match="invalid JSON"):
        _find_result_payload('{"message":"progress only"}')

    record = tmp_path / "unreadable-process-record.json"
    record.write_text("{}", encoding="utf-8")
    adapter = CodexExecAdapter.__new__(CodexExecAdapter)
    adapter.process_record_path = record
    monkeypatch.setattr(Path, "is_file", original_is_file)
    original_read_text = Path.read_text

    def inaccessible(path: Path, *args, **kwargs):
        if path == record:
            raise OSError("record temporarily inaccessible")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", inaccessible)
    adapter._remove_process_record("claim-1")
    assert record.exists()


def test_github_forge_configuration_observation_and_pagination(monkeypatch) -> None:
    with pytest.raises(IssueRouterError, match="not configured"):
        GitHubForge.from_configuration(IssueRouterConfiguration(enabled=False))
    config = _router_configuration()
    with pytest.raises(IssueRouterError, match="GITHUB_TOKEN is not set"):
        GitHubForge.from_configuration(config)
    monkeypatch.setenv("GITHUB_TOKEN", "  test-token  ")
    assert GitHubForge.from_configuration(config).token == "test-token"

    forge = GitHubForge(repository="owner/repo", token="test-token")
    monkeypatch.setattr(
        forge,
        "_request",
        lambda *_args, **_kwargs: {
            "number": 7,
            "html_url": "https://github.example/pull/7",
            "head": {"ref": "branch", "sha": "head"},
            "state": "open",
        },
    )
    assert forge.observe_pull_request(7)["number"] == 7
    monkeypatch.setattr(forge, "_request", lambda *_args, **_kwargs: [])
    with pytest.raises(IssueRouterError, match="invalid pull request"):
        forge.observe_pull_request(7)

    runs = [{"id": index} for index in range(100)]
    requests_seen = []

    def request(method, path, **kwargs):
        requests_seen.append((method, path, kwargs))
        if path.endswith("check-runs"):
            return {"check_runs": runs if kwargs["params"]["page"] == "1" else []}
        return (
            [{"id": index} for index in range(100)]
            if kwargs["params"]["page"] == "1"
            else []
        )

    monkeypatch.setattr(forge, "_request", request)
    assert forge.list_check_runs(7, "sha/with/slash") == runs
    assert len(requests_seen) == 2
    assert "/commits/sha%2Fwith%2Fslash/check-runs" in requests_seen[0][1]
    assert len(forge.list_pull_request_reviews(7)) == 100
    assert requests_seen[-1][2]["params"]["page"] == "2"

    monkeypatch.setattr(
        forge, "_request", lambda *_args, **_kwargs: {"check_runs": [1]}
    )
    with pytest.raises(IssueRouterError, match="invalid check runs"):
        forge.list_check_runs(7, "sha")
    monkeypatch.setattr(forge, "_request", lambda *_args, **_kwargs: [1])
    with pytest.raises(IssueRouterError, match="invalid pull request reviews"):
        forge.list_pull_request_reviews(7)

    fake = FakeForge()
    created = fake.create_or_observe_pull_request(
        title="router work",
        body="bounded summary",
        head_branch="codex/router/kbs-7/r1",
        base_branch="main",
    )
    reused = fake.create_or_observe_pull_request(
        title="ignored duplicate",
        body="ignored duplicate",
        head_branch="codex/router/kbs-7/r1",
        base_branch="main",
    )
    assert reused.number == created.number
    assert fake.observe_pull_request(created.number)["title"] == "router work"
    with pytest.raises(IssueRouterError, match="unknown fake pull request"):
        fake.observe_pull_request(999)
    fake.check_runs[(created.number, "fixture-head")] = [{"name": "unit"}]
    fake.pull_request_reviews[created.number] = [{"state": "APPROVED"}]
    returned_runs = fake.list_check_runs(created.number, "fixture-head")
    returned_runs[0]["name"] = "caller-mutation"
    returned_reviews = fake.list_pull_request_reviews(created.number)
    returned_reviews[0]["state"] = "CHANGED"
    assert fake.check_runs[(created.number, "fixture-head")][0]["name"] == "unit"
    assert fake.pull_request_reviews[created.number][0]["state"] == "APPROVED"


def test_github_forge_events_validate_ownership_and_deduplicate(monkeypatch, tmp_path):
    config = _router_configuration()
    with pytest.raises(IssueRouterError, match="invalid GitHub pull request event"):
        record_github_pull_request_event(tmp_path, config, {"event_id": "bad"})
    with pytest.raises(IssueRouterError, match="invalid GitHub pull request event"):
        record_github_pull_request_event(
            tmp_path, config, _pr_event(kind="issue_comment")
        )
    with pytest.raises(IssueRouterError, match="not configured"):
        record_github_pull_request_event(
            tmp_path,
            IssueRouterConfiguration(enabled=False),
            _pr_event(),
        )
    with pytest.raises(IssueRouterError, match="does not match configured repository"):
        record_github_pull_request_event(
            tmp_path, config, _pr_event(repository="fork/repo")
        )

    monkeypatch.setattr(router_forge, "_all_router_events", lambda _project: [])
    with pytest.raises(IssueRouterError, match="not owned by the Issue Router"):
        record_github_pull_request_event(tmp_path, config, _pr_event())

    ownership = _owned_pull_request()
    monkeypatch.setattr(
        router_forge, "_all_router_events", lambda _project: [ownership]
    )
    with pytest.raises(IssueRouterError, match="not owned by the Issue Router"):
        record_github_pull_request_event(
            tmp_path, config, _pr_event(action="approved", head_sha="old-head")
        )

    recorded = []
    transitions = []
    monkeypatch.setattr(
        router_forge,
        "record_router_event",
        lambda *args, **kwargs: recorded.append((args, kwargs)),
    )
    monkeypatch.setattr(
        router_forge,
        "_apply_forge_transition",
        lambda *args, **kwargs: transitions.append((args, kwargs)),
    )
    assert record_github_pull_request_event(
        tmp_path, config, _pr_event(action="requested_changes")
    )
    assert recorded[0][1]["event_type"] == "router_forge_event"
    assert recorded[0][1]["payload"]["action"] == "requested_changes"

    duplicate = {
        **ownership,
        "payload": {**ownership["payload"], "forge_event_id": "dupe"},
    }
    monkeypatch.setattr(
        router_forge, "_all_router_events", lambda _project: [duplicate]
    )
    assert not record_github_pull_request_event(
        tmp_path, config, _pr_event(event_id="dupe")
    )
    assert len(transitions) == 2

    monkeypatch.setattr(
        router_forge, "_all_router_events", lambda _project: [ownership]
    )
    recorded.clear()
    assert record_github_pull_request_event(
        tmp_path, config, _pr_event(action="closed", merged=True, event_id="merge")
    )
    assert [item[1]["event_type"] for item in recorded] == [
        "router_pull_request_closed",
        "router_forge_event",
    ]


def test_github_check_run_events_and_missing_project_configuration(
    monkeypatch, tmp_path: Path
) -> None:
    config = _router_configuration()
    with pytest.raises(IssueRouterError, match="invalid GitHub check-run event"):
        record_github_check_run_event(tmp_path, config, {})
    check = {
        "schema_version": 1,
        "event_id": "check-1",
        "kind": "check_run",
        "action": "completed",
        "repository": "owner/repo",
        "number": 7,
        "head_sha": "head-7",
        "conclusion": "failure",
    }
    with pytest.raises(IssueRouterError, match="invalid GitHub check-run event"):
        record_github_check_run_event(tmp_path, config, {**check, "action": "created"})
    ownership = _owned_pull_request()
    monkeypatch.setattr(
        router_forge, "_all_router_events", lambda _project: [ownership]
    )
    recorded, transitioned = [], []
    monkeypatch.setattr(
        router_forge,
        "record_router_event",
        lambda *args, **kwargs: recorded.append(kwargs),
    )
    monkeypatch.setattr(
        router_forge,
        "_apply_forge_transition",
        lambda *args, **kwargs: transitioned.append(args),
    )
    assert record_github_check_run_event(tmp_path, config, check)
    assert recorded[0]["payload"]["action"] == "check_run_failure"
    assert transitioned[0][2] == "requested_changes"

    monkeypatch.setattr(
        router_forge,
        "_all_router_events",
        lambda _project: [ownership, {"payload": {"forge_event_id": "check-1"}}],
    )
    assert not record_github_check_run_event(tmp_path, config, check)
    assert len(recorded) == 1

    with pytest.raises(IssueRouterError, match="check-run repository"):
        record_github_check_run_event(
            tmp_path, config, {**check, "repository": "fork/repo"}
        )
    with pytest.raises(IssueRouterError, match="invalid GitHub check-run conclusion"):
        record_github_check_run_event(
            tmp_path, config, {**check, "conclusion": "neutral"}
        )
    with pytest.raises(IssueRouterError, match="not owned by the Issue Router"):
        record_github_check_run_event(
            tmp_path, config, {**check, "head_sha": "stale-head"}
        )

    with pytest.raises(IssueRouterError, match="configuration could not be located"):
        _apply_forge_transition(
            tmp_path / "project",
            "kbs-7",
            "approved",
            SimpleNamespace(head_sha="head-7", merged=False),
        )


def test_forge_helpers_return_valid_data_and_fail_closed_on_bad_project_state(
    monkeypatch, tmp_path: Path
) -> None:
    assert (
        router_forge._pull_request_from_github(
            {
                "number": 7,
                "html_url": "https://github.example/pull/7",
                "head": {"ref": "branch", "sha": "head"},
                "state": "open",
            }
        ).number
        == 7
    )
    with pytest.raises(IssueRouterError, match="invalid pull request"):
        router_forge._pull_request_from_github({"number": 7, "head": []})

    empty = tmp_path / "empty-project"
    empty.mkdir()
    assert router_forge._all_router_events(empty) == []
    events = empty / "events"
    events.mkdir()
    (events / "bad.json").write_text("not-json", encoding="utf-8")
    (events / "non-router.json").write_text(
        json.dumps({"issue_id": "kbs-7", "event_id": "ignored"}),
        encoding="utf-8",
    )
    assert router_forge._all_router_events(empty) == []

    root = tmp_path / "configured"
    root.mkdir()
    (root / ".kanbus.yml").write_text("configuration: {}\n", encoding="utf-8")
    project_dir = root / "project"
    project_dir.mkdir()
    workflow = SimpleNamespace(
        review="review", active="active", blocked="blocked", terminal=["closed"]
    )
    issue = SimpleNamespace(identifier="kbs-7", status="active")
    monkeypatch.setattr(
        router_forge,
        "load_router_context",
        lambda _root: SimpleNamespace(
            router=SimpleNamespace(workflow=workflow), issues=[]
        ),
    )
    with pytest.raises(IssueRouterError, match="unknown router package"):
        _apply_forge_transition(
            project_dir,
            "kbs-unknown",
            "approved",
            SimpleNamespace(head_sha="head", merged=False),
        )

    monkeypatch.setattr(
        router_forge,
        "load_router_context",
        lambda _root: SimpleNamespace(
            router=SimpleNamespace(workflow=workflow), issues=[issue]
        ),
    )
    monkeypatch.setattr(
        router_forge,
        "update_issue",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            router_forge.IssueUpdateError("transition rejected")
        ),
    )
    with pytest.raises(IssueRouterError, match="transition rejected"):
        _apply_forge_transition(
            project_dir,
            "kbs-7",
            "approved",
            SimpleNamespace(head_sha="head", merged=False),
        )


def test_mqtt_listener_tls_callbacks_and_bounded_failures(
    monkeypatch, tmp_path: Path
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    config.realtime.broker = "mqtts://broker.example:8883"
    config.realtime.mqtt_custom_authorizer_name = "kanbus-auth"
    config.realtime.mqtt_api_token = "temporary-token"
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    monkeypatch.setattr(
        coordination_mqtt.gossip, "_resolve_project_label", lambda *_args: None
    )
    tls_calls, clients = [], []

    class TlsContext:
        def set_alpn_protocols(self, protocols):
            tls_calls.append(("alpn", protocols))

    monkeypatch.setattr(coordination_mqtt.ssl, "create_default_context", TlsContext)

    class FakeClient:
        def __init__(self, **kwargs):
            self.client_id = kwargs["client_id"]
            self.subscriptions = []
            self.credentials = None
            clients.append(self)

        def tls_set_context(self, context):
            tls_calls.append(("context", context))

        def tls_set(self):
            tls_calls.append(("default-tls", None))

        def username_pw_set(self, username, password):
            self.credentials = (username, password)

        def connect(self, *_args):
            return None

        def loop_start(self):
            self.on_connect(self, None, None, 0)

        def subscribe(self, topic, qos):
            self.subscriptions.append((topic, qos))
            return 1, 1

        def disconnect(self):
            return None

        def loop_stop(self):
            return None

    _install_fake_paho(monkeypatch, FakeClient)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    listener = coordination_mqtt.start_listener(tmp_path, project_dir, config)
    assert listener is not None and listener.connected.is_set()
    client = clients[0]
    assert client.credentials == (
        "?x-amz-customauthorizer-name=kanbus-auth",
        "temporary-token",
    )
    assert tls_calls[0] == ("alpn", ["mqtt"])
    assert client.subscriptions[0][1] == 0
    assert (
        coordination_mqtt.transport_diagnostics()["listener"]["status"]
        == "subscribe_request_rejected"
    )

    class NotIterable:
        def __bool__(self):
            return True

    client.on_subscribe(client, None, 2, NotIterable())
    assert not listener.subscribed.is_set()
    assert coordination_mqtt._subscription_succeeded(None) is False
    assert coordination_mqtt._subscription_succeeded(NotIterable()) is False
    assert (
        coordination_mqtt._subscription_succeeded([SimpleNamespace(is_failure=True)])
        is False
    )
    assert coordination_mqtt._subscription_succeeded(
        [SimpleNamespace(is_failure=False)]
    )
    listener.stop()

    config.realtime.mqtt_custom_authorizer_name = None
    config.realtime.mqtt_api_token = None
    tls_listener = coordination_mqtt.start_listener(tmp_path, project_dir, config)
    assert tls_listener is not None
    assert ("default-tls", None) in tls_calls
    tls_listener.stop()

    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: False)
    assert coordination_mqtt.start_listener(tmp_path, project_dir, config) is None


def test_mqtt_import_connect_publish_and_overlay_edge_paths(
    monkeypatch, tmp_path: Path
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    monkeypatch.setattr(
        coordination_mqtt.gossip, "_resolve_project_label", lambda *_args: None
    )
    original_import = builtins.__import__

    def no_paho(name, *args, **kwargs):
        if name == "paho.mqtt.client":
            raise ImportError("test paho unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_paho)
    assert coordination_mqtt.start_listener(tmp_path, project_dir, config) is None
    monkeypatch.setattr(builtins, "__import__", original_import)

    class FailingClient:
        def __init__(self, **_kwargs):
            pass

        def connect(self, *_args):
            raise OSError("private broker address")

    _install_fake_paho(monkeypatch, FailingClient)
    assert coordination_mqtt.start_listener(tmp_path, project_dir, config) is None
    assert (
        coordination_mqtt.transport_diagnostics()["listener"]["status"]
        == "connect_failed"
    )

    event_time = datetime(2026, 9, 17, tzinfo=UTC)
    envelope = CoordinationGossipEnvelope(
        id="overlay-envelope",
        ts=coordination.format_timestamp(event_time),
        project="kanbus",
        type="coordination.claim",
        event_id="claim-event",
        producer_id="peer",
        resource="job:mqtt",
        owner="worker",
        claim_id="claim",
        lease_ttl_s=60,
        operation_sequence=3,
    )
    # Keep write-time pruning aligned with this fixture's clock. The envelope
    # deliberately has a short TTL so the expiry path remains covered.
    monkeypatch.setattr(coordination, "utc_now", lambda: event_time)
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: False)
    assert not coordination_mqtt.publish_envelope(
        tmp_path, project_dir, config, envelope
    )
    assert (
        coordination_mqtt.transport_diagnostics()["publisher"]["status"]
        == "provider_unavailable"
    )
    assert (
        coordination_mqtt.overlay_events(
            project_dir, "job:missing", contention_window_s=5, now=event_time
        )
        == []
    )

    coordination_mqtt.record_envelope(project_dir, envelope)
    events = coordination_mqtt.overlay_events(
        project_dir,
        "job:mqtt",
        contention_window_s=5,
        now=event_time + timedelta(seconds=1),
    )
    assert events[0]["payload"]["operation_sequence"] == 3
    assert events[0]["payload"]["contention_window_s"] == 5

    raw = coordination_mqtt._resource_overlay_dir(project_dir, "job:mqtt")
    (raw / "malformed.json").write_text("not-json", encoding="utf-8")
    future = envelope.model_copy(
        update={
            "id": "future-envelope",
            "ts": coordination.format_timestamp(event_time + timedelta(minutes=1)),
        }
    )
    coordination_mqtt.record_envelope(project_dir, future)
    (raw / "not-the-envelope-hash.json").write_text(
        envelope.model_dump_json(), encoding="utf-8"
    )
    visible = coordination_mqtt.overlay_events(
        project_dir,
        "job:mqtt",
        contention_window_s=5,
        now=event_time + timedelta(seconds=1),
    )
    assert [event["event_id"] for event in visible] == ["claim-event"]
    assert (
        coordination_mqtt.overlay_events(
            project_dir,
            "job:absent-after-create",
            contention_window_s=5,
            now=event_time,
        )
        == []
    )
    duplicate_id = envelope.model_copy(update={"resource": "job:other-resource"})
    coordination_mqtt.record_envelope(project_dir, duplicate_id)
    assert len(coordination_mqtt.load_envelopes(project_dir, now=event_time)) == 2
    assert coordination_mqtt.inspect_lease(
        tmp_path / "events", project_dir, "job:mqtt", config, now=event_time
    ).active


def test_mqtt_publisher_selects_and_records_the_lease_envelope(
    monkeypatch, tmp_path: Path
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    timestamp = datetime.now(UTC)
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    monkeypatch.setattr(
        coordination_mqtt.gossip, "_resolve_project_label", lambda *_args: None
    )
    monkeypatch.setattr(
        coordination_mqtt.gossip,
        "_publish_mqtt",
        lambda *_args, **_kwargs: {"status": "published", "qos": 0},
    )
    envelope = coordination_mqtt.make_claim_envelope(
        tmp_path,
        project_dir,
        config,
        resource="job:publish",
        owner="worker",
        claim_id="claim-1",
        event_id="event-1",
        lease_ttl_s=30,
        occurred_at=timestamp,
    )
    assert envelope.project == config.project_key
    assert coordination_mqtt.publish_envelope(tmp_path, project_dir, config, envelope)
    assert coordination_mqtt.transport_diagnostics()["publisher"]["qos"] == 0
    assert [item.id for item in coordination_mqtt.load_envelopes(project_dir)] == [
        envelope.id
    ]

    state, selected = coordination_mqtt.select_lease_envelope(
        tmp_path,
        project_dir,
        tmp_path / "missing-events",
        "job:unclaimed",
        config,
        now=timestamp,
    )
    assert not state.active and selected is None


def test_mqtt_pruning_removes_expired_overlays_and_stale_observations(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    now = datetime.now(UTC)
    expired = CoordinationGossipEnvelope(
        id="expired-overlay",
        ts=coordination.format_timestamp(now - timedelta(days=3)),
        project="kanbus",
        type="coordination.claim",
        event_id="expired-event",
        producer_id="peer",
        resource="job:prune",
        owner="worker",
        claim_id="claim-expired",
        lease_ttl_s=1,
    )
    overlay_dir = coordination_mqtt._overlay_dir(project_dir)
    directory = coordination_mqtt._resource_overlay_dir(project_dir, "job:prune")
    directory.mkdir(parents=True)
    expired_path = directory / f"{coordination_mqtt._sha256_hex(expired.id)}.json"
    expired_path.write_text(expired.model_dump_json(), encoding="utf-8")
    (directory / "misplaced.json").write_text(
        expired.model_dump_json(), encoding="utf-8"
    )

    observation_dir = project_dir / ".overlay" / "coordination-observations"
    observation_dir.mkdir(parents=True)
    stale = observation_dir / "stale.json"
    stale.write_text(
        json.dumps(
            {"observed_at": coordination.format_timestamp(now - timedelta(days=2))}
        ),
        encoding="utf-8",
    )
    invalid = observation_dir / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")

    coordination_mqtt._prune_overlay(overlay_dir, 3600, now=now)
    coordination_mqtt._prune_contention_observations(
        observation_dir, ttl_s=3600, now=now
    )
    assert not expired_path.exists()
    assert (directory / "misplaced.json").exists()
    assert not stale.exists()
    assert invalid.exists()


def test_router_state_rejects_occupied_worktree_and_unsafe_publication(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    common = root / ".git"
    target = common / "kanbus-router-state-worktree"
    target.mkdir(parents=True)
    monkeypatch.setattr(router_state, "_repo_root", lambda _root: root)
    monkeypatch.setattr(
        router_state,
        "_git",
        lambda _root, *args: (
            str(common) if args == ("rev-parse", "--git-common-dir") else ""
        ),
    )
    monkeypatch.setattr(router_state, "_fetch_state", lambda _root: None)
    monkeypatch.setattr(router_state, "_ref_sha", lambda *_args: None)
    monkeypatch.setattr(
        router_state,
        "_try_git",
        lambda _root, *args, **_kwargs: (
            "" if args[:2] == ("worktree", "list") else None
        ),
    )
    with pytest.raises(IssueRouterError, match="path is occupied"):
        router_state.router_state_root(root, refresh=False)

    worktree = tmp_path / "state-worktree"
    monkeypatch.setattr(
        router_state, "router_state_root", lambda *_args, **_kwargs: worktree
    )
    monkeypatch.setattr(
        router_state, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        router_state,
        "load_project_configuration",
        lambda _path: SimpleNamespace(project_directory="project"),
    )

    def selected_path(_root, *args):
        if args[0] == "diff":
            return "unrelated/private.txt"
        return ""

    monkeypatch.setattr(router_state, "_git", selected_path)
    with pytest.raises(IssueRouterError, match="selected an unsafe path"):
        router_state.publish_router_state(root)


def test_router_state_reuses_registered_worktree_and_creates_existing_branch(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    common = root / ".git"
    common.mkdir(parents=True)
    target = common / "kanbus-router-state-worktree"
    monkeypatch.setattr(router_state, "_repo_root", lambda _root: root)
    calls = []

    def git(_root, *args):
        calls.append(args)
        return str(common) if args == ("rev-parse", "--git-common-dir") else ""

    monkeypatch.setattr(router_state, "_git", git)
    monkeypatch.setattr(router_state, "_fetch_state", lambda _root: None)
    monkeypatch.setattr(router_state, "_ref_sha", lambda *_args: "branch-sha")
    monkeypatch.setattr(router_state, "_try_git", lambda *_args, **_kwargs: None)
    assert router_state.router_state_root(root, refresh=False) == target
    assert ("worktree", "add", str(target), router_state.STATE_BRANCH) in calls

    target.mkdir()
    monkeypatch.setattr(
        router_state,
        "_try_git",
        lambda _root, *args, **_kwargs: (
            str(target) if args[:2] == ("worktree", "list") else None
        ),
    )
    monkeypatch.setattr(
        router_state,
        "_git",
        lambda _root, *args: (
            str(common)
            if args == ("rev-parse", "--git-common-dir")
            else "feature-branch"
        ),
    )
    with pytest.raises(IssueRouterError, match="unexpected branch"):
        router_state.router_state_root(root, refresh=False)


def test_router_state_publish_retries_a_lost_lease(monkeypatch, tmp_path: Path) -> None:
    worktree = tmp_path / "state"
    monkeypatch.setattr(
        router_state, "router_state_root", lambda *_args, **_kwargs: worktree
    )
    monkeypatch.setattr(
        router_state, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        router_state,
        "load_project_configuration",
        lambda _path: SimpleNamespace(project_directory="project"),
    )
    monkeypatch.setattr(
        router_state,
        "_git",
        lambda _root, *args: (
            "project/events/event.json\0"
            if args[:3] == ("diff", "--cached", "--name-only")
            else "local-head"
        ),
    )
    monkeypatch.setattr(router_state, "_fetch_state", lambda _root: None)
    monkeypatch.setattr(router_state, "_ref_sha", lambda *_args: "remote-head")
    monkeypatch.setattr(router_state, "_is_ancestor", lambda *_args: False)
    merges = []
    monkeypatch.setattr(router_state, "_merge_ref", lambda *args: merges.append(args))

    def try_git(_root, *args, **_kwargs):
        return "origin-url" if args[:2] == ("remote", "get-url") else 1

    monkeypatch.setattr(router_state, "_try_git", try_git)
    with pytest.raises(IssueRouterError, match="after 5 retries"):
        router_state.publish_router_state(tmp_path)
    assert len(merges) == 10


@pytest.mark.parametrize("advance_remote", [False, True])
def test_router_start_publication_retries_failed_remote_lease(
    monkeypatch, tmp_path: Path, advance_remote: bool
) -> None:
    source = tmp_path / "source"
    source_state = tmp_path / "state"
    monkeypatch.setattr(router_state, "_repo_root", lambda _root: source)
    monkeypatch.setattr(
        router_state, "router_state_root", lambda *_args, **_kwargs: source_state
    )
    monkeypatch.setattr(router_state, "_fetch_state", lambda _root: None)
    monkeypatch.setattr(
        router_state,
        "get_configuration_path",
        lambda _root: tmp_path / ".kanbus.yml",
    )
    monkeypatch.setattr(
        router_state,
        "load_project_configuration",
        lambda _path: SimpleNamespace(project_directory="project"),
    )
    monkeypatch.setattr(router_state, "write_events_batch", lambda *_args: None)
    monkeypatch.setattr(router_state, "_is_ancestor", lambda *_args: False)
    monkeypatch.setattr(router_state, "_merge_ref", lambda *_args: None)

    def git(root, *args):
        if args[:2] == ("rev-parse", "HEAD"):
            return "source-head" if root == source_state else "temp-head"
        return ""

    monkeypatch.setattr(router_state, "_git", git)
    reference_reads = 0

    def ref_sha(_root, _ref):
        nonlocal reference_reads
        reference_reads += 1
        attempt, is_after_push = divmod(reference_reads - 1, 2)
        if advance_remote:
            return f"remote-{attempt + int(is_after_push)}"
        return "remote-stable"

    monkeypatch.setattr(router_state, "_ref_sha", ref_sha)

    def try_git(_root, *args, **_kwargs):
        if args[:2] == ("remote", "get-url"):
            return "origin-url"
        return 1 if args and args[0] == "push" else 0

    monkeypatch.setattr(router_state, "_try_git", try_git)
    event = create_event(
        issue_id="router:kbs-start",
        event_type="router.attempt",
        actor_id="worker",
        payload={"action": "started", "attempt": 1},
    )
    expected = (
        "after 5 retries" if advance_remote else "could not publish router start event"
    )
    with pytest.raises(IssueRouterError, match=expected):
        router_state.publish_router_start_event(
            source, event, validate_claim=lambda _events: None
        )
