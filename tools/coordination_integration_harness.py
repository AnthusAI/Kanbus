"""Opt-in live integration check for isolated Kanbus coordination workers.

This is a dispatcher fixture around the Kanbus CLI coordination primitives. It
does not implement or validate a production router.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import uuid4

ENABLE_ENV = "KANBUS_RUN_LIVE_COORDINATION_HARNESS"
REQUIRED_ENV = {
    "mutex_endpoint": "KANBUS_HARNESS_MUTEX_API_ENDPOINT",
    "mutex_token": "KANBUS_HARNESS_MUTEX_API_TOKEN",
    "mqtt_broker": "KANBUS_HARNESS_MQTT_BROKER",
    "mqtt_authorizer": "KANBUS_HARNESS_MQTT_CUSTOM_AUTHORIZER",
    "mqtt_token": "KANBUS_HARNESS_MQTT_API_TOKEN",
    "tenant_account": "KANBUS_HARNESS_TENANT_ACCOUNT",
    "tenant_project": "KANBUS_HARNESS_TENANT_PROJECT",
    "python_worker": "KANBUS_HARNESS_PYTHON_WORKER",
    "rust_worker": "KANBUS_HARNESS_RUST_WORKER",
}
MUTEX_ENDPOINT_ENV = "KANBUS_COORDINATION_MUTEX_API_ENDPOINT"
MUTEX_TOKEN_ENV = "KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN"
MQTT_ENV = {
    "KANBUS_REALTIME_TRANSPORT": "mqtt",
    "KANBUS_REALTIME_AUTOSTART": "false",
    "KANBUS_REALTIME_KEEPALIVE": "false",
}
ISSUE_ID_RE = re.compile(r"(?m)^\s*ID:\s+([A-Za-z0-9][A-Za-z0-9_-]*)\s*$")
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
HELD_PATTERNS = ("lease already held", "held lease", "lease is held")
WATCH_STARTUP_GRACE_SECONDS = 3.0


class HarnessError(RuntimeError):
    """A configuration, setup, or assertion failure in the harness."""


@dataclass(frozen=True)
class Inputs:
    mutex_endpoint: str
    mutex_token: str
    mqtt_broker: str
    mqtt_authorizer: str
    mqtt_token: str
    tenant_account: str
    tenant_project: str
    python_worker: tuple[str, ...]
    rust_worker: tuple[str, ...]


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def combined(self) -> str:
        return f"{self.stdout}\n{self.stderr}"


@dataclass(frozen=True)
class Worker:
    name: str
    command: tuple[str, ...]
    root: Path


def gossip_watch_command(worker: Worker, broker: str) -> tuple[str, ...]:
    """Build the explicit MQTT-only watcher command used by the delivery probe."""
    return (
        *worker.command,
        "--no-guidance",
        "--no-hooks",
        "gossip",
        "watch",
        "--transport",
        "mqtt",
        "--broker",
        broker,
        "--no-autostart",
        "--print",
    )


def is_matching_claim_envelope(
    envelope: object, *, resource: str, owner: str, claim_id: str
) -> bool:
    """Validate the common wire fields and match a coordination CLAIM."""
    if not isinstance(envelope, dict):
        return False
    required_strings = ("id", "project", "event_id", "producer_id", "ts")
    if any(
        not isinstance(envelope.get(key), str) or not envelope[key]
        for key in required_strings
    ):
        return False
    try:
        timestamp = datetime.fromisoformat(envelope["ts"].replace("Z", "+00:00"))
    except ValueError:
        return False
    ttl = envelope.get("lease_ttl_s")
    if (
        timestamp.tzinfo is None
        or isinstance(ttl, bool)
        or not isinstance(ttl, int)
        or ttl <= 0
        or envelope.get("expires_at") is not None
    ):
        return False
    return (
        envelope.get("type") == "coordination.claim"
        and envelope.get("resource") == resource
        and envelope.get("owner") == owner
        and envelope.get("claim_id") == claim_id
    )


def terminate_process_tree(
    process: subprocess.Popen, grace_seconds: float = 3.0
) -> None:
    """Stop a watcher and any child CLI process started by a command wrapper."""
    is_posix_group = os.name == "posix"
    if is_posix_group:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        if is_posix_group:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        process.wait(timeout=grace_seconds)
    if is_posix_group:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        os.killpg(process.pid, signal.SIGKILL)


class MqttWatcher:
    """Capture a CLI MQTT watch process and stop it with its process group."""

    def __init__(self, worker: Worker, broker: str, env: Mapping[str, str]) -> None:
        self.env = dict(env)
        try:
            self.process = subprocess.Popen(
                gossip_watch_command(worker, broker),
                cwd=worker.root,
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=os.name == "posix",
            )
        except OSError as error:
            raise HarnessError(
                f"could not start MQTT gossip watcher: {error}"
            ) from error
        self.stdout_lines: queue.Queue[str] = queue.Queue()
        self.stderr_tail: deque[str] = deque(maxlen=40)
        self._stdout_reader = threading.Thread(
            target=self._read_stdout, name="kanbus-mqtt-watch-stdout", daemon=True
        )
        self._stderr_reader = threading.Thread(
            target=self._read_stderr, name="kanbus-mqtt-watch-stderr", daemon=True
        )
        self._stdout_reader.start()
        self._stderr_reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.stdout_lines.put(line.rstrip("\r\n"))

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self.stderr_tail.append(_redact(line.rstrip("\r\n"), self.env))

    def wait_until_running(
        self, grace_seconds: float = WATCH_STARTUP_GRACE_SECONDS
    ) -> None:
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            status = self.process.poll()
            if status is not None:
                raise HarnessError(self._failure_message(status))
            time.sleep(min(0.1, max(0.01, deadline - time.monotonic())))

    def wait_for_claim(
        self, *, resource: str, owner: str, claim_id: str, timeout: float
    ) -> dict:
        deadline = time.monotonic() + timeout
        malformed_match = False
        while time.monotonic() < deadline:
            status = self.process.poll()
            if status is not None and self.stdout_lines.empty():
                raise HarnessError(self._failure_message(status))
            try:
                line = self.stdout_lines.get(
                    timeout=min(0.2, max(0.01, deadline - time.monotonic()))
                )
            except queue.Empty:
                continue
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(envelope, dict)
                and envelope.get("resource") == resource
                and envelope.get("owner") == owner
                and envelope.get("claim_id") == claim_id
            ):
                if is_matching_claim_envelope(
                    envelope, resource=resource, owner=owner, claim_id=claim_id
                ):
                    return envelope
                malformed_match = True
        if malformed_match:
            raise HarnessError(
                "MQTT watcher received the probe claim with an invalid envelope"
            )
        raise HarnessError(
            f"MQTT watcher did not receive the probe claim within {timeout:g}s; "
            f"watcher stderr: {' | '.join(self.stderr_tail)}"
        )

    def _failure_message(self, status: int | None) -> str:
        return (
            f"MQTT gossip watcher exited before delivery (status={status}); "
            f"stderr: {' | '.join(self.stderr_tail)}"
        )

    def close(self) -> None:
        terminate_process_tree(self.process)
        self._stdout_reader.join(timeout=1.0)
        self._stderr_reader.join(timeout=1.0)
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


def parse_command(value: str, name: str) -> tuple[str, ...]:
    """Parse an executable command prefix without invoking a shell."""
    command = tuple(shlex.split(value))
    if not command:
        raise HarnessError(f"{name} must be a non-empty executable command")
    return command


def require_inputs(env: Mapping[str, str]) -> Inputs:
    """Load explicit live service credentials and worker command prefixes."""
    if env.get(ENABLE_ENV) != "1":
        raise HarnessError(
            f"live execution is disabled; set {ENABLE_ENV}=1 to run the harness"
        )
    missing = [
        variable
        for variable in REQUIRED_ENV.values()
        if not env.get(variable, "").strip()
    ]
    if missing:
        raise HarnessError("missing required environment inputs: " + ", ".join(missing))

    mutex_endpoint = env[REQUIRED_ENV["mutex_endpoint"]].strip().rstrip("/")
    parsed_mutex = urllib.parse.urlsplit(mutex_endpoint)
    if parsed_mutex.scheme not in {"http", "https"} or not parsed_mutex.netloc:
        raise HarnessError("mutex API endpoint must be an absolute http(s) URL")

    mqtt_broker = env[REQUIRED_ENV["mqtt_broker"]].strip()
    parsed_mqtt = urllib.parse.urlsplit(mqtt_broker)
    if parsed_mqtt.scheme not in {"mqtt", "mqtts"} or not parsed_mqtt.hostname:
        raise HarnessError("MQTT broker must be an absolute mqtt:// or mqtts:// URL")

    tenant_account = env[REQUIRED_ENV["tenant_account"]].strip()
    tenant_project = env[REQUIRED_ENV["tenant_project"]].strip()
    for name, value in (
        ("tenant account", tenant_account),
        ("tenant project", tenant_project),
    ):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
            raise HarnessError(
                f"{name} must be a non-empty MQTT topic segment containing only "
                "letters, digits, '.', '_', or '-'"
            )

    return Inputs(
        mutex_endpoint=mutex_endpoint,
        mutex_token=env[REQUIRED_ENV["mutex_token"]].strip(),
        mqtt_broker=mqtt_broker,
        mqtt_authorizer=env[REQUIRED_ENV["mqtt_authorizer"]].strip(),
        mqtt_token=env[REQUIRED_ENV["mqtt_token"]].strip(),
        tenant_account=tenant_account,
        tenant_project=tenant_project,
        python_worker=parse_command(
            env[REQUIRED_ENV["python_worker"]], "Python worker"
        ),
        rust_worker=parse_command(env[REQUIRED_ENV["rust_worker"]], "Rust worker"),
    )


def parse_issue_id(output: str) -> str:
    """Extract the ID shown by the normal CLI create command."""
    match = ISSUE_ID_RE.search(ANSI_RE.sub("", output))
    if not match:
        raise HarnessError("could not read the disposable task ID from CLI output")
    return match.group(1)


def output_fields(output: str) -> dict[str, str]:
    """Read simple key/value lines from coordination CLI output."""
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if re.fullmatch(r"[a-z_]+", key.strip()):
            fields[key.strip()] = value.strip()
    return fields


def held_lease_result(result: CommandResult) -> bool:
    text = result.combined.lower()
    return result.returncode != 0 and any(pattern in text for pattern in HELD_PATTERNS)


def _redact(text: str, env: Mapping[str, str] | None) -> str:
    if env is None:
        return text
    for name, value in env.items():
        if value and re.search(
            r"token|secret|password|credential", name, re.IGNORECASE
        ):
            text = text.replace(value, "<redacted>")
    return text


def _run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    check: bool = True,
) -> CommandResult:
    try:
        completed = subprocess.run(
            list(args),
            cwd=cwd,
            env=None if env is None else dict(env),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        raise HarnessError(f"command not found: {args[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise HarnessError(
            f"command timed out after {timeout:g}s: {shlex.join(args)}"
        ) from error
    result = CommandResult(
        completed.returncode,
        _redact(completed.stdout, env),
        _redact(completed.stderr, env),
    )
    if check and result.returncode != 0:
        raise HarnessError(
            f"command failed ({result.returncode}): {shlex.join(args)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result


def _git(root: Path | None, *args: str, check: bool = True) -> CommandResult:
    command = ["git"]
    if root is not None:
        command.extend(["-C", str(root)])
    command.extend(args)
    return _run(command, check=check)


def _cli(
    worker: Worker,
    args: Sequence[str],
    *,
    env: Mapping[str, str],
    timeout: float = 30.0,
    check: bool = True,
) -> CommandResult:
    # Disable optional guidance/hooks in this disposable fixture so test setup
    # stays local and deterministic.
    command = [*worker.command, "--no-guidance", "--no-hooks", *args]
    return _run(command, cwd=worker.root, env=env, timeout=timeout, check=check)


def _worker_environment(
    base_env: Mapping[str, str], inputs: Inputs, worker: Worker, *, mutex: bool
) -> dict[str, str]:
    env = dict(base_env)
    env.update(MQTT_ENV)
    env["KANBUS_REALTIME_BROKER"] = inputs.mqtt_broker
    env["KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME"] = inputs.mqtt_authorizer
    env["KANBUS_REALTIME_MQTT_API_TOKEN"] = inputs.mqtt_token
    env["KANBUS_REALTIME_TOPICS_PROJECT_EVENTS"] = (
        f"projects/{inputs.tenant_account}/{inputs.tenant_project}/events"
    )
    env["KANBUS_REALTIME_UDS_SOCKET_PATH"] = str(
        worker.root / ".kanbus-private-uds.sock"
    )
    if mutex:
        env[MUTEX_ENDPOINT_ENV] = inputs.mutex_endpoint
        env[MUTEX_TOKEN_ENV] = inputs.mutex_token
    else:
        # Provider config also excludes mutex_api during the soft duplicate
        # phase; clear inherited credentials so that phase cannot acquire hard.
        env[MUTEX_ENDPOINT_ENV] = ""
        env[MUTEX_TOKEN_ENV] = ""
    return env


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as error:
        raise HarnessError(
            "PyYAML is required by the harness; run it with the py311 environment"
        ) from error
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise HarnessError(f"expected a YAML mapping in {path}")
    return value


def _write_yaml(path: Path, value: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _configure(root: Path, *, providers: list[str], ttl_seconds: int) -> None:
    config_path = root / ".kanbus.yml"
    configuration = _load_yaml(config_path)
    coordination = configuration.setdefault("coordination", {})
    coordination["providers"] = providers
    coordination["contention_window"] = "1s"
    coordination["default_lease_ttl"] = f"{ttl_seconds}s"
    coordination["mutex_api"] = {"endpoint": None, "bearer_token": None}
    realtime = configuration.setdefault("realtime", {})
    realtime.update(
        {
            "transport": "mqtt",
            "broker": "mqtt://127.0.0.1:1883",
            "autostart": False,
            "keepalive": False,
            "uds_socket_path": None,
            "mqtt_custom_authorizer_name": None,
            "mqtt_api_token": None,
        }
    )
    _write_yaml(config_path, configuration)


def _commit_and_push(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    staged = _git(root, "diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        return
    _run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Kanbus integration harness",
            "-c",
            "user.email=kanbus-harness@example.invalid",
            "commit",
            "--no-verify",
            "-m",
            message,
        ]
    )
    _git(root, "push", "--set-upstream", "origin", "main")


def _parallel_claims(
    workers: Sequence[Worker],
    *,
    envs: Mapping[str, Mapping[str, str]],
    resource: str,
    revisions: Mapping[str, int],
    claim_ids: Mapping[str, str],
    task_id: str | None = None,
    timeout: float,
) -> dict[str, CommandResult]:
    barrier = threading.Barrier(len(workers) + 1)
    results: dict[str, CommandResult] = {}
    failures: list[Exception] = []

    def claim(worker: Worker) -> None:
        try:
            barrier.wait(timeout=timeout)
            args = [
                "coordination",
                "claim",
                "--resource",
                resource,
                "--owner",
                worker.name,
                "--claim-id",
                claim_ids[worker.name],
                "--revision",
                str(revisions[worker.name]),
            ]
            claim_result = _cli(
                worker,
                args,
                env=envs[worker.name],
                timeout=timeout,
                check=False,
            )
            if task_id is not None and claim_result.returncode == 0:
                transition = _cli(
                    worker,
                    ["update", task_id, "--status", "in_progress"],
                    env=envs[worker.name],
                    timeout=timeout,
                    check=False,
                )
                results[worker.name] = CommandResult(
                    transition.returncode,
                    f"{claim_result.stdout}{transition.stdout}",
                    f"{claim_result.stderr}{transition.stderr}",
                )
            else:
                results[worker.name] = claim_result
        except (HarnessError, threading.BrokenBarrierError, TimeoutError) as error:
            failures.append(error)

    threads = [threading.Thread(target=claim, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=timeout)
    for thread in threads:
        thread.join(timeout=timeout + 1.0)
    if any(thread.is_alive() for thread in threads):
        raise HarnessError("a worker did not finish its coordination command")
    if failures:
        raise HarnessError(
            f"worker process could not start: {failures[0]}"
        ) from failures[0]
    return results


def _assert_one_hard_winner(
    results: Mapping[str, CommandResult], expected_workers: set[str]
) -> tuple[str, str]:
    if set(results) != expected_workers:
        raise HarnessError("both isolated workers must return a result")
    successes = [name for name, result in results.items() if result.returncode == 0]
    losers = [name for name, result in results.items() if held_lease_result(result)]
    if len(successes) != 1 or len(losers) != 1:
        details = "\n".join(
            f"{name}: exit={result.returncode}\n{result.combined}"
            for name, result in results.items()
        )
        raise HarnessError(
            "expected exactly one hard acquire and one held-lease response;\n" + details
        )
    winner = successes[0]
    fields = output_fields(results[winner].stdout)
    if (
        fields.get("provider") != "mutex_api"
        or fields.get("state") != "active hard mutex"
    ):
        raise HarnessError(
            f"winning worker did not report an active hard mutex: {fields}"
        )
    return winner, losers[0]


def _probe_mqtt_delivery(
    watcher_worker: Worker,
    publisher_worker: Worker,
    *,
    inputs: Inputs,
    watcher_env: Mapping[str, str],
    publisher_env: Mapping[str, str],
    resource: str,
    claim_id: str,
    timeout: float,
) -> dict:
    """Prove a claim published by one runtime arrives at the other runtime."""
    with MqttWatcher(watcher_worker, inputs.mqtt_broker, watcher_env) as watcher:
        watcher.wait_until_running()
        published = _cli(
            publisher_worker,
            [
                "coordination",
                "claim",
                "--resource",
                resource,
                "--owner",
                publisher_worker.name,
                "--claim-id",
                claim_id,
                "--revision",
                "1",
            ],
            env=publisher_env,
            timeout=min(timeout, 15.0),
            check=False,
        )
        fields = output_fields(published.stdout)
        if (
            published.returncode != 0
            or fields.get("provider") != "mqtt"
            or fields.get("state") != "active soft ownership"
        ):
            raise HarnessError(
                "MQTT delivery probe publisher did not use the MQTT provider:\n"
                + published.combined
            )
        return watcher.wait_for_claim(
            resource=resource,
            owner=publisher_worker.name,
            claim_id=claim_id,
            timeout=timeout,
        )


def _inspect(worker: Worker, env: Mapping[str, str], resource: str) -> dict[str, str]:
    result = _cli(
        worker,
        ["coordination", "inspect", "--resource", resource],
        env=env,
        timeout=15.0,
    )
    return output_fields(result.stdout)


def _wait_for_expiry(
    worker: Worker,
    env: Mapping[str, str],
    resource: str,
    expires_at: str,
    ttl_seconds: int,
) -> None:
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise HarnessError(
            f"invalid expires_at value returned by inspect: {expires_at}"
        ) from error
    timeout_at = time.monotonic() + ttl_seconds + 15
    while time.monotonic() < timeout_at:
        fields = _inspect(worker, env, resource)
        if fields.get("state") == "eligible":
            return
        if datetime.now(UTC) < expiry:
            time.sleep(
                min(0.25, max(0.05, (expiry - datetime.now(UTC)).total_seconds()))
            )
        else:
            time.sleep(0.25)
    raise HarnessError("hard lease did not expire within the configured TTL window")


def _best_effort_release(
    inputs: Inputs, resource: str, leases: Sequence[tuple[str, str]]
) -> None:
    """Release only this run's unique hard resource, if a known claim remains."""
    url = (
        f"{inputs.mutex_endpoint}/api/coordination/leases/"
        f"{urllib.parse.quote(resource, safe='')}"
    )
    for owner, claim_id in leases:
        payload = json.dumps({"owner": owner, "claim_id": claim_id}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {inputs.mutex_token}",
                "Content-Type": "application/json",
            },
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(request, timeout=3.0):
                pass
        except (urllib.error.URLError, TimeoutError, OSError):
            pass


