"""Deterministic planning and durable state for the optional Issue Router."""

from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.coordination import inspect_lease, parse_timestamp
from kanbus.event_history import EventRecord, create_event, write_events_batch
from kanbus.issue_listing import IssueListingError, list_issues
from kanbus.models import (
    IssueData,
    IssueRouterConfiguration,
    ProjectConfiguration,
)
from kanbus.project import ProjectMarkerError, get_configuration_path


class IssueRouterError(RuntimeError):
    """A router operation could not be completed safely."""


class RouterPlanRoute(BaseModel):
    """Selected route for one package."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    provider_profile: str


class RouterPlanEligiblePackage(BaseModel):
    """Eligible package in deterministic scheduling order."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str
    route: RouterPlanRoute
    package_issue_ids: list[str]
    pending_since: str
    attempt: int


class RouterPlanDeferredPackage(BaseModel):
    """Package deferred with one stable reason."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str
    reason: str


class RouterPlan(BaseModel):
    """Stable JSON response for ``router plan --json``."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    enabled: bool
    paused: bool
    eligible: list[RouterPlanEligiblePackage]
    deferred: list[RouterPlanDeferredPackage]


class RouterControlState(BaseModel):
    """Mutable host-local scheduler controls, separate from Kanbus board data."""

    model_config = ConfigDict(extra="forbid")

    paused: bool = False
    running: bool = False
    stop_requested: bool = False
    held_routes: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class RouterContext:
    """Loaded project and router data required by one operation."""

    root: Path
    project_dir: Path
    configuration: ProjectConfiguration
    router: IssueRouterConfiguration
    issues: list[IssueData]
    control: RouterControlState
    source_root: Path | None = None


@dataclass(frozen=True)
class _Candidate:
    issue: IssueData
    route_kind: str
    route_name: str
    provider_profile: str
    package_issue_ids: list[str]
    pending_since: datetime
    attempt: int
    scheduling_rank: int


def load_router_context(root: Path) -> RouterContext:
    """Load router configuration, issues, and local controls.

    :param root: Repository root containing ``.kanbus.yml``.
    :type root: Path
    :return: Validated router execution context.
    :rtype: RouterContext
    :raises IssueRouterError: If the project or router is not configured.
    """
    try:
        config_path = get_configuration_path(root)
        configuration = load_project_configuration(config_path)
    except (ProjectMarkerError, ConfigurationError) as error:
        raise IssueRouterError(str(error)) from error
    if configuration.router is None:
        raise IssueRouterError("issue router is not configured")
    project_dir = config_path.parent / configuration.project_directory
    previous_no_daemon = os.environ.get("KANBUS_NO_DAEMON")
    os.environ["KANBUS_NO_DAEMON"] = "1"
    try:
        issues = list_issues(root)
    except IssueListingError as error:
        raise IssueRouterError(str(error)) from error
    finally:
        if previous_no_daemon is None:
            os.environ.pop("KANBUS_NO_DAEMON", None)
        else:
            os.environ["KANBUS_NO_DAEMON"] = previous_no_daemon
    return RouterContext(
        root=root,
        project_dir=project_dir,
        configuration=configuration,
        router=configuration.router,
        issues=issues,
        control=read_router_control(root),
    )


