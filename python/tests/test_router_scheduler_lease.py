"""Watch scheduler lease ownership, renewal, and shutdown ordering tests."""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.coordination import inspect_lease
from kanbus.coordination import claim as soft_claim
from kanbus.coordination import release as soft_release
from kanbus.issue_router import RouterControlState
from kanbus.models import ProjectConfiguration
from kanbus.router_execution import (
    _ClaimHandle,
    IssueRouterError,
    RouterRunResult,
    _acquire_watch_scheduler_claim,
    _assert_scheduler_claim,
    _start_lease_renewer,
    run_router_watch,
)


def _watch_context(tmp_path: Path, providers: list[str]) -> SimpleNamespace:
    configuration_data = copy.deepcopy(DEFAULT_CONFIGURATION)
    configuration_data["coordination"]["providers"] = providers
    if providers[0] == "mutex_api":
        configuration_data["coordination"]["mutex_api"][
            "endpoint"
        ] = "https://mutex.example.test"
        configuration_data["coordination"]["mutex_api"]["bearer_token"] = "test-token"
    configuration = ProjectConfiguration.model_validate(configuration_data)
    return SimpleNamespace(
        root=tmp_path,
        project_dir=tmp_path / "project",
        configuration=configuration,
        router=SimpleNamespace(watch_interval="1s"),
        control=RouterControlState(),
    )


@pytest.mark.parametrize(
    ("providers", "soft_provider", "expected_hard"),
    [(["git"], "git", False), (["mutex_api", "mqtt", "git"], "mqtt", True)],
)
def test_watch_claim_acquires_and_fences_one_durable_scheduler_resource(
    monkeypatch, tmp_path, providers, soft_provider, expected_hard
) -> None:
    import kanbus.router_execution as execution

    context = _watch_context(tmp_path, providers)
    acquisitions = []
    published = []
    fenced = []

    def acquire(
        _context,
        handles,
        resource,
        owner,
        claim_id,
        revision,
        hard,
        **kwargs,
    ):
        acquisitions.append((resource, owner, claim_id, revision, hard, kwargs))
        handles.append(_ClaimHandle("git", resource, owner, claim_id, None, revision))
        if hard:
            handles.append(
                _ClaimHandle("mutex_api", resource, owner, claim_id, None, revision)
            )

    monkeypatch.setattr(execution, "_acquire_router_resource", acquire)
    monkeypatch.setattr(
        execution, "publish_router_state", lambda root: published.append(root)
    )
    monkeypatch.setattr(
        execution,
        "_assert_scheduler_claim",
        lambda _context, handles: fenced.append(tuple(handles)),
    )

    handles, claim_id = _acquire_watch_scheduler_claim(
        context, soft_provider=soft_provider
    )

    assert acquisitions[0][0] == "router:scheduler"
    assert acquisitions[0][1] == f"issue-router:{execution.os.getpid()}"
    assert acquisitions[0][2] == claim_id
    assert acquisitions[0][3:5] == (1, expected_hard)
    assert acquisitions[0][5]["soft_provider"] == soft_provider
    assert acquisitions[0][5]["wait_for_contention"] is True
    assert len(handles) == (2 if expected_hard else 1)
    assert published == [context.root]
    assert fenced == [tuple(handles)]


def test_watch_holds_scheduler_claim_until_after_run_and_releases_before_clear(
    monkeypatch, tmp_path
) -> None:
    import kanbus.router_execution as execution
    import kanbus.router_state

    context = _watch_context(tmp_path, ["git"])
    scheduler_handles = [
        _ClaimHandle("git", "router:scheduler", "owner", "scheduler-a", None, 1)
    ]
    lifecycle = []
    renew_stop = threading.Event()

    class FakeThread:
        def join(self, timeout=None):
            lifecycle.append(("renewal-joined", timeout))

    monkeypatch.setattr(execution, "start_soft_listener", lambda *_args: None)
    monkeypatch.setattr(
        execution,
        "_acquire_watch_scheduler_claim",
        lambda *_args, **_kwargs: (scheduler_handles, "scheduler-a"),
    )
    monkeypatch.setattr(
        execution,
        "_start_lease_renewer",
        lambda _context, handles, claim_id: (
            lifecycle.append(("renewing", handles, claim_id)) or renew_stop,
            FakeThread(),
        ),
    )
    monkeypatch.setattr(
        execution,
        "write_router_control",
        lambda _root, state: lifecycle.append(
            ("control", state.running, state.stop_requested)
        ),
    )
    monkeypatch.setattr(
        execution,
        "record_router_event",
        lambda _project, **kwargs: lifecycle.append(("event", kwargs["event_type"])),
    )
    monkeypatch.setattr(execution, "publish_router_state", lambda *_args: None)
    monkeypatch.setattr(execution, "load_router_context", lambda *_args: context)
    monkeypatch.setattr(
        kanbus.router_state,
        "router_state_root",
        lambda *_args, **_kwargs: context.root,
    )
    monkeypatch.setattr(execution, "_assert_scheduler_claim", lambda *_args: None)
    monkeypatch.setattr(execution, "_reconcile_pull_requests", lambda *_args: None)
    monkeypatch.setattr(execution, "_wait_for_watch_trigger", lambda *_args: False)

    def run_once(_context, **kwargs):
        lifecycle.append(("run", kwargs["scheduler_claim_handles"]))
        context.control.stop_requested = True
        return RouterRunResult()

    monkeypatch.setattr(execution, "run_router_once", run_once)
    monkeypatch.setattr(
        execution,
        "_release_claims",
        lambda _context, handles: lifecycle.append(("released", handles)),
    )

    run_router_watch(context)

    release_index = next(
        i for i, event in enumerate(lifecycle) if event[0] == "released"
    )
    stopped_index = next(
        i for i, event in enumerate(lifecycle) if event[:2] == ("control", False)
    )
    assert release_index < stopped_index
    assert any(
        event[0] == "run" and event[1] is scheduler_handles for event in lifecycle
    )
    assert renew_stop.is_set()


