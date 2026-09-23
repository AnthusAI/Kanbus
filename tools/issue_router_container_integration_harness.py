"""Run a board-backed Issue Router race in isolated Docker workers.

This is an opt-in live test. It creates a uniquely named, harmless routed task
under the fixed Issue Router Testing epic, publishes that task to ``develop``,
then races Python and Rust router containers against a disposable bare Git
mirror. The containers share the mirror and live coordination services, but
never share a checkout or UDS socket.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import yaml

LIVE_GATE = "KANBUS_RUN_LIVE_ROUTER_CONTAINER_HARNESS"
MUTEX_ENDPOINT = "KANBUS_COORDINATION_MUTEX_API_ENDPOINT"
MUTEX_TOKEN = "KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN"
MQTT_BROKER = "KANBUS_REALTIME_BROKER"
MQTT_AUTHORIZER = "KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME"
MQTT_TOKEN = "KANBUS_REALTIME_MQTT_API_TOKEN"
OPENAI_KEY = "OPENAI_API_KEY"
CODEX_API_KEY = "CODEX_API_KEY"
TEST_EPIC_ID = "kbs-d3973c07-13a1-4598-8f32-85e010278121"
TEST_EPIC_TITLE = "Issue Router Testing"
TEST_EPIC_DESCRIPTION = (
    "Validate safe dispatch of real Kanbus board issues through isolated Issue "
    "Router workers. Test tasks under this epic are disposable and must not "
    "modify unrelated issues or source files."
)
TEST_AGENT_CLASS_PREFIX = "router-container-it-"
TEST_IMAGE = "kanbus-issue-router-integration:codex-0.149.0"
DEFAULT_BRANCH = "develop"
STATE_BRANCH = "kanbus/router-state"
ISSUE_ID_RE = re.compile(r"(?m)^\s*ID:\s+([A-Za-z0-9][A-Za-z0-9_-]*)\s*$")
STARTED_RE = re.compile(r"(?:^|\s)started=(\d+)(?:\s|$)")
SECRET_NAME_RE = re.compile(
    r"token|secret|password|credential|authorization|private[_-]?key|api[_-]?key",
    re.IGNORECASE,
)
EXPIRY_TTL = "5s"
EXPIRY_WAIT_SECONDS = 15.0
VALID_SCENARIOS = {"hard-race", "soft-duplicate", "expiry-takeover"}


class HarnessError(RuntimeError):
    """An invalid input, unsafe state, or failed integration assertion."""


@dataclass(frozen=True)
class LiveInputs:
    """Allowlisted credentials required by the router containers."""

    mutex_endpoint: str
    mutex_token: str
    mqtt_broker: str
    mqtt_authorizer: str
    mqtt_token: str
    openai_key: str

    def docker_environment(self) -> dict[str, str]:
        """Return only the service inputs required inside a worker container."""
        environment = {
            MUTEX_ENDPOINT: self.mutex_endpoint,
            MUTEX_TOKEN: self.mutex_token,
            MQTT_BROKER: self.mqtt_broker,
            MQTT_AUTHORIZER: self.mqtt_authorizer,
            MQTT_TOKEN: self.mqtt_token,
            "KANBUS_REALTIME_TRANSPORT": "mqtt",
            "KANBUS_REALTIME_AUTOSTART": "false",
            "KANBUS_REALTIME_KEEPALIVE": "false",
        }
        if self.openai_key:
            environment[CODEX_API_KEY] = self.openai_key
        return environment


@dataclass(frozen=True)
class ProcessResult:
    """Redacted stdout and stderr from a bounded process invocation."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class WorkerResult:
    """One isolated container's runtime and captured execution result."""

    name: str
    issue_root: Path
    result: ProcessResult


def validate_live_inputs(
    env: Mapping[str, str], *, live: bool, publish_board: bool, fake_agent: bool = False
) -> LiveInputs:
    """Validate explicit mutation gates and all live credentials before setup.

    :param env: Environment supplied to the harness.
    :param live: Whether the caller explicitly requested live services.
    :param publish_board: Whether the caller explicitly authorized board pushes.
    :param fake_agent: Whether to use a deterministic fake Codex worker.
    :return: Complete allowlisted service credentials.
    :raises HarnessError: If any gate or required service input is missing.
    """
    if not live or env.get(LIVE_GATE) != "1":
        raise HarnessError(f"set --live and {LIVE_GATE}=1 to enable the live suite")
    if not publish_board:
        raise HarnessError(
            "--publish-board is required before the suite mutates develop"
        )
    values = {
        MUTEX_ENDPOINT: env.get(MUTEX_ENDPOINT, "").strip(),
        MUTEX_TOKEN: env.get(MUTEX_TOKEN, "").strip(),
        MQTT_BROKER: env.get(MQTT_BROKER, "").strip(),
        MQTT_AUTHORIZER: env.get(MQTT_AUTHORIZER, "").strip(),
        MQTT_TOKEN: env.get(MQTT_TOKEN, "").strip(),
        OPENAI_KEY: env.get(OPENAI_KEY, "").strip(),
    }
    required_keys = {
        MUTEX_ENDPOINT,
        MUTEX_TOKEN,
        MQTT_BROKER,
        MQTT_AUTHORIZER,
        MQTT_TOKEN,
    }
    if not fake_agent:
        required_keys.add(OPENAI_KEY)
    missing = [name for name in required_keys if not values[name]]
    if missing:
        raise HarnessError("missing live inputs: " + ", ".join(missing))
    if not re.fullmatch(r"https://[^\s/]+(?:/[^\s]*)?", values[MUTEX_ENDPOINT]):
        raise HarnessError(f"{MUTEX_ENDPOINT} must be an absolute https URL")
    if not re.fullmatch(r"mqtts://[^\s/]+(?::\d+)?(?:/[^\s]*)?", values[MQTT_BROKER]):
        raise HarnessError(f"{MQTT_BROKER} must be an absolute mqtts URL")
    return LiveInputs(
        mutex_endpoint=values[MUTEX_ENDPOINT].rstrip("/"),
        mutex_token=values[MUTEX_TOKEN],
        mqtt_broker=values[MQTT_BROKER],
        mqtt_authorizer=values[MQTT_AUTHORIZER],
        mqtt_token=values[MQTT_TOKEN],
        openai_key=values[OPENAI_KEY],
    )


