"""Disposable-repository integration harness for the Kanbus Issue Router.

Offline runs use a temporary bare Git remote and two isolated clones. Live
Mutex API and MQTT services are available only through the explicit live gate.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import tomllib

ENABLE_LIVE_ENV = "KANBUS_RUN_LIVE_ROUTER_HARNESS"
PYTHON_WORKER_ENV = "KANBUS_HARNESS_PYTHON_WORKER"
RUST_WORKER_ENV = "KANBUS_HARNESS_RUST_WORKER"
MUTEX_ENDPOINT_ENV = "KANBUS_HARNESS_MUTEX_API_ENDPOINT"
MUTEX_TOKEN_ENV = "KANBUS_HARNESS_MUTEX_API_TOKEN"
MQTT_BROKER_ENV = "KANBUS_HARNESS_MQTT_BROKER"
MQTT_AUTHORIZER_ENV = "KANBUS_HARNESS_MQTT_CUSTOM_AUTHORIZER"
MQTT_TOKEN_ENV = "KANBUS_HARNESS_MQTT_API_TOKEN"
MQTT_ACCOUNT_ENV = "KANBUS_HARNESS_TENANT_ACCOUNT"
MQTT_PROJECT_ENV = "KANBUS_HARNESS_TENANT_PROJECT"
MUTEX_RUNTIME_ENDPOINT_ENV = "KANBUS_COORDINATION_MUTEX_API_ENDPOINT"
MUTEX_RUNTIME_TOKEN_ENV = "KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN"
FAKE_LOG_ENV = "KANBUS_HARNESS_FAKE_ADAPTER_LOG"
FAKE_ROLE_ENV = "KANBUS_HARNESS_FAKE_ADAPTER_ROLE"
FAKE_OUTCOME_ENV = "KANBUS_HARNESS_FAKE_ADAPTER_OUTCOME"
FAKE_DELAY_ENV = "KANBUS_HARNESS_FAKE_ADAPTER_DELAY_SECONDS"
FAKE_RELEASE_ENV = "KANBUS_HARNESS_FAKE_ADAPTER_RELEASE_FILE"
FAKE_FORGE_TOKEN_ENV = "KANBUS_HARNESS_FAKE_FORGE_TOKEN"
FAKE_FORGE_TOKEN = "local-fake-forge-token"
ROUTER_STATE_BRANCH = "kanbus/router-state"
ISSUE_ID_RE = re.compile(r"(?m)^\s*ID:\s+([A-Za-z0-9][A-Za-z0-9_-]*)\s*$")
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SECRET_NAME_RE = re.compile(
    r"token|secret|password|credential|authorization|private[_-]?key", re.IGNORECASE
)
RESULT_KEYS = (
    "schema_version",
    "outcome",
    "summary",
    "issue_updates",
    "checkpoint",
    "artifacts",
)
FAKE_ADAPTER_SOURCE = """#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

log_path = os.environ.get("KANBUS_HARNESS_FAKE_ADAPTER_LOG")
if log_path:
    record = json.dumps({"pid": os.getpid(), "role": os.environ.get("KANBUS_HARNESS_FAKE_ADAPTER_ROLE", "run")}) + "\\n"
    descriptor = os.open(log_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, record.encode("utf-8"))
    finally:
        os.close(descriptor)

release_path = os.environ.get("KANBUS_HARNESS_FAKE_ADAPTER_RELEASE_FILE")
if release_path:
    deadline = time.monotonic() + float(os.environ.get("KANBUS_HARNESS_FAKE_ADAPTER_DELAY_SECONDS", "45"))
    while not Path(release_path).exists() and time.monotonic() < deadline:
        time.sleep(0.025)
else:
    time.sleep(float(os.environ.get("KANBUS_HARNESS_FAKE_ADAPTER_DELAY_SECONDS", "0")))

result = {
    "schema_version": 1,
    "outcome": os.environ.get("KANBUS_HARNESS_FAKE_ADAPTER_OUTCOME", "completed"),
    "summary": "Disposable Issue Router integration result.",
    "issue_updates": [],
    "checkpoint": None,
    "artifacts": [],
}
role = os.environ.get("KANBUS_HARNESS_FAKE_ADAPTER_ROLE", "run")
Path.cwd().joinpath(".kanbus-router-harness-" + role + ".txt").write_text(
    "Disposable router adapter output for " + role + "\\n", encoding="utf-8"
)
sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\\n")
"""


class HarnessError(RuntimeError):
    """A configuration, setup, or assertion failure in the harness."""


@dataclass(frozen=True)
class Inputs:
    """Resolved worker commands and optional live service inputs."""

    python_worker: tuple[str, ...]
    rust_worker: tuple[str, ...]
    mutex_endpoint: str | None = None
    mutex_token: str | None = None
    mqtt_broker: str | None = None
    mqtt_authorizer: str | None = None
    mqtt_token: str | None = None
    tenant_account: str | None = None
    tenant_project: str | None = None

    @property
    def mutex_enabled(self) -> bool:
        """Return whether the live hard Mutex API provider is configured."""
        return self.mutex_endpoint is not None

    @property
    def mqtt_enabled(self) -> bool:
        """Return whether a complete live MQTT configuration is available."""
        return self.mqtt_broker is not None


@dataclass(frozen=True)
class CommandResult:
    """Captured result from one bounded subprocess invocation."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def combined(self) -> str:
        """Return stdout and stderr for assertion diagnostics."""
        return f"{self.stdout}\n{self.stderr}"


@dataclass(frozen=True)
class Worker:
    """One router runtime running in an isolated disposable clone."""

    name: str
    command: tuple[str, ...]
    root: Path


