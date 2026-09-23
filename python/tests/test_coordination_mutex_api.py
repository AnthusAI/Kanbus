from __future__ import annotations

import copy
import json
import sys
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
import yaml
from click.testing import CliRunner

from kanbus import coordination, coordination_mutex_api
from kanbus.cli import cli
from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.coordination_mutex_api import MutexApiError, MutexApiUnavailable
from kanbus.models import MutexApiConfiguration


class _Response:
    def __init__(self, status: int, body: dict | None = None) -> None:
        self.status = status
        self._body = b"" if body is None else json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args) -> None:
        return None


class _MemoryMutexApi:
    def __init__(self) -> None:
        self.leases: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict | None, str | None]] = []
        self.fail_unavailable = False
        self.before_request = None

    def __call__(self, request, *, timeout: float) -> _Response:
        assert timeout == coordination_mutex_api.REQUEST_TIMEOUT_SECONDS
        if self.fail_unavailable:
            raise urllib.error.URLError("offline")
        method = request.get_method()
        path = urlparse(request.full_url).path
        route_prefix = "/api/coordination/leases/"
        assert path.startswith(route_prefix)
        resource = unquote(path[len(route_prefix) :])
        body = json.loads(request.data) if request.data else None
        token = request.get_header("Authorization")
        self.calls.append((method, resource, body, token))
        if self.before_request is not None:
            self.before_request(method, resource, body)

        now = int(datetime.now(UTC).timestamp())
        lease = self.leases.get(resource)
        if lease and lease["expires_at"] <= now:
            del self.leases[resource]
            lease = None

        if method == "POST":
            if lease is not None:
                return _Response(409, {"message": "lease already held"})
            assert body is not None
            lease = {
                "resource": resource,
                "owner": body["owner"],
                "claim_id": body["claim_id"],
                "revision": body["revision"],
                "claimed_at": now,
                "expires_at": now + body["ttl_seconds"],
            }
            self.leases[resource] = lease
            return _Response(201, lease)
        if method == "GET":
            if lease is None:
                return _Response(404, {"message": "no live lease"})
            return _Response(200, lease)
        if method in {"PUT", "DELETE"}:
            if lease is None:
                return _Response(404, {"message": "no live lease"})
            assert body is not None
            if (body["owner"], body["claim_id"]) != (
                lease["owner"],
                lease["claim_id"],
            ):
                return _Response(403, {"message": "lease owner mismatch"})
            if method == "PUT":
                lease["expires_at"] = (
                    max(lease["expires_at"], now) + body["extend_seconds"]
                )
                return _Response(200, lease)
            del self.leases[resource]
            return _Response(204)
        raise AssertionError(f"unexpected HTTP method: {method}")


def _api_config() -> MutexApiConfiguration:
    return MutexApiConfiguration(
        endpoint="https://mutex.example.test",
        bearer_token="test-bearer-token",
    )


def _write_project_config(path: Path, *, providers: list[str]) -> None:
    config = copy.deepcopy(DEFAULT_CONFIGURATION)
    config["coordination"].update(
        providers=providers,
        mutex_api={
            "endpoint": "https://mutex.example.test",
            "bearer_token": "test-bearer-token",
        },
    )
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def test_mutex_api_methods_use_bearer_route_and_expected_http_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _MemoryMutexApi()
    monkeypatch.setattr(coordination_mutex_api, "_urlopen", api)
    config = _api_config()

    acquired = coordination_mutex_api.acquire(
        config,
        resource="sched:epoch/1",
        owner="worker-a",
        claim_id="claim-a",
        revision=7,
        ttl_seconds=300,
    )
    assert acquired.revision == 7
    assert api.calls[0] == (
        "POST",
        "sched:epoch/1",
        {
            "owner": "worker-a",
            "claim_id": "claim-a",
            "revision": 7,
            "ttl_seconds": 300,
        },
        "Bearer test-bearer-token",
    )

    with pytest.raises(MutexApiError, match="lease already held") as conflict:
        coordination_mutex_api.acquire(
            config,
            resource="sched:epoch/1",
            owner="worker-b",
            claim_id="claim-b",
            revision=1,
            ttl_seconds=300,
        )
    assert conflict.value.status == 409

    renewed = coordination_mutex_api.renew(
        config,
        resource="sched:epoch/1",
        owner="worker-a",
        claim_id="claim-a",
        extend_seconds=120,
    )
    assert renewed.expires_at > acquired.expires_at
    with pytest.raises(MutexApiError, match="lease owner mismatch") as mismatch:
        coordination_mutex_api.renew(
            config,
            resource="sched:epoch/1",
            owner="worker-b",
            claim_id="claim-a",
            extend_seconds=10,
        )
    assert mismatch.value.status == 403
    with pytest.raises(MutexApiError, match="lease owner mismatch") as release_mismatch:
        coordination_mutex_api.release(
            config,
            resource="sched:epoch/1",
            owner="worker-b",
            claim_id="claim-a",
        )
    assert release_mismatch.value.status == 403

    inspected = coordination_mutex_api.inspect(config, resource="sched:epoch/1")
    assert inspected is not None and inspected.claim_id == "claim-a"
    coordination_mutex_api.release(
        config,
        resource="sched:epoch/1",
        owner="worker-a",
        claim_id="claim-a",
    )
    assert coordination_mutex_api.inspect(config, resource="sched:epoch/1") is None
    with pytest.raises(MutexApiError, match="no live lease") as missing_renew:
        coordination_mutex_api.renew(
            config,
            resource="sched:epoch/1",
            owner="worker-a",
            claim_id="claim-a",
            extend_seconds=10,
        )
    assert missing_renew.value.status == 404
    assert [method for method, *_ in api.calls] == [
        "POST",
        "POST",
        "PUT",
        "PUT",
        "DELETE",
        "GET",
        "DELETE",
        "GET",
        "PUT",
    ]


