"""Security boundary regressions for Issue Router adapters and publication."""

from __future__ import annotations

import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from kanbus import router_execution
from kanbus.coordination_mutex_api import MutexApiError
from kanbus.issue_router import RouterPlanEligiblePackage
from kanbus.models import MutexApiConfiguration, RouterForgeConfiguration
from kanbus.router_execution import IssueRouterError, _ClaimHandle
from kanbus.router_forge import ForgePullRequest, GitHubForge


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://mutex.example.test/api",
        "http://localhost:8888/api",
        "http://127.0.0.1:8888/api",
        "http://[::1]:8888/api",
    ],
)
def test_mutex_endpoint_allows_https_and_explicit_loopback_http(endpoint: str) -> None:
    assert MutexApiConfiguration(endpoint=endpoint).endpoint == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://mutex.example.test/api",
        "http://192.0.2.10/api",
        "http://localhost.example.test/api",
        "http://user@localhost/api",
        "https://@mutex.example.test/api",
    ],
)
def test_mutex_endpoint_rejects_cleartext_non_loopback_or_credentials(
    endpoint: str,
) -> None:
    with pytest.raises(ValidationError):
        MutexApiConfiguration(endpoint=endpoint)


@pytest.mark.parametrize(
    "api_url",
    [
        "https://api.github.com",
        "http://localhost:9000",
        "http://127.0.0.1:9000",
        "http://[::1]:9000",
    ],
)
def test_forge_api_url_allows_https_and_explicit_loopback_http(api_url: str) -> None:
    assert (
        RouterForgeConfiguration(repository="owner/repo", api_url=api_url).api_url
        == api_url
    )


@pytest.mark.parametrize(
    "api_url",
    [
        "http://api.github.com",
        "http://192.0.2.10",
        "http://user@localhost",
        "https://@api.github.com",
    ],
)
def test_forge_api_url_rejects_cleartext_non_loopback_or_credentials(
    api_url: str,
) -> None:
    with pytest.raises(ValidationError):
        RouterForgeConfiguration(repository="owner/repo", api_url=api_url)


def test_renewal_extension_keeps_a_fixed_horizon() -> None:
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    expiry = now + timedelta(seconds=240)

    extension = router_execution._lease_renewal_extension_seconds(expiry, now, 300)

    assert extension == 60
    assert expiry + timedelta(seconds=extension) == now + timedelta(seconds=300)
    assert (
        router_execution._lease_renewal_extension_seconds(
            now + timedelta(seconds=360), now, 300
        )
        == 0
    )


def test_capacity_acquisition_scans_all_slots_until_a_free_slot(
    monkeypatch, tmp_path
) -> None:
    context = SimpleNamespace(
        root=tmp_path,
        project_dir=tmp_path / "project",
        configuration=SimpleNamespace(
            coordination=SimpleNamespace(
                providers=["git"],
                mutex_api=None,
            )
        ),
        router=SimpleNamespace(
            limits=SimpleNamespace(project_wip=3, provider_wip={}, class_wip={})
        ),
    )
    candidate = RouterPlanEligiblePackage.model_validate(
        {
            "issue_id": "kbs-42",
            "route": {
                "kind": "provider",
                "name": "codex",
                "provider_profile": "codex",
            },
            "package_issue_ids": ["kbs-42"],
            "pending_since": "2026-09-17T12:00:00Z",
            "attempt": 1,
        }
    )
    acquired: list[str] = []

    def acquire_resource(_context, handles, resource, *_args, **_kwargs):
        acquired.append(resource)
        if resource in {"router:capacity:project:0", "router:capacity:project:1"}:
            raise router_execution.IssueRouterError("package already claimed")
        handles.append(
            _ClaimHandle("git", resource, "owner", "claim", None, revision=1)
        )

    monkeypatch.setattr(router_execution, "_acquire_router_resource", acquire_resource)

    handles = router_execution._acquire_claims(
        context,
        candidate,
        claim_id="claim",
        revision=1,
        owner="owner",
    )

    assert acquired[-3:] == [
        "router:capacity:project:0",
        "router:capacity:project:1",
        "router:capacity:project:2",
    ]
    assert handles[-1].resource == "router:capacity:project:2"