def validate_test_epic(issue: object | None) -> str:
    """Return ``reuse``/``create`` or reject a fixed-ID collision.

    :param issue: Parsed issue JSON for the fixed test epic, or ``None``.
    :return: The required setup action.
    :raises HarnessError: If the fixed ID belongs to a different issue.
    """
    if issue is None:
        return "create"
    if not isinstance(issue, dict):
        raise HarnessError("fixed test epic record is not a JSON object")
    if issue.get("id") != TEST_EPIC_ID:
        raise HarnessError("fixed test epic record has a mismatched ID")
    if issue.get("type") != "epic" or issue.get("title") != TEST_EPIC_TITLE:
        raise HarnessError(
            f"{TEST_EPIC_ID} exists but is not the expected Issue Router Testing epic"
        )
    return "reuse"


def assert_single_router_start(results: Sequence[WorkerResult]) -> WorkerResult:
    """Require exactly one Python/Rust worker to start the real test task.

    :param results: Completed worker invocations.
    :return: The sole winner's result.
    :raises HarnessError: If zero, multiple, or failed starts are observed.
    """
    if len(results) != 2 or {worker.name for worker in results} != {"python", "rust"}:
        raise HarnessError("race must include exactly one Python and one Rust worker")
    started: list[WorkerResult] = []
    for worker in results:
        matches = STARTED_RE.findall(worker.result.stdout)
        count = int(matches[-1]) if matches else 0
        if count == 1:
            started.append(worker)
        elif count != 0:
            raise HarnessError(f"{worker.name} reported unexpected started={count}")
    if len(started) != 1:
        detail = "\n".join(
            f"{worker.name}: exit={worker.result.returncode}\n"
            f"stdout: {worker.result.stdout}\nstderr: {worker.result.stderr}"
            for worker in results
        )
        raise HarnessError(
            f"hard lease race expected exactly one start, got {len(started)}\n{detail}"
        )
    winner = started[0]
    if winner.result.returncode != 0:
        raise HarnessError(
            f"winning worker {winner.name} failed:\n"
            f"{winner.result.stdout}\n{winner.result.stderr}"
        )
    for worker in results:
        if worker is not winner and worker.result.returncode != 0:
            raise HarnessError(
                f"losing worker {worker.name} failed unexpectedly:\n"
                f"{worker.result.stdout}\n{worker.result.stderr}"
            )
    return winner


def assert_task_result(issue: object, marker: str) -> None:
    """Require the router to publish the marker comment and review status.

    :param issue: Parsed task issue JSON from the winning worker checkout.
    :param marker: Unique text required in the router-authored comment.
    :raises HarnessError: If the task result is missing or out of contract.
    """
    if not isinstance(issue, dict) or issue.get("status") != "review":
        status = issue.get("status") if isinstance(issue, dict) else None
        raise HarnessError(f"routed test issue should be in review, got {status!r}")
    comments = issue.get("comments")
    texts = (
        [
            comment["text"]
            for comment in comments or []
            if isinstance(comment, dict)
            and comment.get("author") == "Kanbus Issue Router"
            and isinstance(comment.get("text"), str)
            and marker in comment["text"]
        ]
        if isinstance(comments, list)
        else []
    )
    if len(texts) != 1:
        raise HarnessError("router did not publish the unique test comment")
    paragraphs = [
        part.strip() for part in re.split(r"\n\s*\n", texts[0]) if part.strip()
    ]
    if len(paragraphs) != 3:
        raise HarnessError(
            f"router comment should contain three paragraphs, got {len(paragraphs)}"
        )
    if "lorem ipsum" not in texts[0].casefold():
        raise HarnessError("router comment does not contain Lorem ipsum text")


