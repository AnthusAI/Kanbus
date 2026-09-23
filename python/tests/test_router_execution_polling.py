"""Tests for production polling of router-owned pull request state."""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from datetime import UTC, datetime

from kanbus import router_execution
from kanbus.router_forge import FakeForge, GitHubForge


def test_reconcile_pull_requests_polls_and_records_completed_check_runs(
    monkeypatch, tmp_path
) -> None:
    forge = FakeForge()
    forge.pull_requests[42] = {
        "number": 42,
        "url": "https://github.example/pull/42",
        "head_branch": "codex/router/kbs-42/r1",
        "head_sha": "head-abc",
        "state": "open",
        "merged": False,
        "title": "router change",
        "body": "router result",
    }
    forge.check_runs[(42, "head-abc")] = [
        {
            "id": 7001,
            "status": "completed",
            "conclusion": "failure",
        },
        {"id": 7002, "status": "in_progress", "conclusion": None},
    ]
    router_configuration = SimpleNamespace(
        forge=SimpleNamespace(repository="owner/repo")
    )
    context = SimpleNamespace(
        router=router_configuration,
        project_dir=tmp_path / "project",
    )
    context.project_dir.mkdir()

    recorded = []
    monkeypatch.setattr(router_execution, "_FAKE_FORGE", forge)
    monkeypatch.setattr(
        router_execution,
        "_read_events",
        lambda _path: [
            {
                "event_type": "router_pull_request_opened",
                "issue_id": "router:kbs-42",
                "payload": {"number": 42, "head_sha": "head-abc"},
            }
        ],
    )
    monkeypatch.setattr(
        router_execution,
        "record_github_check_run_event",
        lambda project_dir, config, payload, **_kwargs: recorded.append(
            (project_dir, config, payload)
        ),
    )

    router_execution._reconcile_pull_requests(context)

    assert len(recorded) == 1
    assert recorded[0][0] == context.project_dir
    assert recorded[0][1] is router_configuration
    assert recorded[0][2] == {
        "schema_version": 1,
        "event_id": "check-run:7001:head-abc",
        "kind": "check_run",
        "action": "completed",
        "repository": "owner/repo",
        "number": 42,
        "head_sha": "head-abc",
        "conclusion": "failure",
    }


def test_reconciliation_polls_latest_review_and_latest_check_per_name(
    monkeypatch, tmp_path
) -> None:
    forge = FakeForge()
    forge.pull_requests[42] = {
        "number": 42,
        "url": "https://github.example/pull/42",
        "head_branch": "codex/router/kbs-42/r1",
        "head_sha": "head-abc",
        "state": "open",
        "merged": False,
    }
    forge.pull_request_reviews[42] = [
        {
            "id": 100,
            "user": {"login": "alice"},
            "state": "APPROVED",
            "commit_id": "head-abc",
            "submitted_at": "2026-09-17T12:00:00Z",
        },
        {
            "id": 101,
            "user": {"login": "bob"},
            "state": "CHANGES_REQUESTED",
            "commit_id": "head-abc",
            "submitted_at": "2026-09-17T12:01:00Z",
        },
        {
            "id": 102,
            "user": {"login": "charlie"},
            "state": "APPROVED",
            "commit_id": "old-head",
            "submitted_at": "2026-09-17T12:02:00Z",
        },
    ]
    forge.check_runs[(42, "head-abc")] = [
        {
            "id": 7001,
            "name": "unit-tests",
            "status": "completed",
            "conclusion": "failure",
            "completed_at": "2026-09-17T12:00:00Z",
            "head_sha": "head-abc",
        },
        {
            "id": 7002,
            "name": "unit-tests",
            "status": "completed",
            "conclusion": "success",
            "completed_at": "2026-09-17T12:01:00Z",
            "head_sha": "head-abc",
        },
        {
            "id": 7003,
            "name": "lint",
            "status": "completed",
            "conclusion": "failure",
            "completed_at": "2026-09-17T12:01:00Z",
            "head_sha": "head-abc",
        },
        {
            "id": 7004,
            "name": "lint",
            "status": "completed",
            "conclusion": "success",
            "completed_at": "2026-09-17T12:00:00Z",
            "head_sha": "head-abc",
        },
    ]
    router_configuration = SimpleNamespace(
        forge=SimpleNamespace(repository="owner/repo")
    )
    context = SimpleNamespace(
        router=router_configuration,
        project_dir=tmp_path / "project",
    )
    context.project_dir.mkdir()
    monkeypatch.setattr(router_execution, "_FAKE_FORGE", forge)
    monkeypatch.setattr(
        router_execution,
        "_read_events",
        lambda _path: [
            {
                "event_type": "router_pull_request_opened",
                "issue_id": "router:kbs-42",
                "payload": {"number": 42, "head_sha": "head-abc"},
            }
        ],
    )
    pull_events = []
    check_events = []
    monkeypatch.setattr(
        router_execution,
        "record_github_pull_request_event",
        lambda _project, _config, payload, **_kwargs: pull_events.append(payload),
    )
    monkeypatch.setattr(
        router_execution,
        "record_github_check_run_event",
        lambda _project, _config, payload, **_kwargs: check_events.append(payload),
    )

    router_execution._reconcile_pull_requests(context)

    assert len(pull_events) == 1
    assert pull_events[0]["action"] == "requested_changes"
    assert pull_events[0]["event_id"].startswith("poll:review:42:head-abc:101:")
    assert [event["event_id"] for event in check_events] == [
        "check-run:7003:head-abc",
        "check-run:7002:head-abc",
    ]
    assert [event["conclusion"] for event in check_events] == ["failure", "success"]


