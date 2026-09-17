"""Structured agent contracts for Issue Router execution."""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kanbus.issue_router import IssueRouterError
from kanbus.models import RouterAgentProfile


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

    def validate_outcome(self) -> RouterAgentResult:
        """Require one supported result outcome."""
        if self.outcome not in {"completed", "blocked", "retryable_failure"}:
            raise IssueRouterError(f'invalid Codex router outcome "{self.outcome}"')
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


class RouterAdapter(Protocol):
    """Narrow execution and cancellation surface required by the router."""

    def execute(self, request: RouterExecutionRequest) -> RouterAgentResult:
        """Run one bounded package and return its structured result."""

    def cancel(self, claim_id: str) -> None:
        """Request cancellation for one active claim."""


class CodexExecAdapter:
    """Run the configured Codex CLI with JSONL output."""

    def __init__(
        self,
        profile: RouterAgentProfile,
        *,
        process_record_path: Path | None = None,
    ) -> None:
        self.profile = profile
        self.process_record_path = process_record_path
        self.process: subprocess.Popen[str] | None = None

    def execute(self, request: RouterExecutionRequest) -> RouterAgentResult:
        """Invoke Codex with a package-bounded structured-result prompt.

        :param request: Validated current-claim execution request.
        :type request: RouterExecutionRequest
        :return: Validated structured Codex result.
        :rtype: RouterAgentResult
        :raises IssueRouterError: If Codex exits unsuccessfully or returns invalid JSON.
        """
        command = [
            self.profile.command,
            *self.profile.args,
            "exec",
            "--json",
            "--cd",
            request.worktree_path,
            _result_contract_prompt(request),
        ]
        try:
            self.process = subprocess.Popen(
                command,
                cwd=request.worktree_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._record_process(request)
            stdout, _ = self.process.communicate(timeout=3600)
            return_code = self.process.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                self.process.communicate()
            raise IssueRouterError("Codex router adapter failed") from error
        finally:
            self.process = None
            self._remove_process_record(request.claim_id)
        if return_code != 0:
            raise IssueRouterError("Codex router adapter failed")
        payload = _find_result_payload(stdout)
        return _parse_result(payload)

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
        "and retryable_failure."
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
    if not payloads:
        raise IssueRouterError("Codex router adapter returned invalid JSON")
    return payloads[-1]


def _parse_result(payload: dict[str, Any]) -> RouterAgentResult:
    outcome = payload.get("outcome")
    if isinstance(outcome, str) and outcome not in {
        "completed",
        "blocked",
        "retryable_failure",
    }:
        raise IssueRouterError(f'invalid Codex router outcome "{outcome}"')
    try:
        result = RouterAgentResult.model_validate(payload)
    except ValidationError as error:
        raise IssueRouterError(
            "Codex router adapter returned invalid result"
        ) from error
    return result.validate_outcome()
