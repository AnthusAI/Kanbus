"""Structured agent contracts for Issue Router execution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from kanbus.issue_router import IssueRouterError
from kanbus.models import RouterAgentProfile
from kanbus.router_conversation import codex_session_id


class RouterIssueUpdate(BaseModel):
    """Agent-proposed issue status update."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1)
    status: str = Field(min_length=1)


class RouterIssueComment(BaseModel):
    """Agent-proposed comment to persist on an issue in its package."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class RouterCheckpoint(BaseModel):
    """Agent-reported checkpoint reference."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1)
    revision: int = Field(ge=1)


class RouterArtifact(BaseModel):
    """Agent-reported artifact reference."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    ref: str = Field(min_length=1)


class RouterAgentResult(BaseModel):
    """Validated result returned by a structured router adapter."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    outcome: str
    summary: str = ""
    issue_updates: list[RouterIssueUpdate] = Field(default_factory=list)
    issue_comments: list[RouterIssueComment] = Field(default_factory=list)
    checkpoint: RouterCheckpoint | None = None
    artifacts: list[RouterArtifact] = Field(default_factory=list)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _reject_boolean_version(cls, value: Any) -> Any:
        """``True == 1`` in Python; the contract version must be the number 1."""
        if isinstance(value, bool):
            raise ValueError("schema_version must be the number 1")
        return value

    def validate_outcome(self, name: str = "Codex") -> RouterAgentResult:
        """Require one supported result outcome."""
        if self.outcome not in {"completed", "blocked", "retryable_failure"}:
            raise IssueRouterError(f'invalid {name} router outcome "{self.outcome}"')
        return self