class FakeForgeServer:
    """Loopback-only GitHub-shaped endpoint used by disposable projects."""

    def __init__(self) -> None:
        self.pull_requests: list[dict[str, object]] = []
        handler = self._handler_type()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.server.pull_requests = self.pull_requests
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="kanbus-fake-forge",
            daemon=True,
        )
        self.thread.start()

    @property
    def api_url(self) -> str:
        """Return the local API root accepted by the router configuration."""
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def close(self) -> None:
        """Stop the local server and wait briefly for its request thread."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)

    def _handler_type(self) -> type[http.server.BaseHTTPRequestHandler]:
        pull_requests = self.pull_requests

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path.split("?", 1)[0].endswith("/pulls"):
                    self._write_json(200, pull_requests)
                else:
                    self._write_json(404, {"message": "not found"})

            def do_POST(self) -> None:
                content_length = int(self.headers.get("Content-Length", "0"))
                try:
                    payload = json.loads(self.rfile.read(content_length) or b"{}")
                except json.JSONDecodeError:
                    self._write_json(400, {"message": "invalid JSON"})
                    return
                if not isinstance(payload, dict):
                    self._write_json(400, {"message": "invalid payload"})
                    return
                number = len(pull_requests) + 1
                item = {
                    "number": number,
                    "html_url": f"http://fake-forge.invalid/pull/{number}",
                    "state": "open",
                    "merged": False,
                    "head": {
                        "ref": payload.get("head", "router"),
                        "sha": f"fake-head-{number}",
                    },
                    "base": {"ref": payload.get("base", "main")},
                    "title": payload.get("title", ""),
                    "body": payload.get("body", ""),
                }
                pull_requests.append(item)
                self._write_json(201, item)

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _write_json(self, status: int, payload: object) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


class RunningCommand:
    """A bounded command process whose process tree can be cleaned up."""

    def __init__(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> None:
        try:
            self.process = subprocess.Popen(
                list(args),
                cwd=cwd,
                env=dict(env),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name == "posix",
            )
        except OSError as error:
            raise HarnessError(f"could not start command: {args[0]}") from error
        self.env = dict(env)
        self.args = tuple(args)

    def finish(self, timeout: float) -> CommandResult:
        """Wait for the process and redact captured output."""
        try:
            stdout, stderr = self.process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            terminate_process_tree(self.process)
            stdout, stderr = self.process.communicate()
            raise HarnessError(
                f"command timed out after {timeout:g}s: {self.args[0]}\n"
                f"{redact_output(stdout, self.env)}{redact_output(stderr, self.env)}"
            ) from error
        return CommandResult(
            self.process.returncode or 0,
            redact_output(stdout, self.env),
            redact_output(stderr, self.env),
        )

    def close(self) -> None:
        """Terminate an unfinished process tree."""
        if self.process.poll() is None:
            terminate_process_tree(self.process)
            self.process.communicate()


def parse_command_prefix(value: str, name: str) -> tuple[str, ...]:
    """Split a worker command prefix without invoking a shell.

    :param value: User-provided command prefix.
    :type value: str
    :param name: Display name for validation errors.
    :type name: str
    :return: Tokenized command prefix.
    :rtype: tuple[str, ...]
    :raises HarnessError: If the command prefix is empty or malformed.
    """
    try:
        command = tuple(shlex.split(value))
    except ValueError as error:
        raise HarnessError(f"{name} command prefix is invalid") from error
    if not command:
        raise HarnessError(f"{name} command prefix must not be empty")
    return command


def require_inputs(
    env: Mapping[str, str],
    *,
    live: bool,
    python_worker: str | None = None,
    rust_worker: str | None = None,
) -> Inputs:
    """Validate worker commands and explicitly gated optional live services.

    :param env: Environment values supplied to the harness.
    :type env: Mapping[str, str]
    :param live: Whether live service configuration may be used.
    :type live: bool
    :param python_worker: Optional command prefix override for Python.
    :type python_worker: str | None
    :param rust_worker: Optional command prefix override for Rust.
    :type rust_worker: str | None
    :return: Validated worker and service inputs.
    :rtype: Inputs
    :raises HarnessError: If the live gate or supplied inputs are invalid.
    """
    if live and env.get(ENABLE_LIVE_ENV) != "1":
        raise HarnessError(
            f"live execution is disabled; set {ENABLE_LIVE_ENV}=1 to run the harness"
        )
    selected_python = (
        python_worker
        or env.get(PYTHON_WORKER_ENV)
        or (f'"{sys.executable}" -m kanbus.cli')
    )
    selected_rust = rust_worker or env.get(RUST_WORKER_ENV) or "kbs"
    python_command = parse_command_prefix(selected_python, "Python worker")
    rust_command = parse_command_prefix(selected_rust, "Rust worker")
    if not live:
        return Inputs(python_command, rust_command)

    mutex_endpoint = _optional_value(env, MUTEX_ENDPOINT_ENV)
    mutex_token = _optional_value(env, MUTEX_TOKEN_ENV)
    if bool(mutex_endpoint) != bool(mutex_token):
        raise HarnessError(f"configure both {MUTEX_ENDPOINT_ENV} and {MUTEX_TOKEN_ENV}")
    if mutex_endpoint and not _absolute_http_url(mutex_endpoint):
        raise HarnessError("Mutex API endpoint must be an absolute http(s) URL")

    mqtt_values = {
        "broker": _optional_value(env, MQTT_BROKER_ENV),
        "authorizer": _optional_value(env, MQTT_AUTHORIZER_ENV),
        "token": _optional_value(env, MQTT_TOKEN_ENV),
        "account": _optional_value(env, MQTT_ACCOUNT_ENV),
        "project": _optional_value(env, MQTT_PROJECT_ENV),
    }
    if any(mqtt_values.values()) and not all(mqtt_values.values()):
        raise HarnessError(
            "MQTT requires broker, custom authorizer, API token, tenant account, "
            "and tenant project inputs"
        )
    mqtt_broker = mqtt_values["broker"]
    if mqtt_broker and not _absolute_mqtt_url(mqtt_broker):
        raise HarnessError("MQTT broker must be an absolute mqtt:// or mqtts:// URL")
    for label, value in (
        ("tenant account", mqtt_values["account"]),
        ("tenant project", mqtt_values["project"]),
    ):
        if value and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
            raise HarnessError(
                f"{label} must be a topic segment containing only letters, digits, "
                "'.', '_', or '-'"
            )
    return Inputs(
        python_worker=python_command,
        rust_worker=rust_command,
        mutex_endpoint=mutex_endpoint.rstrip("/") if mutex_endpoint else None,
        mutex_token=mutex_token,
        mqtt_broker=mqtt_broker,
        mqtt_authorizer=mqtt_values["authorizer"],
        mqtt_token=mqtt_values["token"],
        tenant_account=mqtt_values["account"],
        tenant_project=mqtt_values["project"],
    )


def locked_result_envelope(outcome: str = "completed") -> dict[str, object]:
    """Build the fixed Codex router result object emitted by the fake adapter.

    :param outcome: Supported or deliberately invalid test outcome.
    :type outcome: str
    :return: Result object with the locked six-field shape.
    :rtype: dict[str, object]
    """
    return {
        "schema_version": 1,
        "outcome": outcome,
        "summary": "Disposable Issue Router integration result.",
        "issue_updates": [],
        "checkpoint": None,
        "artifacts": [],
    }


def assert_deterministic_plans(
    python_plan: str,
    rust_plan: str,
    expected_issue_ids: Sequence[str],
) -> None:
    """Require byte-identical plan output and the expected stable order.

    :param python_plan: JSON plan emitted by the Python worker.
    :type python_plan: str
    :param rust_plan: JSON plan emitted by the Rust worker.
    :type rust_plan: str
    :param expected_issue_ids: Expected eligible package order.
    :type expected_issue_ids: Sequence[str]
    :raises HarnessError: If plans differ or the eligible order is wrong.
    """
    if python_plan != rust_plan:
        raise HarnessError("Python and Rust router plans differ byte-for-byte")
    try:
        plan = json.loads(python_plan)
    except json.JSONDecodeError as error:
        raise HarnessError("router plan --json returned invalid JSON") from error
    eligible = plan.get("eligible") if isinstance(plan, dict) else None
    actual = [item.get("issue_id") for item in eligible or [] if isinstance(item, dict)]
    if actual != list(expected_issue_ids):
        raise HarnessError(
            f"router plan order differs: expected {list(expected_issue_ids)}, got {actual}"
        )


def assert_fenced_publication(
    stale_result: CommandResult,
    current_status: str,
    expected_status: str = "review",
) -> None:
    """Require a stale result to fail and leave the accepted status intact.

    :param stale_result: Result of the older concurrent router run.
    :type stale_result: CommandResult
    :param current_status: Status read through ``kanbus show --json``.
    :type current_status: str
    :param expected_status: Status published by the current claim.
    :type expected_status: str
    :raises HarnessError: If stale publication succeeds or changes the status.
    """
    if stale_result.returncode == 0:
        raise HarnessError("stale router result unexpectedly published successfully")
    message = stale_result.combined.lower()
    if not any(
        marker in message
        for marker in (
            "stale router claim",
            "could not publish branch",
            "could not publish router branch",
            "non-fast-forward",
        )
    ):
        raise HarnessError(
            "stale router result failed without a publication-fencing error"
        )
    if current_status != expected_status:
        raise HarnessError(
            f"stale router result changed accepted status to {current_status!r}"
        )


def assert_shared_router_state(
    plan_output: str,
    issue: Mapping[str, object],
    claim_output: str,
    *,
    issue_id: str,
    expected_status: str,
    claim_active: bool,
    expected_eligible_issue_ids: Sequence[str] | None = None,
) -> None:
    """Require fetched router claims and board status to affect CLI planning.

    :param plan_output: Plan JSON produced by the worker after fetching shared state.
    :type plan_output: str
    :param issue: Issue JSON returned by ``kanbus show``.
    :type issue: Mapping[str, object]
    :param claim_output: ``coordination inspect`` output for the router issue claim.
    :type claim_output: str
    :param issue_id: Issue expected to be absent from eligible plans.
    :type issue_id: str
    :param expected_status: Expected shared issue status.
    :type expected_status: str
    :param claim_active: Whether the shared claim should still be active.
    :type claim_active: bool
    :param expected_eligible_issue_ids: Optional exact eligible plan order.
    :type expected_eligible_issue_ids: Sequence[str] | None
    :raises HarnessError: If router-owned state is not visible to the worker.
    """
    try:
        plan = json.loads(plan_output)
    except json.JSONDecodeError as error:
        raise HarnessError(
            "router plan --json returned invalid shared-state JSON"
        ) from error
    eligible = plan.get("eligible") if isinstance(plan, dict) else None
    if not isinstance(eligible, list):
        raise HarnessError("router plan shared-state JSON has no eligible list")
    eligible_issue_ids = [
        package.get("issue_id") for package in eligible if isinstance(package, dict)
    ]
    if expected_eligible_issue_ids is not None and eligible_issue_ids != list(
        expected_eligible_issue_ids
    ):
        raise HarnessError(
            "worker did not plan the expected remaining packages after shared "
            f"state: expected {list(expected_eligible_issue_ids)}, "
            f"got {eligible_issue_ids}"
        )
    if any(
        isinstance(package, dict) and package.get("issue_id") == issue_id
        for package in eligible
    ):
        raise HarnessError(
            f"worker still plans {issue_id} after shared status {expected_status!r}"
        )
    if issue.get("status") != expected_status:
        raise HarnessError(
            f"worker did not reconcile shared status for {issue_id}: "
            f"expected {expected_status!r}, got {issue.get('status')!r}"
        )
    expected_claim = (
        "state: active soft ownership" if claim_active else "state: eligible"
    )
    if expected_claim not in claim_output:
        raise HarnessError(
            f"worker did not reconcile the shared router claim for {issue_id}"
        )


def assert_router_state_ref_advanced(initial_sha: str, current_sha: str) -> None:
    """Require runtime-owned coordination state to advance on its shared ref.

    :param initial_sha: Shared-state branch SHA before router execution.
    :type initial_sha: str
    :param current_sha: Shared-state branch SHA after runtime fetch/publication.
    :type current_sha: str
    :raises HarnessError: If router execution did not publish the state branch.
    """
    if not current_sha or current_sha == initial_sha:
        raise HarnessError(
            f"router execution did not publish shared state to {ROUTER_STATE_BRANCH}"
        )


def assert_output_ref_published(sha: str, ref: str) -> None:
    """Require the router worker to have pushed its result branch."""
    if not sha:
        raise HarnessError(f"router did not publish the expected result ref {ref}")


def assert_output_ref_unchanged(expected_sha: str, current_sha: str, ref: str) -> None:
    """Require stale work not to replace the accepted result branch."""
    assert_output_ref_published(expected_sha, ref)
    if current_sha != expected_sha:
        raise HarnessError(f"stale router result changed published ref {ref}")


def _assert_durable_router_history(
    root: Path, issue_id: str, *, ref: str | None = None
) -> None:
    """Require accepted router claims/results to survive on the fetched ref."""
    records: list[dict[str, object]] = []
    if ref is None:
        event_paths = (
            (path.relative_to(root).as_posix(), path)
            for path in (root / "project" / "events").glob("*.json")
        )
        for relative_path, path in event_paths:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(record, dict):
                records.append(record)
    else:
        event_root = "project/events"
        listed = _run(
            [
                "git",
                "-C",
                str(root),
                "ls-tree",
                "-r",
                "--name-only",
                ref,
                "--",
                event_root,
            ],
            cwd=root,
            env=os.environ,
            timeout=30,
        )
        for relative_path in listed.stdout.splitlines():
            if not relative_path.endswith(".json"):
                continue
            contents = _run(
                ["git", "-C", str(root), "show", f"{ref}:{relative_path}"],
                cwd=root,
                env=os.environ,
                timeout=30,
            ).stdout
            try:
                record = json.loads(contents)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)

    package_events = [
        record
        for record in records
        if record.get("issue_id")
        in {f"router:{issue_id}", f"router:package:{issue_id}"}
    ]
    started = any(
        record.get("event_type")
        in {"router_claimed", "router_attempt", "router.attempt"}
        and (
            record.get("event_type") == "router_claimed"
            or record.get("payload", {}).get("action") == "started"
        )
        for record in package_events
        if isinstance(record.get("payload"), dict)
    )
    completed = any(
        (
            record.get("event_type") == "router_completed"
            or (
                record.get("event_type") == "router_result"
                and record.get("payload", {}).get("outcome") == "completed"
            )
            or (
                record.get("event_type") == "router.result"
                and record.get("payload", {}).get("outcome") == "completed"
            )
        )
        for record in package_events
        if isinstance(record.get("payload"), dict)
    )
    if not started or not completed:
        raise HarnessError(
            f"shared router event history is missing the accepted claim/result for {issue_id}"
        )


def assert_one_hard_start(
    results: Mapping[str, CommandResult], invocation_count: int
) -> None:
    """Require one concurrent hard-coordinated run to start the fake adapter.

    :param results: Run results indexed by worker name.
    :type results: Mapping[str, CommandResult]
    :param invocation_count: New fake-adapter invocations in this race.
    :type invocation_count: int
    :raises HarnessError: If there was not exactly one adapter start.
    """
    if len(results) != 2 or invocation_count != 1:
        details = "\n".join(
            f"{name}: exit={result.returncode}\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
            for name, result in results.items()
        )
        raise HarnessError(
            "hard Mutex API race must execute exactly one adapter "
            f"(workers={len(results)}, adapter_starts={invocation_count})\n"
            f"{details}"
        )
    starts = sum("started=1" in result.stdout for result in results.values())
    if starts != 1:
        details = "\n".join(
            f"{name}: exit={result.returncode}\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
            for name, result in results.items()
        )
        raise HarnessError("hard Mutex API race did not report one start:\n" + details)


def assert_one_mqtt_soft_start(
    results: Mapping[str, CommandResult],
    invocation_count: int,
    accepted_claim_count: int,
) -> None:
    """Require one accepted router start and one adapter call in an MQTT race.

    :param results: Run results indexed by worker name.
    :type results: Mapping[str, CommandResult]
    :param invocation_count: New fake-adapter invocations in the race.
    :type invocation_count: int
    :param accepted_claim_count: Started router claims in shared event history.
    :type accepted_claim_count: int
    :raises HarnessError: If both workers execute or no single claim wins.
    """
    if len(results) != 2 or invocation_count != 1 or accepted_claim_count != 1:
        raise HarnessError(
            "MQTT soft-coordination race must accept one claim and execute one adapter "
            f"(workers={len(results)}, adapter_starts={invocation_count}, "
            f"accepted_claims={accepted_claim_count})"
        )
    started = [name for name, result in results.items() if "started=1" in result.stdout]
    if len(started) != 1:
        details = "\n".join(
            f"{name}: exit={result.returncode} {result.stdout.strip()}"
            for name, result in results.items()
        )
        raise HarnessError(
            "MQTT soft-coordination race did not report one start:\n" + details
        )


def assert_mqtt_claim_exchange(
    claim_ids_by_worker: Mapping[str, Sequence[str]],
    observations_by_worker: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    prior_observation_claim_ids: Mapping[str, Sequence[str]] | None = None,
    require_transport_diagnostics: bool = False,
) -> None:
    """Require new contention snapshots to prove reciprocal MQTT visibility."""
    worker_names = set(claim_ids_by_worker)
    if len(worker_names) != 2 or set(observations_by_worker) != worker_names:
        raise HarnessError(
            "MQTT contention snapshots must be present for exactly two workers "
            f"(workers={sorted(worker_names)}, "
            f"observations={sorted(observations_by_worker)})"
        )
    previous = prior_observation_claim_ids or {}
    latest: dict[str, Mapping[str, object]] = {}
    for name, records in observations_by_worker.items():
        stale_claim_ids = set(previous.get(name, ()))
        valid = [
            record
            for record in records
            if isinstance(record.get("local_claim_id"), str)
            and record.get("claim_id") == record.get("local_claim_id")
            and record.get("local_claim_id") not in stale_claim_ids
            and record.get("resource")
            and record.get("observed_at")
        ]
        if valid:
            latest[name] = max(
                valid, key=lambda record: str(record.get("observed_at", ""))
            )
    current_claims = {
        name: str(record["local_claim_id"]) for name, record in latest.items()
    }
    failures: dict[str, dict[str, object]] = {}
    for name in claim_ids_by_worker:
        record = latest.get(name)
        if record is None:
            failures[name] = {"reason": "missing contention-time observation"}
            continue
        local_claim_id = str(record["local_claim_id"])
        peer_claim_ids = record.get("peer_claim_ids")
        observed_claim_ids = record.get("observed_claim_ids")
        other_claim_ids = {
            claim_id
            for worker_name, claim_id in current_claims.items()
            if worker_name != name
        }
        if (
            not isinstance(peer_claim_ids, list)
            or any(not isinstance(value, str) for value in peer_claim_ids)
            or not isinstance(observed_claim_ids, list)
            or any(not isinstance(value, str) for value in observed_claim_ids)
            or not other_claim_ids.issubset(set(peer_claim_ids))
            or not {local_claim_id, *other_claim_ids}.issubset(set(observed_claim_ids))
        ):
            failures[name] = {
                "local_claim_id": local_claim_id,
                "expected_peer_claim_ids": sorted(other_claim_ids),
                "peer_claim_ids": peer_claim_ids,
                "observed_claim_ids": observed_claim_ids,
            }
        transport = record.get("mqtt_transport")
        # Transport traces are optional; reciprocal peer visibility above is
        # the required proof that the MQTT exchange actually happened.
        if require_transport_diagnostics and isinstance(transport, dict):
            listener = transport.get("listener")
            publisher = transport.get("publisher")
            if (
                not isinstance(listener, dict)
                or not isinstance(publisher, dict)
                or listener.get("connected") is not True
                or listener.get("subscribed") is not True
                or listener.get("connect_reason_code") != 0
                or publisher.get("status") != "published"
                or publisher.get("connected") is not True
                or publisher.get("connect_reason_code") != 0
                or publisher.get("publish_completed") is not True
                or publisher.get("publish_rc") != 0
                or not listener.get("client_id")
                or listener.get("client_id") == publisher.get("client_id")
                or listener.get("topic") != publisher.get("topic")
            ):
                failures.setdefault(name, {}).update(
                    mqtt_transport=transport,
                    transport_reason=(
                        "connection, subscription, publish, or ID mismatch"
                    ),
                )
    if len(current_claims) != 2 or len(set(current_claims.values())) != 2:
        failures["workers"] = {"current_claim_ids": current_claims}
    if failures:
        raise HarnessError(
            "MQTT contention snapshots did not prove bidirectional claim exchange "
            f"(observations={failures})"
        )


def _is_started_router_event(record: Mapping[str, object], issue_id: str) -> bool:
    """Return whether a durable event records an accepted start for an issue."""
    if record.get("issue_id") != f"router:{issue_id}":
        return False
    event_type = record.get("event_type")
    if event_type in {"router_claimed", "router_attempt"}:
        return True
    payload = record.get("payload")
    return (
        event_type in {"router.attempt", "router.attempted"}
        and isinstance(payload, dict)
        and payload.get("action") == "started"
    )


def _shared_router_start_count(root: Path, issue_id: str) -> int:
    """Count accepted router starts on the fetched shared-state branch."""
    ref = f"refs/remotes/origin/{ROUTER_STATE_BRANCH}"
    listed = _run(
        [
            "git",
            "-C",
            str(root),
            "ls-tree",
            "-r",
            "--name-only",
            ref,
            "--",
            "project/events",
        ],
        cwd=root,
        env=os.environ,
        timeout=30,
    )
    count = 0
    for relative_path in listed.stdout.splitlines():
        if not relative_path.endswith(".json"):
            continue
        contents = _run(
            ["git", "-C", str(root), "show", f"{ref}:{relative_path}"],
            cwd=root,
            env=os.environ,
            timeout=30,
        ).stdout
        try:
            record = json.loads(contents)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and _is_started_router_event(record, issue_id):
            count += 1
    return count


def _mqtt_claim_ids(root: Path, resource: str) -> list[str]:
    """Read locally received MQTT claim envelopes for a resource."""
    claim_ids: set[str] = set()
    for project_dir in _router_project_directories(root):
        directory = project_dir / ".overlay" / "coordination"
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.json"):
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(envelope, dict)
                and envelope.get("type") == "coordination.claim"
                and envelope.get("resource") == resource
                and isinstance(envelope.get("claim_id"), str)
            ):
                claim_ids.add(envelope["claim_id"])
    return sorted(claim_ids)


def _mqtt_claim_observations(root: Path, resource: str) -> list[dict[str, object]]:
    """Load contention snapshots from checkout and hidden router worktree."""
    resource_hash = hashlib.sha256(resource.encode("utf-8")).hexdigest()
    records: list[dict[str, object]] = []
    for project_dir in _router_project_directories(root):
        directory = (
            project_dir / ".overlay" / "coordination-observations" / resource_hash
        )
        paths = sorted(directory.glob("*.json")) if directory.is_dir() else ()
        for path in paths:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(record, dict)
                and record.get("resource") == resource
                and isinstance(record.get("local_claim_id"), str)
                and isinstance(record.get("peer_claim_ids"), list)
                and isinstance(record.get("observed_claim_ids"), list)
            ):
                records.append(record)
    return records


def _router_project_directories(root: Path) -> list[Path]:
    """Resolve configured project paths in the checkout and private state worktree."""
    project_directory = "project"
    try:
        import yaml
    except ImportError:
        pass
    else:
        try:
            configuration = yaml.safe_load(
                (root / ".kanbus.yml").read_text(encoding="utf-8")
            )
        except (OSError, yaml.YAMLError):
            configuration = None
        if isinstance(configuration, dict) and isinstance(
            configuration.get("project_directory"), str
        ):
            project_directory = configuration["project_directory"]
    project_path = Path(project_directory)
    if project_path.is_absolute() or ".." in project_path.parts:
        return []
    directories = [root / project_path]
    try:
        common_dir_text = _git(root, "rev-parse", "--git-common-dir").stdout.strip()
        common_dir = Path(common_dir_text)
        if not common_dir.is_absolute():
            common_dir = (root / common_dir).resolve()
        state_worktree = common_dir / "kanbus-router-state-worktree"
        if state_worktree.is_dir():
            directories.append(state_worktree / project_path)
    except HarnessError:
        pass
    return list(dict.fromkeys(directory.resolve() for directory in directories))


def redact_output(text: str, env: Mapping[str, str] | None) -> str:
    """Remove secret environment values and common bearer-token forms.

    :param text: Captured subprocess output.
    :type text: str
    :param env: Environment supplied to the child process.
    :type env: Mapping[str, str] | None
    :return: Redacted output.
    :rtype: str
    """
    if env is not None:
        values = {
            value
            for name, value in env.items()
            if value and SECRET_NAME_RE.search(name)
        }
        for value in sorted(values, key=len, reverse=True):
            text = text.replace(value, "<redacted>")
    text = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s,]+",
        r"\1<redacted>",
        text,
    )
    return text


def terminate_process_tree(
    process: subprocess.Popen[str], grace_seconds: float = 2.0
) -> None:
    """Terminate a worker and its children with bounded graceful cleanup."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        process.wait(timeout=grace_seconds)
    if os.name == "posix":
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        os.killpg(process.pid, signal.SIGKILL)


