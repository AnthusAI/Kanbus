"""Lifecycle hook runtime and built-in providers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

import click

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.models import HookDefinition, HooksConfiguration, IssueData
from kanbus.project import ProjectMarkerError, get_configuration_path

HOOK_SCHEMA_VERSION = "kanbus.hooks.v1"


class HookPhase(str, Enum):
    """Lifecycle hook phase."""

    BEFORE = "before"
    AFTER = "after"


class HookEvent(str, Enum):
    """Normalized lifecycle hook events."""

    ISSUE_CREATE = "issue.create"
    ISSUE_UPDATE = "issue.update"
    ISSUE_CLOSE = "issue.close"
    ISSUE_DELETE = "issue.delete"
    ISSUE_COMMENT = "issue.comment"
    ISSUE_DEPENDENCY = "issue.dependency"
    ISSUE_PROMOTE = "issue.promote"
    ISSUE_LOCALIZE = "issue.localize"
    ISSUE_SHOW = "issue.show"
    ISSUE_LIST = "issue.list"
    ISSUE_READY = "issue.ready"


MUTATING_EVENTS = {
    HookEvent.ISSUE_CREATE,
    HookEvent.ISSUE_UPDATE,
    HookEvent.ISSUE_CLOSE,
    HookEvent.ISSUE_DELETE,
    HookEvent.ISSUE_COMMENT,
    HookEvent.ISSUE_DEPENDENCY,
    HookEvent.ISSUE_PROMOTE,
    HookEvent.ISSUE_LOCALIZE,
}

POLICY_OPERATION_BY_EVENT = {
    HookEvent.ISSUE_CREATE: "create",
    HookEvent.ISSUE_UPDATE: "update",
    HookEvent.ISSUE_CLOSE: "close",
    HookEvent.ISSUE_DELETE: "delete",
    HookEvent.ISSUE_SHOW: "view",
    HookEvent.ISSUE_LIST: "list",
    HookEvent.ISSUE_READY: "ready",
}


class HookExecutionError(RuntimeError):
    """Raised when a blocking hook fails."""


@dataclass(frozen=True)
class HookInvocation:
    """Canonical payload envelope delivered to hook handlers."""

    schema_version: str
    phase: HookPhase
    event: HookEvent
    timestamp: str
    actor: str
    mode: dict[str, Any]
    operation: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "phase": self.phase.value,
            "event": self.event.value,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "mode": self.mode,
            "operation": self.operation,
        }


@dataclass(frozen=True)
class HookResult:
    """Result metadata for one hook execution."""

    hook_id: str
    succeeded: bool
    timed_out: bool
    exit_code: int | None
    duration_ms: int
    message: str


class HookHandler(Protocol):
    """Hook handler execution contract."""

    def run(
        self,
        *,
        hook: HookDefinition,
        invocation: HookInvocation,
        project_root: Path,
        timeout_ms: int,
    ) -> HookResult: ...


class ExternalCommandHookHandler:
    """Execute external command hooks with JSON payload over stdin."""

    def run(
        self,
        *,
        hook: HookDefinition,
        invocation: HookInvocation,
        project_root: Path,
        timeout_ms: int,
    ) -> HookResult:
        env = os.environ.copy()
        env.update(hook.env)

        cwd = project_root
        if hook.cwd:
            candidate = Path(hook.cwd)
            cwd = candidate if candidate.is_absolute() else (project_root / candidate)

        payload = json.dumps(invocation.to_payload(), sort_keys=True, default=str)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                hook.command,
                input=payload,
                text=True,
                capture_output=True,
                timeout=max(timeout_ms, 1) / 1000,
                cwd=cwd,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - started) * 1000)
            return HookResult(
                hook_id=hook.id,
                succeeded=False,
                timed_out=True,
                exit_code=None,
                duration_ms=duration_ms,
                message=f"timed out after {timeout_ms}ms",
            )
        except OSError as error:
            duration_ms = int((time.monotonic() - started) * 1000)
            return HookResult(
                hook_id=hook.id,
                succeeded=False,
                timed_out=False,
                exit_code=None,
                duration_ms=duration_ms,
                message=str(error),
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        succeeded = completed.returncode == 0
        message = (
            "ok"
            if succeeded
            else (completed.stderr.strip() or f"exit code {completed.returncode}")
        )
        return HookResult(
            hook_id=hook.id,
            succeeded=succeeded,
            timed_out=False,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            message=message,
        )


def hooks_globally_disabled(no_hooks: bool = False) -> bool:
    """Return True if hooks are globally disabled by flag or env."""
    if no_hooks:
        return True
    raw = os.environ.get("KANBUS_NO_HOOKS", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def serialize_issue(issue: IssueData | None) -> dict[str, Any] | None:
    """Serialize an issue snapshot for hook payloads."""
    if issue is None:
        return None
    return issue.model_dump(by_alias=True, mode="json")


def list_hooks(root: Path) -> list[dict[str, Any]]:
    """List configured hooks for CLI inspection."""
    hooks_config, _ = _resolve_hook_configuration(root)
    rows: list[dict[str, Any]] = []
    for phase, event_map in (
        (HookPhase.BEFORE, hooks_config.before),
        (HookPhase.AFTER, hooks_config.after),
    ):
        for event_name in sorted(event_map):
            hooks = event_map[event_name]
            for hook in hooks:
                event = _parse_hook_event(event_name)
                timeout_ms = hook.timeout_ms or hooks_config.default_timeout_ms
                rows.append(
                    {
                        "source": "external",
                        "phase": phase.value,
                        "event": event_name,
                        "id": hook.id,
                        "command": " ".join(hook.command),
                        "blocking": _effective_blocking(phase, event, hook),
                        "timeout_ms": timeout_ms,
                    }
                )

    for event in _policy_events():
        rows.append(
            {
                "source": "built-in",
                "phase": HookPhase.AFTER.value,
                "event": event.value,
                "id": "policy-guidance",
                "command": "<built-in>",
                "blocking": False,
                "timeout_ms": None,
            }
        )
    return rows


def validate_hooks(root: Path) -> list[str]:
    """Return validation problems for configured hooks."""
    hooks_config, project_root = _resolve_hook_configuration(root)
    issues: list[str] = []

    for phase_name, event_map in (
        (HookPhase.BEFORE.value, hooks_config.before),
        (HookPhase.AFTER.value, hooks_config.after),
    ):
        for event_name, hooks in event_map.items():
            event = _parse_hook_event(event_name)
            if event is None:
                issues.append(f"hooks.{phase_name}.{event_name}: unknown event")
                continue
            if not hooks:
                issues.append(f"hooks.{phase_name}.{event_name}: empty hook list")
                continue

            seen: set[str] = set()
            for hook in hooks:
                if hook.id in seen:
                    issues.append(
                        f"hooks.{phase_name}.{event_name}: duplicate hook id '{hook.id}'"
                    )
                seen.add(hook.id)

                executable = hook.command[0].strip() if hook.command else ""
                if not executable:
                    issues.append(
                        f"hooks.{phase_name}.{event_name}.{hook.id}: command is empty"
                    )
                    continue

                if _looks_like_path(executable):
                    candidate = Path(executable)
                    resolved = (
                        candidate
                        if candidate.is_absolute()
                        else (project_root / candidate)
                    )
                    if not resolved.exists():
                        issues.append(
                            f"hooks.{phase_name}.{event_name}.{hook.id}: command not found at {resolved}"
                        )
                elif shutil.which(executable) is None:
                    issues.append(
                        f"hooks.{phase_name}.{event_name}.{hook.id}: command '{executable}' is not on PATH"
                    )

                if hook.cwd:
                    cwd = Path(hook.cwd)
                    resolved_cwd = cwd if cwd.is_absolute() else (project_root / cwd)
                    if not resolved_cwd.exists() or not resolved_cwd.is_dir():
                        issues.append(
                            f"hooks.{phase_name}.{event_name}.{hook.id}: cwd '{resolved_cwd}' does not exist"
                        )
    return issues


def run_lifecycle_hooks(
    *,
    root: Path,
    phase: HookPhase,
    event: HookEvent,
    actor: str,
    beads_mode: bool,
    operation: dict[str, Any] | None = None,
    issues_for_policy: list[IssueData] | None = None,
    no_hooks: bool = False,
    no_guidance: bool = False,
) -> None:
    """Run external hooks and built-in policy provider for one lifecycle event."""
    if hooks_globally_disabled(no_hooks):
        return

    hooks_config, project_root = _resolve_hook_configuration(root)
    if not hooks_config.enabled:
        return
    if beads_mode and not hooks_config.run_in_beads_mode:
        return

    invocation = HookInvocation(
        schema_version=HOOK_SCHEMA_VERSION,
        phase=phase,
        event=event,
        timestamp=_now_utc_iso(),
        actor=actor,
        mode={
            "beads_mode": beads_mode,
            "project_root": str(project_root),
            "working_directory": str(Path.cwd()),
            "runtime": "python",
        },
        operation=operation or {},
    )

    handler = ExternalCommandHookHandler()
    hook_definitions = _hooks_for_event(hooks_config, phase, event)
    for hook in hook_definitions:
        timeout_ms = hook.timeout_ms or hooks_config.default_timeout_ms
        result = handler.run(
            hook=hook,
            invocation=invocation,
            project_root=project_root,
            timeout_ms=timeout_ms,
        )
        blocking = _effective_blocking(phase, event, hook)
        if result.succeeded:
            continue
        if phase == HookPhase.BEFORE and blocking:
            raise HookExecutionError(
                f"blocking hook '{hook.id}' failed for {event.value}: {result.message}"
            )
        click.echo(
            (
                f"Hook warning ({event.value}/{phase.value}/{hook.id}): "
                f"{result.message}"
            ),
            err=True,
        )

    if phase == HookPhase.AFTER:
        _run_policy_guidance_provider(
            project_root=project_root,
            event=event,
            issues_for_policy=issues_for_policy or [],
            beads_mode=beads_mode,
            no_guidance=no_guidance,
        )


def _resolve_hook_configuration(root: Path) -> tuple[HooksConfiguration, Path]:
    try:
        config_path = get_configuration_path(root)
        configuration = load_project_configuration(config_path)
        return configuration.hooks, config_path.parent
    except (ConfigurationError, ProjectMarkerError, OSError):
        return HooksConfiguration(), root


def _hooks_for_event(
    hooks_config: HooksConfiguration,
    phase: HookPhase,
    event: HookEvent,
) -> list[HookDefinition]:
    phase_map = hooks_config.before if phase == HookPhase.BEFORE else hooks_config.after
    return list(phase_map.get(event.value, []))


def _effective_blocking(
    phase: HookPhase,
    event: HookEvent | None,
    hook: HookDefinition,
) -> bool:
    if phase == HookPhase.AFTER:
        return False
    if hook.blocking is not None:
        return hook.blocking
    return event in MUTATING_EVENTS


def _policy_events() -> list[HookEvent]:
    return sorted(POLICY_OPERATION_BY_EVENT.keys(), key=lambda value: value.value)


def _run_policy_guidance_provider(
    *,
    project_root: Path,
    event: HookEvent,
    issues_for_policy: list[IssueData],
    beads_mode: bool,
    no_guidance: bool,
) -> None:
    if beads_mode or not issues_for_policy:
        return
    operation_name = POLICY_OPERATION_BY_EVENT.get(event)
    if operation_name is None:
        return
    try:
        from kanbus.policy_context import PolicyOperation
        from kanbus.policy_guidance import emit_guidance_for_issues

        emit_guidance_for_issues(
            project_root,
            issues_for_policy,
            PolicyOperation(operation_name),
            no_guidance=no_guidance,
        )
    except Exception as error:  # pragma: no cover - intentionally non-blocking
        click.echo(
            f"Hook warning ({event.value}/after/policy-guidance): {error}",
            err=True,
        )


def _looks_like_path(command: str) -> bool:
    return command.startswith(".") or "/" in command or "\\" in command


def _parse_hook_event(value: str) -> HookEvent | None:
    try:
        return HookEvent(value)
    except ValueError:
        return None


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