def build_router_plan(context: RouterContext) -> RouterPlan:
    """Build the deterministic plan for all pending or recoverable packages.

    :param context: Loaded router context.
    :type context: RouterContext
    :return: Ordered eligible packages and deferred packages.
    :rtype: RouterPlan
    """
    if not context.router.enabled:
        return RouterPlan(
            enabled=False, paused=context.control.paused, eligible=[], deferred=[]
        )

    # The shared-state worktree gives the scheduler a clean, reconciled board,
    # while the source checkout can contain a just-written immutable event that
    # has not reached the shared branch yet. Plan from their union, as the Rust
    # runtime does, so a worker never overlooks its own durable state.
    events = _planning_events(context)
    issues = [issue.model_copy(deep=True) for issue in context.issues]
    _apply_router_status_overlay(issues, events, context.router)
    planning_context = replace(context, issues=issues)
    issues_by_id = {issue.identifier: issue for issue in issues}
    candidates = _collect_candidates(planning_context, issues_by_id, events)
    candidates.sort(
        key=lambda candidate: (
            candidate.scheduling_rank,
            candidate.pending_since,
            candidate.issue.created_at.astimezone(UTC),
            candidate.issue.identifier,
        )
    )
    active_counts, class_counts, provider_counts = _current_route_counts(
        planning_context, issues_by_id, events
    )
    # Human-managed board work must not consume the router's worker capacity.
    current_wip = sum(active_counts.values())
    current_review = sum(
        issue.status == planning_context.router.workflow.review
        and _route_error(planning_context.router, issue) is None
        and _has_preserved_review_conversation(events, issue.identifier)
        for issue in issues
    )
    # Human-managed board work must not consume the router's worker capacity.
    current_wip = sum(active_counts.values())
    current_review = sum(
        issue.status == context.router.workflow.review
        and _route_error(context.router, issue) is None
        and _has_preserved_review_conversation(events, issue.identifier)
        for issue in context.issues
    )
    eligible: list[RouterPlanEligiblePackage] = []
    deferred: list[RouterPlanDeferredPackage] = []
    for candidate in candidates:
        if (
            candidate.route_kind == "class"
            and candidate.route_name in planning_context.router.classes
        ):
            candidate = replace(
                candidate,
                provider_profile=next(
                    (
                        profile
                        for profile in planning_context.router.classes[
                            candidate.route_name
                        ].providers
                        if planning_context.router.limits.provider_wip.get(profile)
                        is None
                        or provider_counts[profile]
                        < context.router.limits.provider_wip[profile]
                    ),
                    candidate.provider_profile,
                ),
            )
        reason = _defer_reason(
            planning_context,
            candidate,
            issues_by_id,
            events,
            current_wip,
            current_review,
            active_counts,
            class_counts,
            provider_counts,
        )
        if reason is not None:
            deferred.append(
                RouterPlanDeferredPackage(
                    issue_id=candidate.issue.identifier,
                    reason=reason,
                )
            )
            continue
        eligible.append(
            RouterPlanEligiblePackage(
                issue_id=candidate.issue.identifier,
                route=RouterPlanRoute(
                    kind=candidate.route_kind,
                    name=candidate.route_name,
                    provider_profile=candidate.provider_profile,
                ),
                package_issue_ids=candidate.package_issue_ids,
                pending_since=_format_router_timestamp(candidate.pending_since),
                attempt=candidate.attempt,
            )
        )
    return RouterPlan(
        enabled=True,
        paused=context.control.paused,
        eligible=eligible,
        deferred=deferred,
    )


def _planning_events(context: RouterContext) -> list[dict[str, Any]]:
    """Return the de-duplicated local and shared immutable event history."""
    events = _read_events(context.project_dir / "events")
    source_root = context.source_root
    if source_root is not None and source_root.resolve() != context.root.resolve():
        source_events = _read_events(
            source_root / context.configuration.project_directory / "events"
        )
        known_ids = {str(event.get("event_id", "")) for event in events}
        events.extend(
            event
            for event in source_events
            if str(event.get("event_id", "")) not in known_ids
        )
    return sorted(
        events,
        key=lambda event: (
            str(event.get("occurred_at", "")),
            str(event.get("event_id", "")),
        ),
    )