def assert_loser_untouched(issue: object, marker: str) -> None:
    """Require the losing checkout not to independently publish the result."""
    if not isinstance(issue, dict):
        raise HarnessError("losing worker issue record is invalid")
    comments = issue.get("comments")
    if issue.get("status") == "review" or (
        isinstance(comments, list)
        and any(
            isinstance(comment, dict)
            and isinstance(comment.get("text"), str)
            and marker in comment["text"]
            for comment in comments
        )
    ):
        raise HarnessError("losing worker independently mutated the test issue")


def assert_soft_duplicate_permitted(results: Sequence[WorkerResult]) -> int:
    """Permit zero, one, or two starts in soft coordination mode.

    Soft coordination allows documented duplicate starts. This assertion
    ensures exactly one Python and one Rust worker participated, each
    either did not start (started=0) or started exactly once (started=1),
    all returned successfully, and the total count is 1 or 2.

    :param results: Completed worker invocations.
    :return: Total number of starts (1 or 2).
    :raises HarnessError: If the result violates the contract.
    """
    if len(results) != 2 or {worker.name for worker in results} != {"python", "rust"}:
        raise HarnessError("race must include exactly one Python and one Rust worker")
    starts: list[int] = []
    for worker in results:
        if worker.result.returncode != 0:
            raise HarnessError(
                f"soft-duplicate worker {worker.name} failed (exit={worker.result.returncode})"
            )
        matches = STARTED_RE.findall(worker.result.stdout)
        count = int(matches[-1]) if matches else 0
        if count not in (0, 1):
            raise HarnessError(f"{worker.name} reported unexpected started={count}")
        starts.append(count)
    total = sum(starts)
    if total == 0:
        raise HarnessError(
            "soft-duplicate scenario requires at least one worker to start"
        )
    return total


def assert_interrupted_worker(worker: WorkerResult, issue: object) -> None:
    """Require a killed worker to have left the issue in progress, not review.

    :param worker: Killed worker result.
    :param issue: Issue state in the worker's checkout.
    :raises HarnessError: If the worker exited cleanly or mutated the issue.
    """
    if worker.result.returncode == 0:
        raise HarnessError("interrupted worker should have non-zero exit code, got 0")
    if not isinstance(issue, dict):
        raise HarnessError("interrupted worker issue record is invalid")
    if issue.get("status") == "review":
        raise HarnessError("killed worker should not publish review status")


def assert_takeover(worker: WorkerResult, issue: object, marker: str) -> None:
    """Require the takeover worker to have started and completed the task.

    :param worker: The second worker that took over after lease expiry.
    :param issue: Issue state from the router-state commit.
    :param marker: Unique test comment marker.
    :raises HarnessError: If the takeover did not succeed.
    """
    matches = STARTED_RE.findall(worker.result.stdout)
    count = int(matches[-1]) if matches else 0
    if count != 1:
        raise HarnessError(
            f"takeover worker must start exactly once, got started={count}"
        )
    if worker.result.returncode != 0:
        raise HarnessError(f"takeover worker failed (exit={worker.result.returncode})")
    assert_task_result(issue, marker)


def redact(text: str, env: Mapping[str, str]) -> str:
    """Redact secret-valued environment entries and bearer-token text."""
    secrets = {
        value for name, value in env.items() if value and SECRET_NAME_RE.search(name)
    }
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    return re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s,]+",
        r"\1<redacted>",
        text,
    )