def _optional_value(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _absolute_http_url(value: str) -> bool:
    return bool(re.fullmatch(r"https?://[^\s/]+(?:/[^\s]*)?", value))


def _absolute_mqtt_url(value: str) -> bool:
    return bool(re.fullmatch(r"mqtts?://[^\s/]+(?:/[^\s]*)?", value))


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float,
    check: bool = True,
) -> CommandResult:
    process = RunningCommand(args, cwd=cwd, env=env)
    result = process.finish(timeout)
    if check and result.returncode != 0:
        raise HarnessError(
            f"command failed ({result.returncode}): {args[0]}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result


def _git(root: Path | None, *args: str, timeout: float = 30.0) -> CommandResult:
    command = ["git"]
    if root is not None:
        command.extend(["-C", str(root)])
    command.extend(args)
    return _run(command, cwd=root or Path.cwd(), env=os.environ, timeout=timeout)


def _cli(
    worker: Worker,
    args: Sequence[str],
    *,
    env: Mapping[str, str],
    timeout: float,
    check: bool = True,
) -> CommandResult:
    command = [*worker.command, "--no-guidance", "--no-hooks", *args]
    return _run(command, cwd=worker.root, env=env, timeout=timeout, check=check)


def _cli_command(worker: Worker, args: Sequence[str]) -> tuple[str, ...]:
    return (*worker.command, "--no-guidance", "--no-hooks", *args)


def _worker_environment(
    base_env: Mapping[str, str],
    worker: Worker,
    *,
    inputs: Inputs,
    log_path: Path,
    role: str,
    outcome: str = "completed",
    delay_seconds: float = 0.0,
    release_path: Path | None = None,
) -> dict[str, str]:
    env = _environment_with_project_toolchain(base_env)
    env.setdefault("KANBUS_NO_DAEMON", "1")
    source_path = str(Path(__file__).resolve().parents[1] / "python" / "src")
    existing_python_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (source_path, existing_python_path) if value
    )
    env.update(
        {
            FAKE_LOG_ENV: str(log_path),
            FAKE_ROLE_ENV: role,
            FAKE_OUTCOME_ENV: outcome,
            FAKE_DELAY_ENV: str(delay_seconds),
            FAKE_FORGE_TOKEN_ENV: FAKE_FORGE_TOKEN,
            "KANBUS_REALTIME_TRANSPORT": "mqtt" if inputs.mqtt_enabled else "uds",
            "KANBUS_REALTIME_AUTOSTART": "false",
            "KANBUS_REALTIME_KEEPALIVE": "false",
            "KANBUS_REALTIME_UDS_SOCKET_PATH": str(
                worker.root / ".kanbus-harness-uds.sock"
            ),
        }
    )
    if release_path is not None:
        env[FAKE_RELEASE_ENV] = str(release_path)
        env[FAKE_DELAY_ENV] = "45"
    else:
        env.pop(FAKE_RELEASE_ENV, None)
    if inputs.mqtt_enabled:
        env.update(
            {
                "KANBUS_ROUTER_MQTT_DIAGNOSTICS": "1",
                "KANBUS_REALTIME_BROKER": inputs.mqtt_broker or "",
                "KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME": (
                    inputs.mqtt_authorizer or ""
                ),
                "KANBUS_REALTIME_MQTT_API_TOKEN": inputs.mqtt_token or "",
                "KANBUS_REALTIME_TOPICS_PROJECT_EVENTS": (
                    f"projects/{inputs.tenant_account}/{inputs.tenant_project}/events"
                ),
            }
        )
    else:
        env.pop("KANBUS_ROUTER_MQTT_DIAGNOSTICS", None)
        env["KANBUS_REALTIME_BROKER"] = "off"
        env["KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME"] = ""
        env["KANBUS_REALTIME_MQTT_API_TOKEN"] = ""
    if inputs.mutex_enabled:
        env[MUTEX_RUNTIME_ENDPOINT_ENV] = inputs.mutex_endpoint or ""
        env[MUTEX_RUNTIME_TOKEN_ENV] = inputs.mutex_token or ""
    else:
        env[MUTEX_RUNTIME_ENDPOINT_ENV] = ""
        env[MUTEX_RUNTIME_TOKEN_ENV] = ""
    return env


