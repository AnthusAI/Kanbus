"""Behave contracts for multi-router coordination and recovery boundaries."""

from __future__ import annotations

import json
import subprocess
import threading
import urllib.error
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import yaml
from behave import given, then, when

from features.steps import coordination_steps as coordination_steps
from features.steps import issue_router_steps as router_steps
from features.steps.shared import read_issue_file
from kanbus import coordination, coordination_mutex_api
from kanbus.coordination import inspect_lease
from kanbus.event_history import create_event, write_events_batch
from kanbus.issue_router import (
    IssueRouterError,
    build_router_plan,
    load_router_context,
    read_router_events,
    record_router_event,
)
from kanbus.router_adapters import FakeRouterAdapter, RouterAgentResult
from kanbus.router_execution import (
    _acquire_claims,
    _assert_current_claim,
    _candidate_for_package,
    _run_adapter,
    publish_router_result,
    run_router_once,
    set_router_adapter,
)
from kanbus.router_state import publish_router_state, router_state_root


def _git(
    root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run Git in a disposable scenario repository."""
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )


def _config_path(root: Path) -> Path:
    """Return the Kanbus config path for one test checkout."""
    return root / ".kanbus.yml"


def _read_config(root: Path) -> dict:
    """Load YAML config from one test checkout."""
    return yaml.safe_load(_config_path(root).read_text(encoding="utf-8")) or {}


def _write_config(root: Path, payload: dict) -> None:
    """Write YAML config in one disposable checkout."""
    _config_path(root).write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


def _commit_checkout(root: Path, message: str) -> None:
    """Commit fixture state only in a disposable checkout."""
    _git(root, "add", "-A")
    if _git(root, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    _git(
        root,
        "-c",
        "user.name=Router Behave Fixture",
        "-c",
        "user.email=router-fixture@localhost",
        "commit",
        "-m",
        message,
    )


def _worker_roots(context: object) -> list[Path]:
    """Return disposable worker checkouts or the single execution fixture."""
    roots = getattr(context, "router_worker_roots", None)
    if roots is None:
        return [Path(context.working_directory)]
    return [Path(value) for value in roots]


def _sync_workers(context: object) -> None:
    """Align disposable workers to one committed fixture before state worktrees exist."""
    source = Path(context.working_directory)
    project_name = Path(source / ".kanbus.yml").exists()
    assert project_name
    router_steps._commit_disposable_fixture(context)
    worker_roots = _worker_roots(context)
    if all(worker.resolve() == source.resolve() for worker in worker_roots):
        return
    branch = _git(source, "branch", "--show-current").stdout.strip()
    _git(source, "push", "origin", f"HEAD:refs/heads/{branch}")
    fixture_head = _git(source, "rev-parse", "HEAD").stdout.strip()
    temporary_root = Path(context.temp_dir).resolve()
    for worker in worker_roots:
        worker = worker.resolve()
        if not worker.is_relative_to(temporary_root):
            raise AssertionError(
                "router Behave worker is outside its disposable directory"
            )
        _git(worker, "fetch", "origin", branch)
        _git(
            worker,
            "checkout",
            "--force",
            "-B",
            branch,
            f"refs/remotes/origin/{branch}",
        )
        worker_head = _git(worker, "rev-parse", "HEAD").stdout.strip()
        assert worker_head == fixture_head


def _worker_state_roots(context: object) -> list[Path]:
    """Initialize and return both hidden Git state worktrees."""
    _sync_workers(context)
    roots = [router_state_root(root, refresh=True) for root in _worker_roots(context)]
    context.router_worker_state_roots = roots
    return roots


def _set_shared_configuration(context: object, mutate) -> None:
    """Apply one fixture config mutation to the source repository."""
    payload = _read_config(Path(context.working_directory))
    mutate(payload)
    _write_config(Path(context.working_directory), payload)


def _set_workers_configuration(context: object, mutate) -> None:
    """Apply one fixture config mutation to both isolated checkouts."""
    for root in _worker_roots(context):
        payload = _read_config(root)
        mutate(payload)
        _write_config(root, payload)
        _commit_checkout(root, "configure router worker fixture")


def _worker_contexts(context: object):
    """Load each runtime context from its isolated router state worktree."""
    roots = _worker_state_roots(context)
    return [load_router_context(root) for root in roots]


def _candidate(context, package_id: str):
    """Return a router candidate for a package in one worker context."""
    plan = build_router_plan(context)
    candidate = next(
        (item for item in plan.eligible if item.issue_id == package_id), None
    )
    if candidate is not None:
        return candidate
    return _candidate_for_package(context, package_id, [package_id])


def _ensure_fake_mutex_api(
    context: object, endpoint: str = "http://127.0.0.1:1"
) -> None:
    """Install the shared fake mutex API and configure both workers."""
    coordination_steps._install_fake_mutex_api(context)
    for root in _worker_roots(context):
        payload = _read_config(root)
        settings = payload.setdefault("coordination", {}).setdefault("mutex_api", {})
        settings.update(endpoint=endpoint, bearer_token="behave-test-token")
        _write_config(root, payload)
        _commit_checkout(root, "configure fake mutex API")
    source = Path(context.working_directory)
    payload = _read_config(source)
    settings = payload.setdefault("coordination", {}).setdefault("mutex_api", {})
    settings.update(endpoint=endpoint, bearer_token="behave-test-token")
    _write_config(source, payload)


def _configure_provider_chain(context: object, providers: list[str]) -> None:
    """Set the coordination provider chain in source and worker configs."""

    def update(payload: dict) -> None:
        payload.setdefault("coordination", {})["providers"] = providers

    _set_shared_configuration(context, update)
    _set_workers_configuration(context, update)


def _run_worker_claims(
    context: object, package_id: str
) -> list[tuple[bool, str | None]]:
    """Ask both workers' execution guard to acquire the requested package."""
    workers = _worker_contexts(context)
    results = []
    for index, worker_context in enumerate(workers):
        claim_id = f"claim-{'a' if index == 0 else 'b'}"
        candidate = _candidate(worker_context, package_id)
        try:
            handles = _acquire_claims(
                worker_context,
                candidate,
                claim_id=claim_id,
                revision=1,
                owner=f"worker-{'a' if index == 0 else 'b'}",
            )
            handles_by_worker = getattr(context, "router_worker_handles", [None, None])
            handles_by_worker[index] = handles
            context.router_worker_handles = handles_by_worker
            results.append((True, None))
        except IssueRouterError as error:
            results.append((False, str(error)))
    context.router_worker_claim_results = results
    context.router_worker_contexts = workers
    return results


def _coordination_records(events_dir: Path, resource: str) -> list[dict]:
    """Read the immutable Git lease records for one resource."""
    records = []
    for path in events_dir.glob("*.json"):
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if event.get("issue_id") == resource and event.get("event_type", "").startswith(
            "coordination."
        ):
            records.append(event)
    return records


@given("two router workers use isolated checkouts of the same Kanbus project")
def given_two_router_worker_checkouts(context: object) -> None:
    """Create a disposable origin and two independent worker clones."""
    router_steps._install_router(context, deepcopy(router_steps._ROUTER))
    router_steps._write_issue(
        context,
        "kbs-601",
        status="open",
        labels=["agent-provider:codex-default"],
    )
    router_steps._commit_disposable_fixture(context)
    source = Path(context.working_directory)
    branch = _git(source, "branch", "--show-current").stdout.strip()
    origin = Path(context.temp_dir) / "router-origin.git"
    _git(source, "init", "--bare", str(origin))
    _git(source, "remote", "add", "origin", str(origin))
    _git(source, "push", "-u", "origin", branch)
    _git(origin, "symbolic-ref", "HEAD", f"refs/heads/{branch}")
    worker_roots = [
        Path(context.temp_dir) / "worker-a",
        Path(context.temp_dir) / "worker-b",
    ]
    for root in worker_roots:
        subprocess.run(
            ["git", "clone", str(origin), str(root)],
            check=True,
            capture_output=True,
            text=True,
        )
    context.router_origin = origin
    context.router_worker_roots = worker_roots
    context.router_partition_simulated = False


@given('both workers plan package "{package_id}" at the same logical revision')
def given_both_workers_plan_package(context: object, package_id: str) -> None:
    """Ensure both clones contain the same routed package fixture."""
    if package_id != "kbs-601":
        raise AssertionError(f"unexpected package in shared background: {package_id}")
    for root in _worker_roots(context):
        issue_path = root / "project" / "issues" / f"{package_id}.json"
        assert issue_path.exists()
    context.router_plan_package = package_id
    context.router_plan_revision = 1


@given('router coordination mode is "{mode}"')
def given_router_coordination_mode(context: object, mode: str) -> None:
    """Configure soft Git or hard Mutex API provider behavior."""
    if mode == "soft":
        _configure_provider_chain(context, ["git"])
    elif mode == "hard":
        _configure_provider_chain(context, ["mutex_api", "mqtt", "git"])
        _ensure_fake_mutex_api(context)
    else:
        raise AssertionError(f"unsupported coordination mode {mode}")
    context.router_coordination_mode = mode


@given("Git is the only coordination provider")
def given_git_only_provider(context: object) -> None:
    """Select Git-only soft claims on both workers."""
    _configure_provider_chain(context, ["git"])


@when('both router workers start package "{package_id}" during a simulated partition')
def when_both_workers_start_during_partition(context: object, package_id: str) -> None:
    """Acquire locally on each isolated clone before publishing either branch."""
    if package_id != context.router_plan_package:
        raise AssertionError("workers attempted a package different from their plan")
    context.router_partition_simulated = True
    results = _run_worker_claims(context, package_id)
    if results == [(True, None), (True, None)]:
        now = datetime.now(UTC)
        for index, worker_context in enumerate(context.router_worker_contexts):
            claim_id = f"claim-{'a' if index == 0 else 'b'}"
            owner = f"worker-{'a' if index == 0 else 'b'}"
            record_router_event(
                worker_context.project_dir,
                package_id=package_id,
                event_type="router_claimed",
                payload={"claim_id": claim_id, "revision": 1, "owner": owner},
                occurred_at=now + timedelta(seconds=1 - index),
            )
        for root in _worker_roots(context):
            publish_router_state(root)


@then("both workers may report that their claim was accepted")
def then_both_soft_claims_accepted(context: object) -> None:
    """Require both disconnected Git-only workers to accept locally."""
    assert context.router_partition_simulated is True
    assert context.router_worker_claim_results == [(True, None), (True, None)]


@then("the project history should retain both claims")
def then_project_retains_both_claims(context: object) -> None:
    """Verify both immutable lease claims converged into shared Git history."""
    root = router_state_root(_worker_roots(context)[0], refresh=True)
    events_dir = load_router_context(root).project_dir / "events"
    records = _coordination_records(events_dir, "router:issue:kbs-601")
    claim_ids = {
        event.get("payload", {}).get("claim_id")
        for event in records
        if event.get("event_type") == "coordination.claim"
    }
    assert {"claim-a", "claim-b"} <= claim_ids


@then("publication should still accept only the current claim revision")
def then_only_current_claim_can_publish(context: object) -> None:
    """Fence one duplicate claim and accept the lease reducer's winner."""
    root = router_state_root(_worker_roots(context)[0], refresh=True)
    router_context = load_router_context(root)
    lease = inspect_lease(router_context.project_dir / "events", "router:issue:kbs-601")
    assert lease.active and lease.claim_id in {"claim-a", "claim-b"}
    winner = lease.claim_id
    loser = "claim-b" if winner == "claim-a" else "claim-a"
    _assert_current_claim(router_context.project_dir, "kbs-601", winner, 1)
    with_error = None
    try:
        publish_router_result(
            router_context,
            package_id="kbs-601",
            claim_id=loser,
            revision=1,
            result=RouterAgentResult(schema_version=1, outcome="completed"),
        )
    except IssueRouterError as error:
        with_error = str(error)
    assert with_error is not None and with_error.startswith("stale router claim")
    publish_router_result(
        router_context,
        package_id="kbs-601",
        claim_id=winner,
        revision=1,
        result=RouterAgentResult(schema_version=1, outcome="completed"),
    )


@given("the Mutex API provider is available")
def given_mutex_api_available(context: object) -> None:
    """Install the deterministic shared test mutex service."""
    _ensure_fake_mutex_api(context)


@when("both router workers request the package claim at the same time")
def when_both_workers_request_claim(context: object) -> None:
    """Ask both workers to acquire one shared hard lease without releasing it."""
    _configure_provider_chain(context, ["mutex_api", "mqtt", "git"])
    context.router_worker_claim_results = _run_worker_claims(context, "kbs-601")
    context.router_adapter_starts = sum(
        accepted for accepted, _error in context.router_worker_claim_results
    )


@then("exactly one worker should acquire the package claim")
def then_exactly_one_hard_claim(context: object) -> None:
    """Check the fake mutex API granted one active claim."""
    assert (
        sum(accepted for accepted, _error in context.router_worker_claim_results) == 1
    )
    assert len(context.mutex_api_leases) >= 1


@then('the other worker should report "{message}"')
def then_losing_worker_error(context: object, message: str) -> None:
    """Check the losing worker receives the package contention result."""
    errors = [
        error for accepted, error in context.router_worker_claim_results if not accepted
    ]
    assert errors == [message]


@then("the losing worker should not start an adapter")
def then_loser_has_no_adapter(context: object) -> None:
    """Verify adapter startup count follows successful hard claims."""
    assert context.router_adapter_starts == 1


@given("the project WIP limit is {limit:d}")
def given_router_project_wip_limit(context: object, limit: int) -> None:
    """Set the shared router project WIP limit."""

    def update(payload: dict) -> None:
        limits = payload.setdefault("router", deepcopy(router_steps._ROUTER))["limits"]
        limits["project_wip"] = limit
        limits["review_wip"] = min(limits.get("review_wip", limit), limit)

    _set_shared_configuration(context, update)


@given('pending packages "{package_ids}" are eligible')
def given_multiple_pending_router_packages(context: object, package_ids: str) -> None:
    """Create the two pending packages used by the shared WIP scenario."""
    for issue_id in [value.strip() for value in package_ids.split(",")]:
        router_steps._write_issue(
            context,
            issue_id,
            status="open",
            labels=["agent-provider:codex-default"],
        )
    # The background package is unrelated to this WIP race; close it so it
    # cannot consume a scheduling slot ahead of the two explicit candidates.
    router_steps._write_issue(context, "kbs-601", status="closed")
    context.router_wip_package_ids = [value.strip() for value in package_ids.split(",")]


class _BlockingRouterAdapter:
    """Adapter that holds its first request until a peer has planned."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.finish = threading.Event()
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        self.started.set()
        if not self.finish.wait(10):
            raise AssertionError("worker scheduling test timed out")
        return RouterAgentResult(
            schema_version=1,
            outcome="retryable_failure",
            summary="test worker yielded after peer planning",
        )

    def cancel(self, _claim_id: str) -> None:
        self.finish.set()


@when("both router workers run one scheduling pass at the same time")
def when_workers_schedule_with_shared_wip(context: object) -> None:
    """Hold the first adapter while a peer refreshes shared board state."""
    _configure_provider_chain(context, ["mutex_api", "mqtt", "git"])
    _ensure_fake_mutex_api(context)
    package_ids = getattr(context, "router_wip_package_ids", ["kbs-603", "kbs-604"])
    for root in _worker_roots(context):
        payload = _read_config(root)
        limits = payload.setdefault("router", deepcopy(router_steps._ROUTER))["limits"]
        limits["project_wip"] = 1
        limits["review_wip"] = min(limits.get("review_wip", 1), 1)
        _write_config(root, payload)
        _commit_checkout(root, "configure shared WIP limit")
    router_steps._commit_disposable_fixture(context)
    roots = _worker_state_roots(context)
    first_context = load_router_context(roots[0])
    second_root = _worker_roots(context)[1]
    adapter = _BlockingRouterAdapter()
    set_router_adapter("codex-default", adapter)
    context.add_cleanup(lambda: set_router_adapter("codex-default", None))
    holder: dict[str, object] = {}

    def run_first() -> None:
        holder["result"] = run_router_once(first_context)

    thread = threading.Thread(target=run_first, daemon=True)
    thread.start()
    try:
        assert adapter.started.wait(10), "first worker did not start an adapter"
        second_context = load_router_context(
            router_state_root(second_root, refresh=True)
        )
        second_plan = build_router_plan(second_context)
        context.router_wip_peer_plan = second_plan
        context.router_wip_peer_result = run_router_once(second_context)
    finally:
        adapter.finish.set()
        thread.join(timeout=12)
    assert not thread.is_alive(), "first worker did not finish"
    context.router_wip_first_result = holder["result"]
    context.router_wip_adapter = adapter
    context.router_wip_package_ids = package_ids


@then("exactly one adapter should start")
def then_one_shared_wip_adapter(context: object) -> None:
    """Require one adapter call across the two worker scheduling passes."""
    first = context.router_wip_adapter
    peer = context.router_wip_peer_result
    assert len(first.requests) == 1
    assert peer.started == 0


@then("exactly one package should enter the active status")
def then_one_package_enters_active(context: object) -> None:
    """Verify one worker transitioned a package to the configured active state."""
    root = router_state_root(_worker_roots(context)[0], refresh=True)
    project_dir = load_router_context(root).project_dir
    active = [
        issue_id
        for issue_id in context.router_wip_package_ids
        if read_issue_file(project_dir, issue_id).status == "in_progress"
    ]
    assert len(active) == 1, active


@then('the other package should be deferred with reason "{reason}"')
def then_other_package_deferred_reason(context: object, reason: str) -> None:
    """Verify the peer's current plan explains why the other package waits."""
    deferred = {
        item.issue_id: item.reason for item in context.router_wip_peer_plan.deferred
    }
    assert reason in deferred.values(), deferred


@given("the Mutex API endpoint is configured but unreachable")
def given_mutex_api_unreachable(context: object) -> None:
    """Point hard coordination at a valid endpoint while simulating downtime."""
    _ensure_fake_mutex_api(context, "http://127.0.0.1:1")
    original = coordination_mutex_api._urlopen

    def unavailable(*_args, **_kwargs):
        raise urllib.error.URLError("test mutex outage")

    coordination_mutex_api._urlopen = unavailable
    context.add_cleanup(lambda: setattr(coordination_mutex_api, "_urlopen", original))


@when('both router workers attempt package "{package_id}"')
def when_both_workers_attempt_unreachable_claim(
    context: object, package_id: str
) -> None:
    """Attempt hard acquisitions against the unavailable configured service."""
    _sync_workers(context)
    contexts = _worker_contexts(context)
    results = []
    for worker_context in contexts:
        try:
            _acquire_claims(
                worker_context,
                _candidate(worker_context, package_id),
                claim_id=f"unreachable-{len(results)}",
                revision=1,
                owner="unreachable-test-worker",
            )
            results.append((True, None))
        except IssueRouterError as error:
            results.append((False, str(error)))
    context.router_worker_contexts = contexts
    context.router_worker_claim_results = results
    context.router_worker_before_statuses = [
        read_issue_file(item.project_dir, package_id).status for item in contexts
    ]
    context.router_adapter_starts = sum(accepted for accepted, _error in results)


@then("neither worker should start an adapter")
def then_neither_worker_starts_adapter(context: object) -> None:
    """Check an unavailable hard provider never authorizes adapter startup."""
    assert context.router_adapter_starts == 0


@then('both workers should report "{message}"')
def then_both_workers_error(context: object, message: str) -> None:
    """Require the stable hard-provider failure from each clone."""
    errors = [
        error for accepted, error in context.router_worker_claim_results if not accepted
    ]
    assert len(errors) == 2 and all(message in error for error in errors), errors


@then('both workers should leave package "{package_id}" unchanged')
def then_worker_packages_unchanged(context: object, package_id: str) -> None:
    """Confirm a failed hard-provider attempt did not alter either issue."""
    after = [
        read_issue_file(item.project_dir, package_id).status
        for item in context.router_worker_contexts
    ]
    assert after == context.router_worker_before_statuses


@given(
    'router worker "worker-a" owns package "{package_id}" claim "claim-a" until "{expires_at}"'
)
def given_expired_first_router_claim(
    context: object, package_id: str, expires_at: str
) -> None:
    """Seed worker A's expired hard and Git audit claims with a checkpoint."""
    router_steps._write_issue(
        context,
        package_id,
        status="in_progress",
        labels=["agent-provider:codex-default"],
    )
    root = Path(context.working_directory)
    project_dir = root / "project"
    expired = coordination.parse_timestamp(expires_at)
    now = datetime(2026, 9, 17, 10, 6, tzinfo=UTC)
    if not hasattr(context, "router_original_clocks"):
        context.router_original_clocks = (coordination.utc_now,)
        original_runtime_clock = __import__(
            "kanbus.router_execution", fromlist=["utc_now"]
        ).utc_now
        context.router_original_runtime_clock = original_runtime_clock

        def restore() -> None:
            coordination.utc_now = context.router_original_clocks[0]
            import kanbus.router_execution as router_execution

            router_execution.utc_now = context.router_original_runtime_clock

        context.add_cleanup(restore)
    coordination.utc_now = lambda: now
    import kanbus.router_execution as router_execution

    router_execution.utc_now = lambda: now
    router_steps.record_router_event(
        project_dir,
        package_id=package_id,
        event_type="router_claimed",
        payload={"claim_id": "claim-a", "revision": 1, "owner": "worker-a"},
        occurred_at=expired - timedelta(minutes=5),
    )
    router_steps.record_router_event(
        project_dir,
        package_id=package_id,
        event_type="router_checkpoint_accepted",
        payload={
            "claim_id": "claim-a",
            "revision": 1,
            "ref": f"refs/kanbus/router/checkpoints/{package_id}",
        },
        occurred_at=expired - timedelta(minutes=4),
    )
    config = _read_config(root)
    config.setdefault("coordination", {})["providers"] = ["mutex_api", "mqtt", "git"]
    _write_config(root, config)
    _ensure_fake_mutex_api(context)
    context.mutex_api_leases[f"router:issue:{package_id}"] = {
        "resource": f"router:issue:{package_id}",
        "owner": "worker-a",
        "claim_id": "claim-a",
        "revision": 1,
        "claimed_at": int((expired - timedelta(minutes=5)).timestamp()),
        "expires_at": int(expired.timestamp()),
    }
    context.router_takeover_package = package_id
    context.router_takeover_expiry = expired


@when("simulated time advances past the claim expiry")
def when_simulated_time_past_expiry(context: object) -> None:
    """Advance the fake lease clock beyond worker A's expiration."""
    import kanbus.router_execution as router_execution

    now = context.router_takeover_expiry + timedelta(seconds=1)
    coordination.utc_now = lambda: now
    router_execution.utc_now = lambda: now
    context.router_takeover_now = now


@when('router worker "worker-b" requests package "{package_id}"')
def when_worker_b_takes_over(context: object, package_id: str) -> None:
    """Acquire the expired package with a higher revision and inspect checkpoint."""
    roots = _worker_state_roots(context)
    contexts = [load_router_context(root) for root in roots]
    first = contexts[0]
    first.project_dir.joinpath("events").mkdir(parents=True, exist_ok=True)
    publish_router_state(_worker_roots(context)[0])
    second = load_router_context(roots[1])
    current = _candidate(second, package_id)
    revision = 2
    handles = _acquire_claims(
        second,
        current,
        claim_id="claim-b",
        revision=revision,
        owner=f"issue-router:{__import__('os').getpid()}",
    )
    context.router_takeover_handles = handles
    record_router_event(
        second.project_dir,
        package_id=package_id,
        event_type="router_claimed",
        payload={"claim_id": "claim-b", "revision": revision, "owner": "worker-b"},
        occurred_at=context.router_takeover_now,
    )
    publish_router_state(_worker_roots(context)[1])
    refreshed = load_router_context(
        router_state_root(_worker_roots(context)[1], refresh=True)
    )
    candidate = _candidate(refreshed, package_id)
    adapter = FakeRouterAdapter(RouterAgentResult(schema_version=1, outcome="blocked"))
    set_router_adapter("codex-default", adapter)
    context.add_cleanup(lambda: set_router_adapter("codex-default", None))
    _run_adapter(refreshed, candidate, "claim-b", revision)
    context.router_takeover_revision = revision
    context.router_takeover_adapter = adapter
    context.router_takeover_context = refreshed
    context.router_takeover_old_context = load_router_context(
        router_state_root(_worker_roots(context)[0], refresh=True)
    )
    context.router_takeover_root = _worker_roots(context)[1]


@then('worker "worker-b" should acquire a new claim revision')
def then_worker_b_new_revision(context: object) -> None:
    """Verify takeover uses a claim revision newer than worker A's."""
    assert context.router_takeover_revision == 2
    _assert_current_claim(
        context.router_takeover_context.project_dir,
        context.router_takeover_package,
        "claim-b",
        context.router_takeover_revision,
    )


@then('worker "worker-b" should start from the latest accepted checkpoint')
def then_worker_b_uses_checkpoint(context: object) -> None:
    """Check the adapter request carries the accepted checkpoint reference."""
    assert len(context.router_takeover_adapter.requests) == 1
    request = context.router_takeover_adapter.requests[0]
    assert request.checkpoint is not None
    assert (
        request.checkpoint.ref
        == f"refs/kanbus/router/checkpoints/{context.router_takeover_package}"
    )
    assert request.checkpoint.revision == 1


@then('worker "worker-a" should be unable to publish its obsolete result')
def then_worker_a_stale_result_rejected(context: object) -> None:
    """Verify the superseded claim cannot publish a result or checkpoint."""
    before = read_router_events(
        context.router_takeover_context.project_dir, context.router_takeover_package
    )
    error = None
    try:
        publish_router_result(
            context.router_takeover_old_context,
            package_id=context.router_takeover_package,
            claim_id="claim-a",
            revision=1,
            result=RouterAgentResult(
                schema_version=1,
                outcome="completed",
                checkpoint={
                    "ref": f"refs/kanbus/router/checkpoints/{context.router_takeover_package}",
                    "revision": 1,
                },
            ),
        )
    except IssueRouterError as exception:
        error = str(exception)
    after = read_router_events(
        context.router_takeover_context.project_dir, context.router_takeover_package
    )
    assert error is not None and error.startswith("stale router claim claim-a")
    assert [
        event for event in after if event["event_type"] == "router_checkpoint_accepted"
    ] == [
        event for event in before if event["event_type"] == "router_checkpoint_accepted"
    ]


@given("both router workers are watching with interval {seconds:d} seconds")
def given_workers_watch_interval(context: object, seconds: int) -> None:
    """Configure the worker clones for the requested Git polling interval."""
    context.router_watch_interval = seconds

    def update(payload: dict) -> None:
        payload.setdefault("router", deepcopy(router_steps._ROUTER))[
            "watch_interval"
        ] = f"{seconds}s"

    _set_shared_configuration(context, update)
    _set_workers_configuration(context, update)


@given("the MQTT broker becomes unreachable")
def given_router_mqtt_outage(context: object) -> None:
    """Use a local closed MQTT port while retaining Git as fallback."""
    context.router_mqtt_unreachable = True
    for root in [Path(context.working_directory), *_worker_roots(context)]:
        payload = _read_config(root)
        payload.setdefault("realtime", {}).update(
            transport="mqtt",
            broker="mqtt://127.0.0.1:1",
            autostart=False,
        )
        _write_config(root, payload)
        if root != Path(context.working_directory):
            _commit_checkout(root, "configure unavailable MQTT fixture")


@when("the workers poll Git history")
def when_workers_poll_git_history(context: object) -> None:
    """Publish one durable event and refresh both state worktrees from Git."""
    roots = _worker_state_roots(context)
    first = load_router_context(roots[0])
    record_router_event(
        first.project_dir,
        package_id="kbs-601",
        event_type="router_progress",
        payload={
            "claim_id": "poll-event",
            "revision": 1,
            "summary": "durable polling event",
        },
    )
    publish_router_state(_worker_roots(context)[0])
    refreshed = [
        load_router_context(router_state_root(root, refresh=True))
        for root in _worker_roots(context)
    ]
    context.router_poll_contexts = refreshed


@then("both workers should observe durable router events from Git")
def then_both_workers_observe_git_events(context: object) -> None:
    """Require both clones to read the same newly published router event."""
    for worker_context in context.router_poll_contexts:
        events = read_router_events(worker_context.project_dir, "kbs-601")
        assert any(event["event_type"] == "router_progress" for event in events)


@then("both workers should continue planning eligible packages")
def then_workers_keep_planning(context: object) -> None:
    """Verify both workers still produce an eligible plan after MQTT failure."""
    assert context.router_mqtt_unreachable is True
    for worker_context in context.router_poll_contexts:
        plan = build_router_plan(worker_context)
        assert any(item.issue_id == "kbs-601" for item in plan.eligible)


@then("duplicate work may still occur because soft coordination is not hard exclusion")
def then_soft_duplicate_claims_remain_possible(context: object) -> None:
    """Verify independent Git-only checkouts can each accept a local claim."""
    _configure_provider_chain(context, ["git"])
    results = _run_worker_claims(context, "kbs-601")
    assert results == [(True, None), (True, None)]


@given(
    'active package "{package_id}" has accepted checkpoint "{checkpoint}" at revision {revision:d}'
)
def given_active_package_checkpoint(
    context: object, package_id: str, checkpoint: str, revision: int
) -> None:
    """Create the active retry candidate and its last accepted checkpoint."""
    router_steps._write_issue(
        context,
        package_id,
        status="in_progress",
        labels=["agent-provider:codex-default"],
    )
    router_steps._seed_claim(context, package_id, f"claim-{package_id}", revision - 1)
    record_router_event(
        load_router_context(Path(context.working_directory)).project_dir,
        package_id=package_id,
        event_type="router_checkpoint_accepted",
        payload={
            "claim_id": f"claim-{package_id}",
            "revision": revision,
            "ref": checkpoint,
        },
    )
    context.router_active_issue = package_id
    context.router_expected_checkpoint = (checkpoint, revision)


@given('the fake adapter returns outcome "{outcome}" for attempt {attempt:d}')
def given_fake_adapter_attempt_outcome(
    context: object, outcome: str, attempt: int
) -> None:
    """Install a fake adapter for the specified retry attempt."""
    del attempt
    adapter = FakeRouterAdapter(
        RouterAgentResult(schema_version=1, outcome=outcome, summary="fixture failure")
    )
    set_router_adapter("codex-default", adapter)
    context.router_adapter = adapter
    context.add_cleanup(lambda: set_router_adapter("codex-default", None))


@then(
    'the next attempt should start from checkpoint "{checkpoint}" at revision {revision:d}'
)
def then_next_attempt_checkpoint(
    context: object, checkpoint: str, revision: int
) -> None:
    """Verify the adapter request used the prior accepted checkpoint."""
    request = context.router_adapter.requests[0]
    assert request.checkpoint is not None
    assert (request.checkpoint.ref, request.checkpoint.revision) == (
        checkpoint,
        revision,
    )


@then('package "{package_id}" should record the diagnostic "{diagnostic}"')
def then_package_retry_diagnostic(
    context: object, package_id: str, diagnostic: str
) -> None:
    """Find the exact blocked-result diagnostic in append-only history."""
    events = router_steps._router_events(context, package_id)
    assert any(
        event["event_type"] == "router_blocked"
        and event["payload"].get("diagnostic") == diagnostic
        for event in events
    )


@then("the accepted checkpoint should remain available for a human or later router run")
def then_retry_checkpoint_retained(context: object) -> None:
    """Ensure blocked retry history carries forward any accepted checkpoint."""
    events = router_steps._router_events(context, context.router_active_issue)
    checkpoints = [
        event for event in events if event["event_type"] == "router_checkpoint_accepted"
    ]
    blocked = next(
        event for event in reversed(events) if event["event_type"] == "router_blocked"
    )
    if checkpoints:
        checkpoint = checkpoints[-1]
        assert (
            blocked["payload"].get("checkpoint", {}).get("ref")
            == checkpoint["payload"]["ref"]
        )
    else:
        assert blocked["payload"].get("checkpoint") is None


@then('package "{package_id}" should not receive a retry time')
def then_package_has_no_retry_time(context: object, package_id: str) -> None:
    """Ensure blocked outcomes do not schedule retry events."""
    assert not any(
        event["event_type"] == "router_retry_scheduled"
        for event in router_steps._router_events(context, package_id)
    )


@when(
    'claim "{claim_id}" publishes a completed result with checkpoint "{checkpoint}" and artifact "{artifact}"'
)
def when_stale_claim_publishes_refs(
    context: object, claim_id: str, checkpoint: str, artifact: str
) -> None:
    """Try to publish stale checkpoint and artifact references through the runtime fence."""
    router_steps._commit_disposable_fixture(context)
    package_id, _current_claim, _revision = context.router_current_claim
    root = router_state_root(Path(context.working_directory))
    router_context = load_router_context(root)
    error = None
    try:
        publish_router_result(
            router_context,
            package_id=package_id,
            claim_id=claim_id,
            revision=context.router_obsolete_claim[2],
            result=RouterAgentResult(
                schema_version=1,
                outcome="completed",
                checkpoint={
                    "ref": checkpoint,
                    "revision": context.router_obsolete_claim[2],
                },
                artifacts=[{"name": "stale", "ref": artifact}],
            ),
        )
    except IssueRouterError as exception:
        error = str(exception)
    context.router_publication_error = error
    context.router_publication_result = "failed" if error else "accepted"
    context.router_stale_artifact = artifact
    context.router_stale_checkpoint_before = [
        event
        for event in read_router_events(router_context.project_dir, package_id)
        if event["event_type"] == "router_checkpoint_accepted"
    ]
    context.result = SimpleNamespace(
        exit_code=1 if error else 0,
        stdout="",
        stderr=f"error: {error}\n" if error else "",
    )


@then("the accepted checkpoint should not change")
def then_stale_checkpoint_unchanged(context: object) -> None:
    """Check stale output did not append a checkpoint acceptance."""
    package_id = context.router_current_claim[0]
    events = router_steps._router_events(context, package_id)
    current = [
        event for event in events if event["event_type"] == "router_checkpoint_accepted"
    ]
    assert current == context.router_stale_checkpoint_before


@then('no artifact reference from claim "{claim_id}" should be published')
def then_no_stale_artifact(context: object, claim_id: str) -> None:
    """Check an obsolete claim has no artifact event in durable history."""
    events = router_steps._router_events(context, context.router_current_claim[0])
    assert not any(
        event["event_type"] == "router_artifact_published"
        and event["payload"].get("claim_id") == claim_id
        for event in events
    )


@when('claim "{claim_id}" publishes issue update "{issue_id}" to status "{status}"')
def when_claim_publishes_issue_update(
    context: object, claim_id: str, issue_id: str, status: str
) -> None:
    """Pass one proposed status update through result validation and publication."""
    router_steps._commit_disposable_fixture(context)
    package_id, _current_claim, revision = context.router_current_claim
    root = router_state_root(Path(context.working_directory))
    router_context = load_router_context(root)
    package_issue_ids = getattr(context, "router_package_ids", [package_id])
    before = {
        identifier: read_issue_file(router_context.project_dir, identifier).status
        for identifier in package_issue_ids
        if (router_context.project_dir / "issues" / f"{identifier}.json").exists()
    }
    if (router_context.project_dir / "issues" / f"{issue_id}.json").exists():
        before[issue_id] = read_issue_file(router_context.project_dir, issue_id).status
    error = None
    try:
        publish_router_result(
            router_context,
            package_id=package_id,
            claim_id=claim_id,
            revision=revision,
            result=RouterAgentResult(
                schema_version=1,
                outcome="completed",
                issue_updates=[{"issue_id": issue_id, "status": status}],
            ),
            package_issue_ids=package_issue_ids,
        )
    except IssueRouterError as exception:
        error = str(exception)
    context.router_publication_error = error
    context.router_publication_result = "failed" if error else "accepted"
    context.router_issue_status_before = before
    context.result = SimpleNamespace(
        exit_code=1 if error else 0,
        stdout="",
        stderr=f"error: {error}\n" if error else "",
    )


@then("no issue status should change")
def then_issue_statuses_unchanged(context: object) -> None:
    """Ensure invalid result updates do not mutate the board."""
    root = router_state_root(Path(context.working_directory))
    project_dir = load_router_context(root).project_dir
    for issue_id, status in context.router_issue_status_before.items():
        assert read_issue_file(project_dir, issue_id).status == status


def _seed_stale_router_claim(context: object, package_id: str, hours: int) -> datetime:
    """Seed a current claim with its last accepted progress at an old time."""
    router_steps._write_issue(
        context,
        package_id,
        status="in_progress",
        labels=["agent-provider:codex-default"],
    )
    now = datetime.now(UTC)
    started = now - timedelta(hours=hours)
    record_router_event(
        load_router_context(Path(context.working_directory)).project_dir,
        package_id=package_id,
        event_type="router_claimed",
        payload={"claim_id": "claim-current", "revision": 1},
        occurred_at=started,
    )
    context.router_stale_package = package_id
    context.router_stale_started = started
    context.router_stale_now = now
    context.router_stale_progress_at = started
    return started


@given(
    'package "{package_id}" has current claim "{claim_id}" with no progress for {hours:d} hours'
)
def given_package_claim_without_progress(
    context: object, package_id: str, claim_id: str, hours: int
) -> None:
    """Create old ownership history for stale-age assertions."""
    assert claim_id == "claim-current"
    _seed_stale_router_claim(context, package_id, hours)


@when('a human adds a comment to issue "{issue_id}"')
def when_human_comments_on_router_issue(context: object, issue_id: str) -> None:
    """Add an issue comment event without recording router progress."""
    event = create_event(
        issue_id=issue_id,
        event_type="comment_added",
        actor_id="human@example.test",
        payload={"comment": "Still checking this work."},
    )
    write_events_batch(Path(context.working_directory) / "project" / "events", [event])


@when('the adapter sends an empty heartbeat for claim "{claim_id}"')
def when_adapter_sends_empty_heartbeat(context: object, claim_id: str) -> None:
    """Represent an empty heartbeat without appending structured progress."""
    assert claim_id == "claim-current"
    context.router_empty_heartbeat = True


def _stale_age_seconds(context: object) -> int:
    """Derive ownership age from claim, structured progress, and checkpoint events."""
    router_steps._commit_disposable_fixture(context)
    events = router_steps._router_events(context, context.router_stale_package)
    relevant = [
        event
        for event in events
        if event["event_type"]
        in {"router_claimed", "router_progress", "router_checkpoint_accepted"}
        and event.get("payload", {}).get("claim_id") == "claim-current"
    ]
    latest = max(relevant, key=lambda event: (event["occurred_at"], event["event_id"]))
    last_progress = datetime.fromisoformat(latest["occurred_at"].replace("Z", "+00:00"))
    return max(0, int((context.router_stale_now - last_progress).total_seconds()))


@then("the stale ownership age should remain 24 hours")
def then_stale_ownership_age_24_hours(context: object) -> None:
    """Confirm comment and empty heartbeat leave the claim's age unchanged."""
    assert context.router_empty_heartbeat is True
    assert _stale_age_seconds(context) == 24 * 60 * 60


@then("the package should be eligible for takeover")
def then_stale_package_eligible(context: object) -> None:
    """Verify expired ownership leaves an active package eligible again."""
    router_steps._commit_disposable_fixture(context)
    plan = build_router_plan(
        load_router_context(router_state_root(Path(context.working_directory)))
    )
    assert any(item.issue_id == context.router_stale_package for item in plan.eligible)


@when('claim "{claim_id}" publishes structured progress at the current revision')
def when_claim_publishes_structured_progress(context: object, claim_id: str) -> None:
    """Append a structured progress event for the current claim."""
    assert claim_id == "claim-current"
    record_router_event(
        load_router_context(Path(context.working_directory)).project_dir,
        package_id=context.router_stale_package,
        event_type="router_progress",
        payload={
            "claim_id": claim_id,
            "revision": 1,
            "summary": "Structured progress.",
        },
        occurred_at=datetime.now(UTC),
    )
    context.router_stale_now = datetime.now(UTC)


@then("the stale ownership age should reset to zero")
def then_stale_ownership_reset(context: object) -> None:
    """Confirm structured progress renewed stale ownership age."""
    assert _stale_age_seconds(context) <= 1


@when('claim "{claim_id}" publishes an accepted checkpoint at the current revision')
def when_claim_publishes_current_checkpoint(context: object, claim_id: str) -> None:
    """Append an accepted checkpoint for the current logical claim."""
    assert claim_id == "claim-current"
    record_router_event(
        load_router_context(Path(context.working_directory)).project_dir,
        package_id=context.router_stale_package,
        event_type="router_checkpoint_accepted",
        payload={
            "claim_id": claim_id,
            "revision": 1,
            "ref": f"refs/kanbus/router/checkpoints/{context.router_stale_package}",
        },
        occurred_at=datetime.now(UTC),
    )
    context.router_stale_now = datetime.now(UTC)


@then("the stale ownership age should remain zero")
def then_stale_ownership_remains_reset(context: object) -> None:
    """Confirm checkpoint acceptance continues to count as recent progress."""
    assert _stale_age_seconds(context) <= 1
