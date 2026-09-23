"""Focused provider-dispatch and MQTT listener lifecycle tests."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kanbus import coordination_mqtt, coordination_runtime
from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.coordination import LeaseState
from kanbus.models import ProjectConfiguration


def _configuration(*, providers: list[str] | None = None) -> ProjectConfiguration:
    values = copy.deepcopy(DEFAULT_CONFIGURATION)
    if providers is not None:
        values["coordination"]["providers"] = providers
    values["realtime"].update(
        transport="mqtt",
        broker="mqtts://broker.example:8883",
        autostart=False,
        mqtt_custom_authorizer_name=None,
        mqtt_api_token=None,
    )
    return ProjectConfiguration.model_validate(values)


class _WaitSignal:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.timeouts: list[float] = []

    def wait(self, timeout: float) -> bool:
        self.timeouts.append(timeout)
        return self.result


class _Listener:
    def __init__(self, *, connected: bool, subscribed: bool) -> None:
        self.connected = _WaitSignal(connected)
        self.subscribed = _WaitSignal(subscribed)
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def test_provider_selection_uses_git_when_mqtt_is_not_selected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []
    monkeypatch.setattr(
        coordination_mqtt,
        "provider_available",
        lambda *_args: calls.append("probe") or True,
    )

    assert (
        coordination_runtime.select_soft_provider(
            tmp_path, _configuration(providers=["git"])
        )
        == "git"
    )
    assert calls == []
    assert (
        coordination_runtime.select_soft_provider(
            tmp_path, _configuration(providers=["mqtt", "git"])
        )
        == "mqtt"
    )
    assert calls == ["probe"]


def test_listener_setup_waits_for_connection_and_suback_with_custom_auth_budget(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    config.realtime.mqtt_custom_authorizer_name = "integration-auth"
    config.realtime.mqtt_api_token = "must-not-be-printed"
    listener = _Listener(connected=True, subscribed=True)
    ticks = iter((100.0, 101.0, 102.0))
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    monkeypatch.setattr(coordination_mqtt, "start_listener", lambda *_args: listener)
    monkeypatch.setattr(coordination_runtime, "monotonic", lambda: next(ticks))

    selected = coordination_runtime.start_soft_listener(
        tmp_path, tmp_path / "project", config
    )

    assert selected is listener
    assert listener.connected.timeouts == [4.0]
    assert listener.subscribed.timeouts == [3.0]
    assert not listener.stopped


def test_listener_suback_timeout_stops_listener_and_reports_safe_opt_in_diagnostics(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    config.realtime.mqtt_api_token = "secret-value"
    listener = _Listener(connected=True, subscribed=False)
    monkeypatch.setattr(coordination_runtime, "select_soft_provider", lambda *_: "mqtt")
    monkeypatch.setattr(coordination_mqtt, "start_listener", lambda *_args: listener)
    monkeypatch.setattr(
        coordination_mqtt,
        "transport_diagnostics",
        lambda: {
            "listener": {"status": "suback_timeout", "topic": "projects/demo"},
            "publisher": {},
        },
    )
    monkeypatch.setattr(coordination_runtime, "monotonic", lambda: 5.0)
    monkeypatch.setenv("KANBUS_ROUTER_MQTT_DIAGNOSTICS", "1")

    selected = coordination_runtime.start_soft_listener(
        tmp_path, tmp_path / "project", config, ready_timeout=0
    )

    assert selected is None
    assert listener.stopped
    diagnostics = capsys.readouterr().err
    assert '"status":"suback_timeout"' in diagnostics
    assert "secret-value" not in diagnostics


def test_listener_start_failure_falls_back_without_unsolicited_diagnostics(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.delenv("KANBUS_ROUTER_MQTT_DIAGNOSTICS", raising=False)
    monkeypatch.setattr(coordination_runtime, "select_soft_provider", lambda *_: "mqtt")
    monkeypatch.setattr(coordination_mqtt, "start_listener", lambda *_args: None)

    assert (
        coordination_runtime.start_soft_listener(
            tmp_path, tmp_path / "project", _configuration(providers=["mqtt", "git"])
        )
        is None
    )
    assert capsys.readouterr().err == ""


def test_renewal_visibility_waits_for_closed_window_and_uses_selected_lease(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _configuration(providers=["mqtt", "git"])
    root = tmp_path
    project_dir = tmp_path / "project"
    claimed_at = datetime(2026, 9, 17, 12, tzinfo=UTC)
    window_end = claimed_at + timedelta(seconds=5)
    expires_at = claimed_at + timedelta(seconds=300)
    state = LeaseState(
        resource="router:issue:kbs-1",
        owner="worker-a",
        claim_id="claim-a",
        active=True,
        event_id="durable-claim-event",
        claimed_at=claimed_at,
        contention_window_ends_at=window_end,
        expires_at=expires_at,
        operation_sequence=4,
    )
    envelopes = []
    monkeypatch.setattr(
        coordination_mqtt,
        "make_lease_envelope",
        lambda *args, **kwargs: envelopes.append(kwargs) or object(),
    )
    monkeypatch.setattr(
        coordination_mqtt,
        "publish_envelope",
        lambda *_args: False,
    )

    assert (
        coordination_runtime.publish_renewal_visibility(
            root,
            project_dir,
            config,
            resource=state.resource,
            owner="worker-a",
            claim_id="claim-a",
            state=state,
            occurred_at=window_end - timedelta(milliseconds=1),
        )
        is True
    )
    assert envelopes == []

    published = coordination_runtime.publish_renewal_visibility(
        root,
        project_dir,
        config,
        resource=state.resource,
        owner="worker-a",
        claim_id="claim-a",
        state=state,
        occurred_at=window_end,
    )

    assert published is False
    assert envelopes[0]["event_id"] == "durable-claim-event"
    assert envelopes[0]["lease_ttl_s"] == 300
    assert envelopes[0]["operation_sequence"] == 4
