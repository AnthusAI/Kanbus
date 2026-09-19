"""Focused failure and fallback coverage for the Issue Router core and CLI."""

from __future__ import annotations

import copy
import json
import os
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import kanbus.cli as project_cli
from kanbus import coordination_mutex_api
from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.config_loader import ConfigurationError
from kanbus.coordination import CoordinationError, LeaseState
from kanbus.issue_listing import IssueListingError
from kanbus.issue_router import (
    IssueRouterError,
    RouterContext,
    RouterControlState,
    _Candidate,
    _apply_router_status_overlay,
    _collect_candidates,
    _defer_reason,
    _encode_router_event,
    _has_blocking_dependency,
    _pending_since,
    _planning_events,
    _policy_rejects,
    _read_events,
    _resolve_route,
    _route_error,
    build_router_plan,
    load_router_context,
    read_router_control,
    record_router_event,
)
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.project import ProjectMarkerError
from kanbus.router_cli import router_group


def _router_configuration(*, enabled: bool = True) -> ProjectConfiguration:
    data = copy.deepcopy(DEFAULT_CONFIGURATION)
    data["statuses"].append(
        {
            "key": "review",
            "name": "Review",
            "category": "In progress",
            "semantic_category": "in_progress",
        }
    )
    data["workflows"]["default"]["open"].append("review")
    data["workflows"]["default"]["in_progress"].append("review")
    data["workflows"]["default"]["review"] = ["in_progress", "closed"]
    transition_labels = data.setdefault("transition_labels", {}).setdefault(
        "default", {}
    )
    transition_labels["open"] = {
        **transition_labels.get("open", {}),
        "review": "Ready for review",
    }
    transition_labels["in_progress"] = {
        **transition_labels.get("in_progress", {}),
        "review": "Ready for review",
    }
    transition_labels["review"] = {"in_progress": "Request changes", "closed": "Merge"}
    data["router"] = {
        "enabled": enabled,
        "workflow": {
            "pending": "open",
            "active": "in_progress",
            "review": "review",
            "blocked": "blocked",
            "terminal": ["closed"],
        },
        "limits": {"project_wip": 4, "review_wip": 2},
        "providers": {
            "codex": {"adapter": "codex"},
            "backup": {"adapter": "codex"},
        },
        "classes": {"backend": {"providers": ["codex", "backup"]}},
    }
    return ProjectConfiguration.model_validate(data)


def _issue(
    *,
    identifier: str = "kbs-router-test",
    status: str = "open",
    labels: list[str] | None = None,
    dependencies: list[dict[str, str]] | None = None,
    parent: str | None = None,
) -> IssueData:
    now = datetime(2026, 9, 17, tzinfo=UTC)
    return IssueData(
        id=identifier,
        title="Router test issue",
        type="task",
        status=status,
        priority=2,
        labels=["agent-provider:codex"] if labels is None else labels,
        dependencies=dependencies or [],
        parent=parent,
        created_at=now,
        updated_at=now,
    )


def _context(
    root: Path,
    *,
    issues: list[IssueData] | None = None,
    enabled: bool = True,
) -> RouterContext:
    configuration = _router_configuration(enabled=enabled)
    project_dir = root / configuration.project_directory
    (project_dir / "events").mkdir(parents=True, exist_ok=True)
    return RouterContext(
        root=root,
        project_dir=project_dir,
        configuration=configuration,
        router=configuration.router,
        issues=issues or [_issue()],
        control=RouterControlState(),
    )


def test_candidate_collection_skips_only_children_owned_by_routed_ancestors(
    tmp_path: Path,
) -> None:
    routed_parent = _issue(identifier="kbs-routed", labels=["agent-provider:codex"])
    routed_child = _issue(identifier="kbs-routed-child", labels=[], parent="kbs-routed")
    plain_parent = _issue(identifier="kbs-plain", labels=[])
    plain_child = _issue(identifier="kbs-plain-child", labels=[], parent="kbs-plain")
    context = _context(
        tmp_path,
        issues=[routed_parent, routed_child, plain_parent, plain_child],
    )

    candidates = _collect_candidates(
        context,
        {issue.identifier: issue for issue in context.issues},
        [],
    )

    assert [candidate.issue.identifier for candidate in candidates] == [
        "kbs-routed",
        "kbs-plain",
        "kbs-plain-child",
    ]


