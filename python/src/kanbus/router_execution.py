"""Claim-fenced execution, retries, checkpoints, and publication for Issue Router."""

from __future__ import annotations

import hashlib
import json
import math
import os
import posixpath
import signal
import subprocess
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from time import monotonic, sleep
from typing import Callable

from kanbus.coordination import (
    CoordinationError,
    inspect_lease,
    operation_sequence_for_event,
    parse_duration,
    utc_now,
)
from kanbus.coordination import (
    claim as soft_claim,
)
from kanbus.coordination import (
    release as soft_release,
)
from kanbus.coordination import (
    renew as soft_renew,
)
from kanbus.coordination_mutex_api import (
    MutexApiError,
    MutexApiUnavailable,
)
from kanbus.coordination_mutex_api import (
    acquire as mutex_acquire,
)
from kanbus.coordination_mutex_api import (
    inspect as mutex_inspect,
)
from kanbus.coordination_mutex_api import (
    is_configured as mutex_is_configured,
)
from kanbus.coordination_mutex_api import (
    release as mutex_release,
)
from kanbus.coordination_mutex_api import (
    renew as mutex_renew,
)
from kanbus.coordination_runtime import (
    publish_claim_visibility,
    publish_release_visibility,
    publish_renewal_visibility,
    select_soft_provider,
    start_soft_listener,
)
from kanbus.issue_comment import (
    IssueCommentError,
    add_comment as add_issue_comment,
)
from kanbus.issue_router import (
    IssueRouterError,
    RouterContext,
    RouterPlanEligiblePackage,
    _latest_router_event,
    _read_events,
    build_router_plan,
    create_router_event,
    load_router_context,
    read_router_events,
    record_router_event,
    write_router_control,
)
from kanbus.issue_update import IssueUpdateError, update_issue
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.router_adapters import (
    CodexExecAdapter,
    RouterAdapter,
    RouterAgentResult,
    RouterCheckpoint,
    RouterExecutionRequest,
    _process_identity,
)
from kanbus.router_conversation import latest_conversation, record_conversation
from kanbus.router_forge import (
    FakeForge,
    ForgePullRequest,
    GitHubForge,
    record_github_check_run_event,
    record_github_pull_request_event,
)
from kanbus.router_state import publish_router_start_event, publish_router_state

HARD_COORDINATION_ERROR = (
    "hard router coordination requires Mutex API; provider mutex_api is "
    "unavailable; no package was started"
)


@dataclass(frozen=True)
class RouterRunResult:
    """Stable outcome counters for one scheduler pass."""

    started: int = 0
    completed: int = 0
    review: int = 0
    failed: int = 0
    deferred: int = 0
    error: str | None = None


@dataclass
class _ClaimHandle:
    """Lease handles retained until a package run reaches a safe boundary."""

    provider: str
    resource: str
    owner: str
    claim_id: str
    mutex_config: object
    revision: int = 1


_ADAPTER_OVERRIDES: dict[str, RouterAdapter] = {}
_ACTIVE_ADAPTERS: dict[str, tuple[str, RouterAdapter]] = {}
_FAKE_FORGE: FakeForge | None = None
_WORKTREE_PATHS: dict[str, Path] = {}
_WORKTREE_BRANCHES: dict[str, str] = {}
_WORKTREE_HEADS: dict[str, str] = {}
_RENEWAL_ERRORS: dict[str, str] = {}


def set_router_adapter(profile: str, adapter: RouterAdapter | None) -> None:
    """Install or clear an adapter override, primarily for deterministic tests."""
    if adapter is None:
        _ADAPTER_OVERRIDES.pop(profile, None)
    else:
        _ADAPTER_OVERRIDES[profile] = adapter


def set_router_forge(forge: FakeForge | None) -> None:
    """Install a forge override, primarily for deterministic tests."""
    global _FAKE_FORGE
    _FAKE_FORGE = forge


def run_router_once(
    context: RouterContext,
    *,
    listener_managed: bool = False,
    mqtt_listener=None,
    scheduler_claim_handles: list[_ClaimHandle] | None = None,
) -> RouterRunResult:
    """Run at most the first package in the current deterministic plan."""
    listener = (
        None
        if listener_managed
        else start_soft_listener(
            context.root, context.project_dir, context.configuration
        )
    )
    active_listener = mqtt_listener if listener_managed else listener
    try:
        plan = build_router_plan(context)
    except Exception:
        if listener is not None:
            listener.stop()
        raise
    if not plan.eligible:
        if listener is not None:
            listener.stop()
        return RouterRunResult(deferred=len(plan.deferred))
    candidate = plan.eligible[0]
    handles: list[_ClaimHandle] = []
    claim_id = str(uuid.uuid4())
    revision = _next_revision(context.project_dir, candidate.issue_id)
    owner = f"issue-router:{os.getpid()}"
    renewal_stop: threading.Event | None = None
    renewal_thread: threading.Thread | None = None
    renewal_handles: list[_ClaimHandle] = []

    def refresh_renewal_handles(current_handles: list[_ClaimHandle]) -> None:
        nonlocal renewal_stop, renewal_thread
        renewal_handles[:] = [
            handle
            for handle in current_handles
            if handle.resource != "router:scheduler"
        ]
        if not current_handles and renewal_stop is not None:
            renewal_stop.set()
            if renewal_thread is not None:
                renewal_thread.join()
        hard = bool(
            context.configuration.coordination.providers
            and context.configuration.coordination.providers[0] == "mutex_api"
        )
        if (
            hard
            and renewal_thread is None
            and any(
                handle.resource.startswith("router:issue:")
                for handle in renewal_handles
            )
        ):
            renewal_stop, renewal_thread = _start_lease_renewer(
                context, renewal_handles, claim_id, initial_pass=True
            )
            if _RENEWAL_ERRORS.get(claim_id):
                raise IssueRouterError(HARD_COORDINATION_ERROR)

    start_recorded = False
    completed_turn_returned = False
    try:
        handles = _acquire_claims(
            context,
            candidate,
            claim_id=claim_id,
            revision=revision,
            owner=owner,
            soft_provider="mqtt" if active_listener is not None else "git",
            include_scheduler=scheduler_claim_handles is None,
            on_handles_updated=refresh_renewal_handles,
        )
        scheduler_handles = [
            handle for handle in handles if handle.resource == "router:scheduler"
        ]
        if scheduler_claim_handles is None:
            _release_claims(context, scheduler_handles)
        handles = [
            handle for handle in handles if handle.resource != "router:scheduler"
        ]
        renewal_handles[:] = handles
        if renewal_thread is None:
            renewal_stop, renewal_thread = _start_lease_renewer(
                context, renewal_handles, claim_id
            )
        if scheduler_claim_handles is not None:
            _assert_scheduler_claim(context, scheduler_claim_handles)
        # Publish the acquired coordination events first, then publish the
        # started event through a shared-tip validator. A losing soft MQTT
        # contender must not leave a durable start in local cleanup state.
        publish_router_state(context.root, set(candidate.package_issue_ids))
        start_payload = {
            "claim_id": claim_id,
            "revision": revision,
            "attempt": candidate.attempt,
            "provider_profile": candidate.route.provider_profile,
            "package_issue_ids": candidate.package_issue_ids,
            "owner": owner,
            "provider_used": (
                "mutex_api"
                if any(handle.provider == "mutex_api" for handle in handles)
                else (
                    "mqtt"
                    if any(handle.provider == "mqtt" for handle in handles)
                    else "git"
                )
            ),
        }
        started_event = create_router_event(
            package_id=candidate.issue_id,
            event_type="router_claimed",
            payload=start_payload,
            actor_id=owner,
        )
        issue_handle = next(
            handle
            for handle in handles
            if handle.resource == f"router:issue:{candidate.issue_id}"
        )

        def validate_start_claim(events_dir: Path) -> None:
            _validate_router_start_claim(
                context,
                events_dir,
                candidate.issue_id,
                owner,
                claim_id,
                revision,
                issue_handle,
            )
            if scheduler_claim_handles is not None:
                _assert_scheduler_claim(context, scheduler_claim_handles)

        publish_router_start_event(
            context.root, started_event, validate_claim=validate_start_claim
        )
        start_recorded = True
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        if scheduler_claim_handles is not None:
            _assert_scheduler_claim(context, scheduler_claim_handles)
        _transition_package(
            context,
            candidate.issue_id,
            context.router.workflow.active,
            claim_id=claim_id,
            revision=revision,
        )
        if scheduler_claim_handles is not None:
            _assert_scheduler_claim(context, scheduler_claim_handles)
        try:
            result = _run_adapter(context, candidate, claim_id, revision)
        except IssueRouterError as error:
            if str(error).startswith("invalid Codex router outcome"):
                raise
            if scheduler_claim_handles is not None and any(
                _RENEWAL_ERRORS.get(handle.claim_id)
                for handle in scheduler_claim_handles
            ):
                return RouterRunResult(
                    started=1,
                    failed=1,
                    error="router scheduler coordination lease renewal failed",
                )
            if _cancel_was_requested(context.project_dir, candidate.issue_id, claim_id):
                return RouterRunResult(
                    started=1, failed=1, error="router run was cancelled"
                )
            conversation = latest_conversation(context.project_dir, candidate.issue_id)
            lifecycle = (conversation or {}).get("payload", {}).get("lifecycle")
            if lifecycle == "review":
                add_issue_comment(
                    getattr(context, "source_root", None) or context.root,
                    candidate.issue_id,
                    "Kanbus Issue Router",
                    "Agent work was preserved but its automatic result could not be validated. "
                    f"Review the attached agent conversation and branch. Router detail: {error}",
                )
                _transition_package(
                    context,
                    candidate.issue_id,
                    context.router.workflow.review,
                    claim_id=claim_id,
                    revision=revision,
                )
                publish_router_state(context.root, set(candidate.package_issue_ids))
                return RouterRunResult(started=1, review=1, failed=1, error=str(error))
            try:
                add_issue_comment(
                    getattr(context, "source_root", None) or context.root,
                    candidate.issue_id,
                    "Kanbus Issue Router",
                    f"The router could not start an agent session: {error}",
                )
                _transition_package(
                    context,
                    candidate.issue_id,
                    context.router.workflow.blocked,
                    claim_id=claim_id,
                    revision=revision,
                )
                publish_router_state(context.root, set(candidate.package_issue_ids))
                return RouterRunResult(started=1, failed=1, error=str(error))
            except (IssueCommentError, IssueUpdateError, IssueRouterError):
                # If the board itself cannot accept the visible diagnostic,
                # retain the established retry path rather than losing work.
                _schedule_retry(
                    context, candidate.issue_id, claim_id, revision, str(error)
                )
                return RouterRunResult(started=1, failed=1, error=str(error))
        completed_turn_returned = result.outcome == "completed"
        if scheduler_claim_handles is not None:
            scheduler_error = next(
                (
                    _RENEWAL_ERRORS.get(handle.claim_id)
                    for handle in scheduler_claim_handles
                    if _RENEWAL_ERRORS.get(handle.claim_id)
                ),
                None,
            )
            if scheduler_error:
                return RouterRunResult(started=1, failed=1, error=scheduler_error)
            _assert_scheduler_claim(context, scheduler_claim_handles)
        _validate_worktree_changes(context.configuration.project_directory, claim_id)
        _validate_result_scope(context, candidate, result)
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        if result.outcome == "retryable_failure":
            _schedule_retry(
                context,
                candidate.issue_id,
                claim_id,
                revision,
                result.summary or "retryable adapter failure",
            )
            return RouterRunResult(
                started=1, failed=1, error=result.summary or "router adapter failed"
            )
        if result.outcome == "blocked":
            _apply_issue_updates(context, candidate, result, claim_id, revision)
            _apply_issue_comments(context, candidate, result, claim_id, revision)
            _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
            add_issue_comment(
                getattr(context, "source_root", None) or context.root,
                candidate.issue_id,
                "Kanbus Issue Router",
                result.summary or "The agent is awaiting a human reply.",
            )
            _transition_package(
                context,
                candidate.issue_id,
                context.router.workflow.blocked,
                claim_id=claim_id,
                revision=revision,
            )
            record_router_event(
                context.project_dir,
                package_id=candidate.issue_id,
                event_type="router_blocked",
                payload={
                    "claim_id": claim_id,
                    "revision": revision,
                    "summary": result.summary,
                },
            )
            return RouterRunResult(started=1, failed=1)

        _apply_issue_updates(context, candidate, result, claim_id, revision)
        checkpoint = _publish_checkpoint(context, candidate, result, claim_id, revision)
        pull_request = _open_pull_request(
            context, candidate, checkpoint, claim_id, revision
        )
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        _apply_issue_comments(context, candidate, result, claim_id, revision)
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        add_issue_comment(
            getattr(context, "source_root", None) or context.root,
            candidate.issue_id,
            "Kanbus Issue Router",
            _completed_review_comment(result, checkpoint, pull_request),
        )
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        _transition_package(
            context,
            candidate.issue_id,
            context.router.workflow.review,
            claim_id=claim_id,
            revision=revision,
        )
        record_router_event(
            context.project_dir,
            package_id=candidate.issue_id,
            event_type="router_completed",
            payload={
                "claim_id": claim_id,
                "revision": revision,
                "checkpoint": (
                    None if checkpoint is None else checkpoint.model_dump(mode="json")
                ),
                "pull_request": (
                    None
                    if pull_request is None
                    else pull_request.model_dump(mode="json")
                ),
                "artifacts": [
                    item.model_dump(mode="json") for item in result.artifacts
                ],
            },
        )
        publish_router_state(context.root, set(candidate.package_issue_ids))
        return RouterRunResult(
            started=1,
            completed=1,
            review=1,
            deferred=len(plan.deferred) + max(0, len(plan.eligible) - 1),
        )
    except (IssueRouterError, IssueUpdateError) as error:
        started = int(start_recorded)
        if completed_turn_returned:
            try:
                _preserve_completed_turn_after_publication_failure(
                    context, candidate, claim_id, revision, error
                )
                return RouterRunResult(
                    started=started, review=started, failed=started, error=str(error)
                )
            except (IssueCommentError, IssueUpdateError, IssueRouterError):
                # The original failure is still the actionable diagnostic if
                # publishing the preservation record also fails.
                pass
        return RouterRunResult(
            started=started, failed=started, deferred=0, error=str(error)
        )
    finally:
        if renewal_stop is not None:
            renewal_stop.set()
        if renewal_thread is not None:
            renewal_thread.join(timeout=2)
        _RENEWAL_ERRORS.pop(claim_id, None)
        try:
            _release_claims(context, handles)
        finally:
            if listener is not None:
                listener.stop()