def test_hard_claim_conflict_does_not_persist_loser_or_mask_contention(
    monkeypatch, tmp_path
) -> None:
    context = SimpleNamespace(
        root=tmp_path,
        project_dir=tmp_path / "project",
        configuration=SimpleNamespace(
            coordination=SimpleNamespace(
                providers=["mutex_api", "mqtt", "git"],
                mutex_api=object(),
                default_lease_ttl="300s",
            )
        ),
        router=SimpleNamespace(
            limits=SimpleNamespace(project_wip=1, provider_wip={}, class_wip={})
        ),
    )
    candidate = RouterPlanEligiblePackage.model_validate(
        {
            "issue_id": "kbs-42",
            "route": {
                "kind": "provider",
                "name": "codex",
                "provider_profile": "codex",
            },
            "package_issue_ids": ["kbs-42"],
            "pending_since": "2026-09-17T12:00:00Z",
            "attempt": 1,
        }
    )
    mirrored_resources: list[str] = []
    acquired_resources: list[str] = []
    cleanup_resources: list[str] = []

    monkeypatch.setattr(router_execution, "mutex_is_configured", lambda _config: True)

    def acquire_mutex(_config, *, resource, **_kwargs):
        acquired_resources.append(resource)
        if resource == "router:issue:kbs-42":
            raise MutexApiError("already claimed", status=409)

    monkeypatch.setattr(router_execution, "mutex_acquire", acquire_mutex)
    monkeypatch.setattr(
        router_execution,
        "soft_claim",
        lambda _events, _config, *, resource, **_kwargs: mirrored_resources.append(
            resource
        ),
    )

    def fail_cleanup(_context, handles):
        cleanup_resources.extend(handle.resource for handle in handles)
        raise IssueRouterError("router coordination release failed")

    monkeypatch.setattr(router_execution, "_release_claims", fail_cleanup)

    with pytest.raises(IssueRouterError, match="package already claimed"):
        router_execution._acquire_claims(
            context,
            candidate,
            claim_id="claim-loser",
            revision=1,
            owner="worker-loser",
        )

    assert acquired_resources == ["router:scheduler", "router:issue:kbs-42"]
    assert mirrored_resources == ["router:scheduler"]
    assert cleanup_resources == ["router:scheduler", "router:scheduler"]