def test_newer_approval_from_another_reviewer_does_not_clear_changes_request(
    monkeypatch, tmp_path
) -> None:
    forge = FakeForge()
    forge.pull_requests[42] = {
        "number": 42,
        "url": "https://github.example/pull/42",
        "head_branch": "codex/router/kbs-42/r1",
        "head_sha": "head-abc",
        "state": "open",
        "merged": False,
    }
    forge.pull_request_reviews[42] = [
        {
            "id": 101,
            "user": {"login": "alice"},
            "state": "CHANGES_REQUESTED",
            "commit_id": "head-abc",
            "submitted_at": "2026-09-17T12:00:00Z",
        },
        {
            "id": 102,
            "user": {"login": "bob"},
            "state": "APPROVED",
            "commit_id": "head-abc",
            "submitted_at": "2026-09-17T12:01:00Z",
        },
    ]
    context = SimpleNamespace(
        router=SimpleNamespace(forge=SimpleNamespace(repository="owner/repo")),
        project_dir=tmp_path / "project",
    )
    context.project_dir.mkdir()
    monkeypatch.setattr(router_execution, "_FAKE_FORGE", forge)
    monkeypatch.setattr(
        router_execution,
        "_read_events",
        lambda _path: [
            {
                "event_type": "router_pull_request_opened",
                "issue_id": "router:kbs-42",
                "payload": {"number": 42, "head_sha": "head-abc"},
            }
        ],
    )
    events = []
    monkeypatch.setattr(
        router_execution,
        "record_github_pull_request_event",
        lambda _project, _config, payload, **_kwargs: events.append(payload),
    )

    router_execution._reconcile_pull_requests(context)

    assert len(events) == 1
    assert events[0]["action"] == "requested_changes"
    assert events[0]["event_id"].startswith("poll:review:42:head-abc:101:")


def test_github_reviews_and_check_runs_poll_every_api_page(monkeypatch) -> None:
    forge = GitHubForge(repository="owner/repo", token="test")
    requests = []

    def request(_method, path, *, params=None, payload=None):
        del payload
        requests.append((path, params))
        page = int(params["page"])
        if path.endswith("/reviews"):
            return [
                {"id": page * 100 + index} for index in range(100 if page == 1 else 1)
            ]
        return {
            "check_runs": [
                {"id": page * 100 + index} for index in range(100 if page == 1 else 1)
            ]
        }

    monkeypatch.setattr(forge, "_request", request)

    reviews = forge.list_pull_request_reviews(42)
    check_runs = forge.list_check_runs(42, "head-abc")

    assert len(reviews) == len(check_runs) == 101
    assert requests == [
        ("/repos/owner/repo/pulls/42/reviews", {"per_page": "100", "page": "1"}),
        ("/repos/owner/repo/pulls/42/reviews", {"per_page": "100", "page": "2"}),
        (
            "/repos/owner/repo/commits/head-abc/check-runs",
            {"per_page": "100", "page": "1"},
        ),
        (
            "/repos/owner/repo/commits/head-abc/check-runs",
            {"per_page": "100", "page": "2"},
        ),
    ]