def run_router_watch(context: RouterContext) -> None:
    """Reconcile immediately, then poll durable state at the configured interval."""
    interval = parse_duration(context.router.watch_interval)
    listener = start_soft_listener(
        context.root, context.project_dir, context.configuration
    )
    scheduler_handles: list[_ClaimHandle] = []
    scheduler_claim_id: str | None = None
    renewal_stop: threading.Event | None = None
    renewal_thread: threading.Thread | None = None
    control_started = False
    try:
        scheduler_handles, scheduler_claim_id = _acquire_watch_scheduler_claim(
            context,
            soft_provider="mqtt" if listener is not None else "git",
        )
        renewal_stop, renewal_thread = _start_lease_renewer(
            context, scheduler_handles, scheduler_claim_id
        )
        state = context.control.model_copy(
            update={"running": True, "stop_requested": False}
        )
        write_router_control(context.root, state)
        control_started = True
        record_router_event(
            context.project_dir,
            package_id="control",
            event_type="router_started",
            payload={"claim_id": scheduler_claim_id},
        )
        publish_router_state(context.root)
        while True:
            from kanbus.router_state import router_state_root

            current = load_router_context(router_state_root(context.root))
            renewal_error = _RENEWAL_ERRORS.get(scheduler_claim_id)
            if renewal_error:
                raise IssueRouterError(renewal_error)
            if current.control.stop_requested:
                break
            _assert_scheduler_claim(current, scheduler_handles)
            _reconcile_pull_requests(current, scheduler_handles)
            result = run_router_once(
                current,
                listener_managed=True,
                mqtt_listener=listener,
                scheduler_claim_handles=scheduler_handles,
            )
            if result.error and "scheduler coordination lease" in result.error:
                raise IssueRouterError(result.error)
            _wait_for_watch_trigger(listener, interval)
    finally:
        try:
            if renewal_stop is not None:
                renewal_stop.set()
            if renewal_thread is not None:
                renewal_thread.join(timeout=2)
            if scheduler_handles:
                _release_claims(context, scheduler_handles)
            if control_started:
                state = load_router_context(context.root).control.model_copy(
                    update={"running": False, "stop_requested": False}
                )
                write_router_control(context.root, state)
                record_router_event(
                    context.project_dir,
                    package_id="control",
                    event_type="router_stopped",
                    payload={"claim_id": scheduler_claim_id},
                )
                publish_router_state(context.root)
        finally:
            if scheduler_claim_id is not None:
                _RENEWAL_ERRORS.pop(scheduler_claim_id, None)
            if listener is not None:
                listener.stop()


def _wait_for_watch_trigger(listener, interval: float) -> bool:
    """Wait for MQTT or the next poll while checking local stop at short intervals."""
    deadline = monotonic() + interval
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return False
        wait_for = min(0.25, remaining)
        if listener is not None and listener.received.wait(wait_for):
            listener.received.clear()
            return True
        if listener is None:
            sleep(wait_for)


def _acquire_watch_scheduler_claim(
    context: RouterContext, *, soft_provider: str
) -> tuple[list[_ClaimHandle], str]:
    """Acquire and publish the durable lease that elects one watch scheduler."""
    claim_id = str(uuid.uuid4())
    revision = 1
    owner = f"issue-router:{os.getpid()}"
    hard = bool(
        context.configuration.coordination.providers
        and context.configuration.coordination.providers[0] == "mutex_api"
    )
    if hard and not mutex_is_configured(context.configuration.coordination.mutex_api):
        raise IssueRouterError(HARD_COORDINATION_ERROR)
    handles: list[_ClaimHandle] = []
    try:
        _acquire_router_resource(
            context,
            handles,
            "router:scheduler",
            owner,
            claim_id,
            revision,
            hard,
            soft_provider=soft_provider,
            wait_for_contention=True,
        )
        publish_router_state(context.root)
        _assert_scheduler_claim(context, handles)
        return handles, claim_id
    except Exception:
        if handles:
            _release_claims(context, handles)
        raise


def _assert_scheduler_claim(
    context: RouterContext, handles: list[_ClaimHandle]
) -> None:
    """Fence watch scheduling against its actual provider and Git mirror."""
    from kanbus.router_state import router_state_root

    try:
        router_state_root(context.root, refresh=True)
    except IssueRouterError as error:
        raise IssueRouterError(
            "router state reconciliation failed; scheduler lease is not safe"
        ) from error
    for handle in handles:
        try:
            if handle.provider == "mutex_api":
                lease = mutex_inspect(handle.mutex_config, resource=handle.resource)
                if (
                    lease is None
                    or lease.owner != handle.owner
                    or lease.claim_id != handle.claim_id
                    or lease.revision != handle.revision
                ):
                    raise IssueRouterError(
                        f"stale router scheduler claim {handle.claim_id}"
                    )
            elif handle.provider == "mqtt":
                from kanbus.coordination_mqtt import inspect_lease as inspect_mqtt_lease

                lease = inspect_mqtt_lease(
                    context.project_dir / "events",
                    context.project_dir,
                    handle.resource,
                    context.configuration,
                )
                if (
                    not lease.active
                    or lease.owner != handle.owner
                    or lease.claim_id != handle.claim_id
                    or (
                        lease.revision is not None and lease.revision != handle.revision
                    )
                ):
                    raise IssueRouterError(
                        f"stale router scheduler claim {handle.claim_id}"
                    )
            else:
                lease = inspect_lease(context.project_dir / "events", handle.resource)
                if (
                    not lease.active
                    or lease.owner != handle.owner
                    or lease.claim_id != handle.claim_id
                    or (
                        lease.revision is not None and lease.revision != handle.revision
                    )
                ):
                    raise IssueRouterError(
                        f"stale router scheduler claim {handle.claim_id}"
                    )
        except (CoordinationError, MutexApiUnavailable, MutexApiError) as error:
            if handle.provider == "mutex_api":
                raise IssueRouterError(HARD_COORDINATION_ERROR) from error
            raise IssueRouterError(
                "router scheduler coordination lease unavailable"
            ) from error


def count_active_router_runs(project_dir: Path) -> int:
    """Count package claims that have not reached a terminal router outcome."""
    events = _read_events(project_dir / "events")
    package_ids = {
        str(event.get("issue_id", "")).removeprefix("router:")
        for event in events
        if str(event.get("issue_id", "")).startswith("router:")
        and event.get("event_type") == "router_claimed"
    }
    return sum(1 for package_id in package_ids if _claim_is_active(events, package_id))