def _configure(
    root: Path,
    *,
    fake_adapter: Path,
    forge_api_url: str,
    providers: list[str],
    mqtt_enabled: bool,
    ttl_seconds: int,
    contention_window: str = "1s",
) -> None:
    try:
        import yaml
    except ImportError as error:
        raise HarnessError(
            "PyYAML is required; run the harness with the py311 environment"
        ) from error
    config_path = root / ".kanbus.yml"
    try:
        configuration = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise HarnessError("could not read disposable project configuration") from error
    if not isinstance(configuration, dict):
        raise HarnessError("disposable project configuration must be a YAML mapping")
    coordination = configuration.setdefault("coordination", {})
    coordination.update(
        {
            "providers": providers,
            "contention_window": contention_window,
            "default_lease_ttl": f"{ttl_seconds}s",
            "mutex_api": {"endpoint": None, "bearer_token": None},
        }
    )
    configuration["realtime"] = {
        "transport": "mqtt" if mqtt_enabled else "uds",
        "broker": "auto" if mqtt_enabled else "off",
        "autostart": False,
        "keepalive": False,
        "uds_socket_path": None,
        "mqtt_custom_authorizer_name": None,
        "mqtt_api_token": None,
        "topics": {"project_events": "projects/{project}/events"},
    }
    statuses = configuration.setdefault("statuses", [])
    if not any(status.get("key") == "review" for status in statuses):
        statuses.append(
            {
                "key": "review",
                "name": "Review",
                "category": "In progress",
                "semantic_category": "in_progress",
                "collapsed": False,
            }
        )
    workflows = configuration.setdefault("workflows", {})
    default_workflow = workflows.setdefault("default", {})
    default_workflow["open"] = list(
        dict.fromkeys([*default_workflow.get("open", []), "in_progress", "closed"])
    )
    default_workflow["in_progress"] = list(
        dict.fromkeys(
            [
                *default_workflow.get("in_progress", []),
                "open",
                "blocked",
                "closed",
                "review",
            ]
        )
    )
    default_workflow["blocked"] = list(
        dict.fromkeys([*default_workflow.get("blocked", []), "in_progress", "closed"])
    )
    default_workflow["review"] = ["in_progress", "blocked", "closed"]
    transition_labels = configuration.setdefault("transition_labels", {})
    default_labels = transition_labels.setdefault("default", {})
    default_labels.setdefault("in_progress", {})["review"] = "Ready for review"
    default_labels["review"] = {
        "in_progress": "Request changes",
        "blocked": "Close without merge",
        "closed": "Merge",
    }
    configuration["router"] = {
        "enabled": True,
        "workflow": {
            "pending": "open",
            "active": "in_progress",
            "review": "review",
            "blocked": "blocked",
            "terminal": ["closed"],
        },
        "limits": {"project_wip": 20, "review_wip": 10},
        "providers": {
            "codex-default": {
                "adapter": "codex",
                "command": str(fake_adapter),
                "args": [],
            }
        },
        "forge": {
            "provider": "github",
            "repository": "harness/fixture",
            "base_branch": "main",
            "api_url": forge_api_url,
            "token_env": FAKE_FORGE_TOKEN_ENV,
        },
        "retries": {"max_attempts": 3},
        "watch_interval": "1s",
    }
    config_path.write_text(
        yaml.safe_dump(configuration, sort_keys=False), encoding="utf-8"
    )