def test_watch_release_failure_does_not_clear_running_control(
    monkeypatch, tmp_path
) -> None:
    import kanbus.router_execution as execution
    import kanbus.router_state

    context = _watch_context(tmp_path, ["git"])
    scheduler_handles = [
        _ClaimHandle("git", "router:scheduler", "owner", "scheduler-b", None, 1)
    ]
    controls = []

    monkeypatch.setattr(execution, "start_soft_listener", lambda *_args: None)
    monkeypatch.setattr(
        execution,
        "_acquire_watch_scheduler_claim",
        lambda *_args, **_kwargs: (scheduler_handles, "scheduler-b"),
    )
    monkeypatch.setattr(execution, "_start_lease_renewer", lambda *_args: (None, None))
    monkeypatch.setattr(
        execution,
        "write_router_control",
        lambda _root, state: controls.append(state.running),
    )
    monkeypatch.setattr(
        execution, "record_router_event", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(execution, "publish_router_state", lambda *_args: None)
    monkeypatch.setattr(execution, "load_router_context", lambda *_args: context)
    monkeypatch.setattr(
        kanbus.router_state,
        "router_state_root",
        lambda *_args, **_kwargs: context.root,
    )
    monkeypatch.setattr(execution, "_assert_scheduler_claim", lambda *_args: None)
    monkeypatch.setattr(execution, "_reconcile_pull_requests", lambda *_args: None)
    monkeypatch.setattr(execution, "_wait_for_watch_trigger", lambda *_args: None)

    def stop_after_one_pass(_context, **_kwargs):
        context.control.stop_requested = True
        return RouterRunResult()

    monkeypatch.setattr(execution, "run_router_once", stop_after_one_pass)

    def fail_release(_context, _handles):
        raise IssueRouterError("router coordination release could not be published")

    monkeypatch.setattr(execution, "_release_claims", fail_release)

    with pytest.raises(IssueRouterError, match="release could not be published"):
        run_router_watch(context)

    assert controls == [True]


def test_soft_scheduler_fence_rejects_a_replaced_owner(monkeypatch, tmp_path) -> None:
    import kanbus.router_state

    context = _watch_context(tmp_path, ["git"])
    events_dir = context.project_dir / "events"
    events_dir.mkdir(parents=True)
    monkeypatch.setattr(
        kanbus.router_state,
        "router_state_root",
        lambda *_args, **_kwargs: context.root,
    )
    coordination = context.configuration.coordination
    soft_claim(
        events_dir,
        coordination,
        resource="router:scheduler",
        owner="worker-a",
        claim_id="scheduler-a",
        revision=3,
    )
    handle = _ClaimHandle("git", "router:scheduler", "worker-a", "scheduler-a", None, 3)

    _assert_scheduler_claim(context, [handle])

    soft_release(
        events_dir,
        resource="router:scheduler",
        owner="worker-a",
        claim_id="scheduler-a",
    )
    soft_claim(
        events_dir,
        coordination,
        resource="router:scheduler",
        owner="worker-b",
        claim_id="scheduler-b",
        revision=1,
    )

    with pytest.raises(IssueRouterError, match="stale router scheduler claim"):
        _assert_scheduler_claim(context, [handle])


def test_watch_scheduler_lease_is_renewed_until_watch_stops(
    monkeypatch, tmp_path
) -> None:
    import kanbus.router_execution as execution

    context = _watch_context(tmp_path, ["git"])
    context.project_dir.mkdir()
    events_dir = context.project_dir / "events"
    events_dir.mkdir()
    short_coordination = context.configuration.coordination.model_copy(
        update={"default_lease_ttl": "1s"}
    )
    context.configuration = context.configuration.model_copy(
        update={"coordination": short_coordination}
    )
    soft_claim(
        events_dir,
        short_coordination,
        resource="router:scheduler",
        owner="worker-a",
        claim_id="scheduler-renew",
        revision=1,
    )
    renewal_observed = threading.Event()
    original_renew = execution.soft_renew

    def observe_renewal(*args, **kwargs):
        state = original_renew(*args, **kwargs)
        renewal_observed.set()
        return state

    monkeypatch.setattr(execution, "parse_duration", lambda _duration: 1)
    monkeypatch.setattr(execution, "soft_renew", observe_renewal)
    monkeypatch.setattr(execution, "publish_router_state", lambda *_args: None)

    stopped, thread = _start_lease_renewer(
        context,
        [
            _ClaimHandle(
                "git", "router:scheduler", "worker-a", "scheduler-renew", None, 1
            )
        ],
        "scheduler-renew",
    )
    try:
        assert renewal_observed.wait(1.5)
    finally:
        stopped.set()
        thread.join(timeout=2)

    assert not thread.is_alive()
    assert inspect_lease(events_dir, "router:scheduler").active