def test_hard_claims_renew_during_delayed_serial_resource_acquisition(
    monkeypatch, tmp_path
) -> None:
    context = SimpleNamespace(
        root=tmp_path,
        project_dir=tmp_path / "project",
        configuration=SimpleNamespace(
            coordination=SimpleNamespace(
                providers=["mutex_api", "mqtt", "git"],
                mutex_api=object(),
                default_lease_ttl="2s",
            )
        ),
        router=SimpleNamespace(
            limits=SimpleNamespace(
                project_wip=1,
                provider_wip={"codex": 1},
                class_wip={},
            )
        ),
    )
    candidate = RouterPlanEligiblePackage.model_validate(
        {
            "issue_id": "kbs-42",
            "route": {
                "kind": "provider",
                "name": "codex",
                "provider_profile": "codex",
            },
            "package_issue_ids": ["kbs-42"],
            "pending_since": "2026-09-17T12:00:00Z",
            "attempt": 1,
        }
    )
    monkeypatch.setattr(router_execution, "mutex_is_configured", lambda _config: True)
    monkeypatch.setattr(router_execution, "publish_router_state", lambda *_args: None)

    expirations: dict[str, datetime] = {}
    package_renewed_during_capacity_acquire = threading.Event()
    capacity_acquisition_active = threading.Event()
    capacity_acquisition_done = threading.Event()

    def acquire_resource(
        _context,
        handles,
        resource,
        owner,
        claim_id,
        revision,
        hard,
        **_kwargs,
    ):
        assert hard
        if resource.startswith("router:capacity:"):
            capacity_acquisition_active.set()
            time.sleep(1.1)
        handles.append(
            _ClaimHandle("mutex_api", resource, owner, claim_id, None, revision)
        )
        expirations[resource] = datetime.now(UTC) + timedelta(seconds=2)
        if resource == "router:capacity:provider-profile:codex:0":
            capacity_acquisition_done.set()

    def inspect_mutex(_config, *, resource):
        return SimpleNamespace(
            resource=resource,
            owner="worker-a",
            claim_id="claim-a",
            revision=1,
            expires_at=expirations[resource],
        )

    def renew_mutex(_config, *, resource, owner, claim_id, extend_seconds):
        assert owner == "worker-a"
        assert claim_id == "claim-a"
        expirations[resource] += timedelta(seconds=extend_seconds)
        if (
            resource == "router:issue:kbs-42"
            and capacity_acquisition_active.is_set()
            and not capacity_acquisition_done.is_set()
        ):
            package_renewed_during_capacity_acquire.set()
        return inspect_mutex(None, resource=resource)

    monkeypatch.setattr(router_execution, "_acquire_router_resource", acquire_resource)
    monkeypatch.setattr(router_execution, "mutex_inspect", inspect_mutex)
    monkeypatch.setattr(router_execution, "mutex_renew", renew_mutex)

    renewal_handles: list[_ClaimHandle] = []
    renewal_stop = None
    renewal_thread = None

    def update_renewal_handles(handles: list[_ClaimHandle]) -> None:
        nonlocal renewal_stop, renewal_thread
        renewal_handles[:] = [
            handle for handle in handles if handle.resource != "router:scheduler"
        ]
        if renewal_thread is None and any(
            handle.resource.startswith("router:issue:") for handle in renewal_handles
        ):
            renewal_stop, renewal_thread = router_execution._start_lease_renewer(
                context, renewal_handles, "claim-a", initial_pass=True
            )

    try:
        router_execution._acquire_claims(
            context,
            candidate,
            claim_id="claim-a",
            revision=1,
            owner="worker-a",
            on_handles_updated=update_renewal_handles,
        )
        assert package_renewed_during_capacity_acquire.wait(1.0)
        assert capacity_acquisition_done.is_set()
        assert expirations["router:issue:kbs-42"] > datetime.now(UTC)
    finally:
        if renewal_stop is not None:
            renewal_stop.set()
        if renewal_thread is not None:
            renewal_thread.join(timeout=2)
        router_execution._RENEWAL_ERRORS.pop("claim-a", None)


def test_router_start_fence_rejects_loser_selected_by_mqtt(
    monkeypatch, tmp_path
) -> None:
    context = SimpleNamespace(
        project_dir=tmp_path / "project",
        configuration=SimpleNamespace(
            coordination=SimpleNamespace(providers=["mqtt", "git"])
        ),
    )
    own_claim = SimpleNamespace(
        active=True, owner="worker-loser", claim_id="claim-loser"
    )
    mqtt_winner = SimpleNamespace(
        active=True, owner="worker-winner", claim_id="claim-winner"
    )
    monkeypatch.setattr(
        router_execution, "inspect_lease", lambda *_args, **_kwargs: own_claim
    )
    monkeypatch.setattr(
        "kanbus.coordination_mqtt.inspect_lease",
        lambda *_args, **_kwargs: mqtt_winner,
    )

    with pytest.raises(IssueRouterError, match="package already claimed"):
        router_execution._validate_router_start_claim(
            context,
            tmp_path / "shared-events",
            "kbs-42",
            "worker-loser",
            "claim-loser",
            4,
            _ClaimHandle(
                "mqtt",
                "router:issue:kbs-42",
                "worker-loser",
                "claim-loser",
                None,
                revision=4,
            ),
        )