def _fixture_status(worker: Worker, env: Mapping[str, str], task_id: str) -> str:
    result = _cli(worker, ["show", task_id, "--json"], env=env)
    try:
        task = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise HarnessError("CLI show --json did not return valid JSON") from error
    if not isinstance(task, dict) or not isinstance(task.get("status"), str):
        raise HarnessError("CLI show --json did not include task status")
    return task["status"]


def _preflight(inputs: Inputs, cwd: Path) -> None:
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
        result = _run(
            [*command, "--no-guidance", "--no-hooks", "coordination", "--help"],
            cwd=cwd,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise HarnessError(
                f"{name} worker does not expose the coordination CLI:\n{result.stdout}{result.stderr}"
            )


def run_harness(*, keep: bool, ttl_seconds: int, timeout: float) -> Path | None:
    inputs = require_inputs(os.environ)
    if not 1 <= ttl_seconds <= 30:
        raise HarnessError("TTL must be between 1 and 30 seconds for a bounded test")
    _preflight(inputs, Path.cwd())

    temporary = tempfile.TemporaryDirectory(prefix="kanbus-coordination-harness-")
    workspace = Path(temporary.name)
    remote = workspace / "fixture.git"
    root_a = workspace / "worker-python"
    root_b = workspace / "worker-rust"
    try:
        root_a.mkdir()
        root_b.mkdir()
        _git(None, "init", "--bare", "--initial-branch=main", str(remote))
        _git(None, "clone", str(remote), str(root_a))
        _git(None, "clone", str(remote), str(root_b))
    except Exception:
        temporary.cleanup()
        raise

    worker_a = Worker("python-worker", inputs.python_worker, root_a)
    worker_b = Worker("rust-worker", inputs.rust_worker, root_b)
    workers = (worker_a, worker_b)
    base_env = dict(os.environ)
    hard_envs = {
        worker.name: _worker_environment(base_env, inputs, worker, mutex=True)
        for worker in workers
    }
    soft_envs = {
        worker.name: _worker_environment(base_env, inputs, worker, mutex=False)
        for worker in workers
    }
    lease_resource: str | None = None
    known_claims: list[tuple[str, str]] = []

    try:
        _cli(worker_a, ["init"], env=hard_envs[worker_a.name])
        _configure(
            root_a, providers=["mutex_api", "mqtt", "git"], ttl_seconds=ttl_seconds
        )
        run_id = uuid4().hex
        title = f"Disposable coordination fixture {run_id[:10]}"
        created = _cli(
            worker_a,
            [
                "create",
                title,
                "--type",
                "task",
                "--description",
                "Temporary integration fixture for the CLI coordination dispatcher; not a production router.",
            ],
            env=hard_envs[worker_a.name],
        )
        task_id = parse_issue_id(created.stdout)
        lease_resource = f"harness:{run_id}:issue:{task_id}"
        if _fixture_status(worker_a, hard_envs[worker_a.name], task_id) != "open":
            raise HarnessError("new disposable task did not start in the open status")
        _commit_and_push(root_a, "Create disposable coordination fixture")
        _git(root_b, "fetch", "origin", "main")
        _git(root_b, "checkout", "-B", "main", "FETCH_HEAD")

        for root in (root_a, root_b):
            _configure(root, providers=["mqtt", "git"], ttl_seconds=ttl_seconds)
        mqtt_probe_resource = f"harness:{run_id}:mqtt-delivery-probe"
        mqtt_probe_claim_id = f"mqtt-probe-{uuid4().hex}"
        envelope = _probe_mqtt_delivery(
            worker_a,
            worker_b,
            inputs=inputs,
            watcher_env=soft_envs[worker_a.name],
            publisher_env=soft_envs[worker_b.name],
            resource=mqtt_probe_resource,
            claim_id=mqtt_probe_claim_id,
            timeout=timeout,
        )
        print(
            "MQTT delivery verified across runtimes: "
            f"{worker_b.name} -> {worker_a.name} ({envelope['type']})"
        )
        for root in (root_a, root_b):
            _configure(
                root, providers=["mutex_api", "mqtt", "git"], ttl_seconds=ttl_seconds
            )

        claim_ids = {worker.name: f"claim-{uuid4().hex}" for worker in workers}
        known_claims.extend((worker.name, claim_ids[worker.name]) for worker in workers)
        race = _parallel_claims(
            workers,
            envs=hard_envs,
            resource=lease_resource,
            revisions={worker_a.name: 1, worker_b.name: 1},
            claim_ids=claim_ids,
            task_id=task_id,
            timeout=timeout,
        )
        winner_name, loser_name = _assert_one_hard_winner(
            race, {worker.name for worker in workers}
        )
        winner = next(worker for worker in workers if worker.name == winner_name)
        loser = next(worker for worker in workers if worker.name == loser_name)
        print(f"hard acquire winner: {winner.name}")
        print(f"hard acquire loser: {loser.name} (held lease)")

        inspected = _inspect(loser, hard_envs[loser.name], lease_resource)
        if (
            inspected.get("provider") != "mutex_api"
            or inspected.get("owner") != winner_name
        ):
            raise HarnessError(
                f"inspect did not expose the hard lease owner: {inspected}"
            )
        expiry = inspected.get("expires_at")
        if not expiry:
            raise HarnessError("hard lease inspect output omitted expires_at")

        if _fixture_status(winner, hard_envs[winner.name], task_id) != "in_progress":
            raise HarnessError(
                "the hard-lease winner did not progress the fixture task"
            )
        _commit_and_push(winner.root, "Progress fixture after hard acquire")
        _git(loser.root, "pull", "--ff-only", "origin", "main")

        _wait_for_expiry(
            loser, hard_envs[loser.name], lease_resource, expiry, ttl_seconds
        )
        takeover_claim_id = f"claim-{uuid4().hex}"
        known_claims.append((loser.name, takeover_claim_id))
        takeover = _cli(
            loser,
            [
                "coordination",
                "claim",
                "--resource",
                lease_resource,
                "--owner",
                loser.name,
                "--claim-id",
                takeover_claim_id,
                "--revision",
                "2",
            ],
            env=hard_envs[loser.name],
            timeout=15,
            check=False,
        )
        takeover_fields = output_fields(takeover.stdout)
        if (
            takeover.returncode != 0
            or takeover_fields.get("state") != "active hard mutex"
        ):
            raise HarnessError(
                "expired hard lease did not allow takeover:\n" + takeover.combined
            )
        takeover_inspect = _inspect(winner, hard_envs[winner.name], lease_resource)
        if takeover_inspect.get("owner") != loser.name:
            raise HarnessError(
                f"inspect did not expose the takeover owner: {takeover_inspect}"
            )

        released = _cli(
            loser,
            [
                "coordination",
                "release",
                "--resource",
                lease_resource,
                "--owner",
                loser.name,
                "--claim-id",
                takeover_claim_id,
            ],
            env=hard_envs[loser.name],
            check=False,
        )
        if (
            released.returncode != 0
            or output_fields(released.stdout).get("state") != "released"
        ):
            raise HarnessError(
                "takeover owner could not release its hard lease:\n" + released.combined
            )
        if (
            _inspect(winner, hard_envs[winner.name], lease_resource).get("state")
            != "eligible"
        ):
            raise HarnessError("inspect did not report eligible after release")

        for root in (root_a, root_b):
            _configure(root, providers=["mqtt", "git"], ttl_seconds=ttl_seconds)
        soft_resource = f"soft:{lease_resource}"
        soft_claim_ids = {worker.name: f"soft-{uuid4().hex}" for worker in workers}
        soft_results = _parallel_claims(
            workers,
            envs=soft_envs,
            resource=soft_resource,
            revisions={worker_a.name: 1, worker_b.name: 1},
            claim_ids=soft_claim_ids,
            timeout=timeout,
        )
        if any(result.returncode != 0 for result in soft_results.values()):
            details = "\n".join(
                f"{name}: exit={result.returncode}\n{result.combined}"
                for name, result in soft_results.items()
            )
            raise HarnessError(
                "mutex-off soft claims did not both succeed:\n" + details
            )
        if any(
            "active hard mutex" in result.stdout for result in soft_results.values()
        ):
            raise HarnessError("mutex-off claims unexpectedly reported hard ownership")
        print(
            "mutex-off claims: both isolated workers succeeded with soft coordination"
        )
        print(f"disposable task: {task_id} (status=in_progress)")

        if keep:
            return workspace
        return None
    finally:
        if lease_resource is not None:
            _best_effort_release(inputs, lease_resource, known_claims)
        if keep:
            temporary._finalizer.detach()
            print(f"fixture retained at: {workspace}")
        else:
            temporary.cleanup()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run an explicitly enabled live coordination check with a temporary "
            "bare Git remote and two isolated CLI workers."
        )
    )
    parser.add_argument(
        "--keep", action="store_true", help="retain temporary fixture files"
    )
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=5,
        help="short hard lease TTL in seconds (1 to 30; default: 5)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="maximum wait for each worker CLI process (default: 30)",
    )
    arguments = parser.parse_args(argv)
    try:
        run_harness(
            keep=arguments.keep,
            ttl_seconds=arguments.ttl_seconds,
            timeout=arguments.timeout_seconds,
        )
    except HarnessError as error:
        print(f"coordination harness failed: {error}", file=sys.stderr)
        return 1
    print("coordination harness passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