def test_reconciliation_rechecks_scheduler_before_recording_review(
    monkeypatch, tmp_path
) -> None:
    forge = FakeForge()
    forge.pull_requests[42] = {
        "number": 42,
        "url": "https://github.example/pull/42",
        "head_branch": "codex/router/kbs-42/r1",
        "head_sha": "head-abc",
        "state": "open",
        "merged": False,
    }
    forge.pull_request_reviews[42] = [
        {
            "id": 101,
            "state": "APPROVED",
            "commit_id": "head-abc",
            "submitted_at": "2026-09-17T12:01:00Z",
        }
    ]
    context = SimpleNamespace(
        router=SimpleNamespace(forge=SimpleNamespace(repository="owner/repo")),
        project_dir=tmp_path / "project",
    )
    context.project_dir.mkdir()
    monkeypatch.setattr(router_execution, "_FAKE_FORGE", forge)
    monkeypatch.setattr(
        router_execution,
        "_read_events",
        lambda _path: [
            {
                "event_type": "router_pull_request_opened",
                "issue_id": "router:kbs-42",
                "payload": {"number": 42, "head_sha": "head-abc"},
            }
        ],
    )
    fences = []
    recorded = []

    def assert_scheduler(_context, _handles):
        fences.append("checked")
        if len(fences) == 2:
            raise router_execution.IssueRouterError("stale router scheduler claim")

    def record_review(_project, _configuration, payload, *, before_mutation):
        before_mutation()
        recorded.append(payload)

    monkeypatch.setattr(router_execution, "_assert_scheduler_claim", assert_scheduler)
    monkeypatch.setattr(
        router_execution, "record_github_pull_request_event", record_review
    )

    with pytest.raises(
        router_execution.IssueRouterError, match="stale router scheduler"
    ):
        router_execution._reconcile_pull_requests(context, [object()])

    assert recorded == []


def test_pr_event_fences_issue_mutation_after_event_append(monkeypatch, tmp_path):
    from kanbus import router_forge
    from kanbus.router_forge import record_github_pull_request_event

    root = tmp_path
    (root / ".kanbus.yml").write_text("configuration: {}\n", encoding="utf-8")
    project_dir = root / "project"
    project_dir.mkdir()
    issue = SimpleNamespace(identifier="kbs-42", status="active")
    router_configuration = SimpleNamespace(
        forge=SimpleNamespace(repository="owner/repo"),
        workflow=SimpleNamespace(
            active="active",
            review="review",
            blocked="blocked",
            terminal=["closed"],
        ),
    )
    monkeypatch.setattr(
        router_forge,
        "_all_router_events",
        lambda _project: [
            {
                "event_type": "router_pull_request_opened",
                "issue_id": "router:kbs-42",
                "event_id": "opened-event",
                "payload": {
                    "number": 42,
                    "head_sha": "head-abc",
                    "repository": "owner/repo",
                },
            }
        ],
    )
    monkeypatch.setattr(
        router_forge,
        "load_router_context",
        lambda _root: SimpleNamespace(
            router=router_configuration,
            issues=[issue],
        ),
    )
    appended = []
    monkeypatch.setattr(
        router_forge,
        "record_router_event",
        lambda *args, **kwargs: appended.append((args, kwargs)),
    )
    issue_updates = []
    monkeypatch.setattr(
        router_forge,
        "update_issue",
        lambda *_args, **_kwargs: issue_updates.append(True),
    )
    monkeypatch.setattr(
        "kanbus.router_state.publish_router_state", lambda *_args, **_kwargs: None
    )
    checks = []

    def before_mutation():
        checks.append(True)
        if len(checks) == 2:
            raise router_forge.IssueRouterError("stale scheduler claim")

    with pytest.raises(router_forge.IssueRouterError, match="stale scheduler claim"):
        record_github_pull_request_event(
            project_dir,
            router_configuration,
            {
                "schema_version": 1,
                "event_id": "review-event",
                "kind": "pull_request",
                "action": "approved",
                "repository": "owner/repo",
                "number": 42,
                "head_sha": "head-abc",
                "merged": False,
            },
            before_mutation=before_mutation,
        )

    assert len(appended) == 1
    assert issue_updates == []


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(0, 30), (1, 30), (2, 60), (3, 120), (6, 900), (10, 900)],
)
def test_retry_delay_is_exponential_and_capped(attempt, expected):
    assert router_execution.retry_delay_seconds(attempt) == expected