@pytest.mark.parametrize("rename_into_state", [False, True])
def test_worktree_guard_honors_custom_project_directory_and_rename_paths(
    monkeypatch, tmp_path, rename_into_state: bool
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    def git(*arguments: str) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=worktree,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "-b", "main")
    git("config", "user.name", "Router test")
    git("config", "user.email", "router-test@example.invalid")
    (worktree / "app").mkdir()
    (worktree / "app" / "README.md").write_text("app\n", encoding="utf-8")
    (worktree / "board-data").mkdir()
    (worktree / "board-data" / "issue.json").write_text("{}\n", encoding="utf-8")
    git("add", "app/README.md", "board-data/issue.json")
    git("commit", "-m", "fixture")
    if rename_into_state:
        git("mv", "app/README.md", "board-data/renamed.json")
    else:
        git("mv", "board-data/issue.json", "app/renamed.json")
    monkeypatch.setitem(router_execution._WORKTREE_PATHS, "claim", worktree)

    with pytest.raises(
        router_execution.IssueRouterError,
        match="may not modify Kanbus project state directly",
    ):
        router_execution._validate_worktree_changes("board-data", "claim")


def test_worktree_guard_allows_application_edits_outside_configured_state(
    monkeypatch, tmp_path
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    )
    (worktree / "app").mkdir()
    (worktree / "app" / "README.md").write_text("changed\n", encoding="utf-8")
    monkeypatch.setitem(router_execution._WORKTREE_PATHS, "claim", worktree)

    router_execution._validate_worktree_changes("board-data", "claim")


def test_pr_publication_rolls_back_branch_if_claim_is_lost_after_api_call(
    monkeypatch, tmp_path
) -> None:
    root = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    root.mkdir()
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Router test")
    git("config", "user.email", "router-test@example.invalid")
    git("remote", "add", "origin", str(remote))
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-m", "base")
    base_sha = git("rev-parse", "HEAD")
    branch = "codex/router/kbs-42/r1"
    git("update-ref", f"refs/heads/{branch}", base_sha)
    git("push", "origin", f"refs/heads/{branch}:refs/heads/{branch}")
    (root / "README.md").write_text("router change\n", encoding="utf-8")
    git("commit", "-am", "router change")
    published_sha = git("rev-parse", "HEAD")
    git("update-ref", f"refs/heads/{branch}", published_sha)

    class RacingForge(GitHubForge):
        def create_or_observe_pull_request(self, **_kwargs):
            return ForgePullRequest(
                number=42,
                url="https://github.example/pull/42",
                head_branch=branch,
                head_sha=published_sha,
                state="open",
                merged=False,
            )

    forge = RacingForge(repository="owner/repo", token="test")
    router_configuration = SimpleNamespace(
        forge=SimpleNamespace(repository="owner/repo", base_branch="main")
    )
    context = SimpleNamespace(
        root=root,
        project_dir=root / "project",
        router=router_configuration,
        issues=[SimpleNamespace(identifier="kbs-42", title="Router task")],
    )
    candidate = RouterPlanEligiblePackage.model_validate(
        {
            "issue_id": "kbs-42",
            "route": {
                "kind": "provider",
                "name": "codex",
                "provider_profile": "codex",
            },
            "package_issue_ids": ["kbs-42"],
            "pending_since": "2026-09-17T12:00:00Z",
            "attempt": 1,
        }
    )
    monkeypatch.setattr(router_execution, "_FAKE_FORGE", None)
    monkeypatch.setattr(
        GitHubForge,
        "from_configuration",
        classmethod(lambda _cls, _configuration: forge),
    )
    monkeypatch.setitem(router_execution._WORKTREE_BRANCHES, "claim", branch)
    monkeypatch.setitem(router_execution._WORKTREE_HEADS, "claim", published_sha)
    monkeypatch.setattr(router_execution, "record_router_event", lambda *_a, **_k: None)
    monkeypatch.setattr(
        router_execution, "publish_router_state", lambda *_a, **_k: None
    )
    checks = []

    def fence(_context, _package_id, claim_id, revision):
        assert claim_id == "claim"
        assert revision == 7
        checks.append(True)
        if len(checks) == 4:
            raise router_execution.IssueRouterError("stale package claim")

    monkeypatch.setattr(router_execution, "_assert_claim_fence", fence)

    with pytest.raises(router_execution.IssueRouterError, match="stale package claim"):
        router_execution._open_pull_request(
            context, candidate, None, claim_id="claim", revision=7
        )

    observed = subprocess.run(
        ["git", "ls-remote", "origin", f"refs/heads/{branch}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[0]
    assert observed == base_sha
    assert checks == [True, True, True, True]
