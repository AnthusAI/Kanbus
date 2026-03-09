from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from kanbus import hooks
from kanbus.hooks import (
    HookEvent,
    HookExecutionError,
    HookPhase,
    HookResult,
)
from kanbus.models import HookDefinition, HooksConfiguration
from kanbus.project import ProjectMarkerError

from test_helpers import build_issue, build_project_configuration


def _hook(
    hook_id: str,
    command: list[str],
    *,
    blocking: bool | None = None,
    timeout_ms: int | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> HookDefinition:
    payload: dict[str, object] = {"id": hook_id, "command": command}
    if blocking is not None:
        payload["blocking"] = blocking
    if timeout_ms is not None:
        payload["timeout_ms"] = timeout_ms
    if cwd is not None:
        payload["cwd"] = cwd
    if env is not None:
        payload["env"] = env
    return HookDefinition.model_validate(payload)


def _hooks_config(
    before: dict[str, list[HookDefinition]] | None = None,
    after: dict[str, list[HookDefinition]] | None = None,
    *,
    enabled: bool = True,
    run_in_beads_mode: bool = True,
    default_timeout_ms: int = 5000,
) -> HooksConfiguration:
    return HooksConfiguration.model_validate(
        {
            "enabled": enabled,
            "run_in_beads_mode": run_in_beads_mode,
            "default_timeout_ms": default_timeout_ms,
            "before": before or {},
            "after": after or {},
        }
    )


def test_hook_invocation_to_payload_and_serialize_issue() -> None:
    invocation = hooks.HookInvocation(
        schema_version=hooks.HOOK_SCHEMA_VERSION,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_CREATE,
        timestamp="2026-03-09T00:00:00.000Z",
        actor="dev",
        mode={"runtime": "python"},
        operation={"issue_id": "kanbus-1"},
    )
    payload = invocation.to_payload()
    assert payload["phase"] == "before"
    assert payload["event"] == "issue.create"

    issue = build_issue("kanbus-1")
    issue_payload = hooks.serialize_issue(issue)
    assert issue_payload["id"] == "kanbus-1"
    assert hooks.serialize_issue(None) is None


def test_hook_handler_protocol_method_is_noop_callable() -> None:
    invocation = hooks.HookInvocation(
        schema_version=hooks.HOOK_SCHEMA_VERSION,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_CREATE,
        timestamp="2026-03-09T00:00:00.000Z",
        actor="dev",
        mode={},
        operation={},
    )
    hook = _hook("noop", ["echo"])
    assert (
        hooks.HookHandler.run(  # type: ignore[misc]
            object(),
            hook=hook,
            invocation=invocation,
            project_root=Path("."),
            timeout_ms=1,
        )
        is None
    )


def test_hooks_globally_disabled_flag_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert hooks.hooks_globally_disabled(no_hooks=True) is True

    monkeypatch.setenv("KANBUS_NO_HOOKS", "1")
    assert hooks.hooks_globally_disabled() is True
    monkeypatch.setenv("KANBUS_NO_HOOKS", "YES")
    assert hooks.hooks_globally_disabled() is True
    monkeypatch.setenv("KANBUS_NO_HOOKS", "off")
    assert hooks.hooks_globally_disabled() is False


def test_external_command_hook_handler_success_failure_timeout_and_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = hooks.ExternalCommandHookHandler()
    invocation = hooks.HookInvocation(
        schema_version=hooks.HOOK_SCHEMA_VERSION,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_UPDATE,
        timestamp="2026-03-09T00:00:00.000Z",
        actor="dev",
        mode={"runtime": "python"},
        operation={"x": 1},
    )
    hook = _hook("h1", ["cmd"], cwd=".", env={"X": "1"})

    calls: list[dict[str, object]] = []

    def ok_run(*_args, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(
            args=["cmd"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(hooks.subprocess, "run", ok_run)
    result = handler.run(
        hook=hook, invocation=invocation, project_root=tmp_path, timeout_ms=200
    )
    assert result.succeeded is True
    assert result.timed_out is False
    assert result.message == "ok"
    assert calls[0]["cwd"] == tmp_path
    assert calls[0]["env"]["X"] == "1"
    assert json.loads(calls[0]["input"])["event"] == "issue.update"

    def fail_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["cmd"], returncode=7, stdout="", stderr="bad"
        )

    monkeypatch.setattr(hooks.subprocess, "run", fail_run)
    fail = handler.run(
        hook=_hook("h2", ["cmd"]),
        invocation=invocation,
        project_root=tmp_path,
        timeout_ms=10,
    )
    assert fail.succeeded is False
    assert fail.exit_code == 7
    assert fail.message == "bad"

    def fail_no_stderr(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["cmd"], returncode=8, stdout="", stderr=""
        )

    monkeypatch.setattr(hooks.subprocess, "run", fail_no_stderr)
    fail2 = handler.run(
        hook=_hook("h3", ["cmd"]),
        invocation=invocation,
        project_root=tmp_path,
        timeout_ms=10,
    )
    assert fail2.message == "exit code 8"

    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["cmd"], timeout=1)

    monkeypatch.setattr(hooks.subprocess, "run", timeout_run)
    timeout = handler.run(
        hook=_hook("h4", ["cmd"]),
        invocation=invocation,
        project_root=tmp_path,
        timeout_ms=10,
    )
    assert timeout.succeeded is False
    assert timeout.timed_out is True

    def os_error_run(*_args, **_kwargs):
        raise OSError("nope")

    monkeypatch.setattr(hooks.subprocess, "run", os_error_run)
    os_error = handler.run(
        hook=_hook("h5", ["cmd"]),
        invocation=invocation,
        project_root=tmp_path,
        timeout_ms=10,
    )
    assert os_error.succeeded is False
    assert os_error.timed_out is False
    assert "nope" in os_error.message


def test_resolve_hook_configuration_success_and_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = build_project_configuration()
    config_path = tmp_path / ".kanbus.yml"

    monkeypatch.setattr(hooks, "get_configuration_path", lambda _root: config_path)
    monkeypatch.setattr(hooks, "load_project_configuration", lambda _path: cfg)

    resolved, root = hooks._resolve_hook_configuration(tmp_path)
    assert isinstance(resolved, HooksConfiguration)
    assert root == tmp_path

    monkeypatch.setattr(
        hooks,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("missing")),
    )
    fallback, fallback_root = hooks._resolve_hook_configuration(tmp_path)
    assert isinstance(fallback, HooksConfiguration)
    assert fallback_root == tmp_path


def test_hooks_for_event_and_blocking_helpers() -> None:
    before_hook = _hook("b", ["echo"])
    after_hook = _hook("a", ["echo"], blocking=True)
    cfg = _hooks_config(
        before={HookEvent.ISSUE_CREATE.value: [before_hook]},
        after={HookEvent.ISSUE_CREATE.value: [after_hook]},
    )

    assert hooks._hooks_for_event(cfg, HookPhase.BEFORE, HookEvent.ISSUE_CREATE) == [
        before_hook
    ]
    assert hooks._hooks_for_event(cfg, HookPhase.AFTER, HookEvent.ISSUE_CREATE) == [
        after_hook
    ]

    assert (
        hooks._effective_blocking(HookPhase.AFTER, HookEvent.ISSUE_CREATE, before_hook)
        is False
    )
    assert (
        hooks._effective_blocking(
            HookPhase.BEFORE,
            HookEvent.ISSUE_CREATE,
            _hook("x", ["echo"], blocking=True),
        )
        is True
    )
    assert (
        hooks._effective_blocking(
            HookPhase.BEFORE, HookEvent.ISSUE_SHOW, _hook("x2", ["echo"])
        )
        is False
    )
    assert (
        hooks._effective_blocking(
            HookPhase.BEFORE, HookEvent.ISSUE_CREATE, _hook("x3", ["echo"])
        )
        is True
    )

    events = hooks._policy_events()
    assert events == sorted(events, key=lambda e: e.value)


def test_list_hooks_includes_external_and_builtin_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _hooks_config(
        before={
            "issue.create": [_hook("b1", ["echo", "ok"])],
            "unknown": [_hook("b2", ["echo", "ok"])],
        },
        after={"issue.update": [_hook("a1", ["echo", "ok"], timeout_ms=10)]},
        default_timeout_ms=55,
    )
    monkeypatch.setattr(
        hooks, "_resolve_hook_configuration", lambda _root: (cfg, Path("/repo"))
    )

    rows = hooks.list_hooks(Path("/repo"))
    assert any(
        row["source"] == "external" and row["id"] == "b1" and row["timeout_ms"] == 55
        for row in rows
    )
    assert any(
        row["source"] == "external" and row["id"] == "a1" and row["timeout_ms"] == 10
        for row in rows
    )
    assert any(
        row["source"] == "built-in" and row["id"] == "policy-guidance" for row in rows
    )


def test_validate_hooks_reports_all_validation_problems(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "scripts" / "ok.sh"
    script.parent.mkdir(parents=True)
    script.write_text("echo ok", encoding="utf-8")

    cfg = _hooks_config(
        before={
            "bad.event": [_hook("x", ["echo"])],
            HookEvent.ISSUE_CREATE.value: [],
            HookEvent.ISSUE_UPDATE.value: [
                _hook("dup", ["", "arg"]),
                _hook("dup", ["/does/not/exist"]),
                _hook("path-ok", ["./scripts/ok.sh"], cwd="missing-cwd"),
            ],
        },
        after={
            HookEvent.ISSUE_SHOW.value: [
                _hook("no-path", ["definitely-not-on-path"]),
            ]
        },
    )

    monkeypatch.setattr(
        hooks, "_resolve_hook_configuration", lambda _root: (cfg, tmp_path)
    )
    monkeypatch.setattr(
        hooks.shutil,
        "which",
        lambda executable: "/usr/bin/echo" if executable == "echo" else None,
    )

    issues = hooks.validate_hooks(tmp_path)

    assert any("unknown event" in issue for issue in issues)
    assert any("empty hook list" in issue for issue in issues)
    assert any("duplicate hook id 'dup'" in issue for issue in issues)
    assert any("command is empty" in issue for issue in issues)
    assert any("command not found" in issue for issue in issues)
    assert any("is not on PATH" in issue for issue in issues)
    assert any("cwd" in issue and "does not exist" in issue for issue in issues)


def test_run_lifecycle_hooks_short_circuits_and_blocking_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Globally disabled
    monkeypatch.setattr(hooks, "hooks_globally_disabled", lambda _no_hooks: True)
    hooks.run_lifecycle_hooks(
        root=tmp_path,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_CREATE,
        actor="dev",
        beads_mode=False,
    )

    monkeypatch.setattr(hooks, "hooks_globally_disabled", lambda _no_hooks: False)

    # Config disabled
    monkeypatch.setattr(
        hooks,
        "_resolve_hook_configuration",
        lambda _root: (_hooks_config(enabled=False), tmp_path),
    )
    hooks.run_lifecycle_hooks(
        root=tmp_path,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_CREATE,
        actor="dev",
        beads_mode=False,
    )

    # Beads mode blocked
    monkeypatch.setattr(
        hooks,
        "_resolve_hook_configuration",
        lambda _root: (_hooks_config(run_in_beads_mode=False), tmp_path),
    )
    hooks.run_lifecycle_hooks(
        root=tmp_path,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_CREATE,
        actor="dev",
        beads_mode=True,
    )

    # Blocking failure on before/mutating event raises.
    cfg = _hooks_config(before={HookEvent.ISSUE_CREATE.value: [_hook("b1", ["echo"])]})
    monkeypatch.setattr(
        hooks, "_resolve_hook_configuration", lambda _root: (cfg, tmp_path)
    )

    class FailHandler:
        def run(self, **_kwargs):
            return HookResult(
                hook_id="b1",
                succeeded=False,
                timed_out=False,
                exit_code=2,
                duration_ms=1,
                message="failed",
            )

    monkeypatch.setattr(hooks, "ExternalCommandHookHandler", lambda: FailHandler())

    with pytest.raises(HookExecutionError, match="blocking hook 'b1' failed"):
        hooks.run_lifecycle_hooks(
            root=tmp_path,
            phase=HookPhase.BEFORE,
            event=HookEvent.ISSUE_CREATE,
            actor="dev",
            beads_mode=False,
        )


def test_run_lifecycle_hooks_nonblocking_warning_and_after_policy_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before_cfg = _hooks_config(
        before={HookEvent.ISSUE_SHOW.value: [_hook("s1", ["echo"], blocking=False)]}
    )
    monkeypatch.setattr(
        hooks, "_resolve_hook_configuration", lambda _root: (before_cfg, tmp_path)
    )

    class WarnHandler:
        def run(self, **_kwargs):
            return HookResult(
                hook_id="s1",
                succeeded=False,
                timed_out=False,
                exit_code=1,
                duration_ms=1,
                message="warn",
            )

    monkeypatch.setattr(hooks, "ExternalCommandHookHandler", lambda: WarnHandler())
    warned: list[str] = []
    monkeypatch.setattr(hooks.click, "echo", lambda msg, err=True: warned.append(msg))

    hooks.run_lifecycle_hooks(
        root=tmp_path,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_SHOW,
        actor="dev",
        beads_mode=False,
    )
    assert any("Hook warning (issue.show/before/s1): warn" in line for line in warned)

    # AFTER phase always invokes policy provider hook.
    after_cfg = _hooks_config(
        after={HookEvent.ISSUE_UPDATE.value: [_hook("a1", ["echo"])]}
    )
    monkeypatch.setattr(
        hooks, "_resolve_hook_configuration", lambda _root: (after_cfg, tmp_path)
    )

    class OkHandler:
        def run(self, **_kwargs):
            return HookResult(
                hook_id="a1",
                succeeded=True,
                timed_out=False,
                exit_code=0,
                duration_ms=1,
                message="ok",
            )

    monkeypatch.setattr(hooks, "ExternalCommandHookHandler", lambda: OkHandler())
    called: list[tuple[Path, HookEvent, bool, bool, int]] = []

    def fake_provider(
        *,
        project_root: Path,
        event: HookEvent,
        issues_for_policy,
        beads_mode: bool,
        no_guidance: bool,
    ) -> None:
        called.append(
            (project_root, event, beads_mode, no_guidance, len(issues_for_policy))
        )

    monkeypatch.setattr(hooks, "_run_policy_guidance_provider", fake_provider)

    hooks.run_lifecycle_hooks(
        root=tmp_path,
        phase=HookPhase.AFTER,
        event=HookEvent.ISSUE_UPDATE,
        actor="dev",
        beads_mode=False,
        issues_for_policy=[build_issue("kanbus-1")],
        no_guidance=True,
    )
    assert called == [(tmp_path, HookEvent.ISSUE_UPDATE, False, True, 1)]


def test_run_policy_guidance_provider_all_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = build_issue("kanbus-1")

    # No-op cases.
    hooks._run_policy_guidance_provider(
        project_root=Path("/repo"),
        event=HookEvent.ISSUE_UPDATE,
        issues_for_policy=[issue],
        beads_mode=True,
        no_guidance=False,
    )
    hooks._run_policy_guidance_provider(
        project_root=Path("/repo"),
        event=HookEvent.ISSUE_UPDATE,
        issues_for_policy=[],
        beads_mode=False,
        no_guidance=False,
    )
    hooks._run_policy_guidance_provider(
        project_root=Path("/repo"),
        event=HookEvent.ISSUE_COMMENT,
        issues_for_policy=[issue],
        beads_mode=False,
        no_guidance=False,
    )

    calls: list[tuple[str, int, bool]] = []

    def fake_emit(
        project_root: Path, issues_for_policy, operation, *, no_guidance: bool
    ) -> None:
        calls.append((str(project_root), len(issues_for_policy), no_guidance))

    monkeypatch.setattr("kanbus.policy_guidance.emit_guidance_for_issues", fake_emit)

    hooks._run_policy_guidance_provider(
        project_root=Path("/repo"),
        event=HookEvent.ISSUE_CREATE,
        issues_for_policy=[issue],
        beads_mode=False,
        no_guidance=True,
    )
    assert calls == [("/repo", 1, True)]

    monkeypatch.setattr(
        "kanbus.policy_guidance.emit_guidance_for_issues",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("guidance boom")),
    )
    warned: list[str] = []
    monkeypatch.setattr(hooks.click, "echo", lambda msg, err=True: warned.append(msg))

    hooks._run_policy_guidance_provider(
        project_root=Path("/repo"),
        event=HookEvent.ISSUE_UPDATE,
        issues_for_policy=[issue],
        beads_mode=False,
        no_guidance=False,
    )
    assert any(
        "Hook warning (issue.update/after/policy-guidance): guidance boom" in line
        for line in warned
    )


def test_parse_and_path_and_now_helpers() -> None:
    assert hooks._looks_like_path("./x") is True
    assert hooks._looks_like_path("dir/x") is True
    assert hooks._looks_like_path("dir\\x") is True
    assert hooks._looks_like_path("echo") is False

    assert hooks._parse_hook_event("issue.create") == HookEvent.ISSUE_CREATE
    assert hooks._parse_hook_event("invalid") is None

    now = hooks._now_utc_iso()
    assert now.endswith("Z")
    assert "T" in now


def test_validate_hooks_path_executable_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Cover branch where executable is a path and exists.
    script = tmp_path / "bin" / "hook.sh"
    script.parent.mkdir(parents=True)
    script.write_text("echo ok", encoding="utf-8")

    cfg = _hooks_config(
        before={HookEvent.ISSUE_CREATE.value: [_hook("ok", [str(script)])]}
    )
    monkeypatch.setattr(
        hooks, "_resolve_hook_configuration", lambda _root: (cfg, tmp_path)
    )

    issues = hooks.validate_hooks(tmp_path)
    assert issues == []


def test_external_handler_absolute_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = hooks.ExternalCommandHookHandler()
    invocation = hooks.HookInvocation(
        schema_version=hooks.HOOK_SCHEMA_VERSION,
        phase=HookPhase.BEFORE,
        event=HookEvent.ISSUE_UPDATE,
        timestamp="2026-03-09T00:00:00.000Z",
        actor="dev",
        mode={"runtime": "python"},
        operation={},
    )
    abs_cwd = tmp_path / "abs"
    abs_cwd.mkdir(parents=True)
    seen_cwd: list[Path] = []

    def ok_run(*_args, **kwargs):
        seen_cwd.append(Path(kwargs["cwd"]))
        return subprocess.CompletedProcess(
            args=["cmd"], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(hooks.subprocess, "run", ok_run)
    hook = _hook("x", ["cmd"], cwd=str(abs_cwd))
    result = handler.run(
        hook=hook, invocation=invocation, project_root=tmp_path, timeout_ms=1
    )
    assert result.succeeded is True
    assert seen_cwd == [abs_cwd]