def _run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 60,
    check: bool = True,
    secrets: Mapping[str, str] | None = None,
) -> ProcessResult:
    try:
        completed = subprocess.run(
            list(args),
            cwd=cwd,
            env=None if env is None else dict(env),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HarnessError(f"command failed or timed out: {args[0]}") from error
    redact_env = dict(env or {})
    redact_env.update(secrets or {})
    result = ProcessResult(
        completed.returncode,
        redact(completed.stdout, redact_env),
        redact(completed.stderr, redact_env),
    )
    if check and result.returncode:
        raise HarnessError(
            f"command failed ({result.returncode}): {args[0]}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result


def _git(
    root: Path, *args: str, timeout: float = 60, check: bool = True, bare: bool = False
) -> str:
    prefix = ["git", "--git-dir", str(root)] if bare else ["git", "-C", str(root)]
    result = _run([*prefix, *args], timeout=timeout, check=check)
    return result.stdout.strip()


def _project_directory(root: Path) -> Path:
    config = root / ".kanbus.yml"
    match = re.search(
        r"(?m)^project_directory:\s*['\"]?([^\s'\"]+)['\"]?\s*$",
        config.read_text(encoding="utf-8"),
    )
    relative = Path(match.group(1)) if match else Path("project")
    if relative.is_absolute() or ".." in relative.parts:
        raise HarnessError("project_directory must stay inside the repository")
    return relative


def _configure_worker_for_test(
    root: Path,
    agent_class: str,
    fake_agent: bool = False,
    soft_coordination: bool = False,
    lease_ttl: str | None = None,
) -> None:
    """Isolate the task to these workers and prevent GitHub PR creation.

    :param root: Worker checkout directory.
    :param agent_class: Unique agent class identifier for this test.
    :param fake_agent: Whether to use a deterministic fake Codex worker.
    :param soft_coordination: Whether to disable Mutex API and use git coordination.
    :param lease_ttl: Optional lease TTL for coordination (e.g., "5s").
    """
    path = root / ".kanbus.yml"
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise HarnessError("could not load worker Kanbus configuration") from error
    if not isinstance(config, dict) or not isinstance(config.get("router"), dict):
        raise HarnessError("worker checkout has no router configuration")
    router = config["router"]
    implementation = router.get("classes", {}).get("implementation", {})
    providers = (
        implementation.get("providers") if isinstance(implementation, dict) else None
    )
    if (
        not isinstance(providers, list)
        or not providers
        or not isinstance(providers[0], str)
    ):
        raise HarnessError("worker checkout has no implementation provider profile")
    configured_providers = router.get("providers", {})
    provider_profile = (
        configured_providers.get(providers[0])
        if isinstance(configured_providers, dict)
        else None
    )
    provider_args = (
        provider_profile.get("args") if isinstance(provider_profile, dict) else None
    )
    if not isinstance(provider_args, list) or not all(
        isinstance(argument, str) for argument in provider_args
    ):
        raise HarnessError("worker provider profile has no argument list")
    if fake_agent and isinstance(provider_profile, dict):
        provider_profile["command"] = "/opt/fake-codex/codex"
    provider_args.extend(
        (
            "--dangerously-bypass-approvals-and-sandbox",
            "-c",
            "model_catalog_json=/opt/kanbus/codex-models.json",
        )
    )
    classes = router.setdefault("classes", {})
    limits = router.setdefault("limits", {})
    if not isinstance(classes, dict) or not isinstance(limits, dict):
        raise HarnessError("worker router classes and limits must be mappings")
    class_wip = limits.setdefault("class_wip", {})
    if not isinstance(class_wip, dict):
        raise HarnessError("worker router class_wip limit must be a mapping")
    classes.clear()
    class_wip.clear()
    classes[agent_class] = {"providers": [providers[0]]}
    class_wip[agent_class] = 1
    router["forge"] = None
    if soft_coordination:
        coordination = router.setdefault("coordination", {})
        if not isinstance(coordination, dict):
            raise HarnessError("worker router coordination must be a mapping")
        coordination["providers"] = ["git"]
    if lease_ttl is not None:
        coordination = router.setdefault("coordination", {})
        if not isinstance(coordination, dict):
            raise HarnessError("worker router coordination must be a mapping")
        coordination["default_lease_ttl"] = lease_ttl
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _identity_action(root: Path, kbs: Sequence[str]) -> str:
    issues = _project_directory(root) / "issues"
    path = root / issues / f"{TEST_EPIC_ID}.json"
    issue: object | None = None
    if path.exists():
        try:
            issue = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HarnessError("fixed test epic JSON cannot be read") from error
    action = validate_test_epic(issue)
    if action == "create":
        command = [
            *kbs,
            "create",
            TEST_EPIC_TITLE,
            "--type",
            "epic",
            "--priority",
            "1",
            "--id",
            TEST_EPIC_ID,
            "--description",
            TEST_EPIC_DESCRIPTION,
        ]
        _run(command, cwd=root)
    return action


def _set_test_git_identity(root: Path) -> None:
    """Configure a clearly synthetic author for generated test-task commits."""
    _git(root, "config", "user.name", "Kanbus Integration Harness")
    _git(root, "config", "user.email", "kanbus-integration@example.invalid")


def _bare_remote_clone_command(remote_url: str, remote: Path) -> list[str]:
    """Clone only develop, excluding production router-state refs."""
    return [
        "git",
        "clone",
        "--bare",
        "--single-branch",
        "--branch",
        DEFAULT_BRANCH,
        remote_url,
        str(remote),
    ]


def _create_test_issue(
    root: Path, kbs: Sequence[str], run_id: str, agent_class: str
) -> tuple[str, str]:
    marker = f"KANBUS-ROUTER-TEST:{run_id}"
    title = f"Router container smoke test {run_id}"
    description = (
        "Disposable live integration task. Generate exactly three short "
        "paragraphs of Lorem ipsum placeholder text. Post them as one issue "
        f"comment beginning with {marker} using the router result issue_comments "
        "field. Do not change source files or any other issue. Do not claim the "
        "integration suite passed; this task only proves that a real board issue "
        "was dispatched and its comment was published."
    )
    created = _run(
        [
            *kbs,
            "create",
            title,
            "--type",
            "task",
            "--priority",
            "2",
            "--parent",
            TEST_EPIC_ID,
            "--label",
            f"agent-class:{agent_class}",
            "--description",
            description,
        ],
        cwd=root,
    )
    match = ISSUE_ID_RE.search(created.stdout)
    if match is None:
        raise HarnessError("Kanbus did not report the new task ID")
    return match.group(1), marker


def _container_command(
    *,
    name: str,
    worker_root: Path,
    remote: Path,
    image: str,
    runtime: str,
    live: LiveInputs,
    barrier_directory: Path,
    fake_agent: bool = False,
    fake_agent_mode: str = "complete",
) -> list[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "bridge",
        "--mount",
        f"type=bind,source={worker_root.resolve()},target=/workspace-source,readonly",
        "--mount",
        f"type=bind,source={remote.resolve()},target=/kanbus-shared.git",
        "--mount",
        f"type=bind,source={barrier_directory.resolve()},target=/harness-control,readonly",
        "--workdir",
        "/workspace",
        "--env",
        "KANBUS_NO_DAEMON=1",
        "--env",
        f"KANBUS_REALTIME_UDS_SOCKET_PATH=/tmp/{name}.sock",
    ]
    if fake_agent:
        fake_codex_path = (
            Path(__file__).parent / "issue_router_container" / "fake_codex.py"
        )
        command.extend(
            (
                "--mount",
                f"type=bind,source={fake_codex_path.resolve()},target=/opt/fake-codex/codex,readonly",
            )
        )
    for key in (
        MUTEX_ENDPOINT,
        MUTEX_TOKEN,
        MQTT_BROKER,
        MQTT_AUTHORIZER,
        MQTT_TOKEN,
    ):
        command.extend(("--env", key))
    if live.openai_key:
        command.extend(("--env", CODEX_API_KEY))
    if fake_agent:
        command.extend(("--env", f"FAKE_CODEX_MODE={fake_agent_mode}"))
    command.extend(
        (
            "--env",
            "KANBUS_REALTIME_TRANSPORT=mqtt",
            "--env",
            "KANBUS_REALTIME_AUTOSTART=false",
            "--env",
            "KANBUS_REALTIME_KEEPALIVE=false",
        )
    )
    worker_command = (
        ["python3", "-m", "kanbus.cli", "router", "run", "--once"]
        if runtime == "python"
        else ["kbs", "router", "run", "--once"]
    )
    command.extend(
        (
            image,
            "/bin/sh",
            "-c",
            "cp -a /workspace-source/. /workspace/ && touch /tmp/harness-ready && "
            'while [ ! -f /harness-control/start ]; do sleep 0.02; done; exec "$@"',
            "kanbus-harness",
            *worker_command,
        )
    )
    return command


def _start_worker(
    name: str,
    worker_root: Path,
    remote: Path,
    image: str,
    runtime: str,
    live: LiveInputs,
    env: Mapping[str, str],
    barrier_directory: Path,
    fake_agent: bool = False,
    fake_agent_mode: str = "complete",
) -> subprocess.Popen[str]:
    """Start an isolated router container worker.

    :param name: Unique container name.
    :param worker_root: Worker checkout directory.
    :param remote: Shared bare Git mirror.
    :param image: Docker image tag.
    :param runtime: Python or Rust runtime.
    :param live: Validated live service credentials.
    :param env: Host environment for Docker invocation.
    :param barrier_directory: Shared startup barrier directory.
    :param fake_agent: Whether to use a deterministic fake Codex worker.
    :param fake_agent_mode: Mode for fake Codex (complete or hang).
    :return: Running container process.
    :raises HarnessError: If the container cannot be started.
    """
    command = _container_command(
        name=name,
        worker_root=worker_root,
        remote=remote,
        image=image,
        runtime=runtime,
        live=live,
        barrier_directory=barrier_directory,
        fake_agent=fake_agent,
        fake_agent_mode=fake_agent_mode,
    )
    try:
        return subprocess.Popen(
            command,
            cwd=worker_root,
            env=_container_launcher_environment(env, live),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise HarnessError("could not start Docker worker") from error


def _container_launcher_environment(
    env: Mapping[str, str], live: LiveInputs
) -> dict[str, str]:
    """Expose the OpenAI key under Codex's environment name to Docker.

    :param env: Host environment used to invoke Docker.
    :param live: Validated, allowlisted live service credentials.
    :return: Copy of ``env`` with the mapped Codex API key.
    """
    result = dict(env)
    result[CODEX_API_KEY] = live.openai_key
    return result


def _release_worker_barrier(
    names: Sequence[str],
    workers: Sequence[subprocess.Popen[str]],
    barrier_directory: Path,
    timeout: float,
) -> None:
    """Wait until every worker is ready, then release them simultaneously."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(worker.poll() is not None for worker in workers):
            raise HarnessError("a Docker worker exited before the race barrier")
        ready = all(
            _run(
                ["docker", "exec", name, "test", "-f", "/tmp/harness-ready"],
                check=False,
            ).returncode
            == 0
            for name in names
        )
        if ready:
            (barrier_directory / "start").touch()
            return
        time.sleep(0.05)
    raise HarnessError("Docker workers did not reach the race barrier before timeout")


def _read_issue(root: Path, issue_id: str) -> dict[str, object]:
    path = root / _project_directory(root) / "issues" / f"{issue_id}.json"
    try:
        issue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HarnessError(f"could not read routed issue {issue_id}") from error
    if not isinstance(issue, dict):
        raise HarnessError(f"routed issue {issue_id} is not a JSON object")
    return issue


def _read_router_state_issue(
    bare_remote: Path, config_root: Path, issue_id: str
) -> dict[str, object]:
    """Read the authoritative test issue from the shared router-state commit."""
    ref = f"refs/heads/{STATE_BRANCH}"
    issue_path = (
        _project_directory(config_root) / "issues" / f"{issue_id}.json"
    ).as_posix()
    shown = _run(
        ["git", "--git-dir", str(bare_remote), "show", f"{ref}:{issue_path}"],
        check=False,
    )
    if shown.returncode:
        raise HarnessError("shared router state does not contain the test issue")
    try:
        issue = json.loads(shown.stdout)
    except json.JSONDecodeError as error:
        raise HarnessError("shared router-state issue is invalid JSON") from error
    if not isinstance(issue, dict):
        raise HarnessError("shared router-state issue is not a JSON object")
    return issue


def _run_hard_or_soft_race_scenario(
    names: Sequence[str],
    worker_roots: Sequence[Path],
    remote: Path,
    image: str,
    inputs: LiveInputs,
    env: Mapping[str, str],
    barrier_directory: Path,
    fake_agent: bool,
    timeout: float,
) -> list[WorkerResult]:
    """Run the standard hard-race or soft-duplicate race: both workers simultaneous."""
    workers = [
        _start_worker(
            names[0],
            worker_roots[0],
            remote,
            image,
            "python",
            inputs,
            env,
            barrier_directory,
            fake_agent=fake_agent,
        ),
        _start_worker(
            names[1],
            worker_roots[1],
            remote,
            image,
            "rust",
            inputs,
            env,
            barrier_directory,
            fake_agent=fake_agent,
        ),
    ]
    _release_worker_barrier(names, workers, barrier_directory, timeout)
    results: list[WorkerResult] = []
    for index, (name, process, worker_root) in enumerate(
        zip(names, workers, worker_roots, strict=True)
    ):
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            _run(["docker", "rm", "--force", name], check=False)
            process.kill()
            process.communicate()
            raise HarnessError(f"container worker {name} timed out") from error
        redacted_stdout = redact(stdout, inputs.docker_environment())
        redacted_stderr = redact(stderr, inputs.docker_environment())
        results.append(
            WorkerResult(
                "python" if index == 0 else "rust",
                worker_root,
                ProcessResult(
                    process.returncode or 0, redacted_stdout, redacted_stderr
                ),
            )
        )
    return results


def _run_expiry_takeover_scenario(
    names: Sequence[str],
    worker_roots: Sequence[Path],
    remote: Path,
    image: str,
    inputs: LiveInputs,
    env: Mapping[str, str],
    barrier_directory: Path,
    fake_agent: bool,
    timeout: float,
    task_id: str,
    marker: str,
) -> list[WorkerResult]:
    """Run the expiry-takeover scenario: A hangs, kill it, B takes over."""
    results: list[WorkerResult] = []
    py_name = names[0]
    py_root = worker_roots[0]
    rs_name = names[1]
    rs_root = worker_roots[1]

    barrier_a = barrier_directory / "barrier-a"
    barrier_a.mkdir()
    worker_a = _start_worker(
        py_name,
        py_root,
        remote,
        image,
        "python",
        inputs,
        env,
        barrier_a,
        fake_agent=fake_agent,
        fake_agent_mode="hang",
    )
    _release_worker_barrier([py_name], [worker_a], barrier_a, timeout)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state_sha = _git(
            remote,
            "rev-parse",
            "--verify",
            f"refs/heads/{STATE_BRANCH}",
            check=False,
            bare=True,
        )
        if state_sha:
            try:
                state_issue = _read_router_state_issue(remote, py_root, task_id)
                if state_issue.get("status") == "in_progress":
                    break
            except HarnessError:
                pass
        time.sleep(1)
    else:
        _run(["docker", "kill", py_name], check=False)
        worker_a.kill()
        raise HarnessError("worker A did not claim the package before timeout")

    _run(["docker", "kill", py_name], check=False)
    try:
        worker_a.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        worker_a.kill()
        worker_a.communicate()
    local_issue_a = _read_issue(py_root, task_id)
    assert_interrupted_worker(
        WorkerResult(
            "python", py_root, ProcessResult(worker_a.returncode or 0, "", "")
        ),
        local_issue_a,
    )

    time.sleep(EXPIRY_WAIT_SECONDS)

    barrier_b = barrier_directory / "barrier-takeover"
    barrier_b.mkdir()
    worker_b = _start_worker(
        rs_name,
        rs_root,
        remote,
        image,
        "rust",
        inputs,
        env,
        barrier_b,
        fake_agent=fake_agent,
        fake_agent_mode="complete",
    )
    _release_worker_barrier([rs_name], [worker_b], barrier_b, timeout)

    try:
        stdout, stderr = worker_b.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _run(["docker", "rm", "--force", rs_name], check=False)
        worker_b.kill()
        worker_b.communicate()
        raise HarnessError(f"container worker {rs_name} timed out") from error
    redacted_stdout = redact(stdout, inputs.docker_environment())
    redacted_stderr = redact(stderr, inputs.docker_environment())
    result_b = WorkerResult(
        "rust",
        rs_root,
        ProcessResult(worker_b.returncode or 0, redacted_stdout, redacted_stderr),
    )
    results.append(result_b)

    state_issue_b = _read_router_state_issue(remote, rs_root, task_id)
    assert_takeover(result_b, state_issue_b, marker)
    print("takeover succeeded after lease expiry")
    return results


def run_harness(
    *,
    repo_root: Path,
    live: bool,
    publish_board: bool,
    keep: bool,
    timeout: float,
    image: str,
    kbs_command: str | None = None,
    fake_agent: bool = False,
    scenario: str = "hard-race",
) -> Path | None:
    """Race two router runtimes in containers against a real board test issue.

    :param repo_root: Clean Kanbus checkout on the develop branch.
    :param live: Whether live providers were explicitly requested.
    :param publish_board: Whether board commits may be pushed to develop.
    :param keep: Whether to retain the temporary container fixture and logs.
    :param timeout: Maximum duration for each container worker.
    :param image: Docker image tag to build/use.
    :param kbs_command: Optional host Kanbus CLI command prefix.
    :param fake_agent: Whether to use a deterministic fake Codex worker.
    :param scenario: Test scenario: "hard-race", "soft-duplicate", or "expiry-takeover".
    :return: Retained workspace when ``keep`` is true, otherwise ``None``.
    :raises HarnessError: If preflight, execution, verification, or cleanup fails.
    """
    if scenario not in VALID_SCENARIOS:
        raise HarnessError(
            f"invalid scenario {scenario!r}; must be one of {sorted(VALID_SCENARIOS)}"
        )
    if scenario != "hard-race" and not fake_agent:
        raise HarnessError(
            f"scenario {scenario!r} requires --fake-agent for deterministic timing"
        )
    inputs = validate_live_inputs(
        os.environ, live=live, publish_board=publish_board, fake_agent=fake_agent
    )
    repo_root = repo_root.resolve()
    if timeout <= 0:
        raise HarnessError("timeout must be positive")
    branch = _git(repo_root, "branch", "--show-current")
    if branch != DEFAULT_BRANCH:
        raise HarnessError(f"run from {DEFAULT_BRANCH}, not {branch!r}")
    if _git(repo_root, "status", "--porcelain"):
        raise HarnessError("checkout must be clean before a live board test")
    kbs = tuple(
        shlex.split(kbs_command or os.environ.get("KANBUS_HARNESS_BOARD_CLI", "kbs"))
    )
    if not kbs or shutil.which(kbs[0]) is None:
        raise HarnessError("Kanbus CLI is unavailable; set KANBUS_HARNESS_BOARD_CLI")
    _run(["git", "-C", str(repo_root), "fetch", "origin", DEFAULT_BRANCH])
    if _git(repo_root, "rev-parse", "HEAD") != _git(
        repo_root, "rev-parse", f"origin/{DEFAULT_BRANCH}"
    ):
        raise HarnessError("checkout must match origin/develop before a live test")
    remote_url = _git(repo_root, "remote", "get-url", "origin")
    docker_info = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if not docker_info.stdout:
        raise HarnessError("Docker daemon did not report a server version")
    dockerfile = Path(__file__).parent / "issue_router_container" / "Dockerfile"
    _run(
        [
            "docker",
            "build",
            "-f",
            str(dockerfile),
            "-t",
            image,
            str(repo_root),
        ],
        cwd=repo_root,
        timeout=max(timeout, 900),
        secrets=inputs.docker_environment(),
    )
    workspace = Path(tempfile.mkdtemp(prefix="kanbus-router-containers-"))
    controller = workspace / "board-controller"
    remote = workspace / "shared-board.git"
    barrier_directory = workspace / "barrier"
    barrier_directory.mkdir()
    worker_roots = [workspace / "worker-python", workspace / "worker-rust"]
    names = [
        f"kanbus-router-{uuid4().hex[:10]}-py",
        f"kanbus-router-{uuid4().hex[:10]}-rs",
    ]
    task_id: str | None = None
    pushed = False
    failures: list[str] = []
    safe_env = os.environ.copy()
    safe_env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        _run(
            [
                "git",
                "clone",
                "--single-branch",
                "--branch",
                DEFAULT_BRANCH,
                remote_url,
                str(controller),
            ],
            env=safe_env,
            timeout=max(timeout, 120),
        )
        _set_test_git_identity(controller)
        _identity_action(controller, kbs)
        run_id = uuid4().hex[:12]
        agent_class = f"{TEST_AGENT_CLASS_PREFIX}{run_id}"
        task_id, marker = _create_test_issue(controller, kbs, run_id, agent_class)
        _run([*kbs, "commit"], cwd=controller, env=safe_env)
        _run(
            ["git", "-C", str(controller), "push", "origin", DEFAULT_BRANCH],
            env=safe_env,
        )
        pushed = True

        _run(
            _bare_remote_clone_command(remote_url, remote),
            env=safe_env,
            timeout=max(timeout, 120),
        )
        _run(
            ["git", "--git-dir", str(remote), "remote", "set-url", "origin", remote_url]
        )
        for worker_root in worker_roots:
            _run(
                ["git", "clone", "--no-hardlinks", str(remote), str(worker_root)],
                env=safe_env,
                timeout=max(timeout, 120),
            )
            _git(
                worker_root, "remote", "set-url", "origin", "file:///kanbus-shared.git"
            )
            soft_coord = scenario == "soft-duplicate"
            lease_ttl = EXPIRY_TTL if scenario == "expiry-takeover" else None
            _configure_worker_for_test(
                worker_root,
                agent_class,
                fake_agent=fake_agent,
                soft_coordination=soft_coord,
                lease_ttl=lease_ttl,
            )

        if scenario == "expiry-takeover":
            results = _run_expiry_takeover_scenario(
                names,
                worker_roots,
                remote,
                image,
                inputs,
                safe_env,
                barrier_directory,
                fake_agent,
                timeout,
                task_id,
                marker,
            )
        else:
            results = _run_hard_or_soft_race_scenario(
                names,
                worker_roots,
                remote,
                image,
                inputs,
                safe_env,
                barrier_directory,
                fake_agent,
                timeout,
            )

        if scenario == "soft-duplicate":
            total_starts = assert_soft_duplicate_permitted(results)
            starter = next(w for w in results if STARTED_RE.findall(w.result.stdout))
            winning_issue = _read_router_state_issue(
                remote, starter.issue_root, task_id
            )
            assert_task_result(winning_issue, marker)
            print(f"soft-duplicate observed: {total_starts} worker(s) started")
        elif scenario == "expiry-takeover":
            winning_issue = _read_router_state_issue(remote, worker_roots[1], task_id)
        else:
            winner = assert_single_router_start(results)
            state_ref = f"refs/heads/{STATE_BRANCH}"
            state_sha = _git(
                remote, "rev-parse", "--verify", state_ref, check=False, bare=True
            )
            if not state_sha:
                raise HarnessError("workers did not publish shared router state")
            winning_issue = _read_router_state_issue(remote, winner.issue_root, task_id)
            assert_task_result(winning_issue, marker)
            for worker in results:
                if worker is not winner:
                    assert_loser_untouched(
                        _read_issue(worker.issue_root, task_id), marker
                    )

        # Copy only the router-mutated test issue into the board checkout. The
        # router-state ref remains in the disposable mirror; this commit
        # preserves the generated comment without exporting test events.
        _run(
            ["git", "-C", str(controller), "fetch", "origin", DEFAULT_BRANCH],
            env=safe_env,
        )
        _run(
            [
                "git",
                "-C",
                str(controller),
                "merge",
                "--ff-only",
                f"origin/{DEFAULT_BRANCH}",
            ],
            env=safe_env,
        )
        controller_issue_path = (
            controller / _project_directory(controller) / "issues" / f"{task_id}.json"
        )
        controller_issue_path.write_text(
            json.dumps(winning_issue, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _run([*kbs, "commit"], cwd=controller, env=safe_env)
        _run(
            ["git", "-C", str(controller), "push", "origin", DEFAULT_BRANCH],
            env=safe_env,
        )
        print(
            f"Issue Router test succeeded: {task_id} is in Review; "
            "the task is being left visible for inspection."
        )
    except Exception as error:
        failures.append(str(error))
        if task_id is not None and pushed:
            print(
                f"test issue preserved for inspection after failure: {task_id}",
                file=sys.stderr,
            )
        if keep or failures:
            print(f"integration fixture retained at {workspace}", file=sys.stderr)
        if isinstance(error, HarnessError):
            raise
        raise HarnessError(str(error)) from error
    finally:
        for name in names:
            _run(["docker", "rm", "--force", name], check=False)
        if not keep and not failures:
            shutil.rmtree(workspace, ignore_errors=True)
    if keep:
        return workspace
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Run the opt-in container integration suite and report its outcome."""
    parser = argparse.ArgumentParser(
        description="Race Python and Rust router containers on a real board test issue."
    )
    parser.add_argument("--live", action="store_true", help="enable live services")
    parser.add_argument(
        "--publish-board",
        action="store_true",
        help="authorize temporary test-issue commits to develop",
    )
    parser.add_argument(
        "--keep", action="store_true", help="retain fixture checkout/logs"
    )
    parser.add_argument(
        "--fake-agent",
        action="store_true",
        help="run deterministic fake Codex workers; no model API key required",
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(VALID_SCENARIOS),
        default="hard-race",
        help="test scenario (default: hard-race)",
    )
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--image", default=TEST_IMAGE)
    parser.add_argument("--kbs-command", help="host Kanbus CLI command prefix")
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args(argv)
    try:
        run_harness(
            repo_root=args.repo_root,
            live=args.live,
            publish_board=args.publish_board,
            keep=args.keep,
            timeout=args.timeout_seconds,
            image=args.image,
            kbs_command=args.kbs_command,
            fake_agent=args.fake_agent,
            scenario=args.scenario,
        )
    except HarnessError as error:
        print(
            f"container integration harness failed: {redact(str(error), os.environ)}",
            file=sys.stderr,
        )
        return 1
    print("containerized board-dispatch hard-lease test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