def _apply_router_status_overlay(
    issues: list[IssueData],
    events: list[dict[str, Any]],
    router: IssueRouterConfiguration,
) -> None:
    """Project the newest durable router lifecycle onto non-terminal issues."""
    lifecycle_types = {
        "router_claimed",
        "router_completed",
        "router_blocked",
        "router_forge_event",
        "router_pull_request_opened",
        "router_pull_request_approved",
        "router_pull_request_closed",
        "router_check_run_event",
        "router.conversation",
        "router_conversation",
    }
    approvals = {
        str(event.get("issue_id", "")).removeprefix("router:"): str(
            event.get("payload", {}).get("head_sha", "")
        )
        for event in events
        if event.get("event_type") == "router_pull_request_approved"
        and event.get("payload", {}).get("head_sha")
    }
    for issue in issues:
        if issue.status in router.workflow.terminal:
            continue
        routed = [
            event
            for event in events
            if event.get("issue_id") == f"router:{issue.identifier}"
            and event.get("event_type") in lifecycle_types
        ]
        if not routed:
            continue
        event = max(
            routed,
            key=lambda candidate: (
                str(candidate.get("occurred_at", "")),
                str(candidate.get("event_id", "")),
            ),
        )
        # The card itself is canonical.  A durable router event can survive
        # after a human (or the router) has already written the card, so an
        # older projection must not resurrect stale work for scheduling.
        try:
            event_time = parse_timestamp(str(event.get("occurred_at", "")))
        except (TypeError, ValueError):
            event_time = None
        if event_time is not None and issue.updated_at > event_time:
            continue
        board_transition = max(
            (
                candidate
                for candidate in events
                if candidate.get("issue_id") == issue.identifier
                and candidate.get("event_type") == "state_transition"
            ),
            key=lambda candidate: (
                str(candidate.get("occurred_at", "")),
                str(candidate.get("event_id", "")),
            ),
            default=None,
        )
        if board_transition is not None and (
            str(board_transition.get("occurred_at", "")),
            str(board_transition.get("event_id", "")),
        ) >= (
            str(event.get("occurred_at", "")),
            str(event.get("event_id", "")),
        ):
            continue
        payload = event.get("payload", {})
        event_type = event.get("event_type")
        status: str | None = None
        if event_type == "router_claimed":
            status = router.workflow.active
        elif event_type == "router_completed":
            status = router.workflow.review
        elif event_type == "router_blocked":
            status = router.workflow.blocked
        elif event_type in {"router.conversation", "router_conversation"}:
            status = {
                "in_progress": router.workflow.active,
                "blocked": router.workflow.blocked,
                "review": router.workflow.review,
            }.get(payload.get("lifecycle"))
        elif event_type == "router_forge_event" and payload.get("action") in {
            "requested_changes",
            "check_run_failure",
            "checks_failed",
        }:
            status = router.workflow.active
        elif event_type == "router_check_run_event" and payload.get("action") in {
            "check_run_failure",
            "checks_failed",
        }:
            status = router.workflow.active
        elif event_type in {
            "router_pull_request_opened",
            "router_pull_request_approved",
            "router_check_run_event",
        }:
            status = router.workflow.review
        elif event_type == "router_pull_request_closed":
            if not payload.get("merged"):
                status = router.workflow.blocked
            elif payload.get("approved") or approvals.get(issue.identifier) == str(
                payload.get("head_sha", "")
            ):
                status = (
                    router.workflow.terminal[0] if router.workflow.terminal else None
                )
            else:
                status = router.workflow.review
        if status is not None:
            issue.status = status


def format_router_plan_text(plan: RouterPlan) -> str:
    """Render the stable human-readable planning response.

    :param plan: Validated router plan.
    :type plan: RouterPlan
    :return: Deterministic text ending in one newline.
    :rtype: str
    """
    eligible_rows = [
        "  "
        + package.issue_id
        + f" route={package.route.kind}:{package.route.name}"
        + f" provider={package.route.provider_profile}"
        + f" package={','.join(package.package_issue_ids)}"
        + f" pending_since={package.pending_since} attempt={package.attempt}"
        for package in plan.eligible
    ]
    deferred_rows = [
        f"  {package.issue_id} reason={package.reason}" for package in plan.deferred
    ]
    return (
        "\n".join(
            [
                "Eligible:",
                *(eligible_rows or ["  none"]),
                "Deferred:",
                *(deferred_rows or ["  none"]),
                (
                    f"Summary: eligible={len(plan.eligible)} deferred={len(plan.deferred)} "
                    f"paused={str(plan.paused).lower()}"
                ),
            ]
        )
        + "\n"
    )


def read_router_control(root: Path) -> RouterControlState:
    """Read local scheduler controls without consulting Git history.

    :param root: Repository root.
    :type root: Path
    :return: Current local control state or its initial state.
    :rtype: RouterControlState
    :raises IssueRouterError: If local control data is malformed.
    """
    path = router_control_path(root)
    if not path.exists():
        return RouterControlState()
    try:
        return RouterControlState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise IssueRouterError("router local control state is invalid") from error


def write_router_control(root: Path, state: RouterControlState) -> None:
    """Atomically persist host-local router controls.

    :param root: Repository root.
    :type root: Path
    :param state: New local control state.
    :type state: RouterControlState
    """
    path = router_control_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")
    temporary_path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, path)