def test_checkpoint_and_attempt_reducers_select_latest_durable_decision():
    events = [
        {
            "event_type": "router_checkpoint_accepted",
            "occurred_at": "2026-09-17T12:00:00Z",
            "event_id": "checkpoint-1",
            "payload": {"ref": "refs/checkpoint/old", "revision": 1},
        },
        {
            "event_type": "router_checkpoint_accepted",
            "occurred_at": "2026-09-17T12:01:00Z",
            "event_id": "checkpoint-2",
            "payload": {"ref": "refs/checkpoint/new", "revision": 2},
        },
        {
            "event_type": "router_retry_scheduled",
            "occurred_at": "2026-09-17T12:02:00Z",
            "event_id": "retry-1",
            "payload": {"next_attempt": 2},
        },
        {
            "event_type": "router_retry_scheduled",
            "occurred_at": "2026-09-17T12:03:00Z",
            "event_id": "retry-2",
            "payload": {"next_attempt": 3},
        },
    ]

    assert router_execution._accepted_checkpoint(events) == "refs/checkpoint/new"
    assert router_execution._accepted_checkpoint_revision(events) == 2
    assert router_execution._attempt_for_claim(events) == 3
    assert router_execution._accepted_checkpoint([]) is None
    assert router_execution._accepted_checkpoint_revision([]) is None
    assert router_execution._attempt_for_claim([]) == 1


def test_claim_reducer_requires_an_unended_current_claim():
    claim = {
        "event_type": "router_claimed",
        "issue_id": "router:kbs-42",
        "event_id": "claim-1",
        "occurred_at": "2026-09-17T12:00:00Z",
        "payload": {"claim_id": "claim-1", "revision": 1},
    }
    assert router_execution._claim_is_active([claim], "kbs-42") is True
    assert router_execution._claim_is_active([], "kbs-42") is False
    assert (
        router_execution._claim_is_active(
            [
                claim,
                {
                    "event_type": "router_retry_scheduled",
                    "issue_id": "router:kbs-42",
                    "event_id": "retry-1",
                    "occurred_at": "2026-09-17T12:01:00Z",
                    "payload": {"claim_id": "claim-1"},
                },
            ],
            "kbs-42",
        )
        is False
    )


def test_package_resolution_uses_nearest_routed_ancestor(monkeypatch):
    root = SimpleNamespace(
        identifier="kbs-root",
        parent=None,
        labels=["agent-class:review"],
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
    )
    child = SimpleNamespace(identifier="kbs-child", parent="kbs-root", labels=[])
    context = SimpleNamespace(
        issues=[root, child],
        router=SimpleNamespace(
            classes={"review": SimpleNamespace(providers=["codex"])}
        ),
    )
    assert router_execution._resolve_package_id(context, "kbs-child") == "kbs-root"
    assert router_execution._resolve_package_id(context, "kbs-root") == "kbs-root"

    monkeypatch.setattr(
        router_execution,
        "build_router_plan",
        lambda _context: SimpleNamespace(eligible=[]),
    )
    candidate = router_execution._candidate_for_package(context, "kbs-root", None)
    assert candidate.route.kind == "class"
    assert candidate.route.provider_profile == "codex"
    assert candidate.package_issue_ids == ["kbs-root"]