def test_newer_conversation_review_overrides_an_older_router_start(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path, issues=[_issue(status="in_progress")])
    issues = [issue.model_copy(deep=True) for issue in context.issues]
    _apply_router_status_overlay(
        issues,
        [
            _router_event(
                "router_claimed",
                {"action": "started"},
                event_id="started",
            ),
            {
                "event_id": "review",
                "issue_id": "router:kbs-router-test",
                "event_type": "router.conversation",
                "occurred_at": "2026-09-17T00:01:00Z",
                "payload": {"action": "agent_turn", "lifecycle": "review"},
            },
        ],
        context.router,
    )

    assert issues[0].status == "review"


def test_planning_events_include_source_events_not_yet_on_shared_state(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    shared = tmp_path / "shared"
    context = _context(shared)
    context = replace(context, source_root=source)
    shared_event = _router_event("router_claimed", {}, event_id="shared")
    source_event = _router_event("router_completed", {}, event_id="source")
    duplicate = _router_event("router_claimed", {}, event_id="shared")

    monkeypatch.setattr(
        "kanbus.issue_router._read_events",
        lambda path: (
            [shared_event]
            if path == context.project_dir / "events"
            else [duplicate, source_event]
        ),
    )

    assert [event["event_id"] for event in _planning_events(context)] == [
        "shared",
        "source",
    ]


def _router_event(
    event_type: str,
    payload: dict[str, object],
    *,
    issue_id: str = "router:kbs-router-test",
    event_id: str = "event-1",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "issue_id": issue_id,
        "event_type": event_type,
        "occurred_at": "2026-09-17T00:00:00Z",
        "payload": payload,
    }


def _coordination_cli_setup(
    monkeypatch, tmp_path: Path, *, provider: str
) -> tuple[Path, Path, ProjectConfiguration]:
    data = copy.deepcopy(DEFAULT_CONFIGURATION)
    data["coordination"].update(
        providers=["mutex_api", "mqtt", "git"],
        mutex_api={
            "endpoint": "https://mutex.example.invalid",
            "bearer_token": "test-token",
        },
    )
    configuration = ProjectConfiguration.model_validate(data)
    project_dir = tmp_path / configuration.project_directory
    project_dir.mkdir(parents=True, exist_ok=True)
    context = (tmp_path, project_dir, configuration)
    monkeypatch.setattr(project_cli, "_coordination_context", lambda: context)
    monkeypatch.setattr(project_cli, "_coordination_provider", lambda *_args: provider)
    monkeypatch.setattr(
        project_cli,
        "utc_now",
        lambda: datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
    )
    return context


def _coordination_args(command: str) -> list[str]:
    return [
        "coordination",
        command,
        "--resource",
        "job:router-test",
        "--owner",
        "worker-a",
        "--claim-id",
        "claim-a",
    ]


def _active_lease_state(*, provider_event: bool = False) -> LeaseState:
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    return LeaseState(
        resource="job:router-test",
        owner="worker-a",
        claim_id="claim-a",
        expires_at=now + timedelta(minutes=5),
        active=True,
        event_id="event-claim",
        operation_event_id="event-claim" if provider_event else None,
        claimed_at=now,
        contention_window_ends_at=now - timedelta(seconds=1),
        revision=3,
        operation_sequence=1,
    )


def test_load_router_context_wraps_configuration_errors(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "kanbus.issue_router.get_configuration_path",
        lambda _root: tmp_path / ".kanbus.yml",
    )
    monkeypatch.setattr(
        "kanbus.issue_router.load_project_configuration",
        lambda _path: (_ for _ in ()).throw(ConfigurationError("bad project config")),
    )

    with pytest.raises(IssueRouterError, match="bad project config"):
        load_router_context(tmp_path)


def test_load_router_context_rejects_missing_router_configuration(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "kanbus.issue_router.get_configuration_path",
        lambda _root: tmp_path / ".kanbus.yml",
    )
    monkeypatch.setattr(
        "kanbus.issue_router.load_project_configuration",
        lambda _path: SimpleNamespace(router=None),
    )

    with pytest.raises(IssueRouterError, match="issue router is not configured"):
        load_router_context(tmp_path)


@pytest.mark.parametrize("previous", [None, "caller-setting"])
def test_load_router_context_restores_daemon_setting_after_issue_error(
    monkeypatch, tmp_path: Path, previous: str | None
) -> None:
    config_path = tmp_path / ".kanbus.yml"
    configuration = _router_configuration()
    monkeypatch.setattr(
        "kanbus.issue_router.get_configuration_path", lambda _root: config_path
    )
    monkeypatch.setattr(
        "kanbus.issue_router.load_project_configuration", lambda _path: configuration
    )
    monkeypatch.setattr(
        "kanbus.issue_router.list_issues",
        lambda _root: (_ for _ in ()).throw(
            IssueListingError("issue store unavailable")
        ),
    )
    if previous is None:
        monkeypatch.delenv("KANBUS_NO_DAEMON", raising=False)
    else:
        monkeypatch.setenv("KANBUS_NO_DAEMON", previous)

    with pytest.raises(IssueRouterError, match="issue store unavailable"):
        load_router_context(tmp_path)

    if previous is None:
        assert "KANBUS_NO_DAEMON" not in os.environ
    else:
        assert os.environ["KANBUS_NO_DAEMON"] == previous


def test_disabled_router_plan_is_empty_and_preserves_pause_state(
    tmp_path: Path,
) -> None:
    context = replace(
        _context(tmp_path, enabled=False), control=RouterControlState(paused=True)
    )

    plan = build_router_plan(context)

    assert not plan.enabled
    assert plan.paused
    assert plan.eligible == []
    assert plan.deferred == []


@pytest.mark.parametrize("content", ["not-json", '{"unknown": true}'])
def test_read_router_control_rejects_corrupt_or_unknown_fields(
    monkeypatch, tmp_path: Path, content: str
) -> None:
    path = tmp_path / "router-control.json"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr("kanbus.issue_router.router_control_path", lambda _root: path)

    with pytest.raises(IssueRouterError, match="router local control state is invalid"):
        read_router_control(tmp_path)


def test_record_router_event_surfaces_immutable_history_write_failure(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "kanbus.issue_router.write_events_batch",
        lambda *_args: (_ for _ in ()).throw(OSError("disk is read-only")),
    )

    with pytest.raises(IssueRouterError, match="disk is read-only"):
        record_router_event(
            tmp_path,
            package_id="kbs-router-test",
            event_type="router_progress",
            payload={"message": "still working"},
        )


@pytest.mark.parametrize(
    "retry_at",
    ["not-a-timestamp", None],
    ids=["malformed", "missing"],
)
def test_active_retry_candidate_with_invalid_backoff_is_safely_skipped(
    tmp_path: Path, retry_at: object
) -> None:
    context = _context(tmp_path, issues=[_issue(status="in_progress")])
    retry = _router_event("router_retry_scheduled", {"retry_at": retry_at})

    candidates = _collect_candidates(
        context,
        {issue.identifier: issue for issue in context.issues},
        [retry],
    )

    assert candidates == []


def test_active_retry_candidate_with_future_backoff_is_not_restarted(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path, issues=[_issue(status="in_progress")])
    retry = _router_event(
        "router_retry_scheduled",
        {"retry_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    )

    candidates = _collect_candidates(
        context,
        {issue.identifier: issue for issue in context.issues},
        [retry],
    )

    assert candidates == []


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ([], ("", "", "", "invalid_route")),
        (["agent-class:   "], ("", "", "", "invalid_route")),
        (
            ["agent-provider:missing"],
            ("provider", "missing", "missing", "invalid_route"),
        ),
        (["agent-class:missing"], ("class", "missing", "", "invalid_route")),
    ],
)
def test_resolve_route_rejects_missing_blank_and_unknown_routes(
    tmp_path: Path,
    labels: list[str],
    expected: tuple[str, str, str, str | None],
) -> None:
    context = _context(tmp_path)

    assert _resolve_route(context.router, _issue(labels=labels), []) == expected


def test_resolve_class_route_reuses_last_configured_provider() -> None:
    configuration = _router_configuration()
    issue = _issue(labels=["agent-class:backend"])
    previous_claim = _router_event("router_claimed", {"provider_profile": "backup"})

    assert _resolve_route(configuration.router, issue, [previous_claim]) == (
        "class",
        "backend",
        "backup",
        None,
    )


@pytest.mark.parametrize("retry_at", ["not-a-timestamp", None])
def test_pending_package_with_invalid_retry_time_is_deferred(
    tmp_path: Path, retry_at: object
) -> None:
    context = _context(tmp_path)
    issue = context.issues[0]
    candidate = _Candidate(
        issue=issue,
        route_kind="provider",
        route_name="codex",
        provider_profile="codex",
        package_issue_ids=[issue.identifier],
        pending_since=issue.created_at,
        attempt=1,
        scheduling_rank=2,
    )
    retry = _router_event("router_retry_scheduled", {"retry_at": retry_at})

    reason = _defer_reason(
        context,
        candidate,
        {issue.identifier: issue},
        [retry],
        0,
        0,
        Counter(),
        Counter(),
        Counter(),
    )

    assert reason == "retry_backoff"


def test_pending_package_with_future_retry_time_is_deferred(tmp_path: Path) -> None:
    context = _context(tmp_path)
    issue = context.issues[0]
    candidate = _Candidate(
        issue=issue,
        route_kind="provider",
        route_name="codex",
        provider_profile="codex",
        package_issue_ids=[issue.identifier],
        pending_since=issue.created_at,
        attempt=1,
        scheduling_rank=2,
    )
    retry = _router_event(
        "router_retry_scheduled",
        {"retry_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    )

    reason = _defer_reason(
        context,
        candidate,
        {issue.identifier: issue},
        [retry],
        0,
        0,
        Counter(),
        Counter(),
        Counter(),
    )

    assert reason == "retry_backoff"


def test_route_error_rejects_blank_route_name() -> None:
    configuration = _router_configuration()

    assert _route_error(configuration.router, _issue(labels=["agent-provider: "])) == (
        "invalid_route"
    )


def test_pending_since_ignores_transition_with_missing_timestamp(
    tmp_path: Path,
) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    (events_dir / "bad-transition.json").write_text(
        json.dumps(
            {
                "event_id": "bad-transition",
                "issue_id": "kbs-router-test",
                "event_type": "state_transition",
                "payload": {"to_status": "open"},
            }
        ),
        encoding="utf-8",
    )
    issue = _issue()

    assert _pending_since(events_dir, issue, "open") == issue.created_at


def test_blocked_by_dependency_defers_for_missing_or_nonterminal_target(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    missing = _issue(dependencies=[{"target": "kbs-missing", "type": "blocked-by"}])
    active_target = _issue(identifier="kbs-active", status="in_progress")
    waiting = _issue(
        dependencies=[{"target": active_target.identifier, "type": "blocked-by"}]
    )

    assert _has_blocking_dependency(missing, {}, context.router)
    assert _has_blocking_dependency(
        waiting, {active_target.identifier: active_target}, context.router
    )
    nonblocking = _issue(
        dependencies=[{"target": active_target.identifier, "type": "relates-to"}]
    )
    assert not _has_blocking_dependency(
        nonblocking, {active_target.identifier: active_target}, context.router
    )


def test_policy_rejection_is_fail_closed_and_empty_policy_set_is_allowed(
    monkeypatch, tmp_path: Path
) -> None:
    from kanbus.policy_context import PolicyViolationError

    context = _context(tmp_path)
    policies_dir = context.project_dir / "policies"
    policies_dir.mkdir()
    issue = context.issues[0]
    all_issues = {issue.identifier: issue}
    monkeypatch.setattr("kanbus.policy_loader.load_policies", lambda _path: [])
    assert not _policy_rejects(context, issue, all_issues)

    monkeypatch.setattr(
        "kanbus.policy_loader.load_policies", lambda _path: [("x", object())]
    )
    monkeypatch.setattr(
        "kanbus.policy_evaluator.evaluate_policies",
        lambda *_args: (_ for _ in ()).throw(
            PolicyViolationError("policy", "rule", "step", "denied", issue.identifier)
        ),
    )
    assert _policy_rejects(context, issue, all_issues)

    monkeypatch.setattr(
        "kanbus.policy_evaluator.evaluate_policies", lambda *_args: None
    )
    assert not _policy_rejects(context, issue, all_issues)


def test_read_events_ignores_non_json_and_unusable_records(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    (events_dir / "broken.json").write_text("{", encoding="utf-8")
    (events_dir / "not-a-record.json").write_text(
        json.dumps({"event_id": "empty"}), encoding="utf-8"
    )

    assert _read_events(events_dir) == []
    assert _read_events(tmp_path / "missing-events") == []


def test_router_event_encoding_covers_renewal_failure_and_checkpoint_defaults() -> None:
    attempt_type, attempt_payload = _encode_router_event(
        "router_lease_renewal_failed", "kbs-router-test", {"reason": "lost"}
    )
    result_type, result_payload = _encode_router_event(
        "router_completed",
        "kbs-router-test",
        {"checkpoint": {"ref": "sha:abc"}},
    )

    assert (attempt_type, attempt_payload["action"]) == (
        "router.attempt",
        "lease_renewal_failed",
    )
    assert result_type == "router.result"
    assert result_payload["checkpoint_ref"] == "sha:abc"
    assert result_payload["checkpoint_revision"] == 1


def test_router_event_encoding_rejects_unsupported_semantic_event() -> None:
    with pytest.raises(IssueRouterError, match="unsupported router event type mystery"):
        _encode_router_event("mystery", "kbs-router-test", {})


def test_router_group_is_registered_on_the_project_cli() -> None:
    from kanbus.cli import cli

    assert cli.commands["router"] is router_group


def test_router_plan_cli_translates_planning_errors(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("kanbus.router_cli._load_context", lambda: object())
    monkeypatch.setattr(
        "kanbus.router_cli.build_router_plan",
        lambda _context: (_ for _ in ()).throw(IssueRouterError("plan unavailable")),
    )

    result = runner.invoke(router_group, ["plan"])

    assert result.exit_code == 1
    assert result.output == "error: plan unavailable\n"


@pytest.mark.parametrize("args", [["run"], ["run", "--once", "--watch"]])
def test_router_run_cli_requires_one_execution_mode(args: list[str]) -> None:
    result = CliRunner().invoke(router_group, args)

    assert result.exit_code == 2
    assert "select exactly one of --once or --watch" in result.output


@pytest.mark.parametrize(
    ("error", "exit_code", "expected"),
    [
        (KeyboardInterrupt(), 0, ""),
        (IssueRouterError("scheduler failed"), 1, "error: scheduler failed\n"),
    ],
)
def test_router_watch_cli_handles_interrupt_and_runtime_error(
    monkeypatch, error: BaseException, exit_code: int, expected: str
) -> None:
    monkeypatch.setattr("kanbus.router_cli._load_context", lambda: object())
    monkeypatch.setattr(
        "kanbus.router_execution.run_router_watch",
        lambda _context: (_ for _ in ()).throw(error),
    )

    result = CliRunner().invoke(router_group, ["run", "--watch"])

    assert result.exit_code == exit_code
    assert result.output == expected


def test_router_stop_clears_running_flag_when_no_package_is_active(monkeypatch) -> None:
    context = SimpleNamespace(
        control=RouterControlState(running=True),
        project_dir=Path("project"),
        root=Path("."),
    )
    written = []
    monkeypatch.setattr("kanbus.router_cli._load_context", lambda: context)
    monkeypatch.setattr("kanbus.router_cli.count_active_runs", lambda _path: 0)
    monkeypatch.setattr(
        "kanbus.router_cli.write_router_control",
        lambda _root, state: written.append(state),
    )
    monkeypatch.setattr("kanbus.router_cli._record_control", lambda *_args: None)

    result = CliRunner().invoke(router_group, ["stop"])

    assert result.exit_code == 0
    assert result.output == "Issue Router stop requested.\n"
    assert written[0].running is False
    assert written[0].stop_requested is True


def test_router_hold_cli_reports_unknown_agent_class(monkeypatch) -> None:
    configuration = _router_configuration()
    context = SimpleNamespace(
        router=configuration.router,
        control=RouterControlState(),
    )
    monkeypatch.setattr("kanbus.router_cli._load_context", lambda: context)

    result = CliRunner().invoke(router_group, ["hold", "--class", "missing"])

    assert result.exit_code == 2
    assert result.output == 'error: unknown agent class "missing"\n'


def test_coordination_context_reports_project_marker_and_configuration_errors(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        project_cli,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("not a project")),
    )
    marker_error = CliRunner().invoke(
        project_cli.cli, ["coordination", "inspect", "--resource", "job:1"]
    )
    assert marker_error.exit_code == 1
    assert marker_error.output == "Error: not a project\n"

    monkeypatch.setattr(
        project_cli, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        project_cli,
        "load_project_configuration",
        lambda _path: (_ for _ in ()).throw(ConfigurationError("invalid config")),
    )
    config_error = CliRunner().invoke(
        project_cli.cli, ["coordination", "inspect", "--resource", "job:1"]
    )
    assert config_error.exit_code == 1
    assert config_error.output == "Error: invalid config\n"


def test_coordination_claim_falls_back_from_unavailable_mutex_api(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mutex_api")
    state = _active_lease_state()
    monkeypatch.setattr(
        coordination_mutex_api,
        "acquire",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            coordination_mutex_api.MutexApiUnavailable("service down")
        ),
    )
    monkeypatch.setattr(
        project_cli, "_coordination_fallback_provider", lambda *_args: "git"
    )
    monkeypatch.setattr(
        project_cli, "coordination_claim", lambda *_args, **_kwargs: state
    )

    result = CliRunner().invoke(project_cli.cli, _coordination_args("claim"))

    assert result.exit_code == 0
    assert result.output.startswith("provider: git\nresource: job:router-test\n")
    assert "state: active soft ownership" in result.output


def test_coordination_claim_surfaces_mutex_api_rejection(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mutex_api")
    monkeypatch.setattr(
        coordination_mutex_api,
        "acquire",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CoordinationError("mutex claim rejected")
        ),
    )

    result = CliRunner().invoke(project_cli.cli, _coordination_args("claim"))

    assert result.exit_code == 1
    assert result.output == "Error: mutex claim rejected\n"


def test_coordination_claim_failure_rolls_back_and_reports_rollback_failure(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mutex_api")
    lease = coordination_mutex_api.MutexLease(
        resource="job:router-test",
        owner="worker-a",
        claim_id="claim-a",
        revision=1,
        claimed_at=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        expires_at=datetime(2026, 9, 17, 12, 5, tzinfo=UTC),
    )
    released = []
    monkeypatch.setattr(
        coordination_mutex_api, "acquire", lambda *_args, **_kwargs: lease
    )
    monkeypatch.setattr(
        coordination_mutex_api,
        "release",
        lambda *_args, **_kwargs: (
            released.append(True),
            (_ for _ in ()).throw(CoordinationError("rollback refused")),
        ),
    )
    monkeypatch.setattr(
        project_cli,
        "coordination_claim",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CoordinationError("Git history write failed")
        ),
    )

    result = CliRunner().invoke(project_cli.cli, _coordination_args("claim"))

    assert result.exit_code == 1
    assert released == [True]
    assert result.output == (
        "Error: mutex api acquired lease but durable Git claim could not be recorded: "
        "Git history write failed; best-effort mutex release failed: rollback refused\n"
    )


def test_coordination_claim_reports_git_recording_error(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="git")
    monkeypatch.setattr(
        project_cli,
        "coordination_claim",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CoordinationError("claim event invalid")
        ),
    )

    result = CliRunner().invoke(project_cli.cli, _coordination_args("claim"))

    assert result.exit_code == 1
    assert result.output == "Error: claim event invalid\n"


def test_mqtt_claim_visibility_failure_reports_git_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mqtt")
    state = _active_lease_state(provider_event=True)
    monkeypatch.setattr(
        project_cli, "coordination_claim", lambda *_args, **_kwargs: state
    )
    monkeypatch.setattr(
        "kanbus.coordination_runtime.publish_claim_visibility",
        lambda *_args, **_kwargs: False,
    )

    result = CliRunner().invoke(project_cli.cli, _coordination_args("claim"))

    assert result.exit_code == 0
    assert result.output.startswith("provider: git\n")
    assert "state: active soft ownership" in result.output


def test_mutex_renew_unavailable_falls_back_but_api_rejection_is_reported(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mutex_api")
    monkeypatch.setattr(
        coordination_mutex_api,
        "renew",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            coordination_mutex_api.MutexApiUnavailable("service down")
        ),
    )
    monkeypatch.setattr(
        project_cli, "_coordination_fallback_provider", lambda *_args: "git"
    )
    monkeypatch.setattr(
        project_cli,
        "coordination_renew",
        lambda *_args, **_kwargs: _active_lease_state(),
    )
    fallback = CliRunner().invoke(project_cli.cli, _coordination_args("renew"))
    assert fallback.exit_code == 0
    assert fallback.output.startswith("provider: git\n")

    monkeypatch.setattr(
        coordination_mutex_api,
        "renew",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CoordinationError("mutex renewal rejected")
        ),
    )
    rejected = CliRunner().invoke(project_cli.cli, _coordination_args("renew"))
    assert rejected.exit_code == 1
    assert rejected.output == "Error: mutex renewal rejected\n"


def test_mutex_renew_reports_git_history_failure_after_api_success(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mutex_api")
    lease = coordination_mutex_api.MutexLease(
        resource="job:router-test",
        owner="worker-a",
        claim_id="claim-a",
        revision=2,
        claimed_at=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
        expires_at=datetime(2026, 9, 17, 12, 5, tzinfo=UTC),
    )
    monkeypatch.setattr(
        coordination_mutex_api, "renew", lambda *_args, **_kwargs: lease
    )
    monkeypatch.setattr(
        "kanbus.coordination._record_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CoordinationError("history unavailable")
        ),
    )

    result = CliRunner().invoke(project_cli.cli, _coordination_args("renew"))

    assert result.exit_code == 1
    assert result.output == (
        "Error: mutex api renewed lease but durable Git renewal could not be "
        "recorded: history unavailable\n"
    )


def test_mqtt_renew_visibility_failure_reports_git_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mqtt")
    monkeypatch.setattr(
        project_cli,
        "coordination_renew",
        lambda *_args, **_kwargs: _active_lease_state(provider_event=True),
    )
    monkeypatch.setattr(
        "kanbus.coordination_runtime.publish_renewal_visibility",
        lambda *_args, **_kwargs: False,
    )

    result = CliRunner().invoke(project_cli.cli, _coordination_args("renew"))

    assert result.exit_code == 0
    assert result.output.startswith("provider: git\n")
    assert "state: active soft ownership" in result.output


def test_mutex_release_unavailable_falls_back_and_rejection_is_reported(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mutex_api")
    monkeypatch.setattr(
        coordination_mutex_api,
        "release",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            coordination_mutex_api.MutexApiUnavailable("service down")
        ),
    )
    monkeypatch.setattr(
        project_cli, "_coordination_fallback_provider", lambda *_args: "git"
    )
    monkeypatch.setattr(
        project_cli,
        "coordination_release",
        lambda *_args, **_kwargs: "release-event",
    )
    fallback = CliRunner().invoke(project_cli.cli, _coordination_args("release"))
    assert fallback.exit_code == 0
    assert fallback.output == (
        "provider: git\nresource: job:router-test\nstate: released\n"
    )

    monkeypatch.setattr(
        coordination_mutex_api,
        "release",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CoordinationError("mutex release rejected")
        ),
    )
    rejected = CliRunner().invoke(project_cli.cli, _coordination_args("release"))
    assert rejected.exit_code == 1
    assert rejected.output == "Error: mutex release rejected\n"


def test_mutex_release_reports_git_history_failure_after_api_success(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mutex_api")
    monkeypatch.setattr(
        coordination_mutex_api, "release", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "kanbus.coordination._record_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CoordinationError("history unavailable")
        ),
    )

    result = CliRunner().invoke(project_cli.cli, _coordination_args("release"))

    assert result.exit_code == 1
    assert result.output == (
        "Error: mutex api released lease but durable Git release could not be "
        "recorded: history unavailable\n"
    )


def test_git_release_and_mqtt_visibility_errors_and_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="git")
    monkeypatch.setattr(
        project_cli,
        "coordination_release",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CoordinationError("release event invalid")
        ),
    )
    failure = CliRunner().invoke(project_cli.cli, _coordination_args("release"))
    assert failure.exit_code == 1
    assert failure.output == "Error: release event invalid\n"

    _coordination_cli_setup(monkeypatch, tmp_path, provider="mqtt")
    monkeypatch.setattr(
        project_cli, "coordination_release", lambda *_args, **_kwargs: "release-event"
    )
    monkeypatch.setattr(project_cli, "operation_sequence_for_event", lambda *_args: 2)
    monkeypatch.setattr(
        "kanbus.coordination_runtime.publish_release_visibility",
        lambda *_args, **_kwargs: False,
    )
    fallback = CliRunner().invoke(project_cli.cli, _coordination_args("release"))
    assert fallback.exit_code == 0
    assert fallback.output == (
        "provider: git\nresource: job:router-test\nstate: released\n"
    )


