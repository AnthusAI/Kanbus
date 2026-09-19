"""Cross-clone tests for durable, isolated router state publication."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import sleep
from types import SimpleNamespace

import yaml
import pytest

from kanbus import router_state
from kanbus.config_loader import load_project_configuration
from kanbus.coordination import claim as soft_claim
from kanbus.coordination import inspect_lease
from kanbus.event_history import create_event, write_events_batch
from kanbus.issue_router import (
    IssueRouterError,
    RouterContext,
    _latest_router_event,
    build_router_plan,
    load_router_context,
    read_router_events,
    record_router_event,
)
from kanbus.models import IssueData
from kanbus.router_state import (
    publish_router_start_event,
    publish_router_state,
    resolve_router_root,
    router_state_root,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_current_claim_uses_revision_before_same_timestamp_event_id() -> None:
    timestamp = "2026-09-17T12:00:00.000000Z"
    older = {
        "issue_id": "router:kbs-order",
        "event_type": "router_claimed",
        "event_id": "z-r6",
        "occurred_at": timestamp,
        "payload": {"claim_id": "claim-r6", "revision": 6},
    }
    newer = {
        "issue_id": "router:kbs-order",
        "event_type": "router_claimed",
        "event_id": "a-r7",
        "occurred_at": timestamp,
        "payload": {"claim_id": "claim-r7", "revision": 7},
    }

    current = _latest_router_event([older, newer], "kbs-order", "router_claimed")

    assert current is newer


def test_shared_state_fetch_fails_closed_for_advertisement_and_fetch_errors(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(router_state, "_try_git", lambda *_args, **_kwargs: None)
    router_state._fetch_state(tmp_path)

    monkeypatch.setattr(
        router_state,
        "_try_git",
        lambda *_args, **_kwargs: "https://example.invalid/repo",
    )

    def failed_advertisement(*_args, **_kwargs):
        raise subprocess.CalledProcessError(128, "git ls-remote", stderr="offline")

    monkeypatch.setattr(subprocess, "run", failed_advertisement)
    with pytest.raises(IssueRouterError, match="could not fetch shared router state"):
        router_state._fetch_state(tmp_path)

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout="abc refs/heads/kanbus/router-state\n"
        ),
    )
    monkeypatch.setattr(router_state, "_try_git", lambda *_args, **_kwargs: 128)
    with pytest.raises(IssueRouterError, match="could not fetch shared router state"):
        router_state._fetch_state(tmp_path)


def test_git_error_helpers_keep_failures_explicit_and_bounded(
    monkeypatch, tmp_path: Path
) -> None:
    def failed_command(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "git status", stderr="permission denied")

    monkeypatch.setattr(subprocess, "run", failed_command)
    with pytest.raises(IssueRouterError, match="permission denied"):
        router_state._git(tmp_path, "status")

    def missing_git(*_args, **_kwargs):
        raise OSError("git missing")

    monkeypatch.setattr(subprocess, "run", missing_git)
    assert router_state._try_git(tmp_path, "status") is None


def test_router_root_resolves_from_a_repository_subdirectory(tmp_path: Path) -> None:
    _run(tmp_path, "init", "--initial-branch=main")
    nested = tmp_path / "rust" / "src"
    nested.mkdir(parents=True)

    assert resolve_router_root(nested) == tmp_path.resolve()


def test_router_root_rejects_non_git_directories_with_actionable_diagnostic(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        IssueRouterError, match="^issue router requires a Git repository$"
    ):
        resolve_router_root(tmp_path)


def test_merge_conflict_reports_git_diagnostic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stderr="", stdout="conflict in project/issues/kbs-1.json"
        ),
    )
    monkeypatch.setattr(router_state, "_try_git", lambda *_args, **_kwargs: "")

    with pytest.raises(IssueRouterError, match="conflict in project/issues/kbs-1.json"):
        router_state._merge_ref(tmp_path, "origin/kanbus/router-state")


def _run(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _git_identity(root: Path) -> None:
    _run(root, "config", "user.name", "Router State Test")
    _run(root, "config", "user.email", "router-state-test@example.invalid")


def test_second_clone_observes_claim_without_harness_push(
    tmp_path: Path, monkeypatch
) -> None:
    bare = tmp_path / "remote.git"
    source = tmp_path / "seed"
    clone_a = tmp_path / "worker-a"
    clone_b = tmp_path / "worker-b"
    bare.mkdir()
    source.mkdir()
    _run(bare, "init", "--bare", "--initial-branch=main")
    _run(source, "init", "--initial-branch=main")
    _git_identity(source)
    config = yaml.safe_load(
        (REPOSITORY_ROOT / ".kanbus.yml").read_text(encoding="utf-8")
    )
    if not any(status.get("key") == "review" for status in config["statuses"]):
        config["statuses"].append(
            {
                "key": "review",
                "name": "Review",
                "category": "In progress",
                "semantic_category": "in_progress",
            }
        )
    for status in ("open", "in_progress"):
        if "review" not in config["workflows"]["default"][status]:
            config["workflows"]["default"][status].append("review")
    config["workflows"]["default"]["review"] = ["in_progress", "closed"]
    labels = config.setdefault("transition_labels", {}).setdefault("default", {})
    labels["open"] = {**labels.get("open", {}), "review": "Ready for review"}
    labels["in_progress"] = {
        **labels.get("in_progress", {}),
        "review": "Ready for review",
    }
    labels["review"] = {"in_progress": "Request changes", "closed": "Merge"}
    config["router"] = {
        "workflow": {
            "pending": "open",
            "active": "in_progress",
            "review": "review",
            "blocked": "blocked",
            "terminal": ["closed"],
        },
        "limits": {"project_wip": 3, "review_wip": 2},
        "providers": {"codex-default": {"adapter": "codex"}},
        "classes": {},
    }
    (source / ".kanbus.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (source / ".gitignore").write_text("project/events/\n", encoding="utf-8")
    (source / "project" / "issues").mkdir(parents=True)
    (source / "project" / "events").mkdir(parents=True)
    now = datetime.now(UTC)
    issue = IssueData(
        id="kbs-claim",
        title="Shared claim",
        description="",
        type="task",
        status="in_progress",
        priority=2,
        labels=["agent-provider:codex-default"],
        created_at=now,
        updated_at=now,
    )
    (source / "project" / "issues" / "kbs-claim.json").write_text(
        issue.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
    )
    _run(source, "add", ".kanbus.yml", ".gitignore", "project")
    _run(source, "commit", "-m", "initial board")
    _run(source, "remote", "add", "origin", str(bare))
    _run(source, "push", "-u", "origin", "main")
    _run(tmp_path, "clone", str(bare), str(clone_a))
    _run(tmp_path, "clone", str(bare), str(clone_b))

    user_dirt = clone_a / "unrelated-user-note.txt"
    user_dirt.write_text("must not enter router-state\n", encoding="utf-8")
    state_a = router_state_root(clone_a)
    context_a = load_router_context(state_a)
    soft_claim(
        context_a.project_dir / "events",
        context_a.configuration.coordination,
        resource="router:issue:kbs-claim",
        owner="worker-a",
        claim_id="claim-a",
        revision=1,
    )
    project_dir_a = state_a / "project"
    record_router_event(
        project_dir_a,
        package_id="kbs-claim",
        event_type="router_claimed",
        payload={
            "claim_id": "claim-a",
            "revision": 1,
            "attempt": 1,
            "provider_profile": "codex-default",
        },
    )
    record_router_event(
        project_dir_a,
        package_id="kbs-claim",
        event_type="router_checkpoint_accepted",
        payload={"claim_id": "claim-a", "revision": 1, "ref": "refs/kanbus/checkpoint"},
    )
    publish_router_state(state_a, {"kbs-claim"})

    raw_events = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (state_a / "project" / "events").glob("*.json")
    ]
    start_event = next(
        item for item in raw_events if item["payload"].get("action") == "started"
    )
    checkpoint_event = next(
        item
        for item in raw_events
        if item["payload"].get("action") == "checkpoint_accepted"
    )
    assert start_event["event_type"] == "router.attempt"
    assert start_event["payload"]["attempt"] == 1
    assert checkpoint_event["event_type"] == "router.attempt"
    assert checkpoint_event["payload"]["checkpoint_revision"] == 1

    state_b = router_state_root(clone_b)
    observed = read_router_events(state_b / "project", "kbs-claim")
    claim_event = next(
        item for item in observed if item["event_type"] == "router_claimed"
    )
    assert claim_event["payload"]["claim_id"] == "claim-a"
    assert _run(state_b, "branch", "--show-current") == "kanbus/router-state"
    plan_b = build_router_plan(load_router_context(state_b))
    assert not plan_b.eligible, "a second clone must not redispatch a live claim"

    # Model the exact canonical event shape emitted by Rust, without relying
    # on the Python semantic-event encoder, and ensure a Python planner fences
    # that package using the shared router:issue resource.
    context_b = load_router_context(state_b)
    rust_issue = IssueData(
        id="kbs-rust-worker",
        title="Rust worker claim",
        description="",
        type="task",
        status="in_progress",
        priority=2,
        labels=["agent-provider:codex-default"],
        created_at=now,
        updated_at=now,
    )
    (context_b.project_dir / "issues" / "kbs-rust-worker.json").write_text(
        rust_issue.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
    )
    soft_claim(
        context_b.project_dir / "events",
        context_b.configuration.coordination,
        resource="router:issue:kbs-rust-worker",
        owner="worker-rust",
        claim_id="rust-claim",
        revision=1,
    )
    rust_event = create_event(
        issue_id="router:kbs-rust-worker",
        event_type="router.attempt",
        actor_id="worker-rust",
        payload={
            "action": "started",
            "attempt": 1,
            "claim_id": "rust-claim",
            "revision": 1,
            "provider_profile": "codex-default",
            "package_issue_ids": ["kbs-rust-worker"],
        },
    )
    write_events_batch(context_b.project_dir / "events", [rust_event])
    publish_router_state(state_b, {"kbs-rust-worker"})
    assert "kbs-rust-worker" not in [
        item.issue_id
        for item in build_router_plan(load_router_context(state_b)).eligible
    ], "Python must recognize Rust's canonical started event and issue claim"

    status = _run(clone_a, "status", "--short")
    assert "?? unrelated-user-note.txt" in status
    files = _run(
        clone_a,
        "ls-tree",
        "-r",
        "--name-only",
        "refs/remotes/origin/kanbus/router-state",
        "--",
        "project/events",
    )
    assert files
    unrelated = subprocess.run(
        [
            "git",
            "cat-file",
            "-e",
            "refs/remotes/origin/kanbus/router-state:unrelated-user-note.txt",
        ],
        cwd=clone_a,
        check=False,
        capture_output=True,
    )
    assert unrelated.returncode != 0

    # Force a competing state-branch publication after A has committed its
    # local event but before its lease-checked push. A must fetch/merge B's
    # unrelated immutable event and retry rather than treating the CAS miss as
    # a terminal release failure.
    record_router_event(
        state_a / "project",
        package_id="kbs-claim",
        event_type="router_checkpoint_accepted",
        payload={
            "claim_id": "claim-a",
            "revision": 1,
            "ref": "refs/kanbus/checkpoint-a",
        },
    )
    record_router_event(
        state_b / "project",
        package_id="kbs-rust-worker",
        event_type="router_checkpoint_accepted",
        payload={
            "claim_id": "rust-claim",
            "revision": 1,
            "ref": "refs/kanbus/checkpoint-b",
        },
    )
    original_try_git = router_state._try_git
    interleaved = False

    def publish_competing_update(root: Path, *args: str, capture: bool = False):
        nonlocal interleaved
        if not interleaved and root == state_a and args and args[0] == "push":
            interleaved = True
            publish_router_state(state_b, {"kbs-rust-worker"})
        return original_try_git(root, *args, capture=capture)

    monkeypatch.setattr(router_state, "_try_git", publish_competing_update)
    publish_router_state(state_a, {"kbs-claim"})
    assert interleaved
    reconciled_events = list((state_a / "project" / "events").glob("*.json"))
    refs = {
        json.loads(path.read_text(encoding="utf-8"))["payload"].get("checkpoint_ref")
        for path in reconciled_events
    }
    assert "refs/kanbus/checkpoint-a" in refs
    assert "refs/kanbus/checkpoint-b" in refs

    from kanbus.router_execution import _update_checkpoint_ref

    checkpoint_ref = "refs/kanbus/router/checkpoints/kbs-claim"
    checkpoint_sha = _run(state_a, "rev-parse", "HEAD")
    _update_checkpoint_ref(state_a, checkpoint_ref, checkpoint_sha)
    _run(clone_b, "fetch", "origin", f"{checkpoint_ref}:{checkpoint_ref}")
    assert _run(clone_b, "rev-parse", checkpoint_ref) == checkpoint_sha

    # Router lease changes go through the same soft-provider dispatcher as
    # the CLI: the immutable Git event is retained and MQTT receives the
    # matching claim/release envelopes when available.
    from kanbus import coordination_mqtt
    from kanbus.router_execution import _acquire_router_resource, _release_claims

    context_b.configuration.coordination.providers = ["mqtt", "git"]
    monkeypatch.setattr(coordination_mqtt, "provider_available", lambda *_args: True)
    envelopes = []

    def capture_mqtt(_root, target_project, configuration, envelope):
        envelopes.append(envelope)
        coordination_mqtt.record_envelope(
            target_project, envelope, ttl_s=configuration.overlay.ttl_s
        )
        return True

    monkeypatch.setattr(coordination_mqtt, "publish_envelope", capture_mqtt)
    mqtt_handles = []
    _acquire_router_resource(
        context_b,
        mqtt_handles,
        "router:issue:kbs-mqtt-test",
        "worker-mqtt",
        "claim-mqtt",
        1,
        False,
    )
    assert mqtt_handles[0].provider == "mqtt"
    _release_claims(context_b, mqtt_handles)
    assert [envelope.type for envelope in envelopes] == [
        "coordination.claim",
        "coordination.release",
    ]


def test_second_clone_observes_lease_renewal_after_original_ttl(tmp_path: Path) -> None:
    bare = tmp_path / "renew-remote.git"
    source = tmp_path / "renew-seed"
    clone_a = tmp_path / "renew-worker-a"
    clone_b = tmp_path / "renew-worker-b"
    bare.mkdir()
    source.mkdir()
    _run(bare, "init", "--bare", "--initial-branch=main")
    _run(source, "init", "--initial-branch=main")
    _git_identity(source)
    config = yaml.safe_load(
        (REPOSITORY_ROOT / ".kanbus.yml").read_text(encoding="utf-8")
    )
    config["router"] = {
        "workflow": {
            "pending": "open",
            "active": "in_progress",
            "review": "review",
            "blocked": "blocked",
            "terminal": ["closed"],
        },
        "limits": {"project_wip": 3, "review_wip": 2},
        "providers": {"codex-default": {"adapter": "codex"}},
        "classes": {},
    }
    if not any(status.get("key") == "review" for status in config["statuses"]):
        config["statuses"].append(
            {
                "key": "review",
                "name": "Review",
                "category": "In progress",
                "semantic_category": "in_progress",
            }
        )
    for status in ("open", "in_progress"):
        if "review" not in config["workflows"]["default"][status]:
            config["workflows"]["default"][status].append("review")
    config["workflows"]["default"]["review"] = ["in_progress", "closed"]
    labels = config.setdefault("transition_labels", {}).setdefault("default", {})
    labels["open"] = {**labels.get("open", {}), "review": "Ready for review"}
    labels["in_progress"] = {
        **labels.get("in_progress", {}),
        "review": "Ready for review",
    }
    labels["review"] = {"in_progress": "Request changes", "closed": "Merge"}
    (source / ".kanbus.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (source / "project" / "issues").mkdir(parents=True)
    (source / "project" / "events").mkdir(parents=True)
    now = datetime.now(UTC)
    issue = IssueData(
        id="kbs-renewal",
        title="Lease renewal",
        description="",
        type="task",
        status="in_progress",
        priority=2,
        labels=["agent-provider:codex-default"],
        created_at=now,
        updated_at=now,
    )
    (source / "project" / "issues" / "kbs-renewal.json").write_text(
        issue.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
    )
    _run(source, "add", ".kanbus.yml", "project")
    _run(source, "commit", "-m", "initial board")
    _run(source, "remote", "add", "origin", str(bare))
    _run(source, "push", "-u", "origin", "main")
    _run(tmp_path, "clone", str(bare), str(clone_a))
    _run(tmp_path, "clone", str(bare), str(clone_b))

    state_a = router_state_root(clone_a)
    context = load_router_context(state_a)
    short_coordination = context.configuration.coordination.model_copy(
        update={"default_lease_ttl": "1s"}
    )
    short_configuration = context.configuration.model_copy(
        update={"coordination": short_coordination}
    )
    context = RouterContext(
        root=context.root,
        project_dir=context.project_dir,
        configuration=short_configuration,
        router=context.router,
        issues=context.issues,
        control=context.control,
    )
    from kanbus.coordination import claim as soft_claim
    from kanbus.router_execution import _ClaimHandle, _start_lease_renewer

    claim_start = datetime.now(UTC)
    soft_claim(
        context.project_dir / "events",
        short_coordination,
        resource="router:issue:kbs-renewal",
        owner="worker-a",
        claim_id="renew-claim",
        revision=1,
        now=claim_start,
    )
    record_router_event(
        context.project_dir,
        package_id="kbs-renewal",
        event_type="router_claimed",
        payload={
            "claim_id": "renew-claim",
            "revision": 1,
            "attempt": 1,
            "provider_profile": "codex-default",
        },
        occurred_at=claim_start,
    )
    publish_router_state(state_a, {"kbs-renewal"})
    stopped, thread = _start_lease_renewer(
        context,
        [
            _ClaimHandle(
                "git", "router:issue:kbs-renewal", "worker-a", "renew-claim", None
            )
        ],
        "renew-claim",
    )
    sleep(2.0)
    stopped.set()
    thread.join(timeout=2)

    state_b = router_state_root(clone_b)
    observed_context = load_router_context(state_b)
    evaluation_time = claim_start + timedelta(seconds=1.8)
    lease = inspect_lease(
        observed_context.project_dir / "events",
        "router:issue:kbs-renewal",
        now=evaluation_time,
    )
    assert lease.active, "the peer must see a renewal after the original one-second TTL"
    assert not build_router_plan(observed_context).eligible


def test_concurrent_shared_start_publication_accepts_only_selected_claim(
    tmp_path: Path,
) -> None:
    bare = tmp_path / "remote.git"
    source = tmp_path / "seed"
    clone_a = tmp_path / "worker-a"
    clone_b = tmp_path / "worker-b"
    bare.mkdir()
    source.mkdir()
    _run(bare, "init", "--bare", "--initial-branch=main")
    _run(source, "init", "--initial-branch=main")
    _git_identity(source)
    (source / ".kanbus.yml").write_text(
        (REPOSITORY_ROOT / ".kanbus.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (source / "project" / "events").mkdir(parents=True)
    (source / "project" / "issues").mkdir(parents=True)
    (source / "project" / "issues" / ".keep").write_text("\n", encoding="utf-8")
    _run(source, "add", ".kanbus.yml", "project")
    _run(source, "commit", "-m", "initial board")
    _run(source, "remote", "add", "origin", str(bare))
    _run(source, "push", "-u", "origin", "main")
    _run(tmp_path, "clone", str(bare), str(clone_a))
    _run(tmp_path, "clone", str(bare), str(clone_b))

    state_a = router_state_root(clone_a)
    state_b = router_state_root(clone_b)
    configuration = load_project_configuration(state_a / ".kanbus.yml")
    resource = "router:issue:kbs-concurrent"
    soft_claim(
        state_a / "project" / "events",
        configuration.coordination,
        resource=resource,
        owner="worker-a",
        claim_id="claim-a",
        revision=1,
    )
    soft_claim(
        state_b / "project" / "events",
        configuration.coordination,
        resource=resource,
        owner="worker-b",
        claim_id="claim-b",
        revision=1,
    )
    publish_router_state(state_a)
    publish_router_state(state_b)
    state_a = router_state_root(state_a)
    winner = inspect_lease(state_a / "project" / "events", resource)
    assert winner.active and winner.owner and winner.claim_id

    events = {
        owner: create_event(
            issue_id="router:kbs-concurrent",
            event_type="router.attempt",
            actor_id=owner,
            payload={
                "action": "started",
                "attempt": 1,
                "claim_id": claim_id,
                "revision": 1,
                "provider_profile": "codex-default",
            },
        )
        for owner, claim_id in (
            ("worker-a", "claim-a"),
            ("worker-b", "claim-b"),
        )
    }

    def publish(state_root: Path, owner: str, claim_id: str) -> bool:
        def validate(events_dir: Path) -> None:
            current = inspect_lease(events_dir, resource)
            if (
                not current.active
                or current.owner != owner
                or current.claim_id != claim_id
            ):
                raise router_state.IssueRouterError("package already claimed")

        try:
            publish_router_start_event(
                state_root,
                events[owner],
                validate_claim=validate,
            )
        except router_state.IssueRouterError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = list(
            pool.map(
                lambda args: publish(*args),
                [
                    (state_a, "worker-a", "claim-a"),
                    (state_b, "worker-b", "claim-b"),
                ],
            )
        )

    assert sum(accepted) == 1
    shared = router_state_root(state_a)
    starts = []
    for path in (shared / "project" / "events").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("payload", {}).get("action") == "started":
            starts.append(record)
    assert len(starts) == 1
    assert starts[0]["actor_id"] == winner.owner
    assert starts[0]["payload"]["claim_id"] == winner.claim_id