def _write_fake_adapter(path: Path) -> None:
    path.write_text(FAKE_ADAPTER_SOURCE, encoding="utf-8")
    path.chmod(0o700)


def _parse_issue_id(output: str) -> str:
    match = ISSUE_ID_RE.search(ANSI_RE.sub("", output))
    if not match:
        raise HarnessError("could not read a disposable issue ID from CLI output")
    return match.group(1)


def _create_routed_issue(
    worker: Worker, *, env: Mapping[str, str], title: str, timeout: float
) -> str:
    result = _cli(
        worker,
        [
            "create",
            title,
            "--type",
            "task",
            "--assignee",
            "harness-human",
            "--label",
            "agent-provider:codex-default",
            "--description",
            "Temporary Issue Router integration fixture.",
        ],
        env=env,
        timeout=timeout,
    )
    displayed_id = _parse_issue_id(result.stdout)
    issue = _issue_json(worker, displayed_id, env, timeout)
    identifier = issue.get("id", issue.get("identifier"))
    if not isinstance(identifier, str) or not identifier:
        raise HarnessError("kanbus show --json did not return a canonical issue ID")
    return identifier


def _commit_and_push(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    staged = _run(
        ["git", "-C", str(root), "diff", "--cached", "--quiet"],
        cwd=root,
        env=os.environ,
        timeout=30,
        check=False,
    )
    if staged.returncode == 0:
        return
    _run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Kanbus router harness",
            "-c",
            "user.email=kanbus-router-harness@example.invalid",
            "commit",
            "--no-verify",
            "-m",
            message,
        ],
        cwd=root,
        env=os.environ,
        timeout=30,
    )
    _git(root, "push", "--set-upstream", "origin", "main")


def _refresh_clone(root: Path) -> None:
    _git(root, "fetch", "origin", "main")
    _git(root, "pull", "--ff-only", "origin", "main")


def _preflight(inputs: Inputs, cwd: Path, timeout: float) -> None:
    if shutil.which("git") is None:
        raise HarnessError("git must be available on PATH")
    for name, command in (
        ("Python", inputs.python_worker),
        ("Rust", inputs.rust_worker),
    ):
        if shutil.which(command[0]) is None and not (
            Path(command[0]).is_file() and os.access(command[0], os.X_OK)
        ):
            raise HarnessError(f"{name} worker executable is unavailable: {command[0]}")
        command_env = _environment_with_project_toolchain(os.environ)
        if name == "Python":
            source_path = str(Path(__file__).resolve().parents[1] / "python" / "src")
            command_env["PYTHONPATH"] = os.pathsep.join(
                value
                for value in (source_path, command_env.get("PYTHONPATH", ""))
                if value
            )
        result = _run(
            [*command, "--no-guidance", "--no-hooks", "router", "--help"],
            cwd=cwd,
            env=command_env,
            timeout=min(timeout, 30.0),
            check=False,
        )
        if result.returncode != 0:
            raise HarnessError(
                f"{name} worker does not expose the router CLI:\n"
                f"{result.stdout}{result.stderr}"
            )


