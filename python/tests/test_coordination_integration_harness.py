"""Focused offline tests for the opt-in coordination integration harness."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import coordination_integration_harness as harness  # noqa: E402


def _inputs() -> dict[str, str]:
    return {
        harness.ENABLE_ENV: "1",
        harness.REQUIRED_ENV["mutex_endpoint"]: "https://mutex.example.test",
        harness.REQUIRED_ENV["mutex_token"]: "test-value-mutex",
        harness.REQUIRED_ENV["mqtt_broker"]: "mqtts://broker.example.test:8883",
        harness.REQUIRED_ENV["mqtt_authorizer"]: "test-authorizer",
        harness.REQUIRED_ENV["mqtt_token"]: "test-value-mqtt",
        harness.REQUIRED_ENV["tenant_account"]: "test-account",
        harness.REQUIRED_ENV["tenant_project"]: "test-project",
        harness.REQUIRED_ENV["python_worker"]: "python -m kanbus.cli",
        harness.REQUIRED_ENV["rust_worker"]: "/opt/kanbus/kbs",
    }


def test_live_harness_is_disabled_without_explicit_gate() -> None:
    with pytest.raises(harness.HarnessError, match="live execution is disabled"):
        harness.require_inputs({})


def test_required_service_and_worker_inputs_are_explicit() -> None:
    env = _inputs()
    env.pop(harness.REQUIRED_ENV["mqtt_token"])

    with pytest.raises(harness.HarnessError, match="missing required"):
        harness.require_inputs(env)


def test_worker_commands_are_split_without_shell_execution() -> None:
    env = _inputs()
    env[harness.REQUIRED_ENV["python_worker"]] = (
        "conda run -n py311 python -m kanbus.cli"
    )

    inputs = harness.require_inputs(env)

    assert inputs.python_worker == (
        "conda",
        "run",
        "-n",
        "py311",
        "python",
        "-m",
        "kanbus.cli",
    )
    assert inputs.rust_worker == ("/opt/kanbus/kbs",)


def test_environment_requires_valid_service_urls() -> None:
    env = _inputs()
    env[harness.REQUIRED_ENV["mqtt_broker"]] = "https://not-mqtt.example.test"

    with pytest.raises(harness.HarnessError, match="MQTT broker"):
        harness.require_inputs(env)


def test_tenant_scope_is_a_safe_single_mqtt_topic_segment() -> None:
    env = _inputs()
    env[harness.REQUIRED_ENV["tenant_project"]] = "project/other"

    with pytest.raises(harness.HarnessError, match="tenant project"):
        harness.require_inputs(env)


def test_create_output_id_parser_handles_color_and_issue_display() -> None:
    output = "\x1b[2mID:\x1b[0m \x1b[36mKAN-abc123\x1b[0m\nTitle: fixture\n"

    assert harness.parse_issue_id(output) == "KAN-abc123"


def test_held_lease_classification_requires_failure_and_contention_message() -> None:
    held = harness.CommandResult(1, "", "Error: lease already held")
    unavailable = harness.CommandResult(1, "", "mutex api unavailable")
    success = harness.CommandResult(0, "state: active hard mutex", "")

    assert harness.held_lease_result(held)
    assert not harness.held_lease_result(unavailable)
    assert not harness.held_lease_result(success)


def test_coordination_output_fields_ignore_non_key_lines() -> None:
    fields = harness.output_fields(
        "provider: mutex_api\nstate: active hard mutex\nowner: worker-a\n"
        "this line is not a field\n"
    )

    assert fields == {
        "provider": "mutex_api",
        "state": "active hard mutex",
        "owner": "worker-a",
    }


def test_gossip_watch_command_uses_explicit_mqtt_and_no_autostart() -> None:
    worker = harness.Worker(
        "python-worker", ("python", "-m", "kanbus.cli"), Path("/tmp/worker")
    )

    command = harness.gossip_watch_command(worker, "mqtts://broker.example.test:443")

    assert command == (
        "python",
        "-m",
        "kanbus.cli",
        "--no-guidance",
        "--no-hooks",
        "gossip",
        "watch",
        "--transport",
        "mqtt",
        "--broker",
        "mqtts://broker.example.test:443",
        "--no-autostart",
        "--print",
    )


def test_matching_claim_envelope_requires_valid_wire_fields() -> None:
    envelope = {
        "id": "message-1",
        "ts": "2026-09-16T12:00:00Z",
        "project": "kanbus",
        "type": "coordination.claim",
        "event_id": "event-1",
        "producer_id": "rust-worker",
        "resource": "harness:run-1:mqtt-probe",
        "owner": "rust-worker",
        "claim_id": "claim-1",
        "lease_ttl_s": 5,
    }

    assert harness.is_matching_claim_envelope(
        envelope,
        resource="harness:run-1:mqtt-probe",
        owner="rust-worker",
        claim_id="claim-1",
    )
    assert not harness.is_matching_claim_envelope(
        {**envelope, "resource": "another-resource"},
        resource="harness:run-1:mqtt-probe",
        owner="rust-worker",
        claim_id="claim-1",
    )
    assert not harness.is_matching_claim_envelope(
        {**envelope, "lease_ttl_s": True},
        resource="harness:run-1:mqtt-probe",
        owner="rust-worker",
        claim_id="claim-1",
    )
    assert not harness.is_matching_claim_envelope(
        {**envelope, "ts": "not-a-timestamp"},
        resource="harness:run-1:mqtt-probe",
        owner="rust-worker",
        claim_id="claim-1",
    )


def test_watcher_shutdown_terminates_the_process_group() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=os.name == "posix",
    )
    try:
        harness.terminate_process_tree(process, grace_seconds=0.5)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            harness.terminate_process_tree(process, grace_seconds=0.5)


def test_watcher_output_redacts_mqtt_credentials() -> None:
    env = _inputs()

    redacted = harness._redact("token=test-value-mqtt bearer=test-value-mutex", env)

    assert "test-value-mqtt" not in redacted
    assert "test-value-mutex" not in redacted
    assert redacted.count("<redacted>") == 2