def router_control_path(root: Path) -> Path:
    """Resolve the private Git metadata path for local router control state.

    :param root: Repository root.
    :type root: Path
    :return: Git-private router control file path.
    :rtype: Path
    :raises IssueRouterError: If the repository metadata path cannot be resolved.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise IssueRouterError("router requires a Git repository") from error
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = root / path
    return path / "kanbus" / "router-control.json"


def record_router_event(
    project_dir: Path,
    *,
    package_id: str,
    event_type: str,
    payload: dict[str, Any],
    actor_id: str = "issue-router",
    occurred_at: datetime | None = None,
) -> str:
    """Append one immutable event to a package's router history.

    :param project_dir: Kanbus project directory.
    :type project_dir: Path
    :param package_id: Routed package root identifier.
    :type package_id: str
    :param event_type: Router event type.
    :type event_type: str
    :param payload: Structured event content.
    :type payload: dict[str, Any]
    :param actor_id: Actor that produced the event.
    :type actor_id: str
    :param occurred_at: Optional deterministic timestamp.
    :type occurred_at: datetime | None
    :return: The persisted event identifier.
    :rtype: str
    :raises IssueRouterError: If the event cannot be persisted.
    """
    event = create_router_event(
        package_id=package_id,
        event_type=event_type,
        payload=payload,
        actor_id=actor_id,
        occurred_at=occurred_at,
    )
    try:
        write_events_batch(project_dir / "events", [event])
    except (OSError, RuntimeError) as error:
        raise IssueRouterError(str(error)) from error
    return event.event_id


def create_router_event(
    *,
    package_id: str,
    event_type: str,
    payload: dict[str, Any],
    actor_id: str = "issue-router",
    occurred_at: datetime | None = None,
) -> EventRecord:
    """Create a canonical router event without persisting it.

    This is used for start events that must pass the shared-state fencing
    check before they can enter the immutable event log.

    :param package_id: Routed package root identifier.
    :type package_id: str
    :param event_type: Router event type to encode.
    :type event_type: str
    :param payload: Structured event content.
    :type payload: dict[str, Any]
    :param actor_id: Actor that produced the event.
    :type actor_id: str
    :param occurred_at: Optional deterministic event timestamp.
    :type occurred_at: datetime | None
    :return: Canonical event record, not yet persisted.
    :rtype: EventRecord
    """
    canonical_type, canonical_payload = _encode_router_event(
        event_type, package_id, payload
    )
    return create_event(
        issue_id=f"router:{package_id}",
        event_type=canonical_type,
        actor_id=actor_id,
        payload=canonical_payload,
        occurred_at=_format_router_event_timestamp(occurred_at or datetime.now(UTC)),
    )


def read_router_events(project_dir: Path, package_id: str) -> list[dict[str, Any]]:
    """Read immutable router history for one package in stable order.

    :param project_dir: Kanbus project directory.
    :type project_dir: Path
    :param package_id: Routed package root identifier.
    :type package_id: str
    :return: Matching router events ordered by time and identifier.
    :rtype: list[dict[str, Any]]
    """
    return [
        _decode_router_event(event)
        for event in _read_events(project_dir / "events")
        if event.get("issue_id") == f"router:{package_id}"
    ]


def _collect_candidates(
    context: RouterContext,
    issues_by_id: dict[str, IssueData],
    events: list[dict[str, Any]],
) -> list[_Candidate]:
    current_time = datetime.now(UTC)
    candidates: list[_Candidate] = []
    for issue in context.issues:
        # A child belongs to the nearest routed ancestor's package.  An
        # un-routed parent, however, must not make its children disappear
        # from planning: they remain independently diagnosable (and receive
        # the same invalid-route outcome as the Rust runtime).
        if not _has_route_label(issue) and _has_routed_ancestor(issue, issues_by_id):
            continue
        if _has_live_package_claim(context, issue.identifier, events):
            continue
        requested_changes = _has_requested_changes(events, issue.identifier)
        retry_event = _latest_router_event(
            events, issue.identifier, "router_retry_scheduled"
        )
        if issue.status == context.router.workflow.pending:
            rank = 2
        elif issue.status == context.router.workflow.active and requested_changes:
            rank = 1
        elif issue.status == context.router.workflow.active and retry_event is not None:
            retry_at = retry_event.get("payload", {}).get("retry_at")
            try:
                if parse_timestamp(str(retry_at)) > current_time:
                    continue
            except (TypeError, ValueError):
                continue
            rank = 0
        elif issue.status == context.router.workflow.active:
            rank = 0
        else:
            continue
        route = _resolve_route(context.router, issue, events)
        route_kind, route_name, profile, error = route
        if error is not None:
            candidates.append(
                _Candidate(
                    issue=issue,
                    route_kind=route_kind,
                    route_name=route_name,
                    provider_profile=profile,
                    package_issue_ids=[issue.identifier],
                    pending_since=_pending_since(
                        context.project_dir / "events",
                        issue,
                        context.router.workflow.pending,
                    ),
                    attempt=_next_attempt(events, issue.identifier),
                    scheduling_rank=rank,
                )
            )
            continue
        candidates.append(
            _Candidate(
                issue=issue,
                route_kind=route_kind,
                route_name=route_name,
                provider_profile=profile,
                package_issue_ids=_package_issue_ids(issue, issues_by_id),
                pending_since=_pending_since(
                    context.project_dir / "events",
                    issue,
                    context.router.workflow.pending,
                ),
                attempt=_next_attempt(events, issue.identifier),
                scheduling_rank=rank,
            )
        )
    return candidates


def _has_live_package_claim(
    context: RouterContext, issue_id: str, events: list[dict[str, Any]]
) -> bool:
    current = _latest_router_event(events, issue_id, "router_claimed")
    claim_id = (
        "" if current is None else str(current.get("payload", {}).get("claim_id", ""))
    )
    resource = f"router:issue:{issue_id}"
    lease = inspect_lease(context.project_dir / "events", resource)
    if (
        "mqtt" in context.configuration.coordination.providers
        and context.configuration.realtime.transport in {"auto", "mqtt"}
    ):
        from kanbus.coordination_mqtt import inspect_lease as inspect_mqtt_lease

        lease = inspect_mqtt_lease(
            context.project_dir / "events",
            context.project_dir,
            resource,
            context.configuration,
        )
    return lease.active and (not claim_id or lease.claim_id == claim_id)


def _resolve_route(
    router: IssueRouterConfiguration,
    issue: IssueData,
    events: list[dict[str, Any]],
) -> tuple[str, str, str, str | None]:
    labels = [
        label
        for label in issue.labels
        if label.startswith(("agent-class:", "agent-provider:"))
    ]
    if len(labels) != 1:
        return "", "", "", "invalid_route"
    label = labels[0]
    route_kind, route_name = label.split(":", 1)
    if not route_name.strip():
        return "", "", "", "invalid_route"
    if route_kind == "agent-provider":
        if route_name not in router.providers:
            return "provider", route_name, route_name, "invalid_route"
        return "provider", route_name, route_name, None
    agent_class = router.classes.get(route_name)
    if agent_class is None:
        return "class", route_name, "", "invalid_route"
    last_claim = _latest_router_event(events, issue.identifier, "router_claimed")
    previous_profile = (
        last_claim.get("payload", {}).get("provider_profile")
        if last_claim is not None
        else None
    )
    if previous_profile in agent_class.providers:
        return "class", route_name, str(previous_profile), None
    return "class", route_name, agent_class.providers[0], None


def _defer_reason(
    context: RouterContext,
    candidate: _Candidate,
    issues_by_id: dict[str, IssueData],
    events: list[dict[str, Any]],
    current_wip: int,
    current_review: int,
    active_counts: Counter[str],
    class_counts: Counter[str],
    provider_counts: Counter[str],
) -> str | None:
    issue_id = candidate.issue.identifier
    route_key = (
        f"class:{candidate.route_name}"
        if candidate.route_kind == "class"
        else f"provider-profile:{candidate.provider_profile}"
    )
    if context.control.paused:
        return "paused"
    if route_key in context.control.held_routes:
        return "held"
    if _route_error(context.router, candidate.issue) is not None:
        return "invalid_route"
    if _has_blocking_dependency(candidate.issue, issues_by_id, context.router):
        return "dependency_blocked"
    if _policy_rejects(context, candidate.issue, issues_by_id):
        return "policy_rejected"
    retry_event = _latest_router_event(events, issue_id, "router_retry_scheduled")
    if retry_event is not None:
        retry_at = retry_event.get("payload", {}).get("retry_at")
        try:
            if parse_timestamp(str(retry_at)) > datetime.now(UTC):
                return "retry_backoff"
        except (TypeError, ValueError):
            return "retry_backoff"
    # These are admission caps for new starts. Recoverable active packages
    # already consume their WIP slot, so deferring them here can strand work
    # indefinitely when any configured capacity is full.
    if candidate.issue.status == context.router.workflow.pending:
        if current_wip >= context.router.limits.project_wip:
            return "project_wip_limit"
        if current_review >= context.router.limits.review_wip:
            return "review_wip_limit"
        if candidate.route_kind == "class":
            class_limit = context.router.limits.class_wip.get(candidate.route_name)
            if (
                class_limit is not None
                and class_counts[candidate.route_name] >= class_limit
            ):
                return "class_wip_limit"
        provider_limit = context.router.limits.provider_wip.get(
            candidate.provider_profile
        )
        if (
            provider_limit is not None
            and provider_counts[candidate.provider_profile] >= provider_limit
        ):
            return "provider_wip_limit"
    return None


def _route_error(router: IssueRouterConfiguration, issue: IssueData) -> str | None:
    labels = [
        label
        for label in issue.labels
        if label.startswith(("agent-class:", "agent-provider:"))
    ]
    if len(labels) != 1:
        return "invalid_route"
    prefix, name = labels[0].split(":", 1)
    if not name.strip():
        return "invalid_route"
    if prefix == "agent-class":
        if name not in router.classes:
            return "invalid_route"
    elif name not in router.providers:
        return "invalid_route"
    return None


def _package_issue_ids(
    root_issue: IssueData, issues_by_id: dict[str, IssueData]
) -> list[str]:
    children: dict[str, list[IssueData]] = {}
    for issue in issues_by_id.values():
        if issue.parent:
            children.setdefault(issue.parent, []).append(issue)
    package_ids: list[str] = []
    pending = [root_issue]
    while pending:
        issue = pending.pop()
        if issue.identifier != root_issue.identifier and _has_route_label(issue):
            continue
        package_ids.append(issue.identifier)
        pending.extend(
            sorted(
                children.get(issue.identifier, []),
                key=lambda child: child.identifier,
                reverse=True,
            )
        )
    return sorted(package_ids)


def _has_route_label(issue: IssueData) -> bool:
    return any(
        label.startswith(("agent-class:", "agent-provider:")) for label in issue.labels
    )


def _has_routed_ancestor(issue: IssueData, issues_by_id: dict[str, IssueData]) -> bool:
    """Return whether an ancestor owns this issue as a routed package member."""
    seen: set[str] = set()
    parent_id = issue.parent
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = issues_by_id.get(parent_id)
        if parent is None:
            return False
        if _has_route_label(parent):
            return True
        parent_id = parent.parent
    return False


def _pending_since(events_dir: Path, issue: IssueData, pending_status: str) -> datetime:
    transitions: list[tuple[datetime, str]] = []
    if events_dir.is_dir():
        for event in _read_events(events_dir):
            payload = event.get("payload", {})
            if (
                event.get("issue_id") == issue.identifier
                and event.get("event_type") == "state_transition"
                and payload.get("to_status") == pending_status
            ):
                try:
                    transitions.append(
                        (
                            parse_timestamp(str(event["occurred_at"])),
                            str(event["event_id"]),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
    return max(transitions, default=(issue.created_at.astimezone(UTC), ""))[0]


def _next_attempt(events: list[dict[str, Any]], issue_id: str) -> int:
    retries = [
        event
        for event in events
        if event.get("issue_id") == f"router:{issue_id}"
        and event.get("event_type") == "router_retry_scheduled"
    ]
    if retries:
        payload = max(
            retries,
            key=lambda event: (
                str(event.get("occurred_at", "")),
                str(event.get("event_id", "")),
            ),
        ).get("payload", {})
        attempt = payload.get("next_attempt")
        if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt > 0:
            return attempt
    return 1


def _current_route_counts(
    context: RouterContext,
    issues_by_id: dict[str, IssueData],
    events: list[dict[str, Any]],
) -> tuple[Counter[str], Counter[str], Counter[str]]:
    active_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    provider_counts: Counter[str] = Counter()
    wip_statuses = {
        context.router.workflow.active,
        context.router.workflow.review,
        context.router.workflow.blocked,
    }
    for issue in issues_by_id.values():
        if issue.status not in wip_statuses:
            continue
        route = _resolve_route(context.router, issue, events)
        route_kind, route_name, profile, error = route
        if error is not None:
            continue
        active_counts[issue.identifier] += 1
        if route_kind == "class":
            class_counts[route_name] += 1
        provider_counts[profile] += 1
    return active_counts, class_counts, provider_counts


def _has_blocking_dependency(
    issue: IssueData,
    issues_by_id: dict[str, IssueData],
    router: IssueRouterConfiguration,
) -> bool:
    for dependency in issue.dependencies:
        if dependency.dependency_type != "blocked-by":
            continue
        target = issues_by_id.get(dependency.target)
        if target is None or target.status not in router.workflow.terminal:
            return True
    return False


def _policy_rejects(
    context: RouterContext,
    issue: IssueData,
    issues_by_id: dict[str, IssueData],
) -> bool:
    policies_dir = context.project_dir / "policies"
    if not policies_dir.is_dir():
        return False
    try:
        from kanbus.policy_context import (
            PolicyContext,
            PolicyOperation,
            PolicyViolationError,
            StatusTransition,
        )
        from kanbus.policy_evaluator import evaluate_policies
        from kanbus.policy_loader import PolicyLoadError, load_policies

        documents = load_policies(policies_dir)
        if not documents:
            return False
        proposed = issue.model_copy(update={"status": context.router.workflow.active})
        evaluate_policies(
            PolicyContext(
                current_issue=issue,
                proposed_issue=proposed,
                transition=StatusTransition(issue.status, proposed.status),
                operation=PolicyOperation.UPDATE,
                project_configuration=context.configuration,
                all_issues=list(issues_by_id.values()),
            ),
            documents,
        )
    except (PolicyLoadError, PolicyViolationError):
        return True
    return False


def _has_requested_changes(events: list[dict[str, Any]], issue_id: str) -> bool:
    lifecycle_events = [
        event
        for event in events
        if event.get("issue_id") == f"router:{issue_id}"
        and event.get("event_type")
        in {
            "router_forge_event",
            "router_pull_request_approved",
            "router_pull_request_closed",
            "router_pull_request_opened",
            "router_check_run_event",
        }
    ]
    latest = max(
        lifecycle_events,
        key=lambda event: (
            str(event.get("occurred_at", "")),
            str(event.get("event_id", "")),
        ),
        default=None,
    )
    return (
        latest is not None
        and latest.get("event_type") == "router_forge_event"
        and latest.get("payload", {}).get("action") == "requested_changes"
    )


def _latest_router_event(
    events: list[dict[str, Any]], issue_id: str, event_type: str
) -> dict[str, Any] | None:
    matching = [
        event
        for event in events
        if event.get("issue_id") == f"router:{issue_id}"
        and event.get("event_type") == event_type
    ]
    if event_type == "router_claimed":
        return max(
            matching,
            key=lambda event: (
                int(event.get("payload", {}).get("revision", 0)),
                str(event.get("occurred_at", "")),
                str(event.get("event_id", "")),
            ),
            default=None,
        )
    return max(
        matching,
        key=lambda event: (
            str(event.get("occurred_at", "")),
            str(event.get("event_id", "")),
        ),
        default=None,
    )


def _has_preserved_review_conversation(
    events: list[dict[str, Any]], issue_id: str
) -> bool:
    """Return whether a review slot has visible, durable agent evidence."""
    conversation = _latest_router_event(events, issue_id, "router_conversation")
    if conversation is None:
        conversation = _latest_router_event(events, issue_id, "router.conversation")
    return (
        conversation is not None
        and conversation.get("payload", {}).get("lifecycle") == "review"
    )


def _read_events(events_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not events_dir.is_dir():
        return records
    for path in events_dir.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and isinstance(record.get("payload"), dict):
            records.append(record)
    return sorted(
        [_decode_router_event(record) for record in records],
        key=lambda event: (
            str(event.get("occurred_at", "")),
            str(event.get("event_id", "")),
        ),
    )


def _encode_router_event(
    event_type: str, package_id: str, payload: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Encode Python execution facts with the cross-runtime router schema."""
    value = dict(payload)
    if event_type in {
        "router_paused",
        "router_resumed",
        "route_held",
        "route_unheld",
        "router_started",
        "router_stopped",
        "router_stop_requested",
        "router_cancel_requested",
    }:
        action = {
            "router_paused": "pause",
            "router_resumed": "resume",
            "route_held": "hold",
            "route_unheld": "unhold",
            "router_started": "start",
            "router_stopped": "stop",
            "router_stop_requested": "stop",
            "router_cancel_requested": "cancel",
        }[event_type]
        if "target" in value:
            value["route"] = value.pop("target")
        value["action"] = action
        return "router.control", value
    if event_type == "router_cancelled":
        value["outcome"] = "cancelled"
        return "router.result", value
    if event_type in {
        "router_claimed",
        "router_claim_observed",
        "router_retry_scheduled",
        "router_checkpoint_accepted",
        "router_artifact_published",
        "router_progress",
        "router_lease_renewal_failed",
    }:
        if event_type == "router_claimed":
            value["action"] = "started"
            value.setdefault("attempt", 1)
        elif event_type == "router_retry_scheduled":
            value["action"] = "retryable_failure"
            value.setdefault("attempt", value.get("failed_attempt", 1))
        elif event_type == "router_checkpoint_accepted":
            value["action"] = "checkpoint_accepted"
            value["checkpoint_ref"] = value.pop("ref", None)
            value["checkpoint_revision"] = value.get("revision", 1)
        elif event_type == "router_artifact_published":
            value["action"] = "artifact_published"
        elif event_type == "router_progress":
            value["action"] = "progress"
        elif event_type == "router_lease_renewal_failed":
            value["action"] = "lease_renewal_failed"
        else:
            value["action"] = "observed"
        return "router.attempt", value
    if event_type == "router_conversation":
        # Conversation records are append-only evidence.  Do not fold them
        # into a router result: a malformed result must never erase an agent
        # turn, question, command summary, or diagnostic.
        return "router.conversation", value
    if event_type in {"router_completed", "router_blocked", "router_retry_exhausted"}:
        value["outcome"] = (
            "completed" if event_type == "router_completed" else "blocked"
        )
        checkpoint = value.pop("checkpoint", None)
        if isinstance(checkpoint, dict):
            value["checkpoint_ref"] = checkpoint.get("ref")
            value["checkpoint_revision"] = checkpoint.get(
                "revision", value.get("revision", 1)
            )
        return "router.result", value
    if event_type in {
        "router_pull_request_opened",
        "router_pull_request_observed",
        "router_forge_event",
        "router_pull_request_approved",
        "router_pull_request_closed",
    }:
        default_action = {
            "router_pull_request_opened": "opened",
            "router_pull_request_observed": "synchronize",
            "router_pull_request_approved": "approved",
            "router_pull_request_closed": "closed",
        }.get(event_type)
        value["action"] = value.get("action", default_action)
        if "forge_event_id" in value:
            value["event_id"] = value.pop("forge_event_id")
        if event_type == "router_pull_request_opened" and "head_branch" not in value:
            value["head_branch"] = value.get("branch")
        return "router.forge", value
    raise IssueRouterError(f"unsupported router event type {event_type}")