class RouterExecutionRequest(BaseModel):
    """Bounded request delivered to an agent adapter."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    package_id: str
    claim_id: str
    revision: int = Field(ge=1)
    package_issue_ids: list[str]
    checkpoint: RouterCheckpoint | None = None
    worktree_path: str
    # Set when a human replied to a blocked agent: continue that saved session.
    resume_session_id: str | None = None
    reply: str | None = None


class RouterAdapter(Protocol):
    """Narrow execution and cancellation surface required by the router."""

    def execute(self, request: RouterExecutionRequest) -> RouterAgentResult:
        """Run one bounded package and return its structured result."""

    def cancel(self, claim_id: str) -> None:
        """Request cancellation for one active claim."""


class _SubprocessAdapter:
    """Shared subprocess lifecycle for CLI-backed router adapters."""

    display_name = "Codex"
    # OpenCode binds a session to the directory it started in and, resumed from
    # anywhere else, silently does nothing and hangs. Such an adapter is only
    # resumed in its original worktree.
    resume_requires_original_directory = False

    def __init__(
        self,
        profile: RouterAgentProfile,
        *,
        process_record_path: Path | None = None,
        state_dir: Path | None = None,
    ) -> None:
        self.profile = profile
        self.process_record_path = process_record_path
        self.state_dir = state_dir
        self.process: subprocess.Popen[str] | None = None
        self.last_output = ""
        self.last_error = ""
        self.session_id: str | None = None

    def execute(self, request: RouterExecutionRequest) -> RouterAgentResult:
        """Invoke Codex with a package-bounded structured-result prompt.

        :param request: Validated current-claim execution request.
        :type request: RouterExecutionRequest
        :return: Validated structured Codex result.
        :rtype: RouterAgentResult
        :raises IssueRouterError: If Codex exits unsuccessfully or returns invalid JSON.
        """
        command = self._build_command(request)
        try:
            self.process = subprocess.Popen(
                command,
                cwd=request.worktree_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._environment(request),
                **self._popen_extras(),
            )
            self._record_process(request)
            stdout, stderr = self.process.communicate(timeout=3600)
            self.last_output = stdout
            self.last_error = stderr
            self.session_id = self._session_id(stdout)
            return_code = self.process.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                self.process.communicate()
            raise IssueRouterError(
                f"{self.display_name} router adapter failed"
            ) from error
        finally:
            self.process = None
            self._remove_process_record(request.claim_id)
            self._cleanup()
        if return_code != 0:
            raise IssueRouterError(f"{self.display_name} router adapter failed")
        payload = self._result_payload(stdout)
        return self._parse(payload)

    def _build_command(self, request: RouterExecutionRequest) -> list[str]:
        raise NotImplementedError

    def _session_id(self, stdout: str) -> str | None:
        return codex_session_id(stdout)

    def _result_payload(self, stdout: str) -> dict[str, Any]:
        return _find_result_payload(stdout)

    def _popen_extras(self) -> dict[str, Any]:
        return {}

    def _cleanup(self) -> None:
        """Release per-run resources after the subprocess exits."""

    def _parse(self, payload: dict[str, Any]) -> RouterAgentResult:
        return _parse_result(payload, self.display_name)

    def _environment(self, request: RouterExecutionRequest) -> dict[str, str] | None:
        if not self.profile.env:
            return None
        return {**os.environ, **self.profile.env}

    def cancel(self, claim_id: str) -> None:
        """Terminate the active Codex subprocess when one is registered.

        :param claim_id: Active claim identifier.
        :type claim_id: str
        """
        del claim_id
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()

    def _record_process(self, request: RouterExecutionRequest) -> None:
        if self.process_record_path is None or self.process is None:
            return
        path = self.process_record_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "package_id": request.package_id,
                    "claim_id": request.claim_id,
                    "pid": self.process.pid,
                    "process_identity": _process_identity(self.process.pid),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _remove_process_record(self, claim_id: str) -> None:
        path = self.process_record_path
        if path is None or not path.is_file():
            return
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if record.get("claim_id") == claim_id:
            path.unlink(missing_ok=True)


class CodexExecAdapter(_SubprocessAdapter):
    """Run the configured Codex CLI with JSONL output."""

    def _popen_extras(self) -> dict[str, Any]:
        # The prompt is an argument. An inherited stdin makes `codex exec` print
        # "Reading additional input from stdin" and can wait for EOF indefinitely.
        return {"stdin": subprocess.DEVNULL}

    def _build_command(self, request: RouterExecutionRequest) -> list[str]:
        model = ["--model", self.profile.model] if self.profile.model else []
        if request.resume_session_id:
            # `codex exec resume` has no --cd; the process working directory is
            # the worktree and the session is found by its id.
            return [
                str(self.profile.command),
                *self.profile.args,
                "exec",
                "resume",
                "--json",
                *model,
                request.resume_session_id,
                _agent_prompt(request),
            ]
        return [
            str(self.profile.command),
            *self.profile.args,
            "exec",
            "--json",
            *model,
            "--cd",
            request.worktree_path,
            _agent_prompt(request),
        ]


_OPENCODE_FORMAT_HINT = (
    " Reply with the JSON object as your final message and no other text. "
    "schema_version must be the JSON number 1 (not a string). Each issue_updates "
    'item is {"issue_id": "<id>", "status": "<status>"} and each issue_comments '
    'item is {"issue_id": "<id>", "text": "<text>"}; use empty lists when there '
    "is nothing to report. Leave issue_updates empty: the router moves finished "
    "packages to review itself and rejects agent status changes such as closing "
    "an issue. Example: "
    '{"schema_version": 1, "outcome": "completed", "summary": "what you did", '
    '"issue_updates": [], "issue_comments": [], "checkpoint": null, "artifacts": []}'
)


class OpenCodeRunAdapter(_SubprocessAdapter):
    """Run the configured OpenCode CLI with JSON event output."""

    display_name = "OpenCode"
    resume_requires_original_directory = True

    def _environment(self, request: RouterExecutionRequest) -> dict[str, str] | None:
        # Popen's cwd does not update PWD, which OpenCode uses as its project root.
        environment = {**os.environ, **self.profile.env, "PWD": request.worktree_path}
        if "XDG_DATA_HOME" not in self.profile.env:
            environment["XDG_DATA_HOME"] = self._isolated_data_home(
                environment, request.package_id
            )
        if self.profile.service_tier:
            environment["OPENCODE_CONFIG_CONTENT"] = _opencode_config_content(
                environment.get("OPENCODE_CONFIG_CONTENT"),
                str(self.profile.model),
                self.profile.service_tier,
            )
        return environment

    def _isolated_data_home(self, environment: dict[str, str], package_id: str) -> str:
        """Give this package a private OpenCode data dir.

        Concurrent OpenCode processes share one SQLite session database and fail
        with "database is locked", so each package gets its own directory. It
        persists across attempts (when the router provides ``state_dir``) so a
        saved session can be resumed with a human's reply; without one it is a
        temporary directory removed after the run. Provider credentials
        (auth.json) are copied in so non-AWS providers keep working.
        """
        if self.state_dir is not None:
            # Same key scheme as the Rust runtime, so either can resume the
            # other's saved session.
            key = re.sub(r"[^A-Za-z0-9._-]", "_", package_id)
            data_home = self.state_dir / "opencode" / key
            data_home.mkdir(parents=True, exist_ok=True)
            self._data_home = None  # persistent: never removed by cleanup
        else:
            data_home = Path(tempfile.mkdtemp(prefix="kanbus-opencode-"))
            self._data_home = str(data_home)
        shared = Path(
            environment.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
        )
        auth = shared / "opencode" / "auth.json"
        target = data_home / "opencode"
        if auth.is_file() and not (target / "auth.json").exists():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(auth, target / "auth.json")
        return str(data_home)

    def _cleanup(self) -> None:
        data_home = getattr(self, "_data_home", None)
        if data_home:
            shutil.rmtree(data_home, ignore_errors=True)
            self._data_home = None

    def _popen_extras(self) -> dict[str, Any]:
        # `opencode run` appends piped stdin to the prompt and waits for EOF.
        return {"stdin": subprocess.DEVNULL}

    def _build_command(self, request: RouterExecutionRequest) -> list[str]:
        model = ["--model", self.profile.model] if self.profile.model else []
        return [
            str(self.profile.command),
            *self.profile.args,
            "run",
            "--format",
            "json",
            *model,
            *(
                ["--session", request.resume_session_id]
                if request.resume_session_id
                else []
            ),
            _agent_prompt(request) + _OPENCODE_FORMAT_HINT,
        ]

    def _session_id(self, stdout: str) -> str | None:
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                value = event.get("sessionID")
                if isinstance(value, str) and value:
                    return value
        return None

    def _result_payload(self, stdout: str) -> dict[str, Any]:
        text = "".join(_opencode_text_parts(stdout))
        payload = _payload_from_model_text(text)
        if payload is None:
            raise IssueRouterError("OpenCode router adapter returned invalid JSON")
        return payload


ADAPTER_CLASSES: dict[str, type[_SubprocessAdapter]] = {
    "codex": CodexExecAdapter,
    "opencode": OpenCodeRunAdapter,
}
"""Registry of router agent adapters keyed by ``adapter:`` name.