def cancel_router_package(context: RouterContext, issue_id: str) -> str | None:
    """Cancel an active adapter and block its package without losing checkpoint."""
    package_id = _resolve_package_id(context, issue_id)
    events = read_router_events(context.project_dir, package_id)
    claim = _latest_router_event(events, package_id, "router_claimed")
    if claim is None or not _claim_is_active(
        _read_events(context.project_dir / "events"), package_id
    ):
        raise IssueRouterError(f'no active router run for package "{package_id}"')
    payload = claim.get("payload", {})
    claim_id = str(payload.get("claim_id", ""))
    revision = int(payload.get("revision", 1))
    adapter = _ACTIVE_ADAPTERS.get(package_id)
    if adapter is not None:
        adapter[1].cancel(claim_id)
    record_router_event(
        context.project_dir,
        package_id=package_id,
        event_type="router_cancel_requested",
        payload={"claim_id": claim_id, "revision": revision},
    )
    publish_router_state(context.root)
    _signal_registered_adapter(context.root, package_id, claim_id)
    checkpoint = _accepted_checkpoint(events)
    _transition_package(
        context,
        package_id,
        context.router.workflow.blocked,
        claim_id=claim_id,
        revision=revision,
        allow_cancel=True,
    )
    record_router_event(
        context.project_dir,
        package_id=package_id,
        event_type="router_cancelled",
        payload={"claim_id": claim_id, "revision": revision, "checkpoint": checkpoint},
    )
    publish_router_state(context.root)
    return checkpoint


def recover_router_package(context: RouterContext, issue_id: str) -> dict[str, str]:
    """Surface a preserved run without starting a replacement agent session."""
    package_id = _resolve_package_id(context, issue_id)
    record = latest_conversation(context.project_dir, package_id)
    if record is None:
        raise IssueRouterError(f'no recoverable agent run for package "{package_id}"')
    payload = record["payload"]
    result = {
        "issue_id": package_id,
        "lifecycle": str(payload.get("lifecycle", "unknown")),
        "provider": str(payload.get("provider", "unknown")),
        "branch": str(payload.get("branch", "")),
        "worktree": str(payload.get("worktree", "")),
    }
    session = payload.get("session_id")
    if isinstance(session, str) and session:
        result["session_id"] = session
    record_conversation(
        context.project_dir,
        package_id,
        action="recovered",
        provider=result["provider"],
        claim_id=str(payload.get("claim_id", "recovered")),
        revision=int(payload.get("revision", 1)),
        session_id=result.get("session_id"),
        lifecycle=result["lifecycle"],
        branch=result["branch"],
        worktree=result["worktree"],
    )
    target_status = {
        "review": context.router.workflow.review,
        "blocked": context.router.workflow.blocked,
    }.get(result["lifecycle"])
    if target_status is not None:
        _transition_package(
            context,
            package_id,
            target_status,
            claim_id=str(payload.get("claim_id", "recovered")),
            revision=int(payload.get("revision", 1)),
        )
    publish_router_state(context.root, {package_id})
    return result


def retry_delay_seconds(failed_attempt: int) -> int:
    """Return deterministic exponential retry delay, capped at fifteen minutes."""
    return min(30 * (2 ** max(0, failed_attempt - 1)), 900)


def publish_router_result(
    context: RouterContext,
    *,
    package_id: str,
    claim_id: str,
    revision: int,
    result: RouterAgentResult,
    package_issue_ids: list[str] | None = None,
) -> None:
    """Fence and publish a structured router result with workflow-safe updates."""
    _assert_claim_fence(context, package_id, claim_id, revision)
    candidate = _candidate_for_package(context, package_id, package_issue_ids)
    _validate_result_scope(context, candidate, result)
    _apply_issue_updates(context, candidate, result, claim_id, revision)
    if result.outcome == "completed":
        _apply_issue_comments(context, candidate, result, claim_id, revision)
    _publish_checkpoint(context, candidate, result, claim_id, revision)


def _run_adapter(
    context: RouterContext,
    candidate: RouterPlanEligiblePackage,
    claim_id: str,
    revision: int,
) -> RouterAgentResult:
    profile = context.router.providers[candidate.route.provider_profile]
    adapter = _ADAPTER_OVERRIDES.get(profile.command)
    if adapter is None:
        adapter = _ADAPTER_OVERRIDES.get(candidate.route.provider_profile)
    if adapter is None:
        adapter = CodexExecAdapter(
            profile,
            process_record_path=_adapter_process_record_path(
                context.root, candidate.issue_id, claim_id
            ),
        )
    checkpoint = _accepted_checkpoint(
        read_router_events(context.project_dir, candidate.issue_id)
    )
    checkpoint_revision = _accepted_checkpoint_revision(
        read_router_events(context.project_dir, candidate.issue_id)
    )
    branch = _existing_pull_request_branch(context.project_dir, candidate.issue_id)
    if branch is None:
        branch = f"codex/router/{candidate.issue_id}/r{revision}"
    request = RouterExecutionRequest(
        package_id=candidate.issue_id,
        claim_id=claim_id,
        revision=revision,
        package_issue_ids=candidate.package_issue_ids,
        checkpoint=(
            None
            if checkpoint is None
            else RouterCheckpoint(ref=checkpoint, revision=checkpoint_revision or 1)
        ),
        worktree_path=str(
            _create_isolated_worktree(
                context, candidate.issue_id, claim_id, revision, branch=branch
            )
        ),
    )
    worktree_path = Path(request.worktree_path)
    _WORKTREE_PATHS[claim_id] = worktree_path
    _WORKTREE_BRANCHES[claim_id] = branch
    _ACTIVE_ADAPTERS[candidate.issue_id] = (claim_id, adapter)
    record_conversation(
        context.project_dir,
        candidate.issue_id,
        action="started",
        provider="codex",
        claim_id=claim_id,
        revision=revision,
        lifecycle="in_progress",
        worktree=request.worktree_path,
        branch=branch,
    )
    try:
        result = adapter.execute(request).validate_outcome()
        session_id = getattr(adapter, "session_id", None)
        if isinstance(session_id, str) and session_id:
            record_conversation(
                context.project_dir,
                candidate.issue_id,
                action="agent_turn",
                provider="codex",
                claim_id=claim_id,
                revision=revision,
                session_id=session_id,
                lifecycle=("blocked" if result.outcome == "blocked" else "review"),
                message=result.summary
                or (
                    "The agent is awaiting a human reply."
                    if result.outcome == "blocked"
                    else "Agent turn completed; review the preserved branch and log."
                ),
                worktree=request.worktree_path,
                branch=branch,
                log=adapter.last_output + adapter.last_error,
            )
        _validate_worktree_changes(context.configuration.project_directory, claim_id)
        if result.outcome == "completed":
            _commit_isolated_worktree(
                Path(request.worktree_path),
                context.configuration.project_directory,
                candidate.issue_id,
                revision,
            )
            _WORKTREE_HEADS[claim_id] = _git(
                Path(request.worktree_path), ["rev-parse", "HEAD"]
            )
        return result
    except IssueRouterError as error:
        # Evidence is written before the error reaches scheduling logic.  This
        # is what prevents a malformed final object from becoming a black hole.
        session_id = getattr(adapter, "session_id", None)
        raw_output = str(getattr(adapter, "last_output", ""))
        raw_error = str(getattr(adapter, "last_error", ""))
        # A malformed result proves that the agent did run even when its
        # output did not include a resumable Codex session ID. Preserve that
        # turn for human review instead of treating it like a launcher error.
        has_preserved_turn = (
            (isinstance(session_id, str) and bool(session_id))
            or str(error) == "Codex router adapter returned invalid JSON"
            or bool(raw_output or raw_error)
        )
        if has_preserved_turn:
            record_conversation(
                context.project_dir,
                candidate.issue_id,
                action="validation_failed",
                provider="codex",
                claim_id=claim_id,
                revision=revision,
                session_id=session_id,
                lifecycle="review",
                message="The router could not validate the agent result; the raw turn is preserved for review.",
                worktree=request.worktree_path,
                branch=branch,
                log=raw_output + raw_error,
                error=str(error),
            )
        raise
    finally:
        _ACTIVE_ADAPTERS.pop(candidate.issue_id, None)


def _create_isolated_worktree(
    context: RouterContext,
    package_id: str,
    claim_id: str,
    revision: int,
    *,
    branch: str | None = None,
) -> Path:
    git_path = _git(
        context.root, ["rev-parse", "--git-path", "kanbus/router/worktrees"]
    )
    worktree_root = Path(git_path)
    if not worktree_root.is_absolute():
        worktree_root = context.root / worktree_root
    worktree = worktree_root / f"{package_id}-{claim_id}"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    branch = branch or f"codex/router/{package_id}/r{revision}"
    _detach_previous_worktree(context.root, worktree_root, worktree, branch)
    if _remote_branch_exists(context.root, branch):
        _git(
            context.root,
            [
                "fetch",
                "origin",
                f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
            ],
        )
        _git(context.root, ["branch", "-f", branch, f"refs/remotes/origin/{branch}"])
        _git(context.root, ["worktree", "add", str(worktree), branch])
    elif not _local_branch_exists(context.root, branch):
        base_commit = _worktree_base_commit(context.root, worktree_root)
        _git(
            context.root, ["worktree", "add", "-b", branch, str(worktree), base_commit]
        )
    else:
        _git(context.root, ["worktree", "add", str(worktree), branch])
    return worktree


def _existing_pull_request_branch(project_dir: Path, package_id: str) -> str | None:
    events = read_router_events(project_dir, package_id)
    event = _latest_router_event(events, package_id, "router_pull_request_opened")
    if event is None:
        return None
    branch = event.get("payload", {}).get("branch") or event.get("payload", {}).get(
        "head_branch"
    )
    return str(branch) if isinstance(branch, str) and branch else None


def _remote_branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


def _local_branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _detach_previous_worktree(
    root: Path,
    worktree_root: Path,
    destination: Path,
    branch: str,
) -> None:
    listing = _git(root, ["worktree", "list", "--porcelain"])
    for block in listing.split("\n\n"):
        lines = block.splitlines()
        path = next(
            (
                Path(line.removeprefix("worktree "))
                for line in lines
                if line.startswith("worktree ")
            ),
            None,
        )
        branch_name = next(
            (
                line.removeprefix("branch refs/heads/")
                for line in lines
                if line.startswith("branch refs/heads/")
            ),
            None,
        )
        if (
            path is None
            or branch_name != branch
            or path.resolve() == destination.resolve()
        ):
            continue
        try:
            path.resolve().relative_to(worktree_root.resolve())
        except ValueError as error:
            raise IssueRouterError(
                "router branch is checked out outside its managed worktree"
            ) from error
        _git(root, ["worktree", "remove", "--force", str(path)])