def test_mutex_inspect_unavailable_falls_back_and_api_error_is_reported(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mutex_api")
    monkeypatch.setattr(
        coordination_mutex_api,
        "inspect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            coordination_mutex_api.MutexApiUnavailable("service down")
        ),
    )
    monkeypatch.setattr(
        project_cli, "_coordination_fallback_provider", lambda *_args: "git"
    )
    monkeypatch.setattr(
        project_cli,
        "inspect_coordination_lease",
        lambda *_args: LeaseState(resource="job:router-test"),
    )
    fallback = CliRunner().invoke(
        project_cli.cli, ["coordination", "inspect", "--resource", "job:router-test"]
    )
    assert fallback.exit_code == 0
    assert fallback.output == (
        "provider: git\nresource: job:router-test\nstate: eligible\n"
    )

    monkeypatch.setattr(
        coordination_mutex_api,
        "inspect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CoordinationError("mutex inspect rejected")
        ),
    )
    rejected = CliRunner().invoke(
        project_cli.cli, ["coordination", "inspect", "--resource", "job:router-test"]
    )
    assert rejected.exit_code == 1
    assert rejected.output == "Error: mutex inspect rejected\n"


def test_mqtt_inspect_publication_failure_falls_back_to_git_and_errors_are_reported(
    monkeypatch, tmp_path: Path
) -> None:
    _coordination_cli_setup(monkeypatch, tmp_path, provider="mqtt")
    monkeypatch.setattr(
        "kanbus.coordination_mqtt.reconcile_lease",
        lambda *_args: (LeaseState(resource="job:router-test"), False),
    )
    fallback = CliRunner().invoke(
        project_cli.cli, ["coordination", "inspect", "--resource", "job:router-test"]
    )
    assert fallback.exit_code == 0
    assert fallback.output == (
        "provider: git\nresource: job:router-test\nstate: eligible\n"
    )

    monkeypatch.setattr(
        "kanbus.coordination_mqtt.reconcile_lease",
        lambda *_args: (_ for _ in ()).throw(
            CoordinationError("MQTT state could not be reconciled")
        ),
    )
    failure = CliRunner().invoke(
        project_cli.cli, ["coordination", "inspect", "--resource", "job:router-test"]
    )
    assert failure.exit_code == 1
    assert failure.output == "Error: MQTT state could not be reconciled\n"