Add an entry here (and the name to ``models.ROUTER_ADAPTERS``) to support
another agent CLI.
"""


def _opencode_config_content(existing: str | None, model: str, tier: str) -> str:
    """Return OpenCode inline config selecting a Bedrock service tier for one model.

    OpenCode only honours ``serviceTier`` in per-model options; setting it on the
    provider is silently ignored (verified against Bedrock's ResolvedServiceTier).
    """
    try:
        config = json.loads(existing) if existing else {}
    except json.JSONDecodeError:
        config = {}
    provider, _, model_id = model.partition("/")
    entry = (
        config.setdefault("provider", {})
        .setdefault(provider, {})
        .setdefault("models", {})
        .setdefault(model_id, {})
        .setdefault("options", {})
    )
    entry["serviceTier"] = tier
    return json.dumps(config)


def _opencode_text_parts(stdout: str) -> list[str]:
    parts: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            parts.append(part["text"])
    return parts


def _payload_from_model_text(text: str) -> dict[str, Any] | None:
    """Extract the last result object embedded in free-form model text.

    Models wrap the object in prose or fenced blocks and may emit reasoning text
    with stray braces first, so decode a JSON object at every ``{`` and keep the
    last one that carries the result contract keys.
    """
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    index = text.find("{")
    while index != -1:
        try:
            decoded, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index = text.find("{", index + 1)
            continue
        if (
            isinstance(decoded, dict)
            and "outcome" in decoded
            and "schema_version" in decoded
        ):
            found = decoded
        index = text.find("{", end)
    return found


def _process_identity(pid: int) -> str | None:
    """Return a stable identity for the process currently using a PID.

    :param pid: Operating-system process identifier.
    :type pid: int
    :return: Process-start identity or ``None`` when the platform cannot provide it.
    :rtype: str | None
    """
    if os.name == "posix" and Path(f"/proc/{pid}/stat").is_file():
        try:
            stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            stat_fields = stat_text[stat_text.rfind(")") + 2 :].split()
            if len(stat_fields) <= 19:
                return None
            boot_id = (
                Path("/proc/sys/kernel/random/boot_id")
                .read_text(encoding="utf-8")
                .strip()
            )
            executable = os.readlink(f"/proc/{pid}/exe")
            command_digest = hashlib.sha256(
                Path(f"/proc/{pid}/cmdline").read_bytes()
            ).hexdigest()
            return f"linux:{boot_id}:{stat_fields[19]}:{executable}:{command_digest}"
        except OSError:
            return None
    if os.name == "posix":
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "lstart=,command="],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        identity_bytes = result.stdout.strip()
        if identity_bytes:
            return "ps:" + hashlib.sha256(identity_bytes).hexdigest()
    return None


class FakeRouterAdapter:
    """Deterministic in-process adapter for tests and local simulations."""

    def __init__(self, result: RouterAgentResult) -> None:
        self.result = result
        self.requests: list[RouterExecutionRequest] = []
        self.cancelled_claims: list[str] = []

    def execute(self, request: RouterExecutionRequest) -> RouterAgentResult:
        """Return the configured result and retain the request for assertions.

        :param request: Structured execution request.
        :type request: RouterExecutionRequest
        :return: Configured agent result.
        :rtype: RouterAgentResult
        """
        self.requests.append(request)
        return self.result

    def cancel(self, claim_id: str) -> None:
        """Record one cancellation request.

        :param claim_id: Active claim identifier.
        :type claim_id: str
        """
        self.cancelled_claims.append(claim_id)


def _agent_prompt(request: RouterExecutionRequest) -> str:
    """The prompt for a fresh session, or the human's reply for a resumed one."""
    prompt = _result_contract_prompt(request)
    if request.resume_session_id and request.reply:
        return (
            "A human replied to your question:\n\n"
            f"{request.reply}\n\n"
            "Continue the work from where you stopped, in this same session. " + prompt
        )
    if request.reply:
        return (
            "A human replied to a question from an earlier session that could not "
            "be resumed. Start from the issue and any work already on this "
            "branch, and take the reply into account:\n\n"
            f"{request.reply}\n\n" + prompt
        )
    return prompt


def _result_contract_prompt(request: RouterExecutionRequest) -> str:
    allowed_updates = ", ".join(request.package_issue_ids)
    checkpoint = (
        "null" if request.checkpoint is None else request.checkpoint.model_dump_json()
    )
    return (
        "Complete the Kanbus package in this isolated worktree. Only update issue IDs "
        f"in this package: {allowed_updates}. Current claim {request.claim_id} has "
        f"logical revision {request.revision}. Latest accepted checkpoint: {checkpoint}. "
        "Return one JSON object with keys schema_version, outcome, summary, "
        "issue_updates, issue_comments, checkpoint, and artifacts. Put each requested "
        "issue comment in issue_comments with issue_id and text; do not edit the "
        "project's issue files directly. Allowed outcomes are completed, blocked, "
        "and retryable_failure. schema_version must be the JSON number 1, not a "
        "string. The router owns issue status and commits board state: do not run "
        "kbs commit, kbs update or kbs comment; report comments through "
        "issue_comments."
    )


def _find_result_payload(stdout: str) -> dict[str, Any]:
    try:
        decoded = json.loads(stdout)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, dict):
        for candidate in (
            decoded,
            decoded.get("result"),
            decoded.get("structured_output"),
        ):
            if (
                isinstance(candidate, dict)
                and "outcome" in candidate
                and "schema_version" in candidate
            ):
                return candidate
    payloads: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(decoded, dict):
            continue
        if "outcome" in decoded and "schema_version" in decoded:
            payloads.append(decoded)
        item = decoded.get("result")
        if isinstance(item, dict) and "outcome" in item and "schema_version" in item:
            payloads.append(item)
        item = decoded.get("structured_output")
        if isinstance(item, dict) and "outcome" in item and "schema_version" in item:
            payloads.append(item)
        envelope = decoded.get("payload")
        items = [decoded.get("item")]
        if isinstance(envelope, dict):
            items.append(envelope.get("item"))
        for item in items:
            if not isinstance(item, dict):
                continue
            texts = [item.get("text")]
            content = item.get("content")
            if isinstance(content, list):
                texts.extend(
                    part.get("text") for part in content if isinstance(part, dict)
                )
            for text in texts:
                if not isinstance(text, str):
                    continue
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(parsed, dict)
                    and "outcome" in parsed
                    and "schema_version" in parsed
                ):
                    payloads.append(parsed)
    if not payloads:
        raise IssueRouterError("Codex router adapter returned invalid JSON")
    return payloads[-1]