def _worktree_base_commit(root: Path, metadata_dir: Path) -> str:
    """Use HEAD or materialize a private snapshot commit for an unborn test repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    index_path = metadata_dir / f"snapshot-{uuid.uuid4()}.index"
    environment = os.environ.copy()
    environment["GIT_INDEX_FILE"] = str(index_path)
    try:
        subprocess.run(
            ["git", "read-tree", "--empty"],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "-A", "--", "."],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
        )
        tree = subprocess.run(
            ["git", "write-tree"],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        commit = subprocess.run(
            [
                "git",
                "-c",
                "user.name=Kanbus Issue Router",
                "-c",
                "user.email=issue-router@localhost",
                "commit-tree",
                tree,
                "-m",
                "router isolated snapshot",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return commit
    except (OSError, subprocess.CalledProcessError) as error:
        raise IssueRouterError(
            "router could not prepare an isolated worktree"
        ) from error
    finally:
        index_path.unlink(missing_ok=True)


def _publish_checkpoint(
    context: RouterContext,
    candidate: RouterPlanEligiblePackage,
    result: RouterAgentResult,
    claim_id: str,
    revision: int,
) -> RouterCheckpoint | None:
    _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
    checkpoint = result.checkpoint
    if checkpoint is not None and checkpoint.revision != revision:
        raise IssueRouterError(
            f"stale router revision {checkpoint.revision} for package {candidate.issue_id}; current revision is {revision}"
        )
    if checkpoint is not None:
        head = _WORKTREE_HEADS.get(claim_id)
        if head is not None:
            previous_head = _update_checkpoint_ref(context.root, checkpoint.ref, head)
            try:
                _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
            except IssueRouterError:
                _restore_checkpoint_ref(
                    context.root, checkpoint.ref, head, previous_head
                )
                raise
        record_router_event(
            context.project_dir,
            package_id=candidate.issue_id,
            event_type="router_checkpoint_accepted",
            payload={"claim_id": claim_id, "revision": revision, "ref": checkpoint.ref},
        )
    for artifact in result.artifacts:
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        record_router_event(
            context.project_dir,
            package_id=candidate.issue_id,
            event_type="router_artifact_published",
            payload={
                "claim_id": claim_id,
                "revision": revision,
                "name": artifact.name,
                "ref": artifact.ref,
            },
        )
    publish_router_state(context.root, set(candidate.package_issue_ids))
    return checkpoint


def _open_pull_request(
    context: RouterContext,
    candidate: RouterPlanEligiblePackage,
    checkpoint: RouterCheckpoint | None,
    claim_id: str,
    revision: int,
) -> ForgePullRequest | None:
    if context.router.forge is None:
        return None
    forge = _FAKE_FORGE or GitHubForge.from_configuration(context.router)
    branch = _WORKTREE_BRANCHES.get(
        claim_id,
        f"codex/router/{candidate.issue_id}/r{candidate.attempt}",
    )
    _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
    published_head: str | None = None
    previous_head: str | None = None
    if isinstance(forge, GitHubForge):
        branch_ref = f"refs/heads/{branch}"
        previous_head = _remote_ref_sha(context.root, branch_ref)
        published_head = _WORKTREE_HEADS.get(claim_id)
        try:
            subprocess.run(
                [
                    "git",
                    "push",
                    f"--force-with-lease={branch_ref}:{previous_head or ''}",
                    "origin",
                    f"{branch_ref}:{branch_ref}",
                ],
                cwd=context.root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise IssueRouterError(
                "router could not publish branch to GitHub"
            ) from error
        try:
            _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        except IssueRouterError as error:
            if published_head is not None and not _restore_stale_pull_request_branch(
                context.root, branch_ref, published_head, previous_head
            ):
                raise IssueRouterError(
                    "stale router claim; could not safely roll back the PR branch"
                ) from error
            raise
    _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
    pull_request = forge.create_or_observe_pull_request(
        title=f"[{candidate.issue_id}] {next((item.title for item in context.issues if item.identifier == candidate.issue_id), candidate.issue_id)}",
        body=f"Kanbus package: {candidate.issue_id}\n\nAutomated implementation ready for review.",
        head_branch=branch,
        base_branch=context.router.forge.base_branch,
    )
    try:
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        record_router_event(
            context.project_dir,
            package_id=candidate.issue_id,
            event_type="router_pull_request_opened",
            payload={
                "number": pull_request.number,
                "head_sha": pull_request.head_sha,
                "repository": context.router.forge.repository,
                "url": pull_request.url,
                "branch": pull_request.head_branch,
            },
        )
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        publish_router_state(context.root, set(candidate.package_issue_ids))
    except IssueRouterError:
        if (
            isinstance(forge, GitHubForge)
            and published_head is not None
            and not _restore_stale_pull_request_branch(
                context.root, f"refs/heads/{branch}", published_head, previous_head
            )
        ):
            raise IssueRouterError(
                "stale router claim; could not safely roll back the PR branch"
            )
        raise
    return pull_request


def _apply_issue_updates(
    context: RouterContext,
    candidate: RouterPlanEligiblePackage,
    result: RouterAgentResult,
    claim_id: str,
    revision: int,
) -> None:
    package_ids = set(candidate.package_issue_ids)
    issues_by_id = {issue.identifier: issue for issue in context.issues}
    for update in result.issue_updates:
        if update.issue_id not in package_ids:
            raise IssueRouterError(
                f"issue {update.issue_id} is outside router package {candidate.issue_id}"
            )
        issue = issues_by_id.get(update.issue_id)
        if issue is None:
            raise IssueRouterError(
                f"issue {update.issue_id} is outside router package {candidate.issue_id}"
            )
        try:
            from kanbus.workflows import (
                validate_status_transition,
                validate_status_value,
            )

            if (
                update.status in context.router.workflow.terminal
                or update.status == context.router.workflow.review
            ):
                raise ValueError("router-owned status transition")
            configuration = context.configuration
            validate_status_value(
                configuration, issue.issue_type, update.status, issue.identifier
            )
            validate_status_transition(
                configuration, issue.issue_type, issue.status, update.status
            )
        except Exception as error:
            raise IssueRouterError(
                f"router result cannot transition package {candidate.issue_id} from {issue.status} to {update.status}"
            ) from error
    for update in result.issue_updates:
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        issue = issues_by_id[update.issue_id]
        if issue.status != update.status:
            try:
                update_issue(
                    context.root,
                    update.issue_id,
                    title=None,
                    description=None,
                    status=update.status,
                    assignee=None,
                    claim=False,
                    regenerate_right_now=False,
                )
                publish_router_state(context.root, {update.issue_id})
            except IssueUpdateError as error:
                raise IssueRouterError(str(error)) from error
    if result.summary:
        record_router_event(
            context.project_dir,
            package_id=candidate.issue_id,
            event_type="router_progress",
            payload={
                "claim_id": claim_id,
                "revision": revision,
                "summary": result.summary,
            },
        )
    publish_router_state(context.root, set(candidate.package_issue_ids))


def _apply_issue_comments(
    context: RouterContext,
    candidate: RouterPlanEligiblePackage,
    result: RouterAgentResult,
    claim_id: str,
    revision: int,
) -> None:
    """Persist validated agent comments through Kanbus's canonical mutation path."""
    for comment in result.issue_comments:
        if comment.issue_id not in candidate.package_issue_ids:
            raise IssueRouterError(
                f"issue {comment.issue_id} is outside router package {candidate.issue_id}"
            )
        if not comment.text.strip():
            raise IssueRouterError("router issue comment text must not be blank")
    for comment in result.issue_comments:
        _assert_claim_fence(context, candidate.issue_id, claim_id, revision)
        add_issue_comment(
            context.source_root or context.root,
            comment.issue_id,
            "Kanbus Issue Router",
            comment.text,
        )


def _preserve_completed_turn_after_publication_failure(
    context: RouterContext,
    candidate: RouterPlanEligiblePackage,
    claim_id: str,
    revision: int,
    error: Exception,
) -> None:
    """Publish review evidence when a completed turn fails after execution.

    Validation and publication happen after the adapter has returned.  They
    must not turn a completed agent turn into an invisible scheduler failure.
    """
    conversation = latest_conversation(context.project_dir, candidate.issue_id)
    payload = (conversation or {}).get("payload", {})
    branch = str(payload.get("branch") or _WORKTREE_BRANCHES.get(claim_id, "unknown"))
    worktree = str(payload.get("worktree") or _WORKTREE_PATHS.get(claim_id, "unknown"))
    session_id = payload.get("session_id")
    session = str(session_id) if isinstance(session_id, str) and session_id else "unknown"
    diagnostic = (
        "## Agent turn preserved for review\n\n"
        "The agent completed work, but automatic publication failed.\n\n"
        f"- Branch: `{branch}`\n"
        f"- Session: `{session}`\n"
        f"- Worktree: `{worktree}`\n"
        f"- Router detail: {error}"
    )
    record_conversation(
        context.project_dir,
        candidate.issue_id,
        action="publication_failed",
        provider=str(payload.get("provider", "codex")),
        claim_id=claim_id,
        revision=revision,
        session_id=session_id if isinstance(session_id, str) else None,
        lifecycle="review",
        message="Completed agent turn preserved for review after publication failure.",
        branch=branch,
        worktree=worktree,
        error=str(error),
    )
    add_issue_comment(
        getattr(context, "source_root", None) or context.root,
        candidate.issue_id,
        "Kanbus Issue Router",
        diagnostic,
    )
    _transition_package(
        context,
        candidate.issue_id,
        context.router.workflow.review,
        claim_id=claim_id,
        revision=revision,
    )
    record_router_event(
        context.project_dir,
        package_id=candidate.issue_id,
        event_type="router_result",
        payload={
            "outcome": "completed",
            "summary": "Completed agent turn preserved for review after publication failure",
            "diagnostic": diagnostic,
            "publication_failed": True,
            "claim_id": claim_id,
            "revision": revision,
            "session_id": session_id,
            "branch": branch,
            "worktree": worktree,
        },
    )
    publish_router_state(context.root, set(candidate.package_issue_ids))


def _completed_review_comment(
    result: RouterAgentResult,
    checkpoint: RouterCheckpoint | None,
    pull_request: ForgePullRequest | None,
) -> str:
    """Render the non-optional issue record for a completed agent turn.

    Agent-supplied comments are useful supplemental context, but a completed
    turn must remain visible even when the adapter supplies none. The router
    creates this comment only after branch/PR publication has succeeded and
    before it transitions the issue to Review.
    """
    summary = result.summary.strip() or (
        "The agent completed a turn. Review the preserved branch and draft pull request."
    )
    lines = ["## Agent turn complete", "", summary, ""]
    if pull_request is not None:
        lines.extend(
            [
                f"- Draft PR: {pull_request.url}",
                f"- Branch: `{pull_request.head_branch}`",
            ]
        )
    if checkpoint is not None:
        lines.append(f"- Checkpoint: `{checkpoint.ref}`")
    if result.artifacts:
        lines.append("- Artifacts:")
        lines.extend(f"  - `{item.name}`: `{item.ref}`" for item in result.artifacts)
    return "\n".join(lines)