def _decode_router_event(event: dict[str, Any]) -> dict[str, Any]:
    """Provide the legacy semantic names to reducers from canonical records."""
    result = dict(event)
    payload = dict(event.get("payload", {}))
    kind = event.get("event_type")
    if kind == "router.control":
        action = payload.get("action")
        result["event_type"] = {
            "pause": "router_paused",
            "resume": "router_resumed",
            "hold": "route_held",
            "unhold": "route_unheld",
            "cancel": "router_cancel_requested",
            "start": "router_started",
            "stop": "router_stopped",
        }.get(action, "router_control_event")
        if "route" in payload:
            payload["target"] = payload["route"]
    elif kind == "router.attempt":
        action = payload.get("action")
        result["event_type"] = {
            "started": "router_claimed",
            "retryable_failure": "router_retry_scheduled",
            "checkpoint_accepted": "router_checkpoint_accepted",
            "artifact_published": "router_artifact_published",
            "progress": "router_progress",
            "lease_renewal_failed": "router_lease_renewal_failed",
            "observed": "router_claim_observed",
        }.get(action, "router_attempt")
        if "checkpoint_ref" in payload:
            payload["ref"] = payload["checkpoint_ref"]
    elif kind == "router.result":
        outcome = payload.get("outcome")
        result["event_type"] = {
            "completed": "router_completed",
            "blocked": "router_blocked",
            "cancelled": "router_cancelled",
        }.get(outcome, "router_result")
        if payload.get("checkpoint_ref") is not None:
            payload["checkpoint"] = {
                "ref": payload["checkpoint_ref"],
                "revision": payload.get(
                    "checkpoint_revision", payload.get("revision", 1)
                ),
            }
    elif kind == "router.forge":
        action = payload.get("action")
        result["event_type"] = (
            "router_forge_event"
            if action == "requested_changes"
            else (
                "router_pull_request_approved"
                if action == "approved"
                else (
                    "router_pull_request_closed"
                    if action == "closed"
                    else (
                        "router_check_run_event"
                        if action in {"check_run_success", "check_run_failure"}
                        else (
                            "router_forge_diagnostic"
                            if action == "merged_unapproved"
                            else "router_pull_request_opened"
                        )
                    )
                )
            )
        )
        if "event_id" in payload:
            payload["forge_event_id"] = payload["event_id"]
    result["payload"] = payload
    return result


def _format_router_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _format_router_event_timestamp(value: datetime) -> str:
    """Preserve event append order when multiple mutations occur in one second."""
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )
