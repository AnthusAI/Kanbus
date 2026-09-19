"""Focused branch coverage for the Issue Router execution runtime."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from kanbus import router_execution
from kanbus.coordination_mutex_api import MutexApiError, MutexApiUnavailable
from kanbus.coordination import CoordinationError
from kanbus.issue_router import IssueRouterError, RouterPlanEligiblePackage
from kanbus.router_adapters import (
    RouterAgentResult,
    RouterArtifact,
    RouterCheckpoint,
    RouterIssueComment,
)
from kanbus.router_execution import _ClaimHandle


class Listener:
    def __init__(self):
        self.stopped = 0

    def stop(self):
        self.stopped += 1


class Thread:
    def __init__(self):
        self.joined = []

    def set(self):
        pass

    def join(self, timeout=None):
        self.joined.append(timeout)


def candidate(kind="provider"):
    return RouterPlanEligiblePackage.model_validate(
        {
            "issue_id": "kbs-42",
            "route": {
                "kind": kind,
                "name": "review" if kind == "class" else "codex",
                "provider_profile": "codex",
            },
            "package_issue_ids": ["kbs-42", "kbs-43"],
            "pending_since": "2026-09-17T12:00:00Z",
            "attempt": 2,
        }
    )


def context(tmp_path, providers=None, forge=None):
    coordination = SimpleNamespace(
        providers=list(providers or ["git"]),
        mutex_api=None,
        default_lease_ttl="30s",
        contention_window="1s",
    )
    workflow = SimpleNamespace(
        active="active", blocked="blocked", review="review", terminal=["closed"]
    )
    router = SimpleNamespace(
        providers={"codex": SimpleNamespace(adapter="codex", command="codex", args=[])},
        classes={"review": SimpleNamespace(providers=["codex"])},
        workflow=workflow,
        forge=forge,
        limits=SimpleNamespace(project_wip=1, provider_wip={}, class_wip={}),
        retries=SimpleNamespace(max_attempts=3),
        watch_interval="1s",
    )
    issue = SimpleNamespace(
        identifier="kbs-42",
        status="ready",
        title="Router test",
        issue_type="task",
        labels=["agent-provider:codex"],
        parent=None,
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )
    return SimpleNamespace(
        root=tmp_path,
        project_dir=tmp_path / "project",
        configuration=SimpleNamespace(
            coordination=coordination,
            project_directory="board",
            overlay=SimpleNamespace(ttl_s=30),
        ),
        router=router,
        issues=[issue],
        control=SimpleNamespace(),
    )


def result(outcome="completed", summary=""):
    return RouterAgentResult(schema_version=1, outcome=outcome, summary=summary)


def install_run_fakes(monkeypatch, ctx, *, adapter_result=None, adapter_error=None):
    package = candidate()
    listener = Listener()
    worker_thread = Thread()
    released = []
    events = []
    transitions = []
    plan = SimpleNamespace(eligible=[package, package], deferred=["deferred"])
    monkeypatch.setattr(router_execution, "start_soft_listener", lambda *_: listener)
    monkeypatch.setattr(router_execution, "build_router_plan", lambda _ctx: plan)
    monkeypatch.setattr(router_execution, "_next_revision", lambda *_: 3)
    monkeypatch.setattr(
        router_execution,
        "_start_lease_renewer",
        lambda *_a, **_kw: (SimpleNamespace(set=lambda: None), worker_thread),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    monkeypatch.setattr(
        router_execution,
        "create_router_event",
        lambda **kwargs: {
            "event_type": kwargs["event_type"],
            "payload": kwargs["payload"],
        },
    )

    def acquire(_ctx, _candidate, *, on_handles_updated, include_scheduler, **kwargs):
        provider = kwargs.get("soft_provider") or "git"
        handles = []
        if include_scheduler:
            handles.append(
                _ClaimHandle(provider, "router:scheduler", "owner", "claim", None)
            )
        handles.append(
            _ClaimHandle(provider, "router:issue:kbs-42", "owner", "claim", None, 3)
        )
        on_handles_updated(handles)
        return handles

    monkeypatch.setattr(router_execution, "_acquire_claims", acquire)
    monkeypatch.setattr(
        router_execution,
        "_release_claims",
        lambda _ctx, handles: released.append(list(handles)),
    )
    monkeypatch.setattr(
        router_execution,
        "publish_router_start_event",
        lambda _root, _event, validate_claim: validate_claim(
            ctx.project_dir / "events"
        ),
    )
    monkeypatch.setattr(
        router_execution, "_validate_router_start_claim", lambda *_: None
    )
    monkeypatch.setattr(
        router_execution, "_assert_claim_fence", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        router_execution,
        "_transition_package",
        lambda _ctx, _pkg, status, **_kw: transitions.append(status),
    )

    def run_adapter(*_args):
        if adapter_error:
            raise adapter_error
        return adapter_result or result()

    monkeypatch.setattr(router_execution, "_run_adapter", run_adapter)
    monkeypatch.setattr(router_execution, "_validate_worktree_changes", lambda *_: None)
    monkeypatch.setattr(router_execution, "_validate_result_scope", lambda *_: None)
    monkeypatch.setattr(router_execution, "_apply_issue_updates", lambda *_: None)
    monkeypatch.setattr(router_execution, "_publish_checkpoint", lambda *_: None)
    monkeypatch.setattr(router_execution, "_open_pull_request", lambda *_: None)
    if adapter_error is None:
        monkeypatch.setattr(router_execution, "add_issue_comment", lambda *_: None)
    monkeypatch.setattr(
        router_execution,
        "record_router_event",
        lambda _project, **kwargs: events.append(kwargs),
    )
    monkeypatch.setattr(router_execution, "_cancel_was_requested", lambda *_: False)
    return listener, worker_thread, released, events, transitions


def test_run_once_completes_and_cleans_all_claims(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    listener, worker_thread, released, events, transitions = install_run_fakes(
        monkeypatch, ctx
    )

    outcome = router_execution.run_router_once(ctx)

    assert outcome == router_execution.RouterRunResult(
        started=1, completed=1, review=1, deferred=2
    )
    assert transitions == ["active", "review"]
    assert events[-1]["event_type"] == "router_completed"
    assert len(released) == 2
    assert [item.resource for item in released[0]] == ["router:scheduler"]
    assert [item.resource for item in released[1]] == ["router:issue:kbs-42"]
    assert worker_thread.joined == [2]
    assert listener.stopped == 1


def test_completed_turn_always_publishes_an_issue_visible_review_record(
    monkeypatch, tmp_path
):
    """A missing optional adapter comment must not make completed work invisible."""
    ctx = context(tmp_path)
    install_run_fakes(
        monkeypatch,
        ctx,
        adapter_result=result("completed", "Implemented the requested behavior."),
    )
    comments = []
    monkeypatch.setattr(
        router_execution,
        "add_issue_comment",
        lambda _root, issue_id, author, text: comments.append((issue_id, author, text)),
    )

    outcome = router_execution.run_router_once(ctx)

    assert outcome == router_execution.RouterRunResult(
        started=1, completed=1, review=1, deferred=2
    )
    assert comments == [
        (
            "kbs-42",
            "Kanbus Issue Router",
            "## Agent turn complete\n\nImplemented the requested behavior.\n",
        )
    ]


def test_completed_review_record_includes_preserved_review_evidence():
    from kanbus.router_forge import ForgePullRequest

    comment = router_execution._completed_review_comment(
        RouterAgentResult(
            schema_version=1,
            outcome="completed",
            artifacts=[RouterArtifact(name="tests", ref="artifacts/tests.txt")],
        ),
        RouterCheckpoint(ref="refs/kanbus/router/checkpoints/kbs-42", revision=1),
        ForgePullRequest(
            number=42,
            url="https://example.test/pull/42",
            head_branch="codex/router/kbs-42/r1",
            head_sha="abc123",
            state="open",
        ),
    )

    assert comment == (
        "## Agent turn complete\n\n"
        "The agent completed a turn. Review the preserved branch and draft pull request.\n\n"
        "- Draft PR: https://example.test/pull/42\n"
        "- Branch: `codex/router/kbs-42/r1`\n"
        "- Checkpoint: `refs/kanbus/router/checkpoints/kbs-42`\n"
        "- Artifacts:\n"
        "  - `tests`: `artifacts/tests.txt`"
    )


@pytest.mark.parametrize(
    ("adapter_result", "expected_event", "expected_transition"),
    [
        (result("blocked", "blocked by API"), "router_blocked", "blocked"),
        (result("retryable_failure", "transient"), "router_retry_scheduled", None),
    ],
)
def test_run_once_processes_blocked_and_retryable_results(
    monkeypatch, tmp_path, adapter_result, expected_event, expected_transition
):
    ctx = context(tmp_path)
    _, _, _, events, transitions = install_run_fakes(
        monkeypatch, ctx, adapter_result=adapter_result
    )
    comments = []
    monkeypatch.setattr(
        router_execution,
        "add_issue_comment",
        lambda _root, issue_id, author, text: comments.append((issue_id, author, text)),
    )
    if expected_event == "router_retry_scheduled":
        monkeypatch.setattr(
            router_execution,
            "_schedule_retry",
            lambda *_: events.append({"event_type": "router_retry_scheduled"}),
        )

    outcome = router_execution.run_router_once(ctx)

    assert outcome.started == outcome.failed == 1
    assert (expected_transition in transitions) if expected_transition else True
    assert events[-1]["event_type"] == expected_event
    if expected_event == "router_blocked":
        assert comments == [("kbs-42", "Kanbus Issue Router", "blocked by API")]
    else:
        assert comments == []


@pytest.mark.parametrize(
    ("error", "cancel", "retry", "expected"),
    [
        (IssueRouterError("adapter crashed"), False, True, "adapter crashed"),
        (IssueRouterError("adapter crashed"), True, False, "router run was cancelled"),
        (
            IssueRouterError('invalid Codex router outcome "unknown"'),
            False,
            False,
            'invalid Codex router outcome "unknown"',
        ),
    ],
)
def test_run_once_classifies_adapter_errors(
    monkeypatch, tmp_path, error, cancel, retry, expected
):
    ctx = context(tmp_path)
    install_run_fakes(monkeypatch, ctx, adapter_error=error)
    monkeypatch.setattr(router_execution, "_cancel_was_requested", lambda *_: cancel)
    scheduled = []
    monkeypatch.setattr(
        router_execution, "_schedule_retry", lambda *_: scheduled.append(True)
    )

    outcome = router_execution.run_router_once(ctx)

    assert outcome.error == expected
    assert outcome.started == outcome.failed == 1
    assert bool(scheduled) is retry


def test_run_once_stops_listener_for_plan_failure_and_no_eligible_work(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    listener = Listener()
    monkeypatch.setattr(router_execution, "start_soft_listener", lambda *_: listener)
    monkeypatch.setattr(
        router_execution,
        "build_router_plan",
        lambda _ctx: (_ for _ in ()).throw(ValueError("bad plan")),
    )
    with pytest.raises(ValueError, match="bad plan"):
        router_execution.run_router_once(ctx)
    assert listener.stopped == 1

    listener = Listener()
    monkeypatch.setattr(router_execution, "start_soft_listener", lambda *_: listener)
    monkeypatch.setattr(
        router_execution,
        "build_router_plan",
        lambda _ctx: SimpleNamespace(eligible=[], deferred=["kbs-42"]),
    )
    assert router_execution.run_router_once(ctx).deferred == 1
    assert listener.stopped == 1


def test_run_once_returns_unstarted_failure_after_claim_acquisition_error(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    listener = Listener()
    monkeypatch.setattr(router_execution, "start_soft_listener", lambda *_: listener)
    monkeypatch.setattr(
        router_execution,
        "build_router_plan",
        lambda _ctx: SimpleNamespace(eligible=[candidate()], deferred=[]),
    )
    monkeypatch.setattr(router_execution, "_next_revision", lambda *_: 1)
    monkeypatch.setattr(
        router_execution,
        "_acquire_claims",
        lambda *_a, **_kw: (_ for _ in ()).throw(IssueRouterError("already claimed")),
    )
    monkeypatch.setattr(router_execution, "_release_claims", lambda *_: None)

    outcome = router_execution.run_router_once(ctx)

    assert outcome == router_execution.RouterRunResult(error="already claimed")
    assert listener.stopped == 1


def test_wait_watch_trigger_times_out_and_consumes_mqtt_signal(monkeypatch):
    assert router_execution._wait_for_watch_trigger(None, 0) is False

    class Received:
        def __init__(self):
            self.cleared = 0

        def wait(self, _timeout):
            return True

        def clear(self):
            self.cleared += 1

    received = Received()
    assert router_execution._wait_for_watch_trigger(
        SimpleNamespace(received=received), 1
    )
    assert received.cleared == 1


def test_acquire_claims_scans_project_provider_and_class_slots(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    ctx.router.limits = SimpleNamespace(
        project_wip=2,
        provider_wip={"codex": 1},
        class_wip={"review": 1},
    )
    resources = []

    def acquire(_ctx, handles, resource, owner, claim, revision, _hard, **_kw):
        resources.append(resource)
        if resource == "router:capacity:project:0":
            raise IssueRouterError("package already claimed")
        handles.append(_ClaimHandle("git", resource, owner, claim, None, revision))

    monkeypatch.setattr(router_execution, "_acquire_router_resource", acquire)
    monkeypatch.setattr(router_execution, "_release_claims", lambda *_: None)
    handles = router_execution._acquire_claims(
        ctx,
        candidate("class"),
        claim_id="claim-a",
        revision=1,
        owner="worker-a",
        include_scheduler=False,
    )

    assert resources == [
        "router:issue:kbs-42",
        "router:issue:kbs-43",
        "router:capacity:project:0",
        "router:capacity:project:1",
        "router:capacity:provider-profile:codex:0",
        "router:capacity:class:review:0",
    ]
    assert handles[-1].resource == "router:capacity:class:review:0"


def test_acquire_claims_releases_fixed_handles_when_capacity_is_full(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    ctx.router.limits = SimpleNamespace(project_wip=2, provider_wip={}, class_wip={})
    released = []
    updates = []

    def acquire(_ctx, handles, resource, owner, claim, revision, _hard, **_kw):
        if resource.startswith("router:capacity:"):
            raise IssueRouterError("package already claimed")
        handles.append(_ClaimHandle("git", resource, owner, claim, None, revision))

    monkeypatch.setattr(router_execution, "_acquire_router_resource", acquire)
    monkeypatch.setattr(
        router_execution,
        "_release_claims",
        lambda _ctx, handles: released.extend(h.resource for h in handles),
    )
    with pytest.raises(IssueRouterError, match="router capacity is full"):
        router_execution._acquire_claims(
            ctx,
            candidate(),
            claim_id="claim-a",
            revision=1,
            owner="worker-a",
            on_handles_updated=lambda handles: updates.append(list(handles)),
        )
    assert updates[-1] == []
    assert released == [
        "router:scheduler",
        "router:issue:kbs-42",
        "router:issue:kbs-43",
    ]


def test_acquire_hard_resource_maps_conflict_and_service_failure(monkeypatch, tmp_path):
    ctx = context(tmp_path, providers=["mutex_api", "git"])
    ctx.configuration.coordination.mutex_api = object()
    monkeypatch.setattr(router_execution, "mutex_is_configured", lambda _cfg: True)
    monkeypatch.setattr(router_execution, "mutex_acquire", lambda *_a, **_kw: None)
    mirrored = []
    monkeypatch.setattr(
        router_execution,
        "soft_claim",
        lambda *_a, **kw: mirrored.append(kw["resource"]),
    )
    handles = []
    router_execution._acquire_router_resource(
        ctx, handles, "router:issue:kbs-42", "worker", "claim", 2, True
    )
    assert [item.provider for item in handles] == ["mutex_api", "git"]
    assert mirrored == ["router:issue:kbs-42"]

    monkeypatch.setattr(
        router_execution,
        "mutex_acquire",
        lambda *_a, **_kw: (_ for _ in ()).throw(MutexApiError("busy", status=409)),
    )
    with pytest.raises(IssueRouterError, match="package already claimed"):
        router_execution._acquire_router_resource(
            ctx, [], "router:issue:kbs-42", "worker", "claim", 2, True
        )

    monkeypatch.setattr(
        router_execution,
        "mutex_acquire",
        lambda *_a, **_kw: (_ for _ in ()).throw(MutexApiUnavailable("offline")),
    )
    with pytest.raises(IssueRouterError, match="hard router coordination"):
        router_execution._acquire_router_resource(
            ctx, [], "router:issue:kbs-42", "worker", "claim", 2, True
        )


def test_scheduler_claim_checks_git_mqtt_and_mutex_providers(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    monkeypatch.setattr(
        "kanbus.router_state.router_state_root", lambda *_a, **_kw: tmp_path
    )
    lease = SimpleNamespace(active=True, owner="owner", claim_id="claim", revision=1)
    monkeypatch.setattr(router_execution, "inspect_lease", lambda *_a, **_kw: lease)
    handle = _ClaimHandle("git", "router:scheduler", "owner", "claim", None, 1)
    router_execution._assert_scheduler_claim(ctx, [handle])

    monkeypatch.setattr(
        "kanbus.coordination_mqtt.inspect_lease", lambda *_a, **_kw: lease
    )
    mqtt = _ClaimHandle("mqtt", "router:scheduler", "owner", "claim", None, 1)
    router_execution._assert_scheduler_claim(ctx, [mqtt])

    mutex_reads = []
    monkeypatch.setattr(
        router_execution,
        "mutex_inspect",
        lambda _cfg, *, resource: mutex_reads.append(resource) or lease,
    )
    mutex = _ClaimHandle("mutex_api", "router:scheduler", "owner", "claim", object(), 1)
    router_execution._assert_scheduler_claim(ctx, [mutex])
    assert mutex_reads == ["router:scheduler"]


@pytest.mark.parametrize(
    ("provider", "failure", "expected"),
    [
        (
            "git",
            CoordinationError("offline"),
            "scheduler coordination lease unavailable",
        ),
        (
            "mqtt",
            CoordinationError("offline"),
            "scheduler coordination lease unavailable",
        ),
        ("mutex_api", MutexApiUnavailable("offline"), "hard router coordination"),
    ],
)
def test_scheduler_claim_maps_provider_errors(
    monkeypatch, tmp_path, provider, failure, expected
):
    ctx = context(tmp_path)
    monkeypatch.setattr(
        "kanbus.router_state.router_state_root", lambda *_a, **_kw: tmp_path
    )

    def inspect(*_args, **_kwargs):
        raise failure

    if provider == "mutex_api":
        monkeypatch.setattr(router_execution, "mutex_inspect", inspect)
    elif provider == "mqtt":
        monkeypatch.setattr("kanbus.coordination_mqtt.inspect_lease", inspect)
    else:
        monkeypatch.setattr(router_execution, "inspect_lease", inspect)
    handle = _ClaimHandle(provider, "router:scheduler", "owner", "claim", object(), 1)
    with pytest.raises(IssueRouterError, match=expected):
        router_execution._assert_scheduler_claim(ctx, [handle])


def test_scheduler_claim_rejects_stale_lease_and_failed_state_refresh(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    monkeypatch.setattr(
        "kanbus.router_state.router_state_root",
        lambda *_a, **_kw: (_ for _ in ()).throw(IssueRouterError("stale tip")),
    )
    handle = _ClaimHandle("git", "router:scheduler", "owner", "claim", None, 1)
    with pytest.raises(IssueRouterError, match="state reconciliation failed"):
        router_execution._assert_scheduler_claim(ctx, [handle])

    monkeypatch.setattr(
        "kanbus.router_state.router_state_root", lambda *_a, **_kw: tmp_path
    )
    monkeypatch.setattr(
        router_execution,
        "inspect_lease",
        lambda *_a, **_kw: SimpleNamespace(
            active=False, owner="owner", claim_id="claim", revision=1
        ),
    )
    with pytest.raises(IssueRouterError, match="stale router scheduler claim"):
        router_execution._assert_scheduler_claim(ctx, [handle])


def test_watch_scheduler_requires_configured_mutex_and_releases_on_failure(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path, providers=["mutex_api"])
    ctx.configuration.coordination.mutex_api = object()
    monkeypatch.setattr(router_execution, "mutex_is_configured", lambda _cfg: False)
    with pytest.raises(IssueRouterError, match="hard router coordination"):
        router_execution._acquire_watch_scheduler_claim(ctx, soft_provider="git")

    monkeypatch.setattr(router_execution, "mutex_is_configured", lambda _cfg: True)
    monkeypatch.setattr(
        router_execution,
        "_acquire_router_resource",
        lambda _ctx, found, resource, owner, claim, revision, _hard, **_kw: found.append(
            _ClaimHandle("mutex_api", resource, owner, claim, object(), revision)
        ),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    monkeypatch.setattr(
        router_execution,
        "_assert_scheduler_claim",
        lambda *_: (_ for _ in ()).throw(IssueRouterError("stale")),
    )
    released = []
    monkeypatch.setattr(
        router_execution,
        "_release_claims",
        lambda _ctx, found: released.extend(found),
    )
    with pytest.raises(IssueRouterError, match="stale"):
        router_execution._acquire_watch_scheduler_claim(ctx, soft_provider="git")
    assert len(released) == 1


def test_cancel_router_package_cancels_adapter_and_preserves_checkpoint(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    claim = {
        "event_type": "router_claimed",
        "payload": {"claim_id": "claim-a", "revision": 4},
    }
    history = [
        {
            "event_type": "router_checkpoint_accepted",
            "payload": {"ref": "refs/checkpoint/4"},
        }
    ]

    class Adapter:
        def __init__(self):
            self.claims = []

        def cancel(self, claim_id):
            self.claims.append(claim_id)

    adapter = Adapter()
    monkeypatch.setattr(router_execution, "_resolve_package_id", lambda *_: "kbs-42")
    monkeypatch.setattr(router_execution, "read_router_events", lambda *_: history)
    monkeypatch.setattr(router_execution, "_latest_router_event", lambda *_: claim)
    monkeypatch.setattr(router_execution, "_read_events", lambda *_: [])
    monkeypatch.setattr(router_execution, "_claim_is_active", lambda *_: True)
    monkeypatch.setitem(
        router_execution._ACTIVE_ADAPTERS, "kbs-42", ("claim-a", adapter)
    )
    monkeypatch.setattr(
        router_execution, "record_router_event", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    monkeypatch.setattr(router_execution, "_signal_registered_adapter", lambda *_: None)
    transitions = []
    monkeypatch.setattr(
        router_execution,
        "_transition_package",
        lambda *_a, **kw: transitions.append(kw["allow_cancel"]),
    )

    checkpoint = router_execution.cancel_router_package(ctx, "kbs-42")

    assert checkpoint == "refs/checkpoint/4"
    assert adapter.claims == ["claim-a"]
    assert transitions == [True]


def test_cancel_router_package_rejects_inactive_run(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    monkeypatch.setattr(router_execution, "_resolve_package_id", lambda *_: "kbs-42")
    monkeypatch.setattr(router_execution, "read_router_events", lambda *_: [])
    monkeypatch.setattr(router_execution, "_latest_router_event", lambda *_: None)
    with pytest.raises(IssueRouterError, match="no active router run"):
        router_execution.cancel_router_package(ctx, "kbs-42")


def test_retry_scheduler_schedules_or_exhausts_attempts(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    ctx.router.retries.max_attempts = 2
    monkeypatch.setattr(
        router_execution, "_assert_claim_fence", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(router_execution, "load_router_context", lambda _root: ctx)
    monkeypatch.setattr(
        router_execution,
        "read_router_events",
        lambda *_: [
            {
                "event_type": "router_retry_scheduled",
                "occurred_at": "2026-09-17T12:00:00Z",
                "event_id": "retry",
                "payload": {"next_attempt": 2},
            }
        ],
    )
    monkeypatch.setattr(
        router_execution, "_accepted_checkpoint", lambda _events: "refs/cp"
    )
    transitions = []
    records = []
    publications = []
    monkeypatch.setattr(
        router_execution,
        "_transition_package",
        lambda *_a, **kw: transitions.append(kw["status"] if "status" in kw else _a[2]),
    )
    monkeypatch.setattr(
        router_execution,
        "record_router_event",
        lambda _project, **kw: records.append(kw),
    )
    monkeypatch.setattr(
        router_execution, "publish_router_state", lambda *_: publications.append(True)
    )

    router_execution._schedule_retry(ctx, "kbs-42", "claim-a", 3, "timeout")

    assert records[0]["event_type"] == "router_retry_exhausted"
    assert records[0]["payload"]["checkpoint"] == "refs/cp"
    assert transitions == ["blocked"]
    assert len(publications) == 1

    records.clear()
    transitions.clear()
    publications.clear()
    monkeypatch.setattr(router_execution, "_attempt_for_claim", lambda _events: 1)
    router_execution._schedule_retry(ctx, "kbs-42", "claim-a", 3, "timeout")
    assert records[0]["event_type"] == "router_retry_scheduled"
    assert records[0]["payload"]["delay_seconds"] == 30
    assert records[0]["payload"]["diagnostic"] == "timeout"
    assert len(publications) == 2


def test_candidate_fallback_and_package_resolution_errors(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    monkeypatch.setattr(
        router_execution,
        "build_router_plan",
        lambda _ctx: SimpleNamespace(eligible=[]),
    )
    fallback = router_execution._candidate_for_package(
        ctx, "kbs-42", ["kbs-42", "kbs-43"]
    )
    assert fallback.issue_id == "kbs-42"
    assert fallback.package_issue_ids == ["kbs-42", "kbs-43"]
    assert fallback.route.provider_profile == "codex"

    with pytest.raises(IssueRouterError, match="unknown router package"):
        router_execution._candidate_for_package(ctx, "kbs-missing", None)
    ctx.issues[0].labels = []
    with pytest.raises(IssueRouterError, match="no unique router route"):
        router_execution._candidate_for_package(ctx, "kbs-42", None)
    with pytest.raises(IssueRouterError, match="no active router run"):
        router_execution._resolve_package_id(ctx, "missing")


def test_apply_issue_updates_checks_scope_and_applies_status(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    ctx.issues[0].status = "ready"
    monkeypatch.setattr(
        router_execution, "_assert_claim_fence", lambda *_a, **_kw: None
    )
    monkeypatch.setattr("kanbus.workflows.validate_status_value", lambda *_: None)
    monkeypatch.setattr("kanbus.workflows.validate_status_transition", lambda *_: None)
    updates = []
    publications = []
    events = []
    monkeypatch.setattr(
        router_execution,
        "update_issue",
        lambda *args, **kwargs: updates.append((args, kwargs)),
    )
    monkeypatch.setattr(
        router_execution,
        "publish_router_state",
        lambda *_args: publications.append(True),
    )
    monkeypatch.setattr(
        router_execution,
        "record_router_event",
        lambda _project, **kwargs: events.append(kwargs),
    )
    candidate_ = candidate()
    update_result = RouterAgentResult(
        schema_version=1,
        outcome="completed",
        summary="progress update",
        issue_updates=[{"issue_id": "kbs-42", "status": "active"}],
    )
    router_execution._apply_issue_updates(ctx, candidate_, update_result, "claim-a", 3)
    assert len(updates) == 1
    assert updates[0][1]["assignee"] is None
    assert updates[0][1]["claim"] is False
    assert events[0]["event_type"] == "router_progress"
    assert len(publications) == 2

    with pytest.raises(IssueRouterError, match="outside router package"):
        router_execution._validate_result_scope(
            ctx,
            candidate_,
            RouterAgentResult(
                schema_version=1,
                outcome="completed",
                issue_updates=[{"issue_id": "other", "status": "active"}],
            ),
        )


def test_apply_issue_updates_rejects_terminal_status_and_wraps_update_failure(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    monkeypatch.setattr(
        router_execution, "_assert_claim_fence", lambda *_a, **_kw: None
    )
    monkeypatch.setattr("kanbus.workflows.validate_status_value", lambda *_: None)
    monkeypatch.setattr("kanbus.workflows.validate_status_transition", lambda *_: None)
    terminal = RouterAgentResult(
        schema_version=1,
        outcome="completed",
        issue_updates=[{"issue_id": "kbs-42", "status": "closed"}],
    )
    with pytest.raises(IssueRouterError, match="cannot transition"):
        router_execution._apply_issue_updates(ctx, candidate(), terminal, "claim", 1)

    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_args: None)
    completed_hint = RouterAgentResult(
        schema_version=1,
        outcome="completed",
        issue_updates=[{"issue_id": "kbs-42", "status": "completed"}],
    )
    # Completion is router-owned: it becomes the configured Review transition
    # later in the turn rather than a literal project status from the agent.
    router_execution._apply_issue_updates(ctx, candidate(), completed_hint, "claim", 1)

    issue_update_error = router_execution.IssueUpdateError("bad update")
    monkeypatch.setattr(
        router_execution,
        "update_issue",
        lambda *_a, **_kw: (_ for _ in ()).throw(issue_update_error),
    )
    result_with_update = RouterAgentResult(
        schema_version=1,
        outcome="completed",
        issue_updates=[{"issue_id": "kbs-42", "status": "active"}],
    )
    with pytest.raises(IssueRouterError, match="bad update"):
        router_execution._apply_issue_updates(
            ctx, candidate(), result_with_update, "claim", 1
        )


def test_transition_package_noop_unknown_and_update_failure(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    monkeypatch.setattr(
        router_execution, "_assert_claim_fence", lambda *_a, **_kw: None
    )
    assert (
        router_execution._transition_package(
            ctx, "kbs-42", "ready", claim_id="claim", revision=1
        )
        is None
    )
    with pytest.raises(IssueRouterError, match="unknown router package"):
        router_execution._transition_package(
            ctx, "missing", "active", claim_id="claim", revision=1
        )
    monkeypatch.setattr(
        router_execution,
        "update_issue",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            router_execution.IssueUpdateError("invalid transition")
        ),
    )
    with pytest.raises(IssueRouterError, match="invalid transition"):
        router_execution._transition_package(
            ctx, "kbs-42", "active", claim_id="claim", revision=1
        )


def test_router_transition_path_uses_configured_intermediate_status():
    configuration = SimpleNamespace(
        workflows={
            "default": {
                "open": ["in_progress"],
                "in_progress": ["review"],
                "review": [],
            }
        }
    )

    assert router_execution._workflow_transition_path(
        configuration, "task", "open", "review"
    ) == ["in_progress", "review"]


def test_run_once_scheduler_branches_and_hard_initial_renewal(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    scheduler = _ClaimHandle("git", "router:scheduler", "owner", "scheduler", None)
    monkeypatch.setattr(router_execution, "_assert_scheduler_claim", lambda *_: None)
    install_run_fakes(monkeypatch, ctx)
    monkeypatch.setattr(
        router_execution,
        "_RENEWAL_ERRORS",
        {"scheduler": "scheduler lease expired"},
    )
    outcome = router_execution.run_router_once(ctx, scheduler_claim_handles=[scheduler])
    assert outcome.error == "scheduler lease expired"
    assert outcome.started == outcome.failed == 1

    ctx = context(tmp_path, providers=["mutex_api"])
    ctx.configuration.coordination.mutex_api = object()
    monkeypatch.setattr(router_execution.uuid, "uuid4", lambda: "hard")
    monkeypatch.setattr(router_execution, "_next_revision", lambda *_: 1)
    monkeypatch.setattr(router_execution, "_acquire_claims", lambda *_a, **_kw: [])
    monkeypatch.setattr(
        router_execution,
        "_start_lease_renewer",
        lambda *_a, **_kw: (SimpleNamespace(set=lambda: None), Thread()),
    )
    monkeypatch.setattr(
        router_execution,
        "_acquire_claims",
        lambda _ctx, _candidate, *, on_handles_updated, **_kw: (
            on_handles_updated(
                [
                    _ClaimHandle(
                        "mutex_api", "router:issue:kbs-42", "owner", "hard", None
                    )
                ]
            )
            or [_ClaimHandle("mutex_api", "router:issue:kbs-42", "owner", "hard", None)]
        ),
    )
    monkeypatch.setattr(router_execution, "_RENEWAL_ERRORS", {"hard": "failed"})
    monkeypatch.setattr(
        router_execution,
        "build_router_plan",
        lambda _ctx: SimpleNamespace(eligible=[candidate()], deferred=[]),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    monkeypatch.setattr(router_execution, "_release_claims", lambda *_: None)
    outcome = router_execution.run_router_once(ctx)
    assert outcome.error == router_execution.HARD_COORDINATION_ERROR
    assert outcome.started == 0


def test_acquire_soft_resource_git_mqtt_fallback_and_mismatch(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    claim_state = SimpleNamespace(operation_event_id="event", operation_sequence=2)
    lease = SimpleNamespace(active=True, owner="worker", claim_id="claim")
    monkeypatch.setattr(router_execution, "soft_claim", lambda *_a, **_kw: claim_state)
    monkeypatch.setattr(router_execution, "inspect_lease", lambda *_a, **_kw: lease)
    monkeypatch.setattr(router_execution, "select_soft_provider", lambda *_: "git")
    handles = []
    router_execution._acquire_router_resource(
        ctx, handles, "router:issue:kbs-42", "worker", "claim", 1, False
    )
    assert handles[0].provider == "git"

    waited = []
    monkeypatch.setattr(
        router_execution, "publish_claim_visibility", lambda *_a, **_kw: False
    )
    monkeypatch.setattr(router_execution, "sleep", waited.append)
    observations = []
    monkeypatch.setattr(
        "kanbus.coordination_mqtt.record_contention_observation",
        lambda *args, **kwargs: observations.append((args[1], kwargs["ttl_s"])),
    )
    handles = []
    router_execution._acquire_router_resource(
        ctx,
        handles,
        "router:issue:kbs-43",
        "worker",
        "claim",
        1,
        False,
        soft_provider="mqtt",
        wait_for_contention=True,
    )
    assert handles[0].provider == "git"
    assert waited == [1]
    assert observations == [("router:issue:kbs-43", 30)]

    monkeypatch.setattr(
        router_execution, "publish_claim_visibility", lambda *_a, **_kw: True
    )
    monkeypatch.setattr(
        "kanbus.coordination_mqtt.inspect_lease", lambda *_a, **_kw: lease
    )
    handles = []
    router_execution._acquire_router_resource(
        ctx,
        handles,
        "router:issue:kbs-44",
        "worker",
        "claim",
        1,
        False,
        soft_provider="mqtt",
    )
    assert handles[0].provider == "mqtt"

    monkeypatch.setattr(
        "kanbus.coordination_mqtt.inspect_lease",
        lambda *_a, **_kw: SimpleNamespace(
            active=False, owner="worker", claim_id="claim"
        ),
    )
    with pytest.raises(IssueRouterError, match="package already claimed"):
        router_execution._acquire_router_resource(
            ctx,
            [],
            "router:issue:kbs-45",
            "worker",
            "claim",
            1,
            False,
            soft_provider="mqtt",
        )


def test_release_claims_skips_stale_and_publishes_mqtt_release(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    stale = _ClaimHandle("git", "router:issue:old", "other", "old", None)
    current = _ClaimHandle("mqtt", "router:issue:kbs-42", "worker", "claim", None)
    monkeypatch.setattr(
        router_execution,
        "_router_soft_lease_is_current",
        lambda _ctx, handle: handle is current,
    )
    releases = []
    monkeypatch.setattr(
        router_execution,
        "soft_release",
        lambda *_a, **kwargs: releases.append(kwargs["resource"]) or "release-id",
    )
    monkeypatch.setattr(router_execution, "utc_now", lambda: datetime.now(UTC))
    monkeypatch.setattr(router_execution, "operation_sequence_for_event", lambda *_: 9)
    visible = []
    monkeypatch.setattr(
        router_execution,
        "publish_release_visibility",
        lambda *_a, **kwargs: visible.append(kwargs["resource"]),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)

    router_execution._release_claims(ctx, [stale, current])

    assert releases == ["router:issue:kbs-42"]
    assert visible == ["router:issue:kbs-42"]


def test_release_claims_reports_api_and_publish_errors(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    hard = _ClaimHandle("mutex_api", "router:issue:kbs-42", "owner", "claim", object())
    monkeypatch.setattr(
        router_execution,
        "mutex_release",
        lambda *_a, **_kw: (_ for _ in ()).throw(MutexApiUnavailable("offline")),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    with pytest.raises(IssueRouterError, match="release failed"):
        router_execution._release_claims(ctx, [hard])

    monkeypatch.setattr(
        router_execution,
        "publish_router_state",
        lambda *_: (_ for _ in ()).throw(IssueRouterError("not writable")),
    )
    with pytest.raises(IssueRouterError, match="release could not be published"):
        router_execution._release_claims(ctx, [hard])


def test_soft_renewer_extends_lease_and_demotes_mqtt_after_publish_failure(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    ctx.configuration.coordination.default_lease_ttl = "30s"

    class ImmediateEvent:
        def __init__(self):
            self.was_set = False

        def set(self):
            self.was_set = True

        def is_set(self):
            return self.was_set

        def wait(self, _timeout=None):
            return True

    class ImmediateThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(router_execution.threading, "Event", ImmediateEvent)
    monkeypatch.setattr(router_execution.threading, "Thread", ImmediateThread)
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(router_execution, "utc_now", lambda: now)
    handle = _ClaimHandle("mqtt", "router:issue:kbs-42", "owner", "claim-a", None)
    lease = SimpleNamespace(
        active=True,
        owner="owner",
        claim_id="claim-a",
        expires_at=now + timedelta(seconds=5),
    )
    monkeypatch.setattr(
        router_execution, "_router_soft_lease_is_current", lambda *_: True
    )
    monkeypatch.setattr(router_execution, "inspect_lease", lambda *_a, **_kw: lease)
    renewed = []
    monkeypatch.setattr(
        router_execution,
        "soft_renew",
        lambda *_a, **kwargs: renewed.append(kwargs["extend"]) or lease,
    )
    monkeypatch.setattr(
        router_execution, "publish_renewal_visibility", lambda *_a, **_kw: False
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)

    stop, _thread = router_execution._start_lease_renewer(
        ctx, [handle], "claim-a", initial_pass=True
    )

    assert renewed == ["25s"]
    assert handle.provider == "git"
    assert not router_execution._RENEWAL_ERRORS.get("claim-a")
    stop.set()


def test_soft_renewer_records_failure_and_cancels_active_adapter(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    ctx.configuration.coordination.default_lease_ttl = "30s"

    class ImmediateEvent:
        def set(self):
            pass

        def is_set(self):
            return False

        def wait(self, _timeout=None):
            return True

    class ImmediateThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    class Adapter:
        def __init__(self):
            self.cancelled = []

        def cancel(self, claim):
            self.cancelled.append(claim)

    monkeypatch.setattr(router_execution.threading, "Event", ImmediateEvent)
    monkeypatch.setattr(router_execution.threading, "Thread", ImmediateThread)
    handle = _ClaimHandle("git", "router:issue:kbs-42", "owner", "claim-a", None)
    lease = SimpleNamespace(
        active=True,
        owner="owner",
        claim_id="claim-a",
        expires_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    monkeypatch.setattr(
        router_execution, "_router_soft_lease_is_current", lambda *_: True
    )
    monkeypatch.setattr(router_execution, "inspect_lease", lambda *_a, **_kw: lease)
    monkeypatch.setattr(
        router_execution,
        "soft_renew",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            router_execution.CoordinationError("renewal failed")
        ),
    )
    events = []
    monkeypatch.setattr(
        router_execution,
        "record_router_event",
        lambda _project, **kw: events.append(kw),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    adapter = Adapter()
    monkeypatch.setitem(
        router_execution._ACTIVE_ADAPTERS, "kbs-42", ("claim-a", adapter)
    )
    stop, _thread = router_execution._start_lease_renewer(
        ctx, [handle], "claim-a", initial_pass=True
    )
    assert router_execution._RENEWAL_ERRORS["claim-a"] == (
        "router coordination lease renewal failed"
    )
    assert adapter.cancelled == ["claim-a"]
    assert events[0]["event_type"] == "router_lease_renewal_failed"
    router_execution._RENEWAL_ERRORS.pop("claim-a", None)
    stop.set()


def test_lease_renewer_cancels_scheduler_work_on_state_publish_failure(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)

    class ImmediateEvent:
        def set(self):
            pass

        def is_set(self):
            return False

        def wait(self, _timeout=None):
            return True

    class ImmediateThread:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    class Adapter:
        def __init__(self):
            self.cancelled = []

        def cancel(self, claim):
            self.cancelled.append(claim)

    monkeypatch.setattr(router_execution.threading, "Event", ImmediateEvent)
    monkeypatch.setattr(router_execution.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(
        router_execution,
        "publish_router_state",
        lambda *_: (_ for _ in ()).throw(IssueRouterError("disk error")),
    )
    monkeypatch.setattr(router_execution, "_signal_registered_adapter", lambda *_: None)
    adapter = Adapter()
    monkeypatch.setitem(
        router_execution._ACTIVE_ADAPTERS, "kbs-42", ("claim-a", adapter)
    )
    records = []
    monkeypatch.setattr(
        router_execution, "record_router_event", lambda _p, **kw: records.append(kw)
    )
    handle = _ClaimHandle("mutex_api", "router:scheduler", "owner", "claim-a", object())
    monkeypatch.setattr(
        router_execution,
        "mutex_inspect",
        lambda *_a, **_kw: SimpleNamespace(
            owner="owner", claim_id="claim-a", revision=1, expires_at=None
        ),
    )
    stop, _thread = router_execution._start_lease_renewer(
        ctx, [handle], "claim-a", initial_pass=True
    )
    assert router_execution._RENEWAL_ERRORS["claim-a"]
    assert adapter.cancelled == ["claim-a"]
    assert records[0]["payload"]["resource"] == "router:state"
    router_execution._RENEWAL_ERRORS.pop("claim-a", None)
    stop.set()


def test_run_once_handles_scheduler_errors_and_revalidates_after_success(
    monkeypatch, tmp_path
):
    scheduler = _ClaimHandle("git", "router:scheduler", "owner", "sched", None)
    ctx = context(tmp_path)
    install_run_fakes(
        monkeypatch,
        ctx,
        adapter_error=IssueRouterError("adapter failed"),
    )
    monkeypatch.setattr(router_execution, "_assert_scheduler_claim", lambda *_: None)
    monkeypatch.setattr(router_execution, "_RENEWAL_ERRORS", {"sched": "lost"})
    outcome = router_execution.run_router_once(ctx, scheduler_claim_handles=[scheduler])
    assert outcome.error == "router scheduler coordination lease renewal failed"

    ctx = context(tmp_path)
    install_run_fakes(monkeypatch, ctx)
    checks = []
    monkeypatch.setattr(
        router_execution, "_assert_scheduler_claim", lambda *_: checks.append(True)
    )
    monkeypatch.setattr(router_execution, "_RENEWAL_ERRORS", {})
    outcome = router_execution.run_router_once(ctx, scheduler_claim_handles=[scheduler])
    assert outcome.completed == 1
    assert len(checks) == 5


def test_validate_router_start_claim_checks_git_mqtt_and_hard_authority(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    durable = SimpleNamespace(active=True, owner="worker", claim_id="claim")
    monkeypatch.setattr(router_execution, "inspect_lease", lambda *_a, **_kw: durable)
    git_handle = _ClaimHandle("git", "router:issue:kbs-42", "worker", "claim", None, 2)
    router_execution._validate_router_start_claim(
        ctx, tmp_path / "shared", "kbs-42", "worker", "claim", 2, git_handle
    )

    monkeypatch.setattr(
        "kanbus.coordination_mqtt.inspect_lease", lambda *_a, **_kw: durable
    )
    mqtt_handle = _ClaimHandle(
        "mqtt", "router:issue:kbs-42", "worker", "claim", None, 2
    )
    router_execution._validate_router_start_claim(
        ctx, tmp_path / "shared", "kbs-42", "worker", "claim", 2, mqtt_handle
    )

    ctx.configuration.coordination.providers = ["mutex_api"]
    ctx.configuration.coordination.mutex_api = object()
    monkeypatch.setattr(
        router_execution,
        "mutex_inspect",
        lambda *_a, **_kw: SimpleNamespace(
            owner="worker", claim_id="claim", revision=2
        ),
    )
    router_execution._validate_router_start_claim(
        ctx, tmp_path / "shared", "kbs-42", "worker", "claim", 2, git_handle
    )

    monkeypatch.setattr(
        router_execution,
        "mutex_inspect",
        lambda *_a, **_kw: (_ for _ in ()).throw(MutexApiUnavailable("offline")),
    )
    with pytest.raises(IssueRouterError, match="hard router coordination"):
        router_execution._validate_router_start_claim(
            ctx, tmp_path / "shared", "kbs-42", "worker", "claim", 2, git_handle
        )


def test_validate_router_start_claim_rejects_stale_or_unavailable_soft_claim(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    handle = _ClaimHandle("git", "router:issue:kbs-42", "worker", "claim", None, 1)
    monkeypatch.setattr(
        router_execution,
        "inspect_lease",
        lambda *_a, **_kw: SimpleNamespace(
            active=False, owner="worker", claim_id="claim"
        ),
    )
    with pytest.raises(IssueRouterError, match="package already claimed"):
        router_execution._validate_router_start_claim(
            ctx, tmp_path, "kbs-42", "worker", "claim", 1, handle
        )

    durable = SimpleNamespace(active=True, owner="worker", claim_id="claim")
    monkeypatch.setattr(router_execution, "inspect_lease", lambda *_a, **_kw: durable)
    monkeypatch.setattr(
        "kanbus.coordination_mqtt.inspect_lease",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            router_execution.CoordinationError("offline")
        ),
    )
    mqtt_handle = _ClaimHandle(
        "mqtt", "router:issue:kbs-42", "worker", "claim", None, 1
    )
    with pytest.raises(IssueRouterError, match="coordination lease unavailable"):
        router_execution._validate_router_start_claim(
            ctx, tmp_path, "kbs-42", "worker", "claim", 1, mqtt_handle
        )


def test_claim_fence_rejects_state_cancel_and_renewal_failures(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    monkeypatch.setattr(
        "kanbus.router_state.router_state_root", lambda *_a, **_kw: tmp_path
    )
    event = {
        "event_type": "router_claimed",
        "payload": {"claim_id": "claim", "revision": 2, "provider_used": "git"},
    }
    monkeypatch.setattr(router_execution, "_assert_current_claim", lambda *_: None)
    monkeypatch.setattr(router_execution, "read_router_events", lambda *_: [event])
    monkeypatch.setattr(router_execution, "_latest_router_event", lambda *_: event)
    monkeypatch.setattr(router_execution, "_read_events", lambda *_: [])
    monkeypatch.setattr(router_execution, "_cancel_was_requested", lambda *_: False)
    monkeypatch.setattr(router_execution, "inspect_lease", lambda *_a, **_kw: object())
    router_execution._assert_claim_fence(ctx, "kbs-42", "claim", 2)

    monkeypatch.setattr(router_execution, "_cancel_was_requested", lambda *_: True)
    with pytest.raises(IssueRouterError, match="run was cancelled"):
        router_execution._assert_claim_fence(ctx, "kbs-42", "claim", 2)
    monkeypatch.setattr(router_execution, "_cancel_was_requested", lambda *_: False)
    monkeypatch.setattr(router_execution, "_RENEWAL_ERRORS", {"claim": "renew failed"})
    with pytest.raises(IssueRouterError, match="renew failed"):
        router_execution._assert_claim_fence(ctx, "kbs-42", "claim", 2)


def test_publish_checkpoint_records_checkpoint_and_artifacts(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    calls = []
    monkeypatch.setattr(
        router_execution, "_assert_claim_fence", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        router_execution,
        "record_router_event",
        lambda _project, **kw: calls.append(kw),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    checkpoint = RouterCheckpoint(ref="refs/kanbus/router/kbs-42/r1", revision=1)
    artifact = RouterArtifact(name="trace", ref="refs/trace/1")
    returned = router_execution._publish_checkpoint(
        ctx,
        candidate(),
        RouterAgentResult(
            schema_version=1,
            outcome="completed",
            checkpoint=checkpoint,
            artifacts=[artifact],
        ),
        "claim",
        1,
    )
    assert returned == checkpoint
    assert [item["event_type"] for item in calls] == [
        "router_checkpoint_accepted",
        "router_artifact_published",
    ]

    with pytest.raises(IssueRouterError, match="stale router revision"):
        router_execution._publish_checkpoint(
            ctx,
            candidate(),
            RouterAgentResult(
                schema_version=1,
                outcome="completed",
                checkpoint=RouterCheckpoint(ref="refs/cp", revision=2),
            ),
            "claim",
            1,
        )


def test_open_pull_request_fake_forge_records_output(monkeypatch, tmp_path):
    from kanbus.router_forge import FakeForge

    forge = FakeForge()
    ctx = context(
        tmp_path, forge=SimpleNamespace(repository="owner/repo", base_branch="main")
    )
    ctx.issues[0].title = "Test issue"
    monkeypatch.setattr(router_execution, "_FAKE_FORGE", forge)
    monkeypatch.setattr(
        router_execution, "_assert_claim_fence", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        router_execution, "record_router_event", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_a: None)
    package = candidate()
    pr = router_execution._open_pull_request(ctx, package, None, "claim", 1)
    assert pr is not None
    assert pr.head_branch == "codex/router/kbs-42/r2"

    ctx.router.forge = None
    assert router_execution._open_pull_request(ctx, package, None, "claim", 1) is None


def test_remote_branch_helpers_and_git_errors(monkeypatch, tmp_path):
    class Completed:
        def __init__(self, returncode=0, stdout="abc refs/heads/branch\n"):
            self.returncode = returncode
            self.stdout = stdout

    responses = iter([Completed(stdout=""), Completed(returncode=2), Completed()])
    monkeypatch.setattr(
        router_execution.subprocess, "run", lambda *_a, **_kw: next(responses)
    )
    assert router_execution._remote_branch_exists(tmp_path, "branch") is False
    assert router_execution._remote_branch_exists(tmp_path, "branch") is False
    assert router_execution._remote_branch_exists(tmp_path, "branch") is True

    responses = iter([Completed(returncode=0), Completed(returncode=1)])
    monkeypatch.setattr(
        router_execution.subprocess, "run", lambda *_a, **_kw: next(responses)
    )
    assert router_execution._local_branch_exists(tmp_path, "branch") is True
    assert router_execution._local_branch_exists(tmp_path, "branch") is False

    monkeypatch.setattr(
        router_execution.subprocess,
        "run",
        lambda *_a, **_kw: (_ for _ in ()).throw(OSError("git missing")),
    )
    with pytest.raises(IssueRouterError, match="isolated worktree operation failed"):
        router_execution._git(tmp_path, ["status"])
    monkeypatch.setattr(
        router_execution.subprocess,
        "run",
        lambda *_a, **_kw: SimpleNamespace(returncode=1, stdout=""),
    )
    with pytest.raises(IssueRouterError, match="current remote ref"):
        router_execution._remote_ref_sha(tmp_path, "refs/heads/x")


def test_validate_worktree_changes_handles_missing_and_invalid_path(
    monkeypatch, tmp_path
):
    monkeypatch.setitem(
        router_execution._WORKTREE_PATHS, "missing", tmp_path / "absent"
    )
    assert router_execution._validate_worktree_changes("board", "missing") is None
    existing = tmp_path / "worktree"
    existing.mkdir()
    monkeypatch.setitem(router_execution._WORKTREE_PATHS, "claim", existing)
    with pytest.raises(IssueRouterError, match="repository-relative"):
        router_execution._validate_worktree_changes("../board", "claim")
    with pytest.raises(IssueRouterError, match="repository-relative"):
        router_execution._validate_worktree_changes("/absolute/board", "claim")


def test_watch_stops_cleanly_when_control_requests_stop(monkeypatch, tmp_path):
    ctx = context(tmp_path)

    class Control:
        stop_requested = True

        def model_copy(self, update):
            return SimpleNamespace(**update)

    ctx.control = Control()
    listener = Listener()
    scheduler = _ClaimHandle("git", "router:scheduler", "owner", "sched", None)
    state_writes = []
    events = []
    releases = []
    monkeypatch.setattr(router_execution, "start_soft_listener", lambda *_: listener)
    monkeypatch.setattr(
        router_execution,
        "_acquire_watch_scheduler_claim",
        lambda *_a, **_kw: ([scheduler], "sched"),
    )
    monkeypatch.setattr(
        router_execution,
        "_start_lease_renewer",
        lambda *_a, **_kw: (
            SimpleNamespace(set=lambda: state_writes.append("stopped")),
            Thread(),
        ),
    )
    monkeypatch.setattr("kanbus.router_state.router_state_root", lambda *_a: tmp_path)
    monkeypatch.setattr(router_execution, "load_router_context", lambda *_: ctx)
    monkeypatch.setattr(
        router_execution,
        "write_router_control",
        lambda _root, state: state_writes.append(state),
    )
    monkeypatch.setattr(
        router_execution,
        "record_router_event",
        lambda _project, **kw: events.append(kw["event_type"]),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    monkeypatch.setattr(
        router_execution,
        "_release_claims",
        lambda _ctx, handles: releases.extend(handles),
    )

    router_execution.run_router_watch(ctx)

    assert events == ["router_started", "router_stopped"]
    assert len(releases) == 1
    assert listener.stopped == 1
    assert state_writes[0].running is True
    assert state_writes[-1].running is False


@pytest.mark.parametrize(
    ("loop_error", "expected"),
    [
        (None, None),
        (
            router_execution.IssueRouterError("scheduler coordination lease lost"),
            "scheduler coordination lease lost",
        ),
    ],
)
def test_watch_waits_after_reconciliation_and_surfaces_lease_error(
    monkeypatch, tmp_path, loop_error, expected
):
    ctx = context(tmp_path)

    class Control:
        stop_requested = False

        def model_copy(self, update):
            return SimpleNamespace(**update)

    ctx.control = Control()
    loads = []

    def load(_root):
        loads.append(True)
        ctx.control.stop_requested = len(loads) > 1
        return ctx

    listener = Listener()
    scheduler = _ClaimHandle("git", "router:scheduler", "owner", "sched", None)
    waited = []
    monkeypatch.setattr(router_execution, "start_soft_listener", lambda *_: listener)
    monkeypatch.setattr(
        router_execution,
        "_acquire_watch_scheduler_claim",
        lambda *_a, **_kw: ([scheduler], "sched"),
    )
    monkeypatch.setattr(
        router_execution,
        "_start_lease_renewer",
        lambda *_a, **_kw: (SimpleNamespace(set=lambda: None), Thread()),
    )
    monkeypatch.setattr("kanbus.router_state.router_state_root", lambda *_a: tmp_path)
    monkeypatch.setattr(router_execution, "load_router_context", load)
    monkeypatch.setattr(router_execution, "write_router_control", lambda *_: None)
    monkeypatch.setattr(
        router_execution, "record_router_event", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    monkeypatch.setattr(router_execution, "_release_claims", lambda *_: None)
    monkeypatch.setattr(router_execution, "_assert_scheduler_claim", lambda *_: None)
    monkeypatch.setattr(router_execution, "_reconcile_pull_requests", lambda *_: None)
    monkeypatch.setattr(
        router_execution,
        "run_router_once",
        lambda *_a, **_kw: router_execution.RouterRunResult(
            error=str(loop_error) if loop_error else None
        ),
    )
    monkeypatch.setattr(
        router_execution,
        "_wait_for_watch_trigger",
        lambda *_: waited.append(True) or False,
    )

    if expected:
        with pytest.raises(IssueRouterError, match="scheduler coordination lease lost"):
            router_execution.run_router_watch(ctx)
    else:
        router_execution.run_router_watch(ctx)
    assert bool(waited) is (expected is None)
    assert listener.stopped == 1


def test_wait_for_watch_trigger_polls_without_listener(monkeypatch):
    ticks = iter([1.0, 1.1, 2.0])
    sleeps = []
    monkeypatch.setattr(router_execution, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(router_execution, "sleep", sleeps.append)
    assert router_execution._wait_for_watch_trigger(None, 1) is False
    assert sleeps == [pytest.approx(0.25)]


def test_run_once_stops_partial_hard_renewal_handles(monkeypatch, tmp_path):
    ctx = context(tmp_path, providers=["mutex_api"])
    ctx.configuration.coordination.mutex_api = object()
    monkeypatch.setattr(router_execution, "uuid", SimpleNamespace(uuid4=lambda: "hard"))
    monkeypatch.setattr(router_execution, "start_soft_listener", lambda *_: None)
    monkeypatch.setattr(
        router_execution,
        "build_router_plan",
        lambda *_: SimpleNamespace(eligible=[candidate()], deferred=[]),
    )
    monkeypatch.setattr(router_execution, "_next_revision", lambda *_: 1)
    thread = Thread()
    stop = SimpleNamespace(set=lambda: None)
    monkeypatch.setattr(
        router_execution,
        "_start_lease_renewer",
        lambda *_a, **_kw: (stop, thread),
    )
    handle = _ClaimHandle("mutex_api", "router:issue:kbs-42", "owner", "hard", None)

    def acquire(_ctx, _candidate, *, on_handles_updated, **_kwargs):
        on_handles_updated([handle])
        on_handles_updated([])
        raise IssueRouterError("capacity full")

    monkeypatch.setattr(router_execution, "_acquire_claims", acquire)
    monkeypatch.setattr(router_execution, "_RENEWAL_ERRORS", {})
    monkeypatch.setattr(router_execution, "_release_claims", lambda *_: None)
    outcome = router_execution.run_router_once(ctx)
    assert outcome.error == "capacity full"
    assert thread.joined == [None, 2]


def test_run_watch_aborts_on_scheduler_renewal_error(monkeypatch, tmp_path):
    ctx = context(tmp_path)

    class Control:
        stop_requested = False

        def model_copy(self, update):
            return SimpleNamespace(**update)

    ctx.control = Control()
    monkeypatch.setattr(router_execution.uuid, "uuid4", lambda: "watch-id")
    monkeypatch.setattr(router_execution, "start_soft_listener", lambda *_: None)
    handle = _ClaimHandle("git", "router:scheduler", "owner", "watch-id", None)
    monkeypatch.setattr(
        router_execution,
        "_acquire_watch_scheduler_claim",
        lambda *_a, **_kw: ([handle], "watch-id"),
    )
    monkeypatch.setattr(
        router_execution,
        "_start_lease_renewer",
        lambda *_a, **_kw: (SimpleNamespace(set=lambda: None), Thread()),
    )
    monkeypatch.setattr(router_execution, "_RENEWAL_ERRORS", {"watch-id": "lost"})
    monkeypatch.setattr("kanbus.router_state.router_state_root", lambda *_a: tmp_path)
    monkeypatch.setattr(router_execution, "load_router_context", lambda *_: ctx)
    monkeypatch.setattr(router_execution, "write_router_control", lambda *_: None)
    monkeypatch.setattr(
        router_execution, "record_router_event", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    monkeypatch.setattr(router_execution, "_release_claims", lambda *_: None)
    with pytest.raises(IssueRouterError, match="lost"):
        router_execution.run_router_watch(ctx)


def test_run_adapter_default_adapter_executes_and_commits_result(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    package = candidate()
    result_value = result("completed")
    active = SimpleNamespace(
        execute=lambda request: result_value,
        cancel=lambda _claim: None,
    )
    monkeypatch.delitem(router_execution._ADAPTER_OVERRIDES, "codex", raising=False)
    monkeypatch.setitem(router_execution._WORKTREE_PATHS, "claim-run", tmp_path / "old")
    monkeypatch.setitem(router_execution._WORKTREE_BRANCHES, "claim-run", "old-branch")
    monkeypatch.setitem(router_execution._WORKTREE_HEADS, "claim-run", "old-head")
    monkeypatch.setattr(
        router_execution,
        "CodexExecAdapter",
        lambda _profile, **_kwargs: active,
    )
    monkeypatch.setattr(router_execution, "read_router_events", lambda *_: [])
    monkeypatch.setattr(
        router_execution, "_existing_pull_request_branch", lambda *_: None
    )
    worktree = tmp_path / "worktree"
    monkeypatch.setattr(
        router_execution, "_create_isolated_worktree", lambda *_a, **_kw: worktree
    )
    monkeypatch.setattr(router_execution, "_validate_worktree_changes", lambda *_: None)
    commits = []
    monkeypatch.setattr(
        router_execution,
        "_commit_isolated_worktree",
        lambda *args: commits.append(args),
    )
    monkeypatch.setattr(router_execution, "_git", lambda *_: "head-sha")

    returned = router_execution._run_adapter(ctx, package, "claim-run", 3)

    assert returned is result_value
    assert commits == [(worktree, "board", "kbs-42", 3)]
    assert router_execution._WORKTREE_HEADS["claim-run"] == "head-sha"
    assert "kbs-42" not in router_execution._ACTIVE_ADAPTERS


def test_run_adapter_records_a_blocked_turn_as_awaiting_human_reply(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    package = candidate()
    result_value = result("blocked", "Which deployment target should I use?")
    active = SimpleNamespace(
        execute=lambda request: result_value,
        cancel=lambda _claim: None,
        session_id="session-42",
        last_output="agent question",
        last_error="",
    )
    monkeypatch.delitem(router_execution._ADAPTER_OVERRIDES, "codex", raising=False)
    monkeypatch.setattr(router_execution, "CodexExecAdapter", lambda *_a, **_kw: active)
    monkeypatch.setattr(
        router_execution,
        "_adapter_process_record_path",
        lambda *_a: tmp_path / "adapter-process.json",
    )
    monkeypatch.setattr(router_execution, "read_router_events", lambda *_: [])
    monkeypatch.setattr(
        router_execution, "_existing_pull_request_branch", lambda *_: None
    )
    monkeypatch.setattr(
        router_execution,
        "_create_isolated_worktree",
        lambda *_a, **_kw: tmp_path / "worktree",
    )
    monkeypatch.setattr(router_execution, "_validate_worktree_changes", lambda *_: None)
    conversations = []
    monkeypatch.setattr(
        router_execution,
        "record_conversation",
        lambda _project, _package, **payload: conversations.append(payload),
    )

    returned = router_execution._run_adapter(ctx, package, "claim-blocked", 3)

    assert returned is result_value
    assert conversations[-1]["lifecycle"] == "blocked"
    assert conversations[-1]["session_id"] == "session-42"
    assert conversations[-1]["message"] == "Which deployment target should I use?"


def test_create_worktree_fetches_existing_remote_branch(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    commands = []
    monkeypatch.setattr(
        router_execution,
        "_git",
        lambda _root, args: commands.append(args) or ".git/kanbus/router/worktrees",
    )
    monkeypatch.setattr(router_execution, "_detach_previous_worktree", lambda *_: None)
    monkeypatch.setattr(router_execution, "_remote_branch_exists", lambda *_: True)

    path = router_execution._create_isolated_worktree(
        ctx, "kbs-42", "claim", 4, branch="codex/router/kbs-42/r4"
    )

    assert path == tmp_path / ".git/kanbus/router/worktrees/kbs-42-claim"
    assert commands[1][0:2] == ["fetch", "origin"]
    assert commands[2][:2] == ["branch", "-f"]
    assert commands[3][:2] == ["worktree", "add"]


def test_worktree_snapshot_cleans_private_index_on_failure(monkeypatch, tmp_path):
    metadata = tmp_path / "metadata"
    metadata.mkdir()

    class Failed:
        returncode = 1
        stdout = ""

    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1:4] == ["rev-parse", "--verify", "HEAD"]:
            return Failed()
        raise router_execution.subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(router_execution.subprocess, "run", run)
    with pytest.raises(IssueRouterError, match="prepare an isolated worktree"):
        router_execution._worktree_base_commit(tmp_path, metadata)
    assert len(calls) == 2
    assert not list(metadata.glob("snapshot-*.index"))


def test_publish_checkpoint_rolls_back_when_fence_is_lost(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    checkpoint = RouterCheckpoint(ref="refs/kanbus/router/kbs-42/r1", revision=1)
    monkeypatch.setitem(router_execution._WORKTREE_HEADS, "claim", "published")
    monkeypatch.setattr(
        router_execution, "_update_checkpoint_ref", lambda *_: "previous"
    )
    fence_calls = []

    def fence(*_args, **_kwargs):
        fence_calls.append(True)
        if len(fence_calls) == 2:
            raise IssueRouterError("stale")

    monkeypatch.setattr(router_execution, "_assert_claim_fence", fence)
    restored = []
    monkeypatch.setattr(
        router_execution,
        "_restore_checkpoint_ref",
        lambda *args: restored.append(args),
    )
    with pytest.raises(IssueRouterError, match="stale"):
        router_execution._publish_checkpoint(
            ctx,
            candidate(),
            RouterAgentResult(
                schema_version=1, outcome="completed", checkpoint=checkpoint
            ),
            "claim",
            1,
        )
    assert restored == [(tmp_path, checkpoint.ref, "published", "previous")]


def test_result_scope_reports_unknown_issue_and_router_owned_status(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    update_result = RouterAgentResult(
        schema_version=1,
        outcome="completed",
        issue_updates=[{"issue_id": "kbs-43", "status": "active"}],
    )
    with pytest.raises(IssueRouterError, match="outside router package"):
        router_execution._validate_result_scope(ctx, candidate(), update_result)

    ctx.issues[0].labels = ["agent-provider:codex"]
    missing_issue_candidate = candidate()
    missing_issue_candidate.package_issue_ids = ["kbs-42", "missing"]
    with pytest.raises(
        IssueRouterError, match="issue missing is outside router package"
    ):
        router_execution._validate_result_scope(
            ctx,
            missing_issue_candidate,
            RouterAgentResult(
                schema_version=1,
                outcome="completed",
                issue_updates=[{"issue_id": "missing", "status": "active"}],
            ),
        )

    monkeypatch.setattr("kanbus.workflows.validate_status_value", lambda *_: None)
    monkeypatch.setattr("kanbus.workflows.validate_status_transition", lambda *_: None)
    with pytest.raises(IssueRouterError, match="cannot transition"):
        router_execution._validate_result_scope(
            ctx,
            candidate(),
            RouterAgentResult(
                schema_version=1,
                outcome="completed",
                issue_updates=[{"issue_id": "kbs-42", "status": "review"}],
            ),
        )


def test_router_persists_only_in_package_issue_comments(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    candidate_ = candidate()
    result_ = RouterAgentResult(
        schema_version=1,
        outcome="completed",
        issue_comments=[
            RouterIssueComment(issue_id="kbs-42", text="Three paragraphs follow.")
        ],
    )
    source_root = tmp_path / "source-checkout"
    source_root.mkdir()
    comments = []
    fences = []
    monkeypatch.setattr(
        router_execution,
        "_assert_claim_fence",
        lambda *_args: fences.append(True),
    )
    monkeypatch.setattr(
        router_execution,
        "add_issue_comment",
        lambda root, issue_id, author, text: comments.append(
            (root, issue_id, author, text)
        ),
    )

    router_execution._validate_result_scope(ctx, candidate_, result_)
    ctx = ctx.__class__(
        root=ctx.root,
        project_dir=ctx.project_dir,
        configuration=ctx.configuration,
        router=ctx.router,
        issues=ctx.issues,
        control=ctx.control,
        source_root=source_root,
    )
    router_execution._apply_issue_comments(ctx, candidate_, result_, "claim", 1)

    assert comments == [
        (source_root, "kbs-42", "Kanbus Issue Router", "Three paragraphs follow.")
    ]
    assert fences == [True]


def test_router_rejects_blank_and_out_of_package_issue_comments(tmp_path):
    ctx = context(tmp_path)
    with pytest.raises(IssueRouterError, match="outside router package"):
        router_execution._validate_result_scope(
            ctx,
            candidate(),
            RouterAgentResult(
                schema_version=1,
                outcome="completed",
                issue_comments=[
                    {"issue_id": "kbs-outside", "text": "Not in this package."}
                ],
            ),
        )

    with pytest.raises(IssueRouterError, match="must not be blank"):
        router_execution._validate_result_scope(
            ctx,
            candidate(),
            RouterAgentResult(
                schema_version=1,
                outcome="completed",
                issue_comments=[{"issue_id": "kbs-42", "text": "  \n"}],
            ),
        )


def test_acquire_claims_requires_mutex_configuration_and_preserves_other_errors(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path, providers=["mutex_api"])
    candidate_ = candidate()
    monkeypatch.setattr(router_execution, "mutex_is_configured", lambda _cfg: False)
    with pytest.raises(IssueRouterError, match="hard router coordination"):
        router_execution._acquire_claims(
            ctx, candidate_, claim_id="claim", revision=1, owner="worker"
        )

    ctx = context(tmp_path)
    ctx.router.limits.project_wip = 1
    monkeypatch.setattr(
        router_execution,
        "_acquire_router_resource",
        lambda _ctx, handles, resource, *_a, **_kw: (
            handles.append(_ClaimHandle("git", resource, "worker", "claim", None))
            if not resource.startswith("router:capacity:")
            else (_ for _ in ()).throw(IssueRouterError("bad provider"))
        ),
    )
    monkeypatch.setattr(
        router_execution,
        "_release_claims",
        lambda *_: (_ for _ in ()).throw(IssueRouterError("release failed")),
    )
    with pytest.raises(IssueRouterError, match="release failed"):
        router_execution._acquire_claims(
            ctx, candidate_, claim_id="claim", revision=1, owner="worker"
        )


def test_hard_acquire_contention_capacity_path(monkeypatch, tmp_path):
    ctx = context(tmp_path, providers=["mutex_api"])
    ctx.configuration.coordination.mutex_api = object()
    monkeypatch.setattr(router_execution, "mutex_is_configured", lambda _cfg: True)
    monkeypatch.setattr(
        router_execution,
        "mutex_acquire",
        lambda *_a, **_kw: (_ for _ in ()).throw(MutexApiError("busy", status=409)),
    )
    with pytest.raises(IssueRouterError, match="package already claimed"):
        router_execution._acquire_router_resource(
            ctx,
            [],
            "router:capacity:project:0",
            "worker",
            "claim",
            1,
            True,
            allow_contention=True,
        )


def test_scheduler_claim_rejects_stale_mqtt_and_mutex_leases(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    monkeypatch.setattr(
        "kanbus.router_state.router_state_root", lambda *_a, **_kw: tmp_path
    )
    monkeypatch.setattr(
        "kanbus.coordination_mqtt.inspect_lease",
        lambda *_a, **_kw: SimpleNamespace(
            active=False, owner="someone", claim_id="other", revision=2
        ),
    )
    mqtt = _ClaimHandle("mqtt", "router:scheduler", "owner", "claim", None, 1)
    with pytest.raises(IssueRouterError, match="stale router scheduler claim"):
        router_execution._assert_scheduler_claim(ctx, [mqtt])

    monkeypatch.setattr(
        router_execution,
        "mutex_inspect",
        lambda *_a, **_kw: SimpleNamespace(
            owner="someone", claim_id="other", revision=2
        ),
    )
    mutex = _ClaimHandle("mutex_api", "router:scheduler", "owner", "claim", object(), 1)
    with pytest.raises(IssueRouterError, match="stale router scheduler claim"):
        router_execution._assert_scheduler_claim(ctx, [mutex])


def test_release_claims_ignores_lost_owner_during_soft_release(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    handle = _ClaimHandle("git", "router:issue:kbs-42", "owner", "claim", None)
    checks = iter([True, False])
    monkeypatch.setattr(
        router_execution, "_router_soft_lease_is_current", lambda *_: next(checks)
    )
    monkeypatch.setattr(
        router_execution,
        "soft_release",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            router_execution.CoordinationError("lease owner mismatch")
        ),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    router_execution._release_claims(ctx, [handle])


def test_validate_hard_start_rejects_mismatched_revision(monkeypatch, tmp_path):
    ctx = context(tmp_path, providers=["mutex_api"])
    ctx.configuration.coordination.mutex_api = object()
    monkeypatch.setattr(
        router_execution,
        "inspect_lease",
        lambda *_a, **_kw: SimpleNamespace(
            active=True, owner="worker", claim_id="claim"
        ),
    )
    monkeypatch.setattr(
        router_execution,
        "mutex_inspect",
        lambda *_a, **_kw: SimpleNamespace(
            owner="worker", claim_id="claim", revision=1
        ),
    )
    handle = _ClaimHandle(
        "mutex_api", "router:issue:kbs-42", "worker", "claim", object(), 2
    )
    with pytest.raises(IssueRouterError, match="package already claimed"):
        router_execution._validate_router_start_claim(
            ctx, tmp_path, "kbs-42", "worker", "claim", 2, handle
        )


def test_assert_claim_fence_maps_refresh_and_provider_failures(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    monkeypatch.setattr(
        "kanbus.router_state.router_state_root",
        lambda *_a, **_kw: (_ for _ in ()).throw(IssueRouterError("bad state")),
    )
    with pytest.raises(IssueRouterError, match="no package mutation is safe"):
        router_execution._assert_claim_fence(ctx, "kbs-42", "claim", 1)

    event = {
        "event_type": "router_claimed",
        "payload": {"claim_id": "claim", "revision": 1, "provider_used": "git"},
    }
    monkeypatch.setattr(
        "kanbus.router_state.router_state_root", lambda *_a, **_kw: tmp_path
    )
    monkeypatch.setattr(router_execution, "_assert_current_claim", lambda *_: None)
    monkeypatch.setattr(router_execution, "read_router_events", lambda *_: [event])
    monkeypatch.setattr(router_execution, "_latest_router_event", lambda *_: event)
    monkeypatch.setattr(router_execution, "_cancel_was_requested", lambda *_: False)
    monkeypatch.setattr(
        router_execution,
        "inspect_lease",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            router_execution.CoordinationError("offline")
        ),
    )
    monkeypatch.setattr(
        router_execution,
        "_read_events",
        lambda *_: [
            {"issue_id": "router:issue:kbs-42", "event_type": "coordination.claim"}
        ],
    )
    with pytest.raises(IssueRouterError, match="coordination lease unavailable"):
        router_execution._assert_claim_fence(ctx, "kbs-42", "claim", 1)

    ctx.configuration.coordination.providers = ["mutex_api"]
    ctx.configuration.coordination.mutex_api = object()
    monkeypatch.setattr(
        router_execution,
        "mutex_inspect",
        lambda *_a, **_kw: (_ for _ in ()).throw(MutexApiUnavailable("offline")),
    )
    with pytest.raises(IssueRouterError, match="hard router coordination"):
        router_execution._assert_claim_fence(ctx, "kbs-42", "claim", 1)


def test_assert_claim_fence_checks_mqtt_lease_and_detects_stale_claim(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    event = {
        "event_type": "router_claimed",
        "payload": {"claim_id": "claim", "revision": 1, "provider_used": "mqtt"},
    }
    monkeypatch.setattr(
        "kanbus.router_state.router_state_root", lambda *_a, **_kw: tmp_path
    )
    monkeypatch.setattr(router_execution, "_assert_current_claim", lambda *_: None)
    monkeypatch.setattr(router_execution, "read_router_events", lambda *_: [event])
    monkeypatch.setattr(router_execution, "_latest_router_event", lambda *_: event)
    monkeypatch.setattr(router_execution, "_cancel_was_requested", lambda *_: False)
    monkeypatch.setattr(
        "kanbus.coordination_mqtt.inspect_lease",
        lambda *_a, **_kw: SimpleNamespace(active=True, claim_id="other"),
    )
    monkeypatch.setattr(
        router_execution,
        "_read_events",
        lambda *_: [
            {"issue_id": "router:issue:kbs-42", "event_type": "coordination.claim"}
        ],
    )
    with pytest.raises(IssueRouterError, match="stale router claim"):
        router_execution._assert_claim_fence(ctx, "kbs-42", "claim", 1)


def test_signal_registered_adapter_uses_pidfd_when_available(monkeypatch, tmp_path):
    record = tmp_path / "process.json"
    record.write_text(
        '{"schema_version":2,"package_id":"kbs-42","claim_id":"claim",'
        '"pid":42,"process_identity":"stable"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        router_execution, "_adapter_process_record_path", lambda *_: record
    )
    monkeypatch.setattr(router_execution, "_process_identity", lambda _pid: "stable")
    opened = []
    sent = []
    closed = []
    monkeypatch.setattr(
        router_execution.os,
        "pidfd_open",
        lambda pid: opened.append(pid) or 7,
        raising=False,
    )
    monkeypatch.setattr(
        router_execution.signal,
        "pidfd_send_signal",
        lambda fd, sig: sent.append((fd, sig)),
        raising=False,
    )
    monkeypatch.setattr(router_execution.os, "close", closed.append)
    router_execution._signal_registered_adapter(tmp_path, "kbs-42", "claim")
    assert opened == [42]
    assert sent == [(7, router_execution.signal.SIGTERM)]
    assert closed == [7]


def test_latest_review_ignores_stale_and_unsupported_reviews():
    assert (
        router_execution._latest_relevant_review(
            [
                {"commit_id": "old", "state": "APPROVED", "id": 1},
                {"commit_id": "head", "state": "COMMENTED", "id": 2},
                {"commit_id": None, "state": "APPROVED", "id": 3},
            ],
            "head",
        )["id"]
        == 3
    )


def test_reconcile_pull_requests_handles_closed_merged_synchronized_and_bad_checks(
    monkeypatch, tmp_path
):
    class Forge:
        def observe_pull_request(self, number):
            return {
                1: {"state": "closed", "head_sha": "closed-sha", "merged": False},
                2: {"state": "open", "head_sha": "old-sha", "merged": True},
                3: {"state": "open", "head_sha": "new-sha", "merged": False},
            }[number]

        def list_pull_request_reviews(self, number):
            return [{"commit_id": "old-sha", "state": "COMMENTED", "id": 1}]

        def list_check_runs(self, _number, _sha):
            return [
                {"id": 1, "status": "in_progress", "conclusion": None},
                {"id": 2, "status": "completed", "conclusion": "neutral"},
                {
                    "id": 3,
                    "status": "completed",
                    "conclusion": "failure",
                    "head_sha": "old-sha",
                },
                {"id": True, "status": "completed", "conclusion": "success"},
                {
                    "id": 5,
                    "name": "tests",
                    "status": "completed",
                    "conclusion": "success",
                },
            ]

    ctx = context(tmp_path, forge=SimpleNamespace(repository="owner/repo"))
    monkeypatch.setattr(router_execution, "_FAKE_FORGE", Forge())
    monkeypatch.setattr(
        router_execution,
        "_read_events",
        lambda *_: [
            {"event_type": "router_pull_request_opened", "payload": {"number": 0}},
            {"event_type": "router_pull_request_opened", "payload": {"number": 1}},
            {
                "event_type": "router_pull_request_opened",
                "payload": {"number": 2, "head_sha": "old-sha"},
            },
            {
                "event_type": "router_pull_request_opened",
                "payload": {"number": 3, "head_sha": "old-sha"},
            },
        ],
    )
    pull_events = []
    check_events = []

    def record_pull(_project, _router, payload, *, before_mutation):
        before_mutation()
        pull_events.append(payload)

    def record_check(_project, _router, payload, *, before_mutation):
        before_mutation()
        check_events.append(payload)

    monkeypatch.setattr(
        router_execution, "record_github_pull_request_event", record_pull
    )
    monkeypatch.setattr(router_execution, "record_github_check_run_event", record_check)

    router_execution._reconcile_pull_requests(ctx)

    assert [event["action"] for event in pull_events] == ["closed", "synchronize"]
    assert len(check_events) == 1
    assert check_events[0]["event_id"] == "check-run:5:new-sha"


def test_existing_pull_request_branch_supports_new_and_legacy_payloads(
    monkeypatch, tmp_path
):
    events = [
        {"event_type": "router_pull_request_opened", "payload": {"branch": ""}},
        {
            "event_type": "router_pull_request_opened",
            "payload": {"head_branch": "legacy/branch"},
        },
    ]
    monkeypatch.setattr(router_execution, "read_router_events", lambda *_: events)
    monkeypatch.setattr(
        router_execution,
        "_latest_router_event",
        lambda _events, _package, _kind: events[1],
    )
    assert (
        router_execution._existing_pull_request_branch(tmp_path, "kbs-42")
        == "legacy/branch"
    )
    monkeypatch.setattr(
        router_execution,
        "_latest_router_event",
        lambda *_: {"payload": {"branch": 9, "head_branch": ""}},
    )
    assert router_execution._existing_pull_request_branch(tmp_path, "kbs-42") is None


def test_restore_stale_pull_request_branch_returns_false_on_git_failure(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        router_execution.subprocess,
        "run",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            router_execution.subprocess.CalledProcessError(1, ["git", "push"])
        ),
    )
    assert not router_execution._restore_stale_pull_request_branch(
        tmp_path, "refs/heads/router", "stale", None
    )


def test_worktree_change_inspection_and_checkpoint_commit_failures(
    monkeypatch, tmp_path
):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    monkeypatch.setitem(router_execution._WORKTREE_PATHS, "claim", worktree)
    monkeypatch.setattr(
        router_execution.subprocess,
        "run",
        lambda *_a, **_kw: SimpleNamespace(stdout=b" M src/app.py\\0"),
    )
    assert router_execution._validate_worktree_changes("board", "claim") is None

    monkeypatch.setattr(
        router_execution.subprocess,
        "run",
        lambda *_a, **_kw: (_ for _ in ()).throw(OSError("git unavailable")),
    )
    with pytest.raises(IssueRouterError, match="inspect isolated worktree changes"):
        router_execution._validate_worktree_changes("board", "claim")

    monkeypatch.setattr(router_execution, "_git", lambda *_: " M change.txt")
    calls = []

    def fail_commit(args, **kwargs):
        calls.append(args)
        if "commit" in args:
            raise router_execution.subprocess.CalledProcessError(1, args)
        return SimpleNamespace(returncode=0, stdout=b"")

    monkeypatch.setattr(router_execution.subprocess, "run", fail_commit)
    with pytest.raises(IssueRouterError, match="create an isolated checkpoint"):
        router_execution._commit_isolated_worktree(worktree, "project", "kbs-42", 3)
    assert calls[0][1:4] == ["add", "-u", "--"]


def test_update_checkpoint_ref_validates_namespace_and_rolls_back_failed_push(
    monkeypatch, tmp_path
):
    with pytest.raises(IssueRouterError, match="outside the Kanbus namespace"):
        router_execution._update_checkpoint_ref(tmp_path, "refs/heads/nope", "new")

    monkeypatch.setattr(router_execution, "_remote_ref_sha", lambda *_: "old")
    calls = []

    def fail_push(args, **kwargs):
        calls.append(args)
        if args[1] == "push":
            raise router_execution.subprocess.CalledProcessError(1, args)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(router_execution.subprocess, "run", fail_push)
    with pytest.raises(IssueRouterError, match="publish checkpoint ref"):
        router_execution._update_checkpoint_ref(
            tmp_path, "refs/kanbus/router/kbs-42/r1", "new"
        )
    assert calls[-1][:4] == ["git", "update-ref", "refs/kanbus/router/kbs-42/r1", "old"]


@pytest.mark.parametrize(
    ("previous", "remote", "expected_target"),
    [
        (
            None,
            False,
            ["update-ref", "-d", "refs/kanbus/router/kbs-42/r1", "published"],
        ),
        (
            "old",
            True,
            ["update-ref", "refs/kanbus/router/kbs-42/r1", "old", "published"],
        ),
    ],
)
def test_restore_checkpoint_ref_uses_compare_and_swap(
    monkeypatch, tmp_path, previous, remote, expected_target
):
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        if args[1:3] == ["remote", "get-url"]:
            return SimpleNamespace(returncode=0 if remote else 1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(router_execution.subprocess, "run", run)
    router_execution._restore_checkpoint_ref(
        tmp_path,
        "refs/kanbus/router/kbs-42/r1",
        "published",
        previous,
    )
    assert ["git", *expected_target] in calls
    if remote:
        assert any(args[1] == "push" for args in calls)


def test_apply_issue_updates_rejects_unknown_package_issue(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    candidate_ = candidate()
    candidate_.package_issue_ids = ["kbs-42", "ghost"]
    result_value = RouterAgentResult(
        schema_version=1,
        outcome="completed",
        issue_updates=[{"issue_id": "ghost", "status": "active"}],
    )
    with pytest.raises(IssueRouterError, match="issue ghost is outside router package"):
        router_execution._apply_issue_updates(ctx, candidate_, result_value, "claim", 1)


def test_result_scope_runs_workflow_validators_for_allowed_transition(
    monkeypatch, tmp_path
):
    ctx = context(tmp_path)
    validated = []
    monkeypatch.setattr(
        "kanbus.workflows.validate_status_value",
        lambda *_args: validated.append("value"),
    )
    monkeypatch.setattr(
        "kanbus.workflows.validate_status_transition",
        lambda *_args: validated.append("transition"),
    )
    router_execution._validate_result_scope(
        ctx,
        candidate(),
        RouterAgentResult(
            schema_version=1,
            outcome="completed",
            issue_updates=[{"issue_id": "kbs-42", "status": "active"}],
        ),
    )
    assert validated == ["value", "transition"]


def test_update_checkpoint_ref_without_remote_uses_local_ref_and_removes_on_error(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(router_execution, "_local_ref_sha", lambda *_: None)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1:4] == ["remote", "get-url", "origin"]:
            return SimpleNamespace(returncode=1, stdout="")
        if args[1] == "update-ref" and len(calls) == 2:
            raise router_execution.subprocess.CalledProcessError(1, args)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(router_execution.subprocess, "run", run)
    with pytest.raises(IssueRouterError, match="publish checkpoint ref"):
        router_execution._update_checkpoint_ref(
            tmp_path, "refs/kanbus/router/kbs-42/r1", "new"
        )
    assert ["git", "update-ref", "-d", "refs/kanbus/router/kbs-42/r1"] in calls


def test_open_pull_request_maps_git_push_failure(monkeypatch, tmp_path):
    from kanbus.router_forge import GitHubForge

    ctx = context(
        tmp_path, forge=SimpleNamespace(repository="owner/repo", base_branch="main")
    )
    forge = GitHubForge(repository="owner/repo", token="test")
    monkeypatch.setattr(router_execution, "_FAKE_FORGE", forge)
    monkeypatch.setattr(router_execution, "_assert_claim_fence", lambda *_: None)
    monkeypatch.setattr(router_execution, "_remote_ref_sha", lambda *_: None)
    monkeypatch.setitem(router_execution._WORKTREE_HEADS, "claim", "published")
    monkeypatch.setitem(
        router_execution._WORKTREE_BRANCHES, "claim", "codex/router/kbs-42/r2"
    )
    monkeypatch.setattr(
        router_execution.subprocess,
        "run",
        lambda *_a, **_kw: (_ for _ in ()).throw(OSError("push unavailable")),
    )
    with pytest.raises(IssueRouterError, match="publish branch to GitHub"):
        router_execution._open_pull_request(ctx, candidate(), None, "claim", 2)


@pytest.mark.parametrize(
    ("fail_at", "restore_ok", "message"),
    [
        (2, True, "stale package claim"),
        (6, False, "could not safely roll back"),
    ],
)
def test_open_pull_request_rolls_back_if_claim_is_lost(
    monkeypatch, tmp_path, fail_at, restore_ok, message
):
    from kanbus.router_forge import ForgePullRequest, GitHubForge

    class Forge(GitHubForge):
        def create_or_observe_pull_request(self, **_kwargs):
            return ForgePullRequest(
                number=42,
                url="https://github.example/pull/42",
                head_branch="codex/router/kbs-42/r2",
                head_sha="published",
                state="open",
                merged=False,
            )

    ctx = context(
        tmp_path, forge=SimpleNamespace(repository="owner/repo", base_branch="main")
    )
    monkeypatch.setattr(
        router_execution, "_FAKE_FORGE", Forge(repository="owner/repo", token="test")
    )
    monkeypatch.setattr(router_execution, "_remote_ref_sha", lambda *_: None)
    monkeypatch.setitem(router_execution._WORKTREE_HEADS, "claim", "published")
    monkeypatch.setitem(
        router_execution._WORKTREE_BRANCHES, "claim", "codex/router/kbs-42/r2"
    )
    monkeypatch.setattr(
        router_execution.subprocess,
        "run",
        lambda *_a, **_kw: SimpleNamespace(returncode=0, stdout=""),
    )
    checks = []

    def fence(*_args):
        checks.append(True)
        if len(checks) == fail_at:
            raise IssueRouterError("stale package claim")

    monkeypatch.setattr(router_execution, "_assert_claim_fence", fence)
    monkeypatch.setattr(
        router_execution, "record_router_event", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_a: None)
    restores = []
    monkeypatch.setattr(
        router_execution,
        "_restore_stale_pull_request_branch",
        lambda *args: restores.append(args) or restore_ok,
    )

    with pytest.raises(IssueRouterError, match=message):
        router_execution._open_pull_request(ctx, candidate(), None, "claim", 2)
    assert len(restores) == 1


def test_apply_issue_updates_rejects_issue_outside_package(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    with pytest.raises(IssueRouterError, match="outside router package"):
        router_execution._apply_issue_updates(
            ctx,
            candidate(),
            RouterAgentResult(
                schema_version=1,
                outcome="completed",
                issue_updates=[{"issue_id": "other", "status": "active"}],
            ),
            "claim",
            1,
        )


def test_release_claims_reports_non_race_soft_release_error(monkeypatch, tmp_path):
    ctx = context(tmp_path)
    handle = _ClaimHandle("git", "router:issue:kbs-42", "owner", "claim", None)
    monkeypatch.setattr(
        router_execution, "_router_soft_lease_is_current", lambda *_: True
    )
    monkeypatch.setattr(
        router_execution,
        "soft_release",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            router_execution.CoordinationError("event storage unavailable")
        ),
    )
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_: None)
    with pytest.raises(IssueRouterError, match="release failed"):
        router_execution._release_claims(ctx, [handle])


def test_restore_checkpoint_ref_swallows_failed_best_effort_rollback(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        router_execution.subprocess,
        "run",
        lambda *_a, **_kw: (_ for _ in ()).throw(OSError("reference moved")),
    )
    router_execution._restore_checkpoint_ref(
        tmp_path, "refs/kanbus/router/kbs-42/r1", "published", None
    )