def _validate_result_scope(
    context: RouterContext,
    candidate: RouterPlanEligiblePackage,
    result: RouterAgentResult,
) -> None:
    allowed = set(candidate.package_issue_ids)
    for update in result.issue_updates:
        if update.issue_id not in allowed:
            raise IssueRouterError(
                f"issue {update.issue_id} is outside router package {candidate.issue_id}"
            )
        issue = next(
            (item for item in context.issues if item.identifier == update.issue_id),
            None,
        )
        if issue is None:
            raise IssueRouterError(
                f"issue {update.issue_id} is outside router package {candidate.issue_id}"
            )
        try:
            from kanbus.workflows import (
                validate_status_transition,
                validate_status_value,
            )

            if (
                update.status in context.router.workflow.terminal
                or update.status == context.router.workflow.review
            ):
                raise ValueError("router-owned status transition")
            validate_status_value(
                context.configuration, issue.issue_type, update.status, issue.identifier
            )
            validate_status_transition(
                context.configuration, issue.issue_type, issue.status, update.status
            )
        except Exception as error:
            raise IssueRouterError(
                f"router result cannot transition package {candidate.issue_id} from {issue.status} to {update.status}"
            ) from error
    for comment in result.issue_comments:
        if comment.issue_id not in allowed or not any(
            item.identifier == comment.issue_id for item in context.issues
        ):
            raise IssueRouterError(
                f"issue {comment.issue_id} is outside router package {candidate.issue_id}"
            )
        if not comment.text.strip():
            raise IssueRouterError("router issue comment text must not be blank")


def _transition_package(
    context: RouterContext,
    package_id: str,
    status: str,
    *,
    claim_id: str,
    revision: int,
    allow_cancel: bool = False,
) -> None:
    _assert_claim_fence(
        context, package_id, claim_id, revision, allow_cancel=allow_cancel
    )
    try:
        # The context is intentionally a planning snapshot.  A router event can
        # outlive that snapshot (notably after a Git-only refresh), so derive
        # the transition from the canonical card that is about to be mutated.
        issue = load_issue_from_project(context.root, package_id).issue
    except IssueLookupError:
        # Lightweight callers and focused tests can supply an in-memory
        # planning context.  Production router contexts always reload above.
        issue = next(
            (item for item in context.issues if item.identifier == package_id), None
        )
        if issue is None:
            raise IssueRouterError(f'unknown router package "{package_id}"')
    steps = _workflow_transition_path(
        context.configuration, issue.issue_type, issue.status, status
    )
    if not steps:
        return
    try:
        for next_status in steps:
            update_issue(
                context.root,
                package_id,
                title=None,
                description=None,
                status=next_status,
                assignee=None,
                claim=False,
                regenerate_right_now=False,
            )
    except IssueUpdateError as error:
        raise IssueRouterError(str(error)) from error
    publish_router_state(context.root, {package_id})


def _workflow_transition_path(
    configuration,
    issue_type: str,
    current_status: str,
    target_status: str,
) -> list[str]:
    """Return the shortest configured route, excluding ``current_status``."""
    if current_status == target_status:
        return []
    workflows = getattr(configuration, "workflows", None)
    if not isinstance(workflows, dict):
        return [target_status]
    workflow = workflows.get(issue_type, workflows.get("default", {}))
    queue: deque[tuple[str, list[str]]] = deque([(current_status, [])])
    visited = {current_status}
    while queue:
        status, path = queue.popleft()
        for next_status in workflow.get(status, []):
            if next_status in visited:
                continue
            next_path = [*path, next_status]
            if next_status == target_status:
                return next_path
            visited.add(next_status)
            queue.append((next_status, next_path))
    raise IssueRouterError(
        f"router cannot transition package from {current_status} to {target_status} "
        "through the configured workflow"
    )


def _schedule_retry(
    context: RouterContext,
    package_id: str,
    claim_id: str,
    revision: int,
    diagnostic: str,
) -> None:
    _assert_claim_fence(context, package_id, claim_id, revision)
    current = load_router_context(context.root)
    current_attempt = _attempt_for_claim(
        read_router_events(context.project_dir, package_id)
    )
    max_attempts = context.router.retries.max_attempts
    if current_attempt >= max_attempts:
        _transition_package(
            current,
            package_id,
            context.router.workflow.blocked,
            claim_id=claim_id,
            revision=revision,
        )
        record_router_event(
            context.project_dir,
            package_id=package_id,
            event_type="router_retry_exhausted",
            payload={
                "claim_id": claim_id,
                "revision": revision,
                "diagnostic": "maximum retry attempts reached",
                "detail": diagnostic,
                "checkpoint": _accepted_checkpoint(
                    read_router_events(context.project_dir, package_id)
                ),
            },
        )
        publish_router_state(context.root)
        return
    delay = retry_delay_seconds(current_attempt)
    retry_at = datetime.now(UTC) + timedelta(seconds=delay)
    record_router_event(
        context.project_dir,
        package_id=package_id,
        event_type="router_retry_scheduled",
        payload={
            "claim_id": claim_id,
            "revision": revision,
            "failed_attempt": current_attempt,
            "next_attempt": current_attempt + 1,
            "retry_at": retry_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "delay_seconds": delay,
            "diagnostic": diagnostic,
            "checkpoint": _accepted_checkpoint(
                read_router_events(context.project_dir, package_id)
            ),
        },
    )
    publish_router_state(context.root)
    publish_router_state(context.root)


def _acquire_claims(
    context: RouterContext,
    candidate: RouterPlanEligiblePackage,
    *,
    claim_id: str,
    revision: int,
    owner: str,
    soft_provider: str | None = None,
    include_scheduler: bool = True,
    on_handles_updated: Callable[[list[_ClaimHandle]], None] | None = None,
) -> list[_ClaimHandle]:
    configured = context.configuration.coordination.providers
    hard = bool(configured and configured[0] == "mutex_api")
    mutex_config = context.configuration.coordination.mutex_api
    if hard and not mutex_is_configured(mutex_config):
        raise IssueRouterError(HARD_COORDINATION_ERROR)
    handles: list[_ClaimHandle] = []
    try:
        fixed_resources = (["router:scheduler"] if include_scheduler else []) + [
            f"router:issue:{issue_id}" for issue_id in candidate.package_issue_ids
        ]
        for resource in fixed_resources:
            _acquire_router_resource(
                context,
                handles,
                resource,
                owner,
                claim_id,
                revision,
                hard,
                soft_provider=soft_provider,
                wait_for_contention=resource == f"router:issue:{candidate.issue_id}",
            )
            if on_handles_updated is not None:
                on_handles_updated(handles)

        capacity_specs = [("project", "", context.router.limits.project_wip)]
        profile = candidate.route.provider_profile
        if profile in context.router.limits.provider_wip:
            capacity_specs.append(
                (
                    "provider-profile",
                    profile,
                    context.router.limits.provider_wip[profile],
                )
            )
        if (
            candidate.route.kind == "class"
            and candidate.route.name in context.router.limits.class_wip
        ):
            capacity_specs.append(
                (
                    "class",
                    candidate.route.name,
                    context.router.limits.class_wip[candidate.route.name],
                )
            )
        for kind, name, limit in capacity_specs:
            acquired = False
            for slot in range(limit):
                route = f":{name}" if name else ""
                resource = f"router:capacity:{kind}{route}:{slot}"
                try:
                    _acquire_router_resource(
                        context,
                        handles,
                        resource,
                        owner,
                        claim_id,
                        revision,
                        hard,
                        allow_contention=True,
                        soft_provider=soft_provider,
                    )
                    if on_handles_updated is not None:
                        on_handles_updated(handles)
                    acquired = True
                    break
                except IssueRouterError as error:
                    if str(error) != "package already claimed":
                        raise
            if not acquired:
                raise IssueRouterError("router capacity is full")
        return handles
    except Exception as acquisition_error:
        if on_handles_updated is not None:
            on_handles_updated([])
        try:
            _release_claims(context, handles)
        except Exception as release_error:
            # A losing claimant is expected to report contention even if
            # cleanup of resources it did win needs a later retry. In
            # particular, do not replace a Mutex API 409 with a release
            # failure from an unrelated, previously acquired resource.
            if (
                isinstance(acquisition_error, IssueRouterError)
                and str(acquisition_error) == "package already claimed"
            ):
                raise acquisition_error from release_error
            raise
        raise


def _acquire_router_resource(
    context: RouterContext,
    handles: list[_ClaimHandle],
    resource: str,
    owner: str,
    claim_id: str,
    revision: int,
    hard: bool,
    *,
    allow_contention: bool = False,
    soft_provider: str | None = None,
    wait_for_contention: bool = False,
) -> None:
    mutex_config = context.configuration.coordination.mutex_api
    claim_time = utc_now()
    if not hard:
        claim_state = soft_claim(
            context.project_dir / "events",
            context.configuration.coordination,
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            revision=revision,
            now=claim_time,
        )
        provider = soft_provider or select_soft_provider(
            context.root, context.configuration
        )
        state = claim_state
        if provider == "mqtt" and claim_state.operation_event_id:
            published = publish_claim_visibility(
                context.root,
                context.project_dir,
                context.configuration,
                resource=resource,
                owner=owner,
                claim_id=claim_id,
                event_id=claim_state.operation_event_id,
                occurred_at=claim_time,
                lease_ttl_s=parse_duration(
                    context.configuration.coordination.default_lease_ttl
                ),
                operation_sequence=claim_state.operation_sequence,
            )
            if not published:
                provider = "git"
            if wait_for_contention:
                sleep(
                    parse_duration(context.configuration.coordination.contention_window)
                )
                from kanbus.coordination_mqtt import record_contention_observation

                record_contention_observation(
                    context.project_dir,
                    resource,
                    claim_id,
                    contention_window_s=parse_duration(
                        context.configuration.coordination.contention_window
                    ),
                    ttl_s=context.configuration.overlay.ttl_s,
                )
            if published:
                from kanbus.coordination_mqtt import inspect_lease as inspect_mqtt_lease

                state = inspect_mqtt_lease(
                    context.project_dir / "events",
                    context.project_dir,
                    resource,
                    context.configuration,
                )
        if provider == "git":
            state = inspect_lease(context.project_dir / "events", resource)
        if not state.active or state.owner != owner or state.claim_id != claim_id:
            raise IssueRouterError("package already claimed")
        handles.append(
            _ClaimHandle(provider, resource, owner, claim_id, mutex_config, revision)
        )
        return
    try:
        mutex_acquire(
            mutex_config,
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            revision=revision,
            ttl_seconds=parse_duration(
                context.configuration.coordination.default_lease_ttl
            ),
        )
    except (MutexApiUnavailable, MutexApiError) as error:
        if (
            isinstance(error, MutexApiError)
            and error.status == 409
            and allow_contention
        ):
            raise IssueRouterError("package already claimed") from error
        if isinstance(error, MutexApiError) and error.status == 409:
            raise IssueRouterError("package already claimed") from error
        raise IssueRouterError(HARD_COORDINATION_ERROR) from error
    # The Mutex API is authoritative. Only after it grants the lease do we
    # append the durable Git mirror, so a rejected claimant cannot leave a
    # losing soft claim behind. Track each successful acquisition separately
    # for precise cleanup; reverse release order drops the Git mirror first.
    handles.append(
        _ClaimHandle("mutex_api", resource, owner, claim_id, mutex_config, revision)
    )
    soft_claim(
        context.project_dir / "events",
        context.configuration.coordination,
        resource=resource,
        owner=owner,
        claim_id=claim_id,
        revision=revision,
        now=utc_now(),
    )
    handles.append(
        _ClaimHandle("git", resource, owner, claim_id, mutex_config, revision)
    )


