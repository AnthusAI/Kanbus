"""Focused checks for the opt-in board-backed container harness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import issue_router_container_integration_harness as harness


def _live_environment() -> dict[str, str]:
    return {
        harness.LIVE_GATE: "1",
        harness.MUTEX_ENDPOINT: "https://mutex.example.test/prod",
        harness.MUTEX_TOKEN: "mutex-secret",
        harness.MQTT_BROKER: "mqtts://broker.example.test:8883",
        harness.MQTT_AUTHORIZER: "kanbus-mqtt-token-test",
        harness.MQTT_TOKEN: "mqtt-secret",
        harness.OPENAI_KEY: "openai-secret",
    }


def test_live_inputs_require_both_explicit_gates() -> None:
    with pytest.raises(harness.HarnessError, match="set --live"):
        harness.validate_live_inputs(
            _live_environment(), live=False, publish_board=True
        )
    with pytest.raises(harness.HarnessError, match="--publish-board"):
        harness.validate_live_inputs(
            _live_environment(), live=True, publish_board=False
        )


def test_live_inputs_are_allowlisted_and_normalized() -> None:
    inputs = harness.validate_live_inputs(
        _live_environment(), live=True, publish_board=True
    )
    assert inputs.mutex_endpoint == "https://mutex.example.test/prod"
    assert inputs.docker_environment()[harness.MUTEX_TOKEN] == "mutex-secret"
    assert set(inputs.docker_environment()) == {
        harness.MUTEX_ENDPOINT,
        harness.MUTEX_TOKEN,
        harness.MQTT_BROKER,
        harness.MQTT_AUTHORIZER,
        harness.MQTT_TOKEN,
        harness.CODEX_API_KEY,
        "KANBUS_REALTIME_TRANSPORT",
        "KANBUS_REALTIME_AUTOSTART",
        "KANBUS_REALTIME_KEEPALIVE",
    }


def test_docker_command_uses_barrier_and_never_puts_secrets_in_argv(
    tmp_path: Path,
) -> None:
    inputs = harness.validate_live_inputs(
        _live_environment(), live=True, publish_board=True
    )
    command = harness._container_command(
        name="worker-test",
        worker_root=tmp_path / "worker",
        remote=tmp_path / "board.git",
        image="kanbus-test",
        runtime="python",
        live=inputs,
        barrier_directory=tmp_path / "barrier",
    )
    assert any("while [ ! -f /harness-control/start ]" in arg for arg in command)
    assert any("cp -a /workspace-source/. /workspace/" in arg for arg in command)
    assert any("target=/workspace-source,readonly" in arg for arg in command)
    assert harness.MUTEX_TOKEN in command
    assert harness.CODEX_API_KEY in command
    assert "mutex-secret" not in command
    assert "mqtt-secret" not in command
    assert "openai-secret" not in command


def test_container_launcher_maps_openai_key_to_codex_environment_name() -> None:
    inputs = harness.validate_live_inputs(
        _live_environment(), live=True, publish_board=True
    )
    host_environment = {"PATH": "/usr/bin", harness.OPENAI_KEY: "openai-secret"}
    launcher_environment = harness._container_launcher_environment(
        host_environment, inputs
    )
    assert launcher_environment[harness.CODEX_API_KEY] == "openai-secret"
    assert harness.CODEX_API_KEY not in host_environment
    assert launcher_environment[harness.OPENAI_KEY] == "openai-secret"


@pytest.mark.parametrize(
    "environment, expected",
    [
        ({harness.MQTT_BROKER: "mqtt://broker.example.test"}, harness.MQTT_BROKER),
        ({harness.MUTEX_ENDPOINT: "http://mutex.example.test"}, harness.MUTEX_ENDPOINT),
    ],
)
def test_live_input_schemes_are_validated(
    environment: dict[str, str], expected: str
) -> None:
    with pytest.raises(harness.HarnessError, match=expected):
        harness.validate_live_inputs(
            _live_environment() | environment, live=True, publish_board=True
        )


def test_test_epic_is_created_only_when_missing() -> None:
    assert harness.validate_test_epic(None) == "create"
    assert (
        harness.validate_test_epic(
            {
                "id": harness.TEST_EPIC_ID,
                "type": "epic",
                "title": harness.TEST_EPIC_TITLE,
            }
        )
        == "reuse"
    )


def test_worker_mirror_is_pinned_to_develop_not_remote_default(tmp_path: Path) -> None:
    command = harness._bare_remote_clone_command(
        "git@github.com:AnthusAI/Kanbus.git", tmp_path / "board.git"
    )
    assert command == [
        "git",
        "clone",
        "--bare",
        "--single-branch",
        "--branch",
        "develop",
        "git@github.com:AnthusAI/Kanbus.git",
        str(tmp_path / "board.git"),
    ]


def test_worker_config_disables_github_forge(tmp_path: Path) -> None:
    config = tmp_path / ".kanbus.yml"
    config.write_text(
        "project_directory: project\nrouter:\n  forge:\n    provider: github\n"
        "  providers:\n    codex-luna-flex:\n      args: [--model, gpt-5.6-luna, -c, 'service_tier=flex']\n"
        "    repository: example/project\n  limits:\n    class_wip:\n"
        "      implementation: 1\n  classes:\n    implementation:\n"
        "      providers: [codex-luna-flex]\n",
        encoding="utf-8",
    )
    harness._configure_worker_for_test(tmp_path, "router-container-it-test")
    loaded = harness.yaml.safe_load(config.read_text(encoding="utf-8"))
    assert loaded["router"]["forge"] is None
    assert loaded["project_directory"] == "project"
    assert loaded["router"]["classes"]["router-container-it-test"] == {
        "providers": ["codex-luna-flex"]
    }
    assert loaded["router"]["providers"]["codex-luna-flex"]["args"][-3:] == [
        "--dangerously-bypass-approvals-and-sandbox",
        "-c",
        "model_catalog_json=/opt/kanbus/codex-models.json",
    ]
    assert loaded["router"]["classes"] == {
        "router-container-it-test": {"providers": ["codex-luna-flex"]}
    }
    assert loaded["router"]["limits"]["class_wip"]["router-container-it-test"] == 1
    assert loaded["router"]["limits"]["class_wip"] == {"router-container-it-test": 1}


@pytest.mark.parametrize(
    "issue",
    [
        {"id": "different-id", "type": "epic", "title": harness.TEST_EPIC_TITLE},
        {"id": harness.TEST_EPIC_ID, "type": "task", "title": harness.TEST_EPIC_TITLE},
        {"id": harness.TEST_EPIC_ID, "type": "epic", "title": "Other epic"},
    ],
)
def test_test_epic_id_collision_is_fatal(issue: dict[str, str]) -> None:
    with pytest.raises(harness.HarnessError):
        harness.validate_test_epic(issue)


def test_start_assertion_requires_one_successful_runtime() -> None:
    loser = harness.WorkerResult(
        "python", Path("python"), harness.ProcessResult(0, "started=0", "")
    )
    winner = harness.WorkerResult(
        "rust", Path("rust"), harness.ProcessResult(0, "started=1", "")
    )
    assert harness.assert_single_router_start([loser, winner]) is winner
    rust_loser = harness.WorkerResult(
        "rust", Path("rust"), harness.ProcessResult(0, "started=0", "")
    )
    with pytest.raises(harness.HarnessError, match="got 0"):
        harness.assert_single_router_start([loser, rust_loser])
    with pytest.raises(harness.HarnessError, match="exactly one Python and one Rust"):
        harness.assert_single_router_start([winner, winner])


def test_loser_may_report_hard_lease_contention_but_not_other_errors() -> None:
    winner = harness.WorkerResult(
        "rust", Path("rust"), harness.ProcessResult(0, "started=1", "")
    )
    contended = harness.WorkerResult(
        "python",
        Path("python"),
        harness.ProcessResult(1, "started=0", "error: package already claimed"),
    )
    assert harness.assert_single_router_start([contended, winner]) is winner
    broken = harness.WorkerResult(
        "python", Path("python"), harness.ProcessResult(1, "started=0", "error: boom")
    )
    with pytest.raises(harness.HarnessError, match="failed unexpectedly"):
        harness.assert_single_router_start([broken, winner])


def test_task_result_requires_review_and_router_comment() -> None:
    issue = {
        "status": "review",
        "comments": [
            {
                "author": "Kanbus Issue Router",
                "text": "KANBUS-ROUTER-TEST:abc Lorem ipsum dolor sit amet.\n\n"
                "Second paragraph.\n\nThird paragraph.",
            }
        ],
    }
    harness.assert_task_result(issue, "KANBUS-ROUTER-TEST:abc")
    with pytest.raises(harness.HarnessError, match="in review"):
        harness.assert_task_result({"status": "open", "comments": []}, "marker")
    with pytest.raises(harness.HarnessError, match="three paragraphs"):
        harness.assert_task_result(
            {
                "status": "review",
                "comments": [{"author": "Kanbus Issue Router", "text": "marker only"}],
            },
            "marker",
        )
    with pytest.raises(harness.HarnessError, match="Lorem ipsum"):
        harness.assert_task_result(
            {
                "status": "review",
                "comments": [
                    {
                        "author": "Kanbus Issue Router",
                        "text": "marker one\n\ntwo\n\nthree",
                    }
                ],
            },
            "marker",
        )


def test_loser_must_not_publish_result() -> None:
    harness.assert_loser_untouched({"status": "open", "comments": []}, "marker")
    with pytest.raises(harness.HarnessError, match="independently mutated"):
        harness.assert_loser_untouched(
            {
                "status": "open",
                "comments": [{"text": "result marker"}],
            },
            "marker",
        )


def test_redaction_removes_secret_values() -> None:
    assert (
        harness.redact(
            "token=abc and Authorization: Bearer xyz",
            {harness.MQTT_TOKEN: "abc", "OTHER": "xyz"},
        )
        == "token=<redacted> and Authorization: Bearer <redacted>"
    )


def test_fake_agent_validation_skips_openai_key() -> None:
    env = {
        harness.LIVE_GATE: "1",
        harness.MUTEX_ENDPOINT: "https://mutex.example.test/prod",
        harness.MUTEX_TOKEN: "mutex-secret",
        harness.MQTT_BROKER: "mqtts://broker.example.test:8883",
        harness.MQTT_AUTHORIZER: "kanbus-mqtt-token-test",
        harness.MQTT_TOKEN: "mqtt-secret",
    }
    inputs = harness.validate_live_inputs(
        env, live=True, publish_board=True, fake_agent=True
    )
    assert inputs.openai_key == ""


def test_real_agent_validation_requires_openai_key() -> None:
    env = {
        harness.LIVE_GATE: "1",
        harness.MUTEX_ENDPOINT: "https://mutex.example.test/prod",
        harness.MUTEX_TOKEN: "mutex-secret",
        harness.MQTT_BROKER: "mqtts://broker.example.test:8883",
        harness.MQTT_AUTHORIZER: "kanbus-mqtt-token-test",
        harness.MQTT_TOKEN: "mqtt-secret",
    }
    with pytest.raises(harness.HarnessError, match="missing live inputs"):
        harness.validate_live_inputs(
            env, live=True, publish_board=True, fake_agent=False
        )


def test_docker_environment_omits_codex_key_when_empty() -> None:
    env = {
        harness.LIVE_GATE: "1",
        harness.MUTEX_ENDPOINT: "https://mutex.example.test/prod",
        harness.MUTEX_TOKEN: "mutex-secret",
        harness.MQTT_BROKER: "mqtts://broker.example.test:8883",
        harness.MQTT_AUTHORIZER: "kanbus-mqtt-token-test",
        harness.MQTT_TOKEN: "mqtt-secret",
    }
    inputs = harness.validate_live_inputs(
        env, live=True, publish_board=True, fake_agent=True
    )
    docker_env = inputs.docker_environment()
    assert harness.CODEX_API_KEY not in docker_env
    assert docker_env[harness.MUTEX_TOKEN] == "mutex-secret"


def test_container_command_mounts_fake_codex_when_enabled(tmp_path: Path) -> None:
    fake_agent_env = {
        harness.LIVE_GATE: "1",
        harness.MUTEX_ENDPOINT: "https://mutex.example.test/prod",
        harness.MUTEX_TOKEN: "mutex-secret",
        harness.MQTT_BROKER: "mqtts://broker.example.test:8883",
        harness.MQTT_AUTHORIZER: "kanbus-mqtt-token-test",
        harness.MQTT_TOKEN: "mqtt-secret",
    }
    inputs = harness.validate_live_inputs(
        fake_agent_env, live=True, publish_board=True, fake_agent=True
    )
    command = harness._container_command(
        name="worker-test",
        worker_root=tmp_path / "worker",
        remote=tmp_path / "board.git",
        image="kanbus-test",
        runtime="python",
        live=inputs,
        barrier_directory=tmp_path / "barrier",
        fake_agent=True,
        fake_agent_mode="hang",
    )
    command_str = " ".join(command)
    assert "/opt/fake-codex/codex" in command_str
    assert "FAKE_CODEX_MODE=hang" in command_str
    assert harness.CODEX_API_KEY not in command


def test_container_command_without_fake_agent_has_no_fake_mount(tmp_path: Path) -> None:
    inputs = harness.validate_live_inputs(
        _live_environment(), live=True, publish_board=True
    )
    command = harness._container_command(
        name="worker-test",
        worker_root=tmp_path / "worker",
        remote=tmp_path / "board.git",
        image="kanbus-test",
        runtime="python",
        live=inputs,
        barrier_directory=tmp_path / "barrier",
        fake_agent=False,
    )
    command_str = " ".join(command)
    assert "/opt/fake-codex/codex" not in command_str
    assert "FAKE_CODEX_MODE" not in command_str


def test_worker_config_with_fake_agent_sets_codex_path(tmp_path: Path) -> None:
    config = tmp_path / ".kanbus.yml"
    config.write_text(
        "project_directory: project\nrouter:\n  forge:\n    provider: github\n"
        "  providers:\n    codex-luna-flex:\n      args: [--model, gpt-5.6-luna, -c, 'service_tier=flex']\n"
        "    repository: example/project\n  limits:\n    class_wip:\n"
        "      implementation: 1\n  classes:\n    implementation:\n"
        "      providers: [codex-luna-flex]\n",
        encoding="utf-8",
    )
    harness._configure_worker_for_test(
        tmp_path, "router-container-it-test", fake_agent=True
    )
    loaded = harness.yaml.safe_load(config.read_text(encoding="utf-8"))
    assert (
        loaded["router"]["providers"]["codex-luna-flex"]["command"]
        == "/opt/fake-codex/codex"
    )


FAKE_CODEX = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "issue_router_container"
    / "fake_codex.py"
)
FAKE_ISSUE_ID = "kbs-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
FAKE_MARKER = "KANBUS-ROUTER-TEST:abc123def456"


def _fake_codex_environment(tmp_path: Path, mode: str) -> dict[str, str]:
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    stub = bin_directory / "kbs"
    stub.write_text(
        f"#!/bin/sh\necho 'ID: {FAKE_ISSUE_ID}'\necho '{FAKE_MARKER} disposable'\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{bin_directory}{os.pathsep}{os.environ['PATH']}",
        "FAKE_CODEX_MODE": mode,
    }


def test_fake_codex_result_is_accepted_by_the_router_parser(tmp_path: Path) -> None:
    from kanbus import router_adapters

    completed = subprocess.run(
        [
            sys.executable,
            str(FAKE_CODEX),
            "exec",
            "--json",
            f"Complete Kanbus package {FAKE_ISSUE_ID}. Only update: {FAKE_ISSUE_ID}.",
        ],
        capture_output=True,
        text=True,
        env=_fake_codex_environment(tmp_path, "complete"),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    first_line = json.loads(completed.stdout.splitlines()[0])
    assert first_line["type"] == "thread.started"
    result = router_adapters.RouterAgentResult.model_validate(
        router_adapters._find_result_payload(completed.stdout)
    )
    assert result.outcome == "completed"
    assert [comment.issue_id for comment in result.issue_comments] == [FAKE_ISSUE_ID]
    text = result.issue_comments[0].text
    paragraphs = [part for part in text.split("\n\n") if part.strip()]
    assert len(paragraphs) == 3
    assert text.startswith(FAKE_MARKER)
    assert "lorem ipsum" in text.casefold()


def test_fake_codex_hang_mode_reports_a_thread_and_keeps_running(
    tmp_path: Path,
) -> None:
    process = subprocess.Popen(
        [sys.executable, str(FAKE_CODEX), "exec", "--json", "prompt"],
        stdout=subprocess.PIPE,
        text=True,
        env=_fake_codex_environment(tmp_path, "hang"),
    )
    try:
        assert process.stdout is not None
        first_line = json.loads(process.stdout.readline())
        assert first_line["type"] == "thread.started"
        time.sleep(1)
        assert process.poll() is None
    finally:
        process.kill()
        process.wait(timeout=5)


def test_worker_config_with_soft_coordination_sets_git_provider(tmp_path: Path) -> None:
    config = tmp_path / ".kanbus.yml"
    config.write_text(
        "project_directory: project\nrouter:\n  forge:\n    provider: github\n"
        "  providers:\n    codex-luna-flex:\n      args: [--model, gpt-5.6-luna]\n"
        "  limits:\n    class_wip:\n      implementation: 1\n"
        "  classes:\n    implementation:\n      providers: [codex-luna-flex]\n",
        encoding="utf-8",
    )
    harness._configure_worker_for_test(
        tmp_path, "router-container-it-test", soft_coordination=True
    )
    loaded = harness.yaml.safe_load(config.read_text(encoding="utf-8"))
    assert loaded["coordination"]["providers"] == ["git"]


def test_worker_config_with_lease_ttl_sets_coordination_ttl(tmp_path: Path) -> None:
    config = tmp_path / ".kanbus.yml"
    config.write_text(
        "project_directory: project\nrouter:\n  forge:\n    provider: github\n"
        "  providers:\n    codex-luna-flex:\n      args: [--model, gpt-5.6-luna]\n"
        "  limits:\n    class_wip:\n      implementation: 1\n"
        "  classes:\n    implementation:\n      providers: [codex-luna-flex]\n",
        encoding="utf-8",
    )
    harness._configure_worker_for_test(
        tmp_path, "router-container-it-test", lease_ttl="5s"
    )
    loaded = harness.yaml.safe_load(config.read_text(encoding="utf-8"))
    assert loaded["coordination"]["default_lease_ttl"] == "5s"


def test_soft_duplicate_permitted_accepts_one_start() -> None:
    loser = harness.WorkerResult(
        "python", Path("python"), harness.ProcessResult(0, "started=0", "")
    )
    winner = harness.WorkerResult(
        "rust", Path("rust"), harness.ProcessResult(0, "started=1", "")
    )
    total = harness.assert_soft_duplicate_permitted([loser, winner])
    assert total == 1


def test_soft_duplicate_permitted_accepts_two_starts() -> None:
    py_start = harness.WorkerResult(
        "python", Path("python"), harness.ProcessResult(0, "started=1", "")
    )
    rs_start = harness.WorkerResult(
        "rust", Path("rust"), harness.ProcessResult(0, "started=1", "")
    )
    total = harness.assert_soft_duplicate_permitted([py_start, rs_start])
    assert total == 2


def test_soft_duplicate_permitted_rejects_zero_starts() -> None:
    no_start = [
        harness.WorkerResult(
            "python", Path("python"), harness.ProcessResult(0, "started=0", "")
        ),
        harness.WorkerResult(
            "rust", Path("rust"), harness.ProcessResult(0, "started=0", "")
        ),
    ]
    with pytest.raises(harness.HarnessError, match="at least one worker to start"):
        harness.assert_soft_duplicate_permitted(no_start)


def test_soft_duplicate_permitted_rejects_non_zero_exit() -> None:
    failed = harness.WorkerResult(
        "python", Path("python"), harness.ProcessResult(1, "started=0", "error")
    )
    winner = harness.WorkerResult(
        "rust", Path("rust"), harness.ProcessResult(0, "started=1", "")
    )
    with pytest.raises(harness.HarnessError, match="failed"):
        harness.assert_soft_duplicate_permitted([failed, winner])


def test_interrupted_worker_accepts_in_progress_and_non_zero_exit() -> None:
    worker = harness.WorkerResult(
        "python", Path("python"), harness.ProcessResult(137, "", "")
    )
    issue = {"status": "in_progress", "comments": []}
    harness.assert_interrupted_worker(worker, issue)


def test_interrupted_worker_rejects_review_status() -> None:
    worker = harness.WorkerResult(
        "python", Path("python"), harness.ProcessResult(137, "", "")
    )
    issue = {"status": "review", "comments": []}
    with pytest.raises(harness.HarnessError, match="should not publish review"):
        harness.assert_interrupted_worker(worker, issue)


def test_interrupted_worker_rejects_zero_exit() -> None:
    worker = harness.WorkerResult(
        "python", Path("python"), harness.ProcessResult(0, "", "")
    )
    issue = {"status": "in_progress", "comments": []}
    with pytest.raises(harness.HarnessError, match="non-zero exit"):
        harness.assert_interrupted_worker(worker, issue)


def test_takeover_accepts_one_start_with_valid_result() -> None:
    worker = harness.WorkerResult(
        "rust", Path("rust"), harness.ProcessResult(0, "started=1", "")
    )
    issue = {
        "status": "review",
        "comments": [
            {
                "author": "Kanbus Issue Router",
                "text": "KANBUS-ROUTER-TEST:abc Lorem ipsum dolor sit amet.\n\n"
                "Second paragraph.\n\nThird paragraph.",
            }
        ],
    }
    harness.assert_takeover(worker, issue, "KANBUS-ROUTER-TEST:abc")


def test_takeover_rejects_zero_starts() -> None:
    worker = harness.WorkerResult(
        "rust", Path("rust"), harness.ProcessResult(0, "started=0", "")
    )
    issue = {"status": "review", "comments": []}
    with pytest.raises(harness.HarnessError, match="started=0"):
        harness.assert_takeover(worker, issue, "marker")


def test_takeover_rejects_non_zero_exit() -> None:
    worker = harness.WorkerResult(
        "rust", Path("rust"), harness.ProcessResult(1, "started=1", "error")
    )
    issue = {"status": "review", "comments": []}
    with pytest.raises(harness.HarnessError, match="failed"):
        harness.assert_takeover(worker, issue, "marker")


def test_run_harness_rejects_invalid_scenario() -> None:
    with pytest.raises(harness.HarnessError, match="invalid scenario"):
        harness.run_harness(
            repo_root=Path("."),
            live=True,
            publish_board=True,
            keep=False,
            timeout=1.0,
            image="test",
            fake_agent=True,
            scenario="bogus",
        )


def test_run_harness_soft_duplicate_requires_fake_agent() -> None:
    with pytest.raises(harness.HarnessError, match="requires --fake-agent"):
        harness.run_harness(
            repo_root=Path("."),
            live=True,
            publish_board=True,
            keep=False,
            timeout=1.0,
            image="test",
            fake_agent=False,
            scenario="soft-duplicate",
        )


def test_run_harness_expiry_takeover_requires_fake_agent() -> None:
    with pytest.raises(harness.HarnessError, match="requires --fake-agent"):
        harness.run_harness(
            repo_root=Path("."),
            live=True,
            publish_board=True,
            keep=False,
            timeout=1.0,
            image="test",
            fake_agent=False,
            scenario="expiry-takeover",
        )


def test_worker_config_defaults_to_hard_mutex_coordination(tmp_path: Path) -> None:
    config = tmp_path / ".kanbus.yml"
    config.write_text(
        "project_directory: project\ncoordination:\n  providers: [git]\nrouter:\n"
        "  providers:\n    codex-luna-flex:\n      args: [--model, gpt-5.6-luna]\n"
        "  limits:\n    class_wip:\n      implementation: 1\n  classes:\n"
        "    implementation:\n      providers: [codex-luna-flex]\n",
        encoding="utf-8",
    )
    harness._configure_worker_for_test(tmp_path, "router-container-it-test")
    loaded = harness.yaml.safe_load(config.read_text(encoding="utf-8"))
    assert loaded["coordination"]["providers"] == ["mutex_api", "mqtt", "git"]


def test_reported_issue_identifier_resolves_to_the_stored_full_identifier(
    tmp_path: Path,
) -> None:
    (tmp_path / ".kanbus.yml").write_text("project_directory: project\n")
    issues = tmp_path / "project" / "issues"
    issues.mkdir(parents=True)
    full = "kbs-db23027c-cea8-4f9c-827e-795b4fd6a2e9"
    (issues / f"{full}.json").write_text("{}")
    assert harness._full_issue_identifier(tmp_path, "kbs-db2302") == full
    with pytest.raises(harness.HarnessError, match="found 0"):
        harness._full_issue_identifier(tmp_path, "kbs-ffffff")


def _bare_state_repository(tmp_path: Path, events: dict[str, dict]) -> Path:
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "kanbus/router-state", str(work)])
    (work / "project" / "events").mkdir(parents=True)
    for name, event in events.items():
        (work / "project" / "events" / name).write_text(json.dumps(event))
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "-C", str(work), "add", "-A"])
    subprocess.run(["git", "-C", str(work), *identity, "commit", "-q", "-m", "x"])
    bare = tmp_path / "state.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)])
    return bare


def test_start_event_detection_requires_a_started_attempt(tmp_path: Path) -> None:
    issue = "kbs-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
    claim = {"event_type": "coordination.claim", "issue_id": issue, "payload": {}}
    started = {
        "event_type": "router.attempt",
        "issue_id": f"router:{issue}",
        "payload": {"action": "started"},
    }
    only_claim = _bare_state_repository(tmp_path / "a", {"1.json": claim})
    assert harness._start_event_published(only_claim, issue) is False
    with_start = _bare_state_repository(
        tmp_path / "b", {"1.json": claim, "2.json": started}
    )
    assert harness._start_event_published(with_start, issue) is True
    assert harness._start_event_published(with_start, "kbs-other") is False