def _parse_result(payload: dict[str, Any], name: str = "Codex") -> RouterAgentResult:
    outcome = payload.get("outcome")
    if isinstance(outcome, str) and outcome not in {
        "completed",
        "blocked",
        "retryable_failure",
    }:
        raise IssueRouterError(f'invalid {name} router outcome "{outcome}"')
    try:
        result = RouterAgentResult.model_validate(
            _normalize_schema_version(_normalize_artifacts(payload))
        )
    except ValidationError as error:
        raise IssueRouterError(
            f"{name} router adapter returned invalid result"
        ) from error
    return result.validate_outcome(name)


def _normalize_schema_version(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept the contract version written as "1", "1.0" or 1.0.

    Models routinely quote the number. The version is a constant of the
    contract, so coercing these spellings loses nothing; every other value is
    still rejected by ``RouterAgentResult``.
    """
    version = payload.get("schema_version")
    if isinstance(version, bool):
        return payload
    if isinstance(version, str) and version.strip() in {"1", "1.0"}:
        return {**payload, "schema_version": 1}
    if isinstance(version, float) and version == 1.0:
        return {**payload, "schema_version": 1}
    return payload


def _normalize_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep a valid result when optional agent artifact metadata is non-canonical.

    Artifact references are advisory evidence, rather than authority to mutate an
    issue. Codex commonly reports a local ``path`` with descriptive or
    verification metadata, while the router contract stores named refs. Preserve
    canonical artifacts exactly, normalize that known shape, and omit entries that
    cannot name and reference an artifact. All non-artifact result fields remain
    strictly validated by ``RouterAgentResult``.
    """
    normalized = dict(payload)
    artifacts = payload.get("artifacts")
    if artifacts is None:
        return normalized
    if not isinstance(artifacts, list):
        normalized["artifacts"] = []
        return normalized
    normalized["artifacts"] = [
        artifact
        for item in artifacts
        if (artifact := _normalize_artifact(item)) is not None
    ]
    return normalized


def _normalize_artifact(item: Any) -> dict[str, str] | None:
    """Return the canonical representation of one optional artifact entry."""
    if not isinstance(item, dict):
        return None
    name = item.get("name")
    reference = item.get("ref")
    if (
        isinstance(name, str)
        and name.strip()
        and isinstance(reference, str)
        and reference.strip()
    ):
        return {"name": name, "ref": reference}
    path = item.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    path_name = Path(path).name.strip()
    if not path_name:
        return None
    return {"name": path_name, "ref": path}