def _release_claims(context: RouterContext, handles: list[_ClaimHandle]) -> None:
    release_errors: list[Exception] = []
    for handle in reversed(handles):
        try:
            if handle.provider == "mutex_api":
                mutex_release(
                    handle.mutex_config,
                    resource=handle.resource,
                    owner=handle.owner,
                    claim_id=handle.claim_id,
                )
            else:
                if not _router_soft_lease_is_current(context, handle):
                    continue
                released_at = utc_now()
                try:
                    event_id = soft_release(
                        context.project_dir / "events",
                        resource=handle.resource,
                        owner=handle.owner,
                        claim_id=handle.claim_id,
                        now=released_at,
                    )
                except CoordinationError as error:
                    if str(
                        error
                    ) == "lease owner mismatch" and not _router_soft_lease_is_current(
                        context, handle
                    ):
                        continue
                    raise
                if handle.provider == "mqtt":
                    publish_release_visibility(
                        context.root,
                        context.project_dir,
                        context.configuration,
                        resource=handle.resource,
                        owner=handle.owner,
                        claim_id=handle.claim_id,
                        event_id=event_id,
                        occurred_at=released_at,
                        operation_sequence=operation_sequence_for_event(
                            context.project_dir / "events", handle.resource, event_id
                        ),
                    )
        except (CoordinationError, MutexApiUnavailable, MutexApiError) as error:
            release_errors.append(error)
    if handles:
        try:
            publish_router_state(context.root)
        except IssueRouterError as error:
            raise IssueRouterError(
                f"router coordination release could not be published: {error}"
            ) from error
    if release_errors:
        raise IssueRouterError(
            "router coordination release failed"
        ) from release_errors[0]


def _router_soft_lease_is_current(context: RouterContext, handle: _ClaimHandle) -> bool:
    """Check whether a soft lease still belongs to this router handle."""
    lease = inspect_lease(
        context.project_dir / "events", handle.resource, now=utc_now()
    )
    return (
        lease.active
        and lease.owner == handle.owner
        and lease.claim_id == handle.claim_id
    )


def _assert_current_claim(
    project_dir: Path,
    package_id: str,
    claim_id: str,
    revision: int,
) -> None:
    events = read_router_events(project_dir, package_id)
    current = _latest_router_event(events, package_id, "router_claimed")
    payload = {} if current is None else current.get("payload", {})
    current_claim = str(payload.get("claim_id", ""))
    current_revision = int(payload.get("revision", 0))
    if current_claim != claim_id:
        raise IssueRouterError(
            f"stale router claim {claim_id} for package {package_id}; current claim is {current_claim} at revision {current_revision}"
        )
    if revision != current_revision:
        raise IssueRouterError(
            f"stale router revision {revision} for package {package_id}; current revision is {current_revision}"
        )


def _validate_router_start_claim(
    context: RouterContext,
    shared_events_dir: Path,
    package_id: str,
    owner: str,
    claim_id: str,
    revision: int,
    issue_handle: _ClaimHandle,
) -> None:
    """Fence a not-yet-persisted start against shared and live claim state."""
    resource = f"router:issue:{package_id}"
    now = utc_now()
    durable = inspect_lease(shared_events_dir, resource, now=now)
    if not durable.active or durable.owner != owner or durable.claim_id != claim_id:
        raise IssueRouterError("package already claimed")

    hard = bool(
        context.configuration.coordination.providers
        and context.configuration.coordination.providers[0] == "mutex_api"
    )
    if hard:
        try:
            lease = mutex_inspect(
                context.configuration.coordination.mutex_api,
                resource=resource,
            )
        except (MutexApiUnavailable, MutexApiError) as error:
            raise IssueRouterError(HARD_COORDINATION_ERROR) from error
        if (
            lease is None
            or lease.owner != owner
            or lease.claim_id != claim_id
            or lease.revision != revision
        ):
            raise IssueRouterError("package already claimed")
    elif issue_handle.provider == "mqtt":
        try:
            from kanbus.coordination_mqtt import inspect_lease as inspect_mqtt_lease

            live = inspect_mqtt_lease(
                shared_events_dir,
                context.project_dir,
                resource,
                context.configuration,
                now=now,
            )
        except CoordinationError as error:
            raise IssueRouterError("router coordination lease unavailable") from error
        if not live.active or live.owner != owner or live.claim_id != claim_id:
            raise IssueRouterError("package already claimed")