def test_mutex_api_cli_acquires_before_git_event_and_keeps_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_project_config(
        tmp_path / ".kanbus.yml", providers=["mutex_api", "mqtt", "git"]
    )
    monkeypatch.chdir(tmp_path)
    api = _MemoryMutexApi()
    events_dir = project_dir / "events"

    def assert_order(method: str, resource: str, _body: dict | None) -> None:
        if method == "POST" and resource == "job:hard":
            assert not events_dir.exists() or not list(events_dir.glob("*.json"))

    api.before_request = assert_order
    monkeypatch.setattr(coordination_mutex_api, "_urlopen", api)

    result = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:hard",
            "--owner",
            "worker-a",
            "--claim-id",
            "claim-hard",
            "--revision",
            "7",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "provider: mutex_api" in result.output
    assert "state: active hard mutex" in result.output
    assert "revision: 7" in result.output
    event = json.loads(next(events_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert event["event_type"] == "coordination.claim"
    assert event["payload"]["revision"] == 7
    assert api.calls[0][0] == "POST"

    renewed = CliRunner().invoke(
        cli,
        [
            "coordination",
            "renew",
            "--resource",
            "job:hard",
            "--owner",
            "worker-a",
            "--claim-id",
            "claim-hard",
            "--extend",
            "120s",
        ],
    )
    assert renewed.exit_code == 0, renewed.output
    assert "provider: mutex_api" in renewed.output
    assert "state: active hard mutex" in renewed.output
    inspect = CliRunner().invoke(
        cli, ["coordination", "inspect", "--resource", "job:hard"]
    )
    assert inspect.exit_code == 0
    assert "claim_id: claim-hard" in inspect.output
    released = CliRunner().invoke(
        cli,
        [
            "coordination",
            "release",
            "--resource",
            "job:hard",
            "--owner",
            "worker-a",
            "--claim-id",
            "claim-hard",
        ],
    )
    assert released.exit_code == 0
    assert "state: released" in released.output
    records = [json.loads(path.read_text()) for path in events_dir.glob("*.json")]
    assert {record["event_type"] for record in records} == {
        "coordination.claim",
        "coordination.renew",
        "coordination.release",
    }
    assert api.leases == {}

    default_revision = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:default-revision",
            "--owner",
            "worker-a",
            "--claim-id",
            "claim-default-revision",
        ],
    )
    assert default_revision.exit_code == 0, default_revision.output
    assert api.calls[-1][2]["revision"] == 1
    call_count = len(api.calls)
    invalid_revision = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:invalid-revision",
            "--owner",
            "worker-a",
            "--claim-id",
            "claim-invalid-revision",
            "--revision",
            "0",
        ],
    )
    assert invalid_revision.exit_code == 2
    assert len(api.calls) == call_count


def test_mutex_api_conflict_is_not_downgraded_to_soft_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project").mkdir()
    _write_project_config(
        tmp_path / ".kanbus.yml", providers=["mutex_api", "mqtt", "git"]
    )
    monkeypatch.chdir(tmp_path)
    api = _MemoryMutexApi()
    api.leases["job:held"] = {
        "resource": "job:held",
        "owner": "worker-existing",
        "claim_id": "claim-existing",
        "revision": 2,
        "claimed_at": int(datetime.now(UTC).timestamp()),
        "expires_at": int(datetime.now(UTC).timestamp()) + 300,
    }
    monkeypatch.setattr(coordination_mutex_api, "_urlopen", api)

    result = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:held",
            "--owner",
            "worker-new",
            "--claim-id",
            "claim-new",
        ],
    )
    assert result.exit_code == 1
    assert "lease already held" in result.stderr
    assert not list((tmp_path / "project" / "events").glob("*.json"))