def _environment_with_project_toolchain(
    base_env: Mapping[str, str],
) -> dict[str, str]:
    """Apply the repository-pinned Rust toolchain in disposable clone roots."""
    env = dict(base_env)
    toolchain_path = Path(__file__).resolve().parents[1] / "rust-toolchain.toml"
    if toolchain_path.is_file():
        try:
            toolchain = tomllib.loads(toolchain_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise HarnessError(
                "could not read the repository Rust toolchain pin"
            ) from error
        channel = toolchain.get("toolchain", {}).get("channel")
        if isinstance(channel, str) and channel:
            env["RUSTUP_TOOLCHAIN"] = channel
            rustup = shutil.which("rustup")
            if rustup is not None:
                selected_rustc = subprocess.run(
                    [rustup, "which", "rustc", "--toolchain", channel],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                if selected_rustc.returncode == 0:
                    env["RUSTC"] = selected_rustc.stdout.strip()
    return env


def _read_fake_calls(log_path: Path) -> list[dict[str, object]]:
    if not log_path.exists():
        return []
    calls: list[dict[str, object]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise HarnessError("fake adapter invocation log is malformed") from error
        if isinstance(item, dict):
            calls.append(item)
    return calls


def _wait_for_fake_role(log_path: Path, role: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(call.get("role") == role for call in _read_fake_calls(log_path)):
            return
        time.sleep(0.025)
    raise HarnessError(f"fake adapter did not start role {role!r} within {timeout:g}s")


def _issue_json(
    worker: Worker, issue_id: str, env: Mapping[str, str], timeout: float
) -> dict:
    result = _cli(worker, ["show", issue_id, "--json"], env=env, timeout=timeout)
    try:
        issue = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise HarnessError("kanbus show --json returned invalid JSON") from error
    if not isinstance(issue, dict):
        raise HarnessError("kanbus show --json did not return an issue object")
    return issue


def _router_state_issue_json(root: Path, issue_id: str) -> dict:
    """Read an issue record from the fetched router-state commit."""
    ref = f"refs/remotes/origin/{ROUTER_STATE_BRANCH}"
    path = f"project/issues/{issue_id}.json"
    result = _git(root, "show", f"{ref}:{path}")
    try:
        issue = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise HarnessError(
            "shared router-state issue record is invalid JSON"
        ) from error
    if not isinstance(issue, dict):
        raise HarnessError("shared router-state issue record is not an object")
    return issue


def _router_plan(worker: Worker, env: Mapping[str, str], timeout: float) -> str:
    return _cli(
        worker,
        ["router", "plan", "--json"],
        env=env,
        timeout=timeout,
    ).stdout


def _coordination_state(
    worker: Worker,
    resource: str,
    env: Mapping[str, str],
    timeout: float,
) -> str:
    return _cli(
        worker,
        ["coordination", "inspect", "--resource", resource],
        env=env,
        timeout=timeout,
    ).stdout


def _fetch_router_state(root: Path) -> str:
    """Fetch the runtime-owned coordination branch and return its remote SHA."""
    source = f"refs/heads/{ROUTER_STATE_BRANCH}"
    destination = f"refs/remotes/origin/{ROUTER_STATE_BRANCH}"
    _git(root, "fetch", "origin", f"{source}:{destination}")
    return _git(root, "rev-parse", destination).stdout.strip()


def _remote_ref_sha(root: Path, branch: str) -> str:
    result = _git(root, "ls-remote", "--heads", "origin", f"refs/heads/{branch}")
    if not result.stdout.strip():
        return ""
    return result.stdout.split()[0]


def _initialize_router_state_branch(root: Path) -> str:
    """Create the initial shared-state ref during disposable fixture setup."""
    source = _git(root, "rev-parse", "HEAD").stdout.strip()
    _git(root, "push", "origin", f"{source}:refs/heads/{ROUTER_STATE_BRANCH}")
    return source


def _assert_shared_state_visible(
    worker: Worker,
    issue_id: str,
    *,
    probe_root: Path,
    expected_status: str,
    claim_active: bool,
    env: Mapping[str, str],
    timeout: float,
    expected_eligible_issue_ids: Sequence[str] | None = None,
) -> str:
    """Fetch router state, then verify CLI behavior from that committed snapshot."""
    state_sha = _fetch_router_state(worker.root)
    _git(worker.root, "worktree", "add", "--detach", str(probe_root), state_sha)
    try:
        probe = Worker(worker.name, worker.command, probe_root)
        plan_output = _router_plan(probe, env, timeout)
        issue = _issue_json(probe, issue_id, env, timeout)
        claim_output = _coordination_state(
            probe,
            f"router:issue:{issue_id}",
            env,
            timeout,
        )
        assert_shared_router_state(
            plan_output,
            issue,
            claim_output,
            issue_id=issue_id,
            expected_status=expected_status,
            claim_active=claim_active,
            expected_eligible_issue_ids=expected_eligible_issue_ids,
        )
    finally:
        _git(worker.root, "worktree", "remove", "--force", str(probe_root))
    return state_sha


def _exercise_mqtt_soft_race(
    *,
    inputs: Inputs,
    worker_a: Worker,
    worker_b: Worker,
    issue_id: str,
    log_path: Path,
    timeout: float,
    initial_state_sha: str,
) -> None:
    """Race the Python and Rust workers using their live MQTT soft claims."""
    if not inputs.mqtt_enabled:
        raise HarnessError("MQTT soft-coordination race requires complete MQTT inputs")
    _fetch_router_state(worker_a.root)
    _fetch_router_state(worker_b.root)
    resource = f"router:issue:{issue_id}"
    prior_observation_claim_ids = {
        worker.name: {
            str(record["local_claim_id"])
            for record in _mqtt_claim_observations(worker.root, resource)
            if isinstance(record.get("local_claim_id"), str)
        }
        for worker in (worker_a, worker_b)
    }

    log_path.write_text("", encoding="utf-8")
    base_env = dict(os.environ)
    envs = {
        worker.name: _worker_environment(
            base_env,
            worker,
            inputs=inputs,
            log_path=log_path,
            role=f"mqtt-{worker.name}",
            delay_seconds=0.75,
        )
        for worker in (worker_a, worker_b)
    }
    results = _parallel_run_once((worker_a, worker_b), envs, timeout=timeout)
    calls = _read_fake_calls(log_path)
    _fetch_router_state(worker_a.root)
    _fetch_router_state(worker_b.root)
    accepted_claims = _shared_router_start_count(worker_a.root, issue_id)
    assert_one_mqtt_soft_start(results, len(calls), accepted_claims)

    claim_ids_by_worker = {
        worker.name: _mqtt_claim_ids(worker.root, resource)
        for worker in (worker_a, worker_b)
    }
    try:
        assert_mqtt_claim_exchange(
            claim_ids_by_worker,
            {
                worker.name: _mqtt_claim_observations(worker.root, resource)
                for worker in (worker_a, worker_b)
            },
            prior_observation_claim_ids=prior_observation_claim_ids,
            require_transport_diagnostics=True,
        )
    except HarnessError as error:
        setup_diagnostics: dict[str, object] = {}
        for worker in (worker_a, worker_b):
            prefix = "MQTT coordination diagnostics: "
            for line in results[worker.name].stderr.splitlines():
                if not line.startswith(prefix):
                    continue
                try:
                    setup_diagnostics[worker.name] = json.loads(line[len(prefix) :])
                except json.JSONDecodeError:
                    continue
        if setup_diagnostics:
            raise HarnessError(
                f"{error}\nMQTT setup diagnostics: {setup_diagnostics}"
            ) from error
        raise
    winner = next(
        worker
        for worker in (worker_a, worker_b)
        if "started=1" in results[worker.name].stdout
    )
    winner_result = results[winner.name]
    if winner_result.returncode != 0 or "completed=1" not in winner_result.stdout:
        raise HarnessError(
            "accepted MQTT router claim did not complete its adapter run:\n"
            + winner_result.combined
        )
    output_branch = f"codex/router/{issue_id}/r1"
    assert_output_ref_published(
        _remote_ref_sha(winner.root, output_branch), output_branch
    )
    state_sha = _fetch_router_state(worker_a.root)
    assert_router_state_ref_advanced(initial_state_sha, state_sha)
    _assert_durable_router_history(
        worker_a.root,
        issue_id,
        ref=f"refs/remotes/origin/{ROUTER_STATE_BRANCH}",
    )
    print(
        "live MQTT soft coordination verified: both workers exchanged QoS 0 "
        "claims and one accepted claim started one adapter"
    )


def _parallel_run_once(
    workers: Sequence[Worker],
    envs: Mapping[str, Mapping[str, str]],
    *,
    timeout: float,
) -> dict[str, CommandResult]:
    barrier = threading.Barrier(len(workers) + 1)
    results: dict[str, CommandResult] = {}
    failures: list[Exception] = []

    def run(worker: Worker) -> None:
        try:
            barrier.wait(timeout=timeout)
            results[worker.name] = _cli(
                worker,
                ["router", "run", "--once"],
                env=envs[worker.name],
                timeout=timeout,
                check=False,
            )
        except (HarnessError, threading.BrokenBarrierError) as error:
            failures.append(error)

    threads = [threading.Thread(target=run, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=timeout)
    for thread in threads:
        thread.join(timeout=timeout + 1)
    if any(thread.is_alive() for thread in threads):
        raise HarnessError("a router run did not finish within its bounded timeout")
    if failures:
        raise HarnessError(
            f"a router worker could not start: {failures[0]}"
        ) from failures[0]
    return results


def _exercise_hard_mutex(
    *,
    inputs: Inputs,
    worker_a: Worker,
    worker_b: Worker,
    issue_id: str,
    fake_adapter: Path,
    forge_api_url: str,
    log_path: Path,
    timeout: float,
    ttl_seconds: int,
) -> None:
    _configure(
        worker_a.root,
        fake_adapter=fake_adapter,
        forge_api_url=forge_api_url,
        providers=["mutex_api", "mqtt", "git"],
        mqtt_enabled=inputs.mqtt_enabled,
        ttl_seconds=ttl_seconds,
    )
    _commit_and_push(worker_a.root, "Configure live hard router coordination")
    _refresh_clone(worker_b.root)
    initial_state_sha = _initialize_router_state_branch(worker_a.root)
    _fetch_router_state(worker_b.root)
    log_path.write_text("", encoding="utf-8")
    base_env = dict(os.environ)
    envs = {
        worker.name: _worker_environment(
            base_env,
            worker,
            inputs=inputs,
            log_path=log_path,
            role="hard-race",
            delay_seconds=0.75,
        )
        for worker in (worker_a, worker_b)
    }
    results = _parallel_run_once((worker_a, worker_b), envs, timeout=timeout)
    calls = _read_fake_calls(log_path)
    assert_one_hard_start(results, len(calls))
    winner = next(
        worker
        for worker in (worker_a, worker_b)
        if "started=1" in results[worker.name].stdout
    )
    output_branch = f"codex/router/{issue_id}/r1"
    assert_output_ref_published(
        _remote_ref_sha(winner.root, output_branch), output_branch
    )
    loser = worker_b if winner == worker_a else worker_a
    state_sha = _assert_shared_state_visible(
        loser,
        issue_id,
        probe_root=loser.root.parent / f"{loser.name}-state-probe",
        expected_status="review",
        claim_active=False,
        env=envs[loser.name],
        timeout=timeout,
    )
    assert_router_state_ref_advanced(initial_state_sha, state_sha)
    _assert_durable_router_history(
        loser.root,
        issue_id,
        ref=f"refs/remotes/origin/{ROUTER_STATE_BRANCH}",
    )
    shared_issue = _router_state_issue_json(loser.root, issue_id)
    if shared_issue.get("assignee") != "harness-human":
        raise HarnessError("hard-coordinated router run changed the human assignee")
    print("live Mutex API coordination verified: exactly one hard router start")


def run_harness(
    *,
    live: bool,
    keep: bool,
    timeout: float,
    ttl_seconds: int,
    python_worker: str | None = None,
    rust_worker: str | None = None,
) -> Path | None:
    """Run the disposable two-clone Issue Router integration scenario.

    :param live: Enable optional live Mutex API and MQTT coordination scenarios.
    :type live: bool
    :param keep: Preserve the temporary bare remote and clones for inspection.
    :type keep: bool
    :param timeout: Maximum time allowed for each CLI command.
    :type timeout: float
    :param ttl_seconds: Mutex TTL used during a live hard-coordination run.
    :type ttl_seconds: int
    :param python_worker: Optional Python CLI command prefix.
    :type python_worker: str | None
    :param rust_worker: Optional Rust CLI command prefix.
    :type rust_worker: str | None
    :return: Retained fixture root when ``keep`` is enabled.
    :rtype: Path | None
    :raises HarnessError: If setup or any integration assertion fails.
    """
    if timeout <= 0:
        raise HarnessError("timeout must be positive")
    if not 1 <= ttl_seconds <= 30:
        raise HarnessError("Mutex TTL must be between 1 and 30 seconds")
    inputs = require_inputs(
        os.environ,
        live=live,
        python_worker=python_worker,
        rust_worker=rust_worker,
    )
    _preflight(inputs, Path.cwd(), timeout)

    temporary = tempfile.TemporaryDirectory(prefix="kanbus-router-harness-")
    workspace = Path(temporary.name)
    remote = workspace / "fixture.git"
    root_a = workspace / "worker-python"
    root_b = workspace / "worker-rust"
    observer_root = workspace / "worker-rust-observer"
    fake_adapter = workspace / "fake-codex"
    log_path = workspace / "fake-adapter-invocations.jsonl"
    try:
        fake_forge = FakeForgeServer()
        _git(None, "init", "--bare", "--initial-branch=main", str(remote))
        _git(None, "clone", str(remote), str(root_a))
        worker_a = Worker("python-worker", inputs.python_worker, root_a)
        worker_b = Worker("rust-worker", inputs.rust_worker, root_b)
        observer = Worker("rust-observer", inputs.rust_worker, observer_root)
        _write_fake_adapter(fake_adapter)
        setup_env = _worker_environment(
            os.environ,
            worker_a,
            inputs=inputs,
            log_path=log_path,
            role="setup",
        )
        _cli(worker_a, ["init"], env=setup_env, timeout=timeout)
        _configure(
            root_a,
            fake_adapter=fake_adapter,
            forge_api_url=fake_forge.api_url,
            providers=["git"],
            mqtt_enabled=inputs.mqtt_enabled,
            ttl_seconds=ttl_seconds,
        )
        run_id = uuid4().hex[:10]
        primary_issue = _create_routed_issue(
            worker_a,
            env=setup_env,
            title=f"Router harness primary {run_id}",
            timeout=timeout,
        )
        secondary_issue = _create_routed_issue(
            worker_a,
            env=setup_env,
            title=f"Router harness secondary {run_id}",
            timeout=timeout,
        )
        _commit_and_push(root_a, "Seed disposable Issue Router project")
        initial_state_sha = _initialize_router_state_branch(root_a)
        _git(None, "clone", str(remote), str(root_b))
        _git(None, "clone", str(remote), str(observer_root))

        base_env = dict(os.environ)
        plan_envs = {
            worker.name: _worker_environment(
                base_env,
                worker,
                inputs=inputs,
                log_path=log_path,
                role="plan",
            )
            for worker in (worker_a, worker_b, observer)
        }
        python_plan = _router_plan(worker_a, plan_envs[worker_a.name], timeout)
        rust_plan = _router_plan(worker_b, plan_envs[worker_b.name], timeout)
        assert_deterministic_plans(
            python_plan,
            rust_plan,
            [primary_issue, secondary_issue],
        )
        print(
            "Python and Rust router plans are byte-identical and deterministically ordered"
        )

        log_path.write_text("", encoding="utf-8")
        release_path = workspace / "release-primary-adapter"
        primary_env = _worker_environment(
            base_env,
            worker_a,
            inputs=inputs,
            log_path=log_path,
            role="primary",
            outcome="completed",
            release_path=release_path,
        )
        primary_process = RunningCommand(
            _cli_command(worker_a, ["router", "run", "--once"]),
            cwd=worker_a.root,
            env=primary_env,
        )
        try:
            _wait_for_fake_role(log_path, "primary", timeout)
            active_state_sha = _assert_shared_state_visible(
                worker_b,
                primary_issue,
                probe_root=workspace / "rust-active-state",
                expected_status="in_progress",
                claim_active=True,
                env=plan_envs[worker_b.name],
                timeout=timeout,
                expected_eligible_issue_ids=[secondary_issue],
            )
            assert_router_state_ref_advanced(initial_state_sha, active_state_sha)
            secondary_env = _worker_environment(
                base_env,
                worker_b,
                inputs=inputs,
                log_path=log_path,
                role="secondary",
                outcome="completed",
            )
            secondary = _cli(
                worker_b,
                ["router", "run", "--once"],
                env=secondary_env,
                timeout=timeout,
                check=False,
            )
            if secondary.returncode != 0 or "completed=1" not in secondary.stdout:
                raise HarnessError(
                    "second Git-only router did not complete the remaining package:\n"
                    + secondary.combined
                )
            _wait_for_fake_role(log_path, "secondary", timeout)
            secondary_output_branch = f"codex/router/{secondary_issue}/r1"
            secondary_output_sha = _remote_ref_sha(root_b, secondary_output_branch)
            assert_output_ref_published(secondary_output_sha, secondary_output_branch)
            secondary_state_sha = _assert_shared_state_visible(
                observer,
                secondary_issue,
                probe_root=workspace / "observer-secondary-state",
                expected_status="review",
                claim_active=False,
                env=plan_envs[observer.name],
                timeout=timeout,
            )
            assert_router_state_ref_advanced(active_state_sha, secondary_state_sha)
            release_path.touch()
            primary = primary_process.finish(timeout)
            if primary.returncode != 0 or "completed=1" not in primary.stdout:
                raise HarnessError(
                    "first Git-only router did not complete its package after "
                    "the second router finished:\n" + primary.combined
                )
        finally:
            release_path.touch()
            primary_process.close()

        observer_env = _worker_environment(
            base_env,
            observer,
            inputs=inputs,
            log_path=log_path,
            role="observer",
        )
        primary_state_sha = _assert_shared_state_visible(
            observer,
            primary_issue,
            probe_root=workspace / "observer-primary-state",
            expected_status="review",
            claim_active=False,
            env=observer_env,
            timeout=timeout,
        )
        assert_router_state_ref_advanced(secondary_state_sha, primary_state_sha)
        primary_output_branch = f"codex/router/{primary_issue}/r1"
        assert_output_ref_published(
            _remote_ref_sha(root_a, primary_output_branch), primary_output_branch
        )
        assert_output_ref_unchanged(
            secondary_output_sha,
            _remote_ref_sha(root_a, secondary_output_branch),
            secondary_output_branch,
        )
        _assert_durable_router_history(
            observer.root,
            primary_issue,
            ref=f"refs/remotes/origin/{ROUTER_STATE_BRANCH}",
        )
        _assert_durable_router_history(
            observer.root,
            secondary_issue,
            ref=f"refs/remotes/origin/{ROUTER_STATE_BRANCH}",
        )
        primary_issue_record = _router_state_issue_json(observer.root, primary_issue)
        secondary_issue_record = _router_state_issue_json(
            observer.root, secondary_issue
        )
        if primary_issue_record.get("status") != "review":
            raise HarnessError(
                "first completed result did not move its package to review"
            )
        if secondary_issue_record.get("status") != "review":
            raise HarnessError(
                "second completed result did not move its package to review"
            )
        if any(
            issue_record.get("assignee") != "harness-human"
            for issue_record in (primary_issue_record, secondary_issue_record)
        ):
            raise HarnessError("router result changed a human assignee")
        calls = _read_fake_calls(log_path)
        call_roles = [call.get("role") for call in calls]
        if sorted(call_roles) != ["primary", "secondary"]:
            raise HarnessError(
                "connected Git-only workers did not execute primary then secondary: "
                f"adapter roles were {call_roles!r}"
            )
        print(
            "connected Git-only coordination verified: the second worker saw the "
            "active primary claim and executed the secondary package"
        )

        print(
            "router-published shared claim, accepted status, and event history "
            "were visible in the independent Rust clone"
        )

        if inputs.mqtt_enabled:
            mqtt_remote = workspace / "mqtt-fixture.git"
            mqtt_root_a = workspace / "mqtt-worker-python"
            mqtt_root_b = workspace / "mqtt-worker-rust"
            _git(None, "init", "--bare", "--initial-branch=main", str(mqtt_remote))
            _git(None, "clone", str(mqtt_remote), str(mqtt_root_a))
            mqtt_worker_a = Worker(
                "mqtt-python-worker", inputs.python_worker, mqtt_root_a
            )
            mqtt_worker_b = Worker("mqtt-rust-worker", inputs.rust_worker, mqtt_root_b)
            mqtt_setup_env = _worker_environment(
                os.environ,
                mqtt_worker_a,
                inputs=inputs,
                log_path=log_path,
                role="mqtt-setup",
            )
            _cli(mqtt_worker_a, ["init"], env=mqtt_setup_env, timeout=timeout)
            _configure(
                mqtt_root_a,
                fake_adapter=fake_adapter,
                forge_api_url=fake_forge.api_url,
                providers=["mqtt", "git"],
                mqtt_enabled=True,
                ttl_seconds=max(ttl_seconds, 30),
                contention_window="5s",
            )
            mqtt_issue = _create_routed_issue(
                mqtt_worker_a,
                env=mqtt_setup_env,
                title=f"Router harness MQTT race {uuid4().hex[:10]}",
                timeout=timeout,
            )
            _commit_and_push(mqtt_root_a, "Seed MQTT soft-coordination router fixture")
            mqtt_initial_state_sha = _initialize_router_state_branch(mqtt_root_a)
            _git(None, "clone", str(mqtt_remote), str(mqtt_root_b))
            _exercise_mqtt_soft_race(
                inputs=inputs,
                worker_a=mqtt_worker_a,
                worker_b=mqtt_worker_b,
                issue_id=mqtt_issue,
                log_path=log_path,
                timeout=timeout,
                initial_state_sha=mqtt_initial_state_sha,
            )

        if inputs.mutex_enabled:
            hard_remote = workspace / "hard-fixture.git"
            hard_root_a = workspace / "hard-worker-python"
            hard_root_b = workspace / "hard-worker-rust"
            _git(None, "init", "--bare", "--initial-branch=main", str(hard_remote))
            _git(None, "clone", str(hard_remote), str(hard_root_a))
            hard_worker_a = Worker(
                "hard-python-worker", inputs.python_worker, hard_root_a
            )
            hard_worker_b = Worker("hard-rust-worker", inputs.rust_worker, hard_root_b)
            hard_setup_env = _worker_environment(
                os.environ,
                hard_worker_a,
                inputs=inputs,
                log_path=log_path,
                role="hard-setup",
            )
            _cli(hard_worker_a, ["init"], env=hard_setup_env, timeout=timeout)
            _configure(
                hard_root_a,
                fake_adapter=fake_adapter,
                forge_api_url=fake_forge.api_url,
                providers=["git"],
                mqtt_enabled=inputs.mqtt_enabled,
                ttl_seconds=ttl_seconds,
            )
            hard_issue = _create_routed_issue(
                hard_worker_a,
                env=hard_setup_env,
                title=f"Router harness hard mutex {uuid4().hex[:10]}",
                timeout=timeout,
            )
            _commit_and_push(hard_root_a, "Seed hard-mutex router fixture")
            _git(None, "clone", str(hard_remote), str(hard_root_b))
            log_path.write_text("", encoding="utf-8")
            _exercise_hard_mutex(
                inputs=inputs,
                worker_a=hard_worker_a,
                worker_b=hard_worker_b,
                issue_id=hard_issue,
                fake_adapter=fake_adapter,
                forge_api_url=fake_forge.api_url,
                log_path=log_path,
                timeout=timeout,
                ttl_seconds=ttl_seconds,
            )

        if keep:
            temporary._finalizer.detach()
            print(f"fixture retained at: {workspace}")
            return workspace
        return None
    except Exception:
        if keep:
            temporary._finalizer.detach()
            print(f"failed fixture retained at: {workspace}", file=sys.stderr)
        else:
            temporary.cleanup()
        raise
    finally:
        if "fake_forge" in locals():
            fake_forge.close()
        if not keep:
            temporary.cleanup()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse harness options and report integration failures.

    :param argv: Optional command-line arguments.
    :type argv: Sequence[str] | None
    :return: Process exit status.
    :rtype: int
    """
    parser = argparse.ArgumentParser(
        description=(
            "Run disposable Python and Rust Kanbus Issue Router workers against "
            "a temporary bare Git remote."
        )
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="enable live MQTT and optional Mutex API scenarios (requires the env gate)",
    )
    parser.add_argument(
        "--keep", action="store_true", help="retain the disposable fixture"
    )
    parser.add_argument(
        "--python-worker",
        help="Python CLI command prefix; defaults to KANBUS_HARNESS_PYTHON_WORKER or this interpreter",
    )
    parser.add_argument(
        "--rust-worker",
        help="Rust CLI command prefix; defaults to KANBUS_HARNESS_RUST_WORKER or kbs",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="maximum wait for each router CLI process (default: 60)",
    )
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=15,
        help="live Mutex API lease TTL (1 to 30; default: 15)",
    )
    arguments = parser.parse_args(argv)
    try:
        run_harness(
            live=arguments.live,
            keep=arguments.keep,
            timeout=arguments.timeout_seconds,
            ttl_seconds=arguments.ttl_seconds,
            python_worker=arguments.python_worker,
            rust_worker=arguments.rust_worker,
        )
    except HarnessError as error:
        print(
            f"Issue Router integration harness failed: {redact_output(str(error), os.environ)}",
            file=sys.stderr,
        )
        return 1
    print("Issue Router integration harness passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