def _restore_stale_pull_request_branch(
    root: Path,
    branch_ref: str,
    stale_head: str,
    previous_head: str | None,
) -> bool:
    """CAS-restore a PR branch only when it still points at the stale run.

    :param root: User repository root.
    :type root: Path
    :param branch_ref: Fully qualified remote branch ref.
    :type branch_ref: str
    :param stale_head: Commit published by the stale run.
    :type stale_head: str
    :param previous_head: Branch commit visible before stale publication.
    :type previous_head: str | None
    """
    target = f"{previous_head}:{branch_ref}" if previous_head else f":{branch_ref}"
    try:
        subprocess.run(
            [
                "git",
                "push",
                f"--force-with-lease={branch_ref}:{stale_head}",
                "origin",
                target,
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def _assert_claim_fence(
    context: RouterContext,
    package_id: str,
    claim_id: str,
    revision: int,
    *,
    allow_cancel: bool = False,
) -> None:
    """Check both the logical event revision and its authoritative live lease."""
    from kanbus.router_state import router_state_root

    try:
        router_state_root(context.root, refresh=True)
    except IssueRouterError as error:
        raise IssueRouterError(
            "router state reconciliation failed; no package mutation is safe"
        ) from error
    _assert_current_claim(context.project_dir, package_id, claim_id, revision)
    current = _latest_router_event(
        read_router_events(context.project_dir, package_id),
        package_id,
        "router_claimed",
    )
    payload = {} if current is None else current.get("payload", {})
    if not allow_cancel and _cancel_was_requested(
        context.project_dir, package_id, claim_id
    ):
        raise IssueRouterError("router run was cancelled")
    renewal_error = _RENEWAL_ERRORS.get(claim_id)
    if renewal_error:
        raise IssueRouterError(renewal_error)
    resource = f"router:issue:{package_id}"
    hard = bool(
        context.configuration.coordination.providers
        and context.configuration.coordination.providers[0] == "mutex_api"
    )
    try:
        if hard:
            lease = mutex_inspect(
                context.configuration.coordination.mutex_api,
                resource=resource,
            )
            if (
                lease is None
                or lease.owner != f"issue-router:{os.getpid()}"
                or lease.claim_id != claim_id
                or lease.revision != revision
            ):
                raise IssueRouterError(
                    f"stale router claim {claim_id} for package {package_id}; current claim is not held at revision {revision}"
                )
        else:
            provider_used = str(payload.get("provider_used", "git"))
            if provider_used == "mqtt":
                from kanbus.coordination_mqtt import inspect_lease as inspect_mqtt_lease

                lease = inspect_mqtt_lease(
                    context.project_dir / "events",
                    context.project_dir,
                    resource,
                    context.configuration,
                )
            else:
                lease = inspect_lease(context.project_dir / "events", resource)
            lease_events = [
                event
                for event in _read_events(context.project_dir / "events")
                if event.get("issue_id") == resource
                and event.get("event_type") == "coordination.claim"
            ]
            if lease_events and (not lease.active or lease.claim_id != claim_id):
                raise IssueRouterError(
                    f"stale router claim {claim_id} for package {package_id}; current claim is not held at revision {revision}"
                )
    except (CoordinationError, MutexApiUnavailable, MutexApiError) as error:
        message = (
            HARD_COORDINATION_ERROR if hard else "router coordination lease unavailable"
        )
        raise IssueRouterError(message) from error


def _cancel_was_requested(project_dir: Path, package_id: str, claim_id: str) -> bool:
    """Check durable router history so an executor honors remote cancellation."""
    return any(
        event.get("event_type") == "router_cancel_requested"
        and str(event.get("payload", {}).get("claim_id", "")) == claim_id
        for event in read_router_events(project_dir, package_id)
    )


def _adapter_process_record_path(root: Path, package_id: str, claim_id: str) -> Path:
    """Return a host-local PID record path outside the user's project tree."""
    common_dir_text = _git(root, ["rev-parse", "--git-common-dir"])
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = (root / common_dir).resolve()
    record_key = hashlib.sha256(f"{package_id}\0{claim_id}".encode()).hexdigest()
    return common_dir / "kanbus-router-adapters" / f"{record_key}.json"


def _signal_registered_adapter(root: Path, package_id: str, claim_id: str) -> None:
    """Terminate only the process record belonging to the active package claim."""
    path = _adapter_process_record_path(root, package_id, claim_id)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        pid = record.get("pid")
        process_identity = record.get("process_identity")
        if (
            record.get("schema_version") != 2
            or record.get("package_id") != package_id
            or record.get("claim_id") != claim_id
            or isinstance(pid, bool)
            or not isinstance(pid, int)
            or pid < 1
            or not isinstance(process_identity, str)
            or not process_identity
            or _process_identity(pid) != process_identity
        ):
            return
        pidfd_open = getattr(os, "pidfd_open", None)
        pidfd_send_signal = getattr(signal, "pidfd_send_signal", None)
        if callable(pidfd_open) and callable(pidfd_send_signal):
            process_handle = pidfd_open(pid)
            try:
                if _process_identity(pid) == process_identity:
                    pidfd_send_signal(process_handle, signal.SIGTERM)
            finally:
                os.close(process_handle)
        elif _process_identity(pid) == process_identity:
            os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError, TypeError):
        return


def _start_lease_renewer(
    context: RouterContext,
    handles: list[_ClaimHandle],
    claim_id: str,
    *,
    initial_pass: bool = False,
) -> tuple[threading.Event, threading.Thread]:
    """Renew active leases while a configured adapter is running."""
    stopped = threading.Event()
    initial_cycle_complete = threading.Event() if initial_pass else None
    ttl_seconds = parse_duration(context.configuration.coordination.default_lease_ttl)
    interval = max(0.05, min(ttl_seconds / 3, 30.0))

    def renew_loop() -> None:
        first_pass = True
        while not stopped.is_set():
            if not (initial_pass and first_pass) and stopped.wait(interval):
                return
            active_handles = list(handles)
            if not active_handles:
                if initial_cycle_complete is not None and first_pass:
                    initial_cycle_complete.set()
                first_pass = False
                continue
            for handle in active_handles:
                if handle.claim_id != claim_id:
                    continue
                try:
                    if handle.provider == "mutex_api":
                        renewed_at = utc_now()
                        lease = mutex_inspect(
                            handle.mutex_config, resource=handle.resource
                        )
                        if (
                            lease is None
                            or lease.owner != handle.owner
                            or lease.claim_id != handle.claim_id
                            or lease.revision != handle.revision
                        ):
                            raise MutexApiUnavailable(
                                "router coordination lease renewal failed"
                            )
                        extension_seconds = _lease_renewal_extension_seconds(
                            lease.expires_at, renewed_at, ttl_seconds
                        )
                        if extension_seconds:
                            mutex_renew(
                                handle.mutex_config,
                                resource=handle.resource,
                                owner=handle.owner,
                                claim_id=handle.claim_id,
                                extend_seconds=extension_seconds,
                            )
                    else:
                        renewed_at = utc_now()
                        if not _router_soft_lease_is_current(context, handle):
                            continue
                        lease = inspect_lease(
                            context.project_dir / "events",
                            handle.resource,
                            now=renewed_at,
                        )
                        extension_seconds = _lease_renewal_extension_seconds(
                            lease.expires_at, renewed_at, ttl_seconds
                        )
                        if extension_seconds:
                            try:
                                renewed_state = soft_renew(
                                    context.project_dir / "events",
                                    context.configuration.coordination,
                                    resource=handle.resource,
                                    owner=handle.owner,
                                    claim_id=handle.claim_id,
                                    extend=f"{extension_seconds}s",
                                    now=renewed_at,
                                )
                            except CoordinationError as error:
                                if str(
                                    error
                                ) == "lease owner mismatch" and not _router_soft_lease_is_current(
                                    context, handle
                                ):
                                    continue
                                raise
                            if (
                                not renewed_state.active
                                or renewed_state.owner != handle.owner
                                or renewed_state.claim_id != handle.claim_id
                            ):
                                continue
                            if not _router_soft_lease_is_current(context, handle):
                                continue
                        else:
                            renewed_state = lease
                        if (
                            extension_seconds
                            and handle.provider == "mqtt"
                            and not publish_renewal_visibility(
                                context.root,
                                context.project_dir,
                                context.configuration,
                                resource=handle.resource,
                                owner=handle.owner,
                                claim_id=handle.claim_id,
                                state=renewed_state,
                                occurred_at=renewed_at,
                            )
                        ):
                            handle.provider = "git"
                except (CoordinationError, MutexApiUnavailable, MutexApiError) as error:
                    _RENEWAL_ERRORS[claim_id] = (
                        "router coordination lease renewal failed"
                    )
                    package_id = handle.resource.removeprefix("router:issue:")
                    if package_id == handle.resource:
                        package_id = "control"
                    record_router_event(
                        context.project_dir,
                        package_id=package_id,
                        event_type="router_lease_renewal_failed",
                        payload={
                            "claim_id": claim_id,
                            "resource": handle.resource,
                            "message": str(error),
                        },
                    )
                    active = _ACTIVE_ADAPTERS.get(package_id)
                    if active is not None:
                        active[1].cancel(claim_id)
                    if package_id == "control":
                        _cancel_active_adapters(context)
                    if initial_cycle_complete is not None and first_pass:
                        initial_cycle_complete.set()
                    return
            try:
                publish_router_state(context.root)
            except IssueRouterError as error:
                _RENEWAL_ERRORS[claim_id] = "router coordination lease renewal failed"
                package_id = next(
                    (
                        handle.resource.removeprefix("router:issue:")
                        for handle in active_handles
                        if handle.resource.startswith("router:issue:")
                    ),
                    "control",
                )
                active = _ACTIVE_ADAPTERS.get(package_id)
                if active is not None:
                    active[1].cancel(claim_id)
                if package_id == "control":
                    _cancel_active_adapters(context)
                record_router_event(
                    context.project_dir,
                    package_id=package_id,
                    event_type="router_lease_renewal_failed",
                    payload={
                        "claim_id": claim_id,
                        "resource": "router:state",
                        "message": str(error),
                    },
                )
                if initial_cycle_complete is not None and first_pass:
                    initial_cycle_complete.set()
                return
            if initial_cycle_complete is not None and first_pass:
                initial_cycle_complete.set()
            first_pass = False

    thread = threading.Thread(
        target=renew_loop,
        name=f"kanbus-router-renew-{claim_id}",
        daemon=True,
    )
    thread.start()
    if initial_cycle_complete is not None:
        initial_cycle_complete.wait()
    return stopped, thread


def _lease_renewal_extension_seconds(
    current_expiry: datetime | None,
    renewed_at: datetime,
    lease_ttl_seconds: int,
) -> int:
    """Return only the extension needed to preserve a fixed TTL horizon.

    :param current_expiry: Current lease expiration from its authoritative provider.
    :type current_expiry: datetime | None
    :param renewed_at: Timestamp of the renewal operation.
    :type renewed_at: datetime
    :param lease_ttl_seconds: Configured lease horizon in seconds.
    :type lease_ttl_seconds: int
    :return: Positive extension in seconds, or zero when the lease already reaches
        the target horizon.
    :rtype: int
    """
    if current_expiry is None:
        return 0
    target_expiry = renewed_at + timedelta(seconds=lease_ttl_seconds)
    return max(0, math.ceil((target_expiry - current_expiry).total_seconds()))


def _cancel_active_adapters(context: RouterContext) -> None:
    """Stop local and registered adapter processes if the scheduler lease is lost."""
    for package_id, (claim_id, adapter) in list(_ACTIVE_ADAPTERS.items()):
        adapter.cancel(claim_id)
        _signal_registered_adapter(context.root, package_id, claim_id)


def _next_revision(project_dir: Path, package_id: str) -> int:
    events = read_router_events(project_dir, package_id)
    return (
        max(
            (int(event.get("payload", {}).get("revision", 0)) for event in events),
            default=0,
        )
        + 1
    )


def _accepted_checkpoint(events: list[dict[str, object]]) -> str | None:
    event = max(
        (
            item
            for item in events
            if item.get("event_type") == "router_checkpoint_accepted"
        ),
        key=lambda item: (
            str(item.get("occurred_at", "")),
            str(item.get("event_id", "")),
        ),
        default=None,
    )
    if event is None:
        return None
    return str(event.get("payload", {}).get("ref", "")) or None


def _accepted_checkpoint_revision(events: list[dict[str, object]]) -> int | None:
    event = max(
        (
            item
            for item in events
            if item.get("event_type") == "router_checkpoint_accepted"
        ),
        key=lambda item: (
            str(item.get("occurred_at", "")),
            str(item.get("event_id", "")),
        ),
        default=None,
    )
    return None if event is None else int(event.get("payload", {}).get("revision", 0))


def _attempt_for_claim(events: list[dict[str, object]]) -> int:
    retry = max(
        (
            event
            for event in events
            if event.get("event_type") == "router_retry_scheduled"
        ),
        key=lambda event: (
            str(event.get("occurred_at", "")),
            str(event.get("event_id", "")),
        ),
        default=None,
    )
    if retry is None:
        return 1
    return max(1, int(retry.get("payload", {}).get("next_attempt", 1)))


def _claim_is_active(events: list[dict[str, object]], package_id: str) -> bool:
    history = [
        event for event in events if event.get("issue_id") == f"router:{package_id}"
    ]
    claim = _latest_router_event(history, package_id, "router_claimed")
    if claim is None:
        return False
    claim_id = claim.get("payload", {}).get("claim_id")
    end_types = {
        "router_completed",
        "router_blocked",
        "router_cancelled",
        "router_retry_scheduled",
        "router_retry_exhausted",
    }
    return not any(
        event.get("event_type") in end_types
        and event.get("payload", {}).get("claim_id") == claim_id
        for event in history
    )


def _resolve_package_id(context: RouterContext, issue_id: str) -> str:
    issue = next((item for item in context.issues if item.identifier == issue_id), None)
    if issue is None:
        raise IssueRouterError(f'no active router run for package "{issue_id}"')
    if issue.parent:
        # The nearest explicitly routed ancestor is the package root.
        by_id = {item.identifier: item for item in context.issues}
        parent_id = issue.parent
        while parent_id in by_id:
            parent = by_id[parent_id]
            if any(
                label.startswith(("agent-class:", "agent-provider:"))
                for label in parent.labels
            ):
                return parent.identifier
            parent_id = parent.parent or ""
    return issue_id


def _candidate_for_package(
    context: RouterContext,
    package_id: str,
    package_issue_ids: list[str] | None,
) -> RouterPlanEligiblePackage:
    plan = build_router_plan(context)
    candidate = next(
        (item for item in plan.eligible if item.issue_id == package_id), None
    )
    if candidate is not None:
        return candidate
    root = next(
        (item for item in context.issues if item.identifier == package_id), None
    )
    if root is None:
        raise IssueRouterError(f'unknown router package "{package_id}"')
    labels = [
        label
        for label in root.labels
        if label.startswith(("agent-class:", "agent-provider:"))
    ]
    if len(labels) != 1:
        raise IssueRouterError(f'package "{package_id}" has no unique router route')
    prefix, name = labels[0].split(":", 1)
    kind = "class" if prefix == "agent-class" else "provider"
    profile = context.router.classes[name].providers[0] if kind == "class" else name
    from kanbus.issue_router import RouterPlanRoute

    return RouterPlanEligiblePackage(
        issue_id=package_id,
        route=RouterPlanRoute(kind=kind, name=name, provider_profile=profile),
        package_issue_ids=package_issue_ids or [package_id],
        pending_since=root.created_at.isoformat(),
        attempt=1,
    )


def _reconcile_pull_requests(
    context: RouterContext,
    scheduler_claim_handles: list[_ClaimHandle] | None = None,
) -> None:
    if context.router.forge is None:
        return
    forge = _FAKE_FORGE or GitHubForge.from_configuration(context.router)

    def assert_scheduler_claim() -> None:
        if scheduler_claim_handles is not None:
            _assert_scheduler_claim(context, scheduler_claim_handles)

    all_events = _read_events(context.project_dir / "events")
    opened = [
        event
        for event in all_events
        if event.get("event_type") == "router_pull_request_opened"
    ]
    for event in opened:
        assert_scheduler_claim()
        number = int(event.get("payload", {}).get("number", 0))
        if not number:
            continue
        pull = forge.observe_pull_request(number)
        head_sha = str(pull.get("head_sha") or pull.get("head", {}).get("sha", ""))
        merged = bool(pull.get("merged", False))
        if pull.get("state") == "closed":
            record_github_pull_request_event(
                context.project_dir,
                context.router,
                {
                    "schema_version": 1,
                    "event_id": f"poll:pull_request:{number}:{head_sha}:closed:{int(merged)}",
                    "kind": "pull_request",
                    "action": "closed",
                    "repository": context.router.forge.repository,
                    "number": number,
                    "head_sha": head_sha,
                    "merged": merged,
                },
                before_mutation=assert_scheduler_claim,
            )
            continue
        if merged:
            continue
        old_sha = str(event.get("payload", {}).get("head_sha", ""))
        if head_sha and head_sha != old_sha:
            record_github_pull_request_event(
                context.project_dir,
                context.router,
                {
                    "schema_version": 1,
                    "event_id": f"poll:pull_request:{number}:{head_sha}:synchronize",
                    "kind": "pull_request",
                    "action": "synchronize",
                    "repository": context.router.forge.repository,
                    "number": number,
                    "head_sha": head_sha,
                    "merged": False,
                },
                before_mutation=assert_scheduler_claim,
            )

        reviews = forge.list_pull_request_reviews(number)
        latest_review = _latest_relevant_review(reviews, head_sha)
        if latest_review is not None:
            review_state = str(latest_review["state"])
            action = "approved" if review_state == "APPROVED" else "requested_changes"
            review_id = latest_review.get("id", "unknown")
            submitted_at = str(latest_review.get("submitted_at", "unknown"))
            assert_scheduler_claim()
            record_github_pull_request_event(
                context.project_dir,
                context.router,
                {
                    "schema_version": 1,
                    "event_id": (
                        f"poll:review:{number}:{head_sha}:{review_id}:"
                        f"{submitted_at}:{review_state}"
                    ),
                    "kind": "pull_request",
                    "action": action,
                    "repository": context.router.forge.repository,
                    "number": number,
                    "head_sha": head_sha,
                    "merged": False,
                },
                before_mutation=assert_scheduler_claim,
            )

        latest_by_name: dict[str, dict[str, object]] = {}
        for check_run in forge.list_check_runs(number, head_sha):
            if check_run.get("status") != "completed":
                continue
            conclusion = check_run.get("conclusion")
            if conclusion not in {
                "success",
                "failure",
                "cancelled",
                "timed_out",
                "action_required",
            }:
                continue
            check_head_sha = check_run.get("head_sha")
            if check_head_sha is not None and check_head_sha != head_sha:
                continue
            name = str(check_run.get("name") or "check")
            previous = latest_by_name.get(name)
            update_key = (
                str(check_run.get("completed_at") or check_run.get("updated_at") or ""),
                str(check_run.get("id", "")),
            )
            previous_key = (
                (
                    ""
                    if previous is None
                    else str(
                        previous.get("completed_at") or previous.get("updated_at") or ""
                    )
                ),
                "" if previous is None else str(previous.get("id", "")),
            )
            if previous is None or update_key > previous_key:
                latest_by_name[name] = check_run

        for check_run in (latest_by_name[name] for name in sorted(latest_by_name)):
            check_run_id = check_run.get("id")
            if isinstance(check_run_id, bool) or not isinstance(check_run_id, int):
                continue
            conclusion = str(check_run["conclusion"])
            assert_scheduler_claim()
            record_github_check_run_event(
                context.project_dir,
                context.router,
                {
                    "schema_version": 1,
                    "event_id": f"check-run:{check_run_id}:{head_sha}",
                    "kind": "check_run",
                    "action": "completed",
                    "repository": context.router.forge.repository,
                    "number": number,
                    "head_sha": head_sha,
                    "conclusion": conclusion,
                },
                before_mutation=assert_scheduler_claim,
            )


def _latest_relevant_review(
    reviews: list[dict[str, object]], head_sha: str
) -> dict[str, object] | None:
    """Reduce GitHub reviews to each reviewer's latest state for this head.

    A single newest review is insufficient: a newer approval from one reviewer
    must not erase another reviewer's still-current request for changes.
    """
    latest_by_reviewer: dict[str, dict[str, object]] = {}
    for review in reviews:
        if review.get("commit_id") not in {None, head_sha}:
            continue
        if review.get("state") not in {"APPROVED", "CHANGES_REQUESTED"}:
            continue
        user = review.get("user")
        reviewer = (
            user.get("login")
            if isinstance(user, dict) and isinstance(user.get("login"), str)
            else None
        )
        reviewer_key = str(reviewer or f"review:{review.get('id', 'unknown')}")
        previous = latest_by_reviewer.get(reviewer_key)
        ordering = (
            str(review.get("submitted_at", "")),
            str(review.get("id", "")),
        )
        previous_ordering = (
            (
                str(previous.get("submitted_at", "")),
                str(previous.get("id", "")),
            )
            if previous is not None
            else None
        )
        if previous is None or ordering > previous_ordering:
            latest_by_reviewer[reviewer_key] = review

    changes_requested = [
        review
        for review in latest_by_reviewer.values()
        if review.get("state") == "CHANGES_REQUESTED"
    ]
    candidates = changes_requested or [
        review
        for review in latest_by_reviewer.values()
        if review.get("state") == "APPROVED"
    ]
    return max(
        candidates,
        key=lambda review: (
            str(review.get("submitted_at", "")),
            str(review.get("id", "")),
        ),
        default=None,
    )


def _git(root: Path, arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise IssueRouterError("router isolated worktree operation failed") from error
    return result.stdout.strip()


def _remote_ref_sha(root: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "ls-remote", "origin", ref],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise IssueRouterError("router could not inspect the current remote ref")
    first = result.stdout.strip().split(maxsplit=1)
    return first[0] if first else None


def _validate_worktree_changes(project_directory: str, claim_id: str) -> None:
    """Reject adapter edits to Kanbus project state outside canonical mutations."""
    worktree = _WORKTREE_PATHS.get(claim_id)
    if worktree is None or not worktree.exists():
        return
    normalized_directory = posixpath.normpath(project_directory.replace("\\", "/"))
    project_path = PurePosixPath(normalized_directory)
    if project_path.is_absolute() or ".." in project_path.parts:
        raise IssueRouterError("router project directory must be repository-relative")
    try:
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--no-renames",
            ],
            cwd=worktree,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise IssueRouterError(
            "router could not inspect isolated worktree changes"
        ) from error
    for record in status.split(b"\0"):
        if len(record) < 4:
            continue
        changed_path = PurePosixPath(os.fsdecode(record[3:]))
        if changed_path == project_path or project_path in changed_path.parents:
            raise IssueRouterError(
                "router adapter may not modify Kanbus project state directly"
            )


def _commit_isolated_worktree(
    worktree: Path, project_directory: str, package_id: str, revision: int
) -> None:
    """Commit validated agent changes on the isolated router branch."""
    try:
        # Stage tracked edits first. This cannot add ignored shared router
        # events, while preserving deletes and modifications to tracked source.
        subprocess.run(
            ["git", "add", "-u", "--", "."],
            cwd=worktree,
            check=True,
            capture_output=True,
            text=True,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", "."],
            cwd=worktree,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        project_path = PurePosixPath(
            posixpath.normpath(project_directory.replace("\\", "/"))
        )
        source_paths = [
            os.fsdecode(path)
            for path in untracked
            if path
            and not (
                (candidate := PurePosixPath(os.fsdecode(path))) == project_path
                or project_path in candidate.parents
            )
        ]
        if source_paths:
            subprocess.run(
                ["git", "add", "--", *source_paths],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Kanbus Issue Router",
                "-c",
                "user.email=issue-router@localhost",
                "commit",
                "--allow-empty",
                "-m",
                f"[{package_id}] router checkpoint r{revision}",
            ],
            cwd=worktree,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise IssueRouterError(
            "router could not create an isolated checkpoint"
        ) from error


def _update_checkpoint_ref(root: Path, ref: str, object_id: str) -> str | None:
    """Lease-publish a checkpoint ref and return its previously advertised SHA."""
    if not ref.startswith("refs/kanbus/router/"):
        raise IssueRouterError("router checkpoint ref is outside the Kanbus namespace")
    has_remote = (
        subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )
    previous = _remote_ref_sha(root, ref) if has_remote else _local_ref_sha(root, ref)
    try:
        subprocess.run(
            ["git", "update-ref", ref, object_id],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        if has_remote:
            subprocess.run(
                [
                    "git",
                    "push",
                    f"--force-with-lease={ref}:{previous or ''}",
                    "origin",
                    f"{ref}:{ref}",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
    except (OSError, subprocess.CalledProcessError) as error:
        if previous is None:
            subprocess.run(
                ["git", "update-ref", "-d", ref],
                cwd=root,
                check=False,
                capture_output=True,
            )
        else:
            subprocess.run(
                ["git", "update-ref", ref, previous],
                cwd=root,
                check=False,
                capture_output=True,
            )
        raise IssueRouterError("router could not publish checkpoint ref") from error
    return previous


def _local_ref_sha(root: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--hash", ref],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _restore_checkpoint_ref(
    root: Path, ref: str, published_sha: str, previous_sha: str | None
) -> None:
    """Best-effort CAS rollback when the claim loses its fence after publishing."""
    try:
        if previous_sha is None:
            subprocess.run(
                ["git", "update-ref", "-d", ref, published_sha],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            target = f":{ref}"
        else:
            subprocess.run(
                ["git", "update-ref", ref, previous_sha, published_sha],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            target = f"{previous_sha}:{ref}"
        if (
            subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            ).returncode
            == 0
        ):
            subprocess.run(
                [
                    "git",
                    "push",
                    f"--force-with-lease={ref}:{published_sha}",
                    "origin",
                    target,
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
    except (OSError, subprocess.CalledProcessError):
        # The failed claim has no further authority. The newer ref owner wins.
        return


__all__ = [
    "RouterRunResult",
    "cancel_router_package",
    "count_active_router_runs",
    "publish_router_result",
    "retry_delay_seconds",
    "run_router_once",
    "run_router_watch",
    "set_router_adapter",
    "set_router_forge",
]
