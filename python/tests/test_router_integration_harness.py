"""Focused offline tests for the disposable router integration harness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import issue_router_integration_harness as harness  # noqa: E402


def _live_inputs() -> dict[str, str]:
    return {
        harness.ENABLE_LIVE_ENV: "1",
        harness.MUTEX_ENDPOINT_ENV: "https://mutex.example.test/api",
        harness.MUTEX_TOKEN_ENV: "secret-mutex-token",
        harness.MQTT_BROKER_ENV: "mqtts://broker.example.test:8883",
        harness.MQTT_AUTHORIZER_ENV: "test-authorizer",
        harness.MQTT_TOKEN_ENV: "secret-mqtt-token",
        harness.MQTT_ACCOUNT_ENV: "test-account",
        harness.MQTT_PROJECT_ENV: "test-project",
    }


def test_offline_inputs_default_to_python_and_rust_command_prefixes() -> None:
    inputs = harness.require_inputs({}, live=False)

    assert inputs.python_worker[-2:] == ("-m", "kanbus.cli")
    assert inputs.rust_worker == ("kbs",)
    assert not inputs.mutex_enabled
    assert not inputs.mqtt_enabled


def test_worker_command_prefixes_are_split_without_shell_execution() -> None:
    inputs = harness.require_inputs(
        {},
        live=False,
        python_worker="conda run -n py311 python -m kanbus.cli",
        rust_worker="cargo run --manifest-path rust/Cargo.toml --bin kbs --",
    )

    assert inputs.python_worker == (
        "conda",
        "run",
        "-n",
        "py311",
        "python",
        "-m",
        "kanbus.cli",
    )
    assert inputs.rust_worker[-3:] == ("--bin", "kbs", "--")


def test_worker_environment_disables_daemon_by_default_and_honors_override(
    tmp_path: Path,
) -> None:
    inputs = harness.require_inputs({}, live=False)
    worker = harness.Worker("offline", inputs.python_worker, tmp_path)

    default_env = harness._worker_environment(
        {}, worker, inputs=inputs, log_path=tmp_path / "calls.jsonl", role="unit"
    )
    explicit_env = harness._worker_environment(
        {"KANBUS_NO_DAEMON": "0"},
        worker,
        inputs=inputs,
        log_path=tmp_path / "calls.jsonl",
        role="unit",
    )

    assert default_env["KANBUS_NO_DAEMON"] == "1"
    assert explicit_env["KANBUS_NO_DAEMON"] == "0"


def test_live_mode_requires_an_explicit_environment_gate() -> None:
    with pytest.raises(harness.HarnessError, match="live execution is disabled"):
        harness.require_inputs({}, live=True)


def test_live_mutex_requires_endpoint_and_token_together() -> None:
    env = {
        harness.ENABLE_LIVE_ENV: "1",
        harness.MUTEX_ENDPOINT_ENV: "https://mutex.test",
    }

    with pytest.raises(harness.HarnessError, match="configure both"):
        harness.require_inputs(env, live=True)


def test_live_mqtt_requires_complete_credentials_and_safe_topic_segments() -> None:
    env = _live_inputs()
    env[harness.MQTT_PROJECT_ENV] = "account/project"

    with pytest.raises(harness.HarnessError, match="tenant project"):
        harness.require_inputs(env, live=True)


def test_live_inputs_accept_both_optional_services() -> None:
    inputs = harness.require_inputs(_live_inputs(), live=True)

    assert inputs.mutex_enabled
    assert inputs.mqtt_enabled
    assert inputs.mutex_endpoint == "https://mutex.example.test/api"


def test_locked_result_envelope_has_exactly_the_six_contract_fields() -> None:
    envelope = harness.locked_result_envelope()

    assert tuple(envelope) == harness.RESULT_KEYS
    assert envelope["schema_version"] == 1
    assert envelope["outcome"] == "completed"
    assert json.loads(json.dumps(envelope)) == envelope


def test_plan_comparison_checks_byte_identity_and_expected_order() -> None:
    plan = json.dumps({"eligible": [{"issue_id": "kbs-a"}, {"issue_id": "kbs-b"}]})

    harness.assert_deterministic_plans(plan, plan, ["kbs-a", "kbs-b"])

    with pytest.raises(harness.HarnessError, match="byte-for-byte"):
        harness.assert_deterministic_plans(plan, plan + "\n", ["kbs-a", "kbs-b"])
    with pytest.raises(harness.HarnessError, match="order differs"):
        harness.assert_deterministic_plans(plan, plan, ["kbs-b", "kbs-a"])


def test_publication_fence_requires_stale_claim_error_and_current_status() -> None:
    stale = harness.CommandResult(1, "", "error: stale router claim claim-old")

    harness.assert_fenced_publication(stale, "review")

    with pytest.raises(harness.HarnessError, match="unexpectedly published"):
        harness.assert_fenced_publication(
            harness.CommandResult(0, "completed", ""), "review"
        )
    with pytest.raises(harness.HarnessError, match="changed accepted status"):
        harness.assert_fenced_publication(stale, "blocked")


def test_shared_state_assertion_requires_remote_claim_and_board_status() -> None:
    plan = json.dumps({"eligible": [{"issue_id": "kbs-secondary"}], "deferred": []})

    harness.assert_shared_router_state(
        plan,
        {"status": "in_progress"},
        "provider: git\nstate: active soft ownership\nclaim_id: claim-a\n",
        issue_id="kbs-primary",
        expected_status="in_progress",
        claim_active=True,
    )
    harness.assert_shared_router_state(
        plan,
        {"status": "in_progress"},
        "provider: git\nstate: active soft ownership\nclaim_id: claim-a\n",
        issue_id="kbs-primary",
        expected_status="in_progress",
        claim_active=True,
        expected_eligible_issue_ids=["kbs-secondary"],
    )
    with pytest.raises(harness.HarnessError, match="did not reconcile shared status"):
        harness.assert_shared_router_state(
            plan,
            {"status": "open"},
            "state: active soft ownership",
            issue_id="kbs-primary",
            expected_status="in_progress",
            claim_active=True,
        )
    with pytest.raises(harness.HarnessError, match="expected remaining packages"):
        harness.assert_shared_router_state(
            plan,
            {"status": "in_progress"},
            "state: active soft ownership",
            issue_id="kbs-primary",
            expected_status="in_progress",
            claim_active=True,
            expected_eligible_issue_ids=["kbs-primary", "kbs-secondary"],
        )


def test_shared_router_state_must_advance_beyond_fixture_setup() -> None:
    harness.assert_router_state_ref_advanced("before", "after")

    with pytest.raises(harness.HarnessError, match="did not publish shared state"):
        harness.assert_router_state_ref_advanced("before", "before")


def test_stale_result_must_not_replace_the_accepted_output_ref() -> None:
    harness.assert_output_ref_published("sha-current", "codex/router/kbs-a/r1")
    harness.assert_output_ref_unchanged(
        "sha-current", "sha-current", "codex/router/kbs-a/r1"
    )

    with pytest.raises(harness.HarnessError, match="did not publish"):
        harness.assert_output_ref_published("", "codex/router/kbs-a/r1")
    with pytest.raises(harness.HarnessError, match="changed published ref"):
        harness.assert_output_ref_unchanged(
            "sha-current", "sha-stale", "codex/router/kbs-a/r1"
        )


def test_durable_router_event_history_requires_start_and_completed_result(
    tmp_path: Path,
) -> None:
    events = tmp_path / "project" / "events"
    events.mkdir(parents=True)
    (events / "claim.json").write_text(
        json.dumps(
            {
                "issue_id": "router:kbs-primary",
                "event_type": "router.attempt",
                "payload": {"action": "started", "claim_id": "claim-a"},
            }
        ),
        encoding="utf-8",
    )
    (events / "result.json").write_text(
        json.dumps(
            {
                "issue_id": "router:kbs-primary",
                "event_type": "router.result",
                "payload": {"outcome": "completed", "revision": 1},
            }
        ),
        encoding="utf-8",
    )

    harness._assert_durable_router_history(tmp_path, "kbs-primary")


def test_hard_start_assertion_requires_one_worker_start_and_one_adapter_call() -> None:
    results = {
        "python": harness.CommandResult(0, "started=1", ""),
        "rust": harness.CommandResult(0, "started=0", ""),
    }

    harness.assert_one_hard_start(results, 1)

    with pytest.raises(harness.HarnessError, match="exactly one adapter"):
        harness.assert_one_hard_start(results, 2)

    failed_results = {
        "python": harness.CommandResult(1, "started=0", "error: Mutex API unavailable"),
        "rust": harness.CommandResult(1, "started=0", "error: stale claim"),
    }
    with pytest.raises(harness.HarnessError) as error:
        harness.assert_one_hard_start(failed_results, 0)
    assert "stderr: error: Mutex API unavailable" in str(error.value)
    assert "stderr: error: stale claim" in str(error.value)


def test_mqtt_soft_race_requires_one_adapter_and_one_accepted_claim() -> None:
    results = {
        "python": harness.CommandResult(0, "started=1 completed=1", ""),
        "rust": harness.CommandResult(0, "started=0 completed=0", ""),
    }

    harness.assert_one_mqtt_soft_start(results, 1, 1)

    with pytest.raises(harness.HarnessError, match="adapter_starts=2"):
        harness.assert_one_mqtt_soft_start(results, 2, 1)
    with pytest.raises(harness.HarnessError, match="accepted_claims=2"):
        harness.assert_one_mqtt_soft_start(results, 1, 2)
    with pytest.raises(harness.HarnessError, match="did not report one start"):
        harness.assert_one_mqtt_soft_start(
            {
                "python": harness.CommandResult(0, "started=1", ""),
                "rust": harness.CommandResult(0, "started=1", ""),
            },
            1,
            1,
        )


def test_mqtt_soft_race_requires_each_worker_to_observe_both_claim_ids() -> None:
    # The envelope scrape is intentionally incomplete: snapshots, not retained
    # post-run overlays, identify and prove the current claims.
    claim_ids = {"python": [], "rust": ["claim-b"]}
    harness.assert_mqtt_claim_exchange(
        claim_ids,
        {
            "python": [
                {
                    "claim_id": "claim-a",
                    "local_claim_id": "claim-a",
                    "peer_claim_ids": ["claim-b"],
                    "observed_claim_ids": ["claim-a", "claim-b"],
                    "observed_at": "2026-09-16T13:00:01Z",
                    "resource": "router:issue:kbs-race",
                }
            ],
            "rust": [
                {
                    "claim_id": "claim-b",
                    "local_claim_id": "claim-b",
                    "peer_claim_ids": ["claim-a"],
                    "observed_claim_ids": ["claim-a", "claim-b"],
                    "observed_at": "2026-09-16T13:00:01Z",
                    "resource": "router:issue:kbs-race",
                }
            ],
        },
    )

    with pytest.raises(harness.HarnessError, match="contention snapshots"):
        harness.assert_mqtt_claim_exchange(
            {"python": [], "rust": ["claim-b"]},
            {"python": [], "rust": []},
        )
    # Post-run envelopes cannot make up for a peer that arrived after the
    # worker closed its contention window.
    with pytest.raises(harness.HarnessError, match="contention snapshots"):
        harness.assert_mqtt_claim_exchange(
            claim_ids,
            {
                "python": [
                    {
                        "claim_id": "claim-a",
                        "local_claim_id": "claim-a",
                        "peer_claim_ids": [],
                        "observed_claim_ids": ["claim-a"],
                        "observed_at": "2026-09-16T13:00:01Z",
                        "resource": "router:issue:kbs-race",
                    }
                ],
                "rust": [
                    {
                        "claim_id": "claim-b",
                        "local_claim_id": "claim-b",
                        "peer_claim_ids": ["claim-a"],
                        "observed_claim_ids": ["claim-a", "claim-b"],
                        "observed_at": "2026-09-16T13:00:01Z",
                        "resource": "router:issue:kbs-race",
                    }
                ],
            },
        )
    with pytest.raises(harness.HarnessError, match="contention snapshots"):
        harness.assert_mqtt_claim_exchange(
            {"python": [], "rust": ["new-rust"]},
            {
                "python": [
                    {
                        "claim_id": "claim-a",
                        "local_claim_id": "claim-a",
                        "peer_claim_ids": ["claim-b"],
                        "observed_claim_ids": ["claim-a", "claim-b"],
                        "observed_at": "2026-09-16T13:00:01Z",
                        "resource": "router:issue:kbs-race",
                    }
                ],
                "rust": [
                    {
                        "claim_id": "claim-b",
                        "local_claim_id": "claim-b",
                        "peer_claim_ids": ["claim-a"],
                        "observed_claim_ids": ["claim-a", "claim-b"],
                        "observed_at": "2026-09-16T13:00:01Z",
                        "resource": "router:issue:kbs-race",
                    }
                ],
            },
            prior_observation_claim_ids={
                "python": ["claim-a"],
                "rust": ["claim-b"],
            },
        )


def test_mqtt_transport_diagnostics_require_distinct_ready_connections() -> None:
    def snapshot(local: str, peer: str) -> dict[str, object]:
        listener_id = f"listener-{local}"
        publisher_id = f"publisher-{local}"
        transport = {
            "listener": {
                "connected": True,
                "subscribed": True,
                "connect_reason_code": 0,
                "client_id": listener_id,
                "topic": "projects/account/project/events",
            },
            "publisher": {
                "status": "published",
                "connected": True,
                "connect_reason_code": 0,
                "publish_completed": True,
                "publish_rc": 0,
                "client_id": publisher_id,
                "topic": "projects/account/project/events",
            },
        }
        return {
            "claim_id": local,
            "local_claim_id": local,
            "peer_claim_ids": [peer],
            "observed_claim_ids": [local, peer],
            "observed_at": "2026-09-16T13:00:01Z",
            "resource": "router:issue:kbs-race",
            "mqtt_transport": transport,
        }

    harness.assert_mqtt_claim_exchange(
        {"python": [], "rust": []},
        {
            "python": [snapshot("claim-a", "claim-b")],
            "rust": [snapshot("claim-b", "claim-a")],
        },
        require_transport_diagnostics=True,
    )
    broken = snapshot("claim-b", "claim-a")
    broken["mqtt_transport"]["publisher"]["client_id"] = "listener-claim-b"
    with pytest.raises(harness.HarnessError, match="transport_reason"):
        harness.assert_mqtt_claim_exchange(
            {"python": [], "rust": []},
            {
                "python": [snapshot("claim-a", "claim-b")],
                "rust": [broken],
            },
            require_transport_diagnostics=True,
        )


def test_missing_mqtt_transport_diagnostics_allows_reciprocal_peer_exchange() -> None:
    def snapshot(local: str, peer: str) -> dict[str, object]:
        return {
            "claim_id": local,
            "local_claim_id": local,
            "peer_claim_ids": [peer],
            "observed_claim_ids": [local, peer],
            "observed_at": "2026-09-16T13:00:01Z",
            "resource": "router:issue:kbs-race",
        }

    harness.assert_mqtt_claim_exchange(
        {"python": [], "rust": []},
        {
            "python": [snapshot("claim-a", "claim-b")],
            "rust": [snapshot("claim-b", "claim-a")],
        },
        require_transport_diagnostics=True,
    )


def test_peer_exchange_still_requires_reciprocal_peer_ids_without_transport() -> None:
    def snapshot(local: str, peer_ids: list[str]) -> dict[str, object]:
        peer = "claim-b" if local == "claim-a" else "claim-a"
        return {
            "claim_id": local,
            "local_claim_id": local,
            "peer_claim_ids": peer_ids,
            # Keep the aggregate list complete so this specifically verifies
            # that peer_claim_ids itself is the reciprocal-exchange evidence.
            "observed_claim_ids": [local, peer],
            "observed_at": "2026-09-16T13:00:01Z",
            "resource": "router:issue:kbs-race",
        }

    with pytest.raises(harness.HarnessError, match="contention snapshots"):
        harness.assert_mqtt_claim_exchange(
            {"python": [], "rust": []},
            {
                "python": [snapshot("claim-a", [])],
                "rust": [snapshot("claim-b", ["claim-a"])],
            },
            require_transport_diagnostics=True,
        )


def test_harness_scans_configured_checkout_and_hidden_state_worktree(
    tmp_path: Path,
) -> None:
    root = tmp_path / "worker"
    root.mkdir()
    harness._run(["git", "init", "-q"], cwd=root, env={}, timeout=10)
    (root / ".kanbus.yml").write_text(
        "project_directory: board-data\n", encoding="utf-8"
    )
    common_dir = Path(
        harness._git(root, "rev-parse", "--git-common-dir").stdout.strip()
    )
    if not common_dir.is_absolute():
        common_dir = (root / common_dir).resolve()
    state_worktree = common_dir / "kanbus-router-state-worktree"
    (state_worktree / "board-data").mkdir(parents=True)

    assert harness._router_project_directories(root) == [
        (root / "board-data").resolve(),
        (state_worktree / "board-data").resolve(),
    ]


def test_shared_router_start_counter_matches_only_started_events() -> None:
    assert harness._is_started_router_event(
        {
            "issue_id": "router:kbs-race",
            "event_type": "router.attempt",
            "payload": {"action": "started", "claim_id": "claim-a"},
        },
        "kbs-race",
    )
    assert not harness._is_started_router_event(
        {
            "issue_id": "router:kbs-race",
            "event_type": "router.attempt",
            "payload": {"action": "completed", "claim_id": "claim-a"},
        },
        "kbs-race",
    )
    assert not harness._is_started_router_event(
        {
            "issue_id": "router:kbs-other",
            "event_type": "router.attempt",
            "payload": {"action": "started", "claim_id": "claim-a"},
        },
        "kbs-race",
    )


def test_output_redaction_hides_secret_values_from_child_environment() -> None:
    env = {
        "KANBUS_HARNESS_MUTEX_API_TOKEN": "sensitive-token-value",
        "PUBLIC_SETTING": "visible-value",
    }

    redacted = harness.redact_output(
        "authorization=none sensitive-token-value visible-value", env
    )

    assert "sensitive-token-value" not in redacted
    assert "visible-value" in redacted


def test_fake_adapter_emits_locked_envelope_and_does_not_read_real_credentials() -> (
    None
):
    source = harness.FAKE_ADAPTER_SOURCE

    assert '"schema_version": 1' in source
    assert '"issue_updates": []' in source
    assert '"checkpoint": None' in source
    assert '"artifacts": []' in source
    assert "KANBUS_HARNESS_MUTEX_API_TOKEN" not in source