def test_mutex_api_unavailability_falls_back_to_git_without_aws_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project").mkdir()
    _write_project_config(
        tmp_path / ".kanbus.yml", providers=["mutex_api", "mqtt", "git"]
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    # Force MQTT unavailable regardless of the host's real environment (e.g.
    # a developer running an always-on Mosquitto broker per the REALTIME
    # guide on the default port). "off" is the supported broker value that
    # disables MQTT outright, matching this test's actual intent: both
    # mutex_api and MQTT unavailable, so coordination falls back to git.
    monkeypatch.setenv("KANBUS_REALTIME_BROKER", "off")
    api = _MemoryMutexApi()
    api.fail_unavailable = True
    monkeypatch.setattr(coordination_mutex_api, "_urlopen", api)

    result = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:fallback",
            "--owner",
            "worker",
            "--claim-id",
            "claim-fallback",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "provider: git" in result.output
    assert len(list((tmp_path / "project" / "events").glob("*.json"))) == 1
    assert "boto" not in sys.modules


def test_mutex_api_unavailability_falls_back_to_available_mqtt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project").mkdir()
    _write_project_config(
        tmp_path / ".kanbus.yml", providers=["mutex_api", "mqtt", "git"]
    )
    monkeypatch.chdir(tmp_path)
    api = _MemoryMutexApi()
    api.fail_unavailable = True
    monkeypatch.setattr(coordination_mutex_api, "_urlopen", api)
    monkeypatch.setattr("kanbus.coordination_mqtt.provider_available", lambda *_: True)
    monkeypatch.setattr("kanbus.coordination_mqtt.publish_envelope", lambda *_: True)

    result = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:mqtt-fallback",
            "--owner",
            "worker",
            "--claim-id",
            "claim-fallback",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "provider: mqtt" in result.output
    assert len(list((tmp_path / "project" / "events").glob("*.json"))) == 1


def test_failed_durable_append_attempts_best_effort_mutex_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project").mkdir()
    _write_project_config(
        tmp_path / ".kanbus.yml", providers=["mutex_api", "mqtt", "git"]
    )
    monkeypatch.chdir(tmp_path)
    api = _MemoryMutexApi()
    monkeypatch.setattr(coordination_mutex_api, "_urlopen", api)
    monkeypatch.setattr(
        "kanbus.cli.coordination_claim",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            coordination.CoordinationError("disk full")
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "coordination",
            "claim",
            "--resource",
            "job:rollback",
            "--owner",
            "worker",
            "--claim-id",
            "claim-rollback",
        ],
    )
    assert result.exit_code == 1
    assert "durable Git claim could not be recorded: disk full" in result.stderr
    assert [method for method, *_ in api.calls] == ["POST", "DELETE"]
    assert api.leases == {}


def test_mutex_api_configuration_environment_overrides_and_unconfigured_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".kanbus.yml"
    config = copy.deepcopy(DEFAULT_CONFIGURATION)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv(
        "KANBUS_COORDINATION_MUTEX_API_ENDPOINT", "https://env.example.test"
    )
    monkeypatch.setenv("KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN", "env-secret")
    loaded = load_project_configuration(path)
    assert loaded.coordination.mutex_api.endpoint == "https://env.example.test"
    assert loaded.coordination.mutex_api.bearer_token == "env-secret"
    assert not coordination_mutex_api.is_configured(MutexApiConfiguration())


def test_invalid_mutex_api_endpoint_uses_field_qualified_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = copy.deepcopy(DEFAULT_CONFIGURATION)
    config["coordination"]["mutex_api"] = {"endpoint": "not-a-url"}
    path = tmp_path / ".kanbus.yml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    monkeypatch.delenv("KANBUS_COORDINATION_MUTEX_API_ENDPOINT", raising=False)

    with pytest.raises(ConfigurationError) as error:
        load_project_configuration(path)

    assert str(error.value) == (
        "coordination.mutex_api.endpoint: must be an absolute http(s) URL"
    )


def test_mutex_api_unavailable_is_distinct_from_api_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def offline(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(coordination_mutex_api, "_urlopen", offline)
    with pytest.raises(MutexApiUnavailable, match="mutex api unavailable"):
        coordination_mutex_api.inspect(_api_config(), resource="job:offline")


def test_mutex_api_inspect_treats_stale_success_as_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = {
        "resource": "job:expired",
        "owner": "worker",
        "claim_id": "claim",
        "revision": 1,
        "claimed_at": 1_700_000_000,
        "expires_at": 1_700_000_001,
    }
    monkeypatch.setattr(
        coordination_mutex_api,
        "_urlopen",
        lambda *_args, **_kwargs: _Response(200, stale),
    )
    assert coordination_mutex_api.inspect(_api_config(), resource="job:expired") is None
