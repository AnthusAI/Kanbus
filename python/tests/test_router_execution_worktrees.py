"""Isolation and recovery tests for router-owned Git worktrees."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus.issue_router import IssueRouterError
from kanbus.router_conversation import record_conversation
from kanbus.router_execution import (
    _commit_isolated_worktree,
    _create_isolated_worktree,
    _worktree_base_commit,
    recover_router_package,
)
import kanbus.router_execution as router_execution


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _initialized_repository(root: Path) -> None:
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.name", "Router Worktree Test")
    _git(root, "config", "user.email", "router-worktree@example.invalid")
    (root / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "initial")


def test_unborn_repository_snapshot_uses_private_index(tmp_path):
    _git(tmp_path, "init", "--initial-branch=main")
    (tmp_path / "source.txt").write_text("snapshot contents\n", encoding="utf-8")
    metadata = tmp_path / ".git" / "kanbus" / "router" / "worktrees"
    metadata.mkdir(parents=True)

    snapshot = _worktree_base_commit(tmp_path, metadata)

    assert _git(tmp_path, "show", f"{snapshot}:source.txt") == "snapshot contents"
    assert _git(tmp_path, "rev-parse", "--verify", "HEAD", check=False) == ""
    assert not list(metadata.glob("snapshot-*.index"))


def test_isolated_worktree_reuses_router_branch_only_under_managed_root(tmp_path):
    _initialized_repository(tmp_path)
    context = SimpleNamespace(root=tmp_path)

    first = _create_isolated_worktree(context, "kbs-1", "claim-1", 1)
    (first / "router-change.txt").write_text("work\n", encoding="utf-8")
    _commit_isolated_worktree(first, "project", "kbs-1", 1)
    first_commit = _git(first, "rev-parse", "HEAD")

    second = _create_isolated_worktree(context, "kbs-1", "claim-2", 1)

    assert second != first
    assert _git(second, "branch", "--show-current") == "codex/router/kbs-1/r1"
    assert _git(second, "rev-parse", "HEAD") == first_commit
    assert _git(second, "log", "-1", "--format=%s") == "[kbs-1] router checkpoint r1"


def test_router_refuses_to_detach_same_branch_from_user_worktree(tmp_path):
    _initialized_repository(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-user-worktree"
    branch = "codex/router/kbs-outside/r1"
    try:
        _git(tmp_path, "worktree", "add", "-b", branch, str(outside), "HEAD")
        context = SimpleNamespace(root=tmp_path)

        with pytest.raises(
            IssueRouterError, match="checked out outside its managed worktree"
        ):
            _create_isolated_worktree(
                context, "kbs-outside", "claim-1", 1, branch=branch
            )
    finally:
        if outside.exists():
            _git(tmp_path, "worktree", "remove", "--force", str(outside))


def test_isolated_checkpoint_noop_and_user_changes_are_committed(tmp_path):
    _initialized_repository(tmp_path)
    initial = _git(tmp_path, "rev-parse", "HEAD")

    _commit_isolated_worktree(tmp_path, "project", "kbs-1", 4)
    assert _git(tmp_path, "log", "-1", "--format=%s") == "[kbs-1] router checkpoint r4"
    empty_checkpoint = _git(tmp_path, "rev-parse", "HEAD")
    assert _git(tmp_path, "rev-parse", "HEAD^") == initial

    (tmp_path / "untracked.txt").write_text("agent output\n", encoding="utf-8")
    _commit_isolated_worktree(tmp_path, "project", "kbs-1", 4)

    assert _git(tmp_path, "log", "-1", "--format=%s") == "[kbs-1] router checkpoint r4"
    assert _git(tmp_path, "rev-parse", "HEAD^") == empty_checkpoint
    assert _git(tmp_path, "show", "HEAD:untracked.txt") == "agent output"


def test_isolated_checkpoint_excludes_ignored_router_events(tmp_path):
    _initialized_repository(tmp_path)
    (tmp_path / ".gitignore").write_text("project/events/\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore")
    _git(tmp_path, "commit", "-m", "ignore router events")
    (tmp_path / "tracked.txt").write_text("agent change\n", encoding="utf-8")
    (tmp_path / "new_agent_test.py").write_text("assert True\n", encoding="utf-8")
    event_path = tmp_path / "project" / "events" / "router.jsonl"
    event_path.parent.mkdir(parents=True)
    event_path.write_text("router event\n", encoding="utf-8")

    _commit_isolated_worktree(tmp_path, "project", "kbs-1", 5)

    assert _git(tmp_path, "show", "HEAD:tracked.txt") == "agent change"
    assert _git(tmp_path, "show", "HEAD:new_agent_test.py") == "assert True"
    assert _git(tmp_path, "status", "--porcelain") == ""


def test_recovering_preserved_turn_publishes_one_visible_issue_summary(
    tmp_path, monkeypatch
):
    """Recovery must make old preserved work visible, rather than merely mark it handled."""
    project_dir = tmp_path / "project"
    (project_dir / "events").mkdir(parents=True)
    issue_id = "kbs-recovered"
    record_conversation(
        project_dir,
        issue_id,
        action="agent_turn",
        provider="codex",
        claim_id="claim-recovered",
        revision=3,
        session_id="session-recovered",
        lifecycle="review",
        branch="codex/router/kbs-recovered/r3",
        worktree="/tmp/kbs-recovered",
    )
    context = SimpleNamespace(
        root=tmp_path,
        source_root=None,
        project_dir=project_dir,
        issues=[SimpleNamespace(identifier=issue_id, parent=None)],
        router=SimpleNamespace(
            workflow=SimpleNamespace(review="review", blocked="blocked")
        ),
    )
    comments: list[tuple[str, str, str]] = []
    transitions: list[tuple[str, str]] = []
    monkeypatch.setattr(
        router_execution,
        "add_issue_comment",
        lambda _root, package, author, text: comments.append((package, author, text)),
    )
    monkeypatch.setattr(
        router_execution,
        "_transition_package",
        lambda _context, package, status, **_kwargs: transitions.append(
            (package, status)
        ),
    )
    monkeypatch.setattr(
        router_execution, "publish_router_state", lambda *_args, **_kwargs: None
    )

    recovered = recover_router_package(context, issue_id)
    recover_router_package(context, issue_id)

    assert recovered["session_id"] == "session-recovered"
    assert transitions == [(issue_id, "review"), (issue_id, "review")]
    assert len(comments) == 1
    assert comments[0][0:2] == (issue_id, "Kanbus Issue Router")
    assert "## Agent run recovered" in comments[0][2]
    assert "`session-recovered`" in comments[0][2]


def test_router_comment_does_not_trigger_unrelated_ai_summary_work(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(
        router_execution,
        "_add_issue_comment",
        lambda *_args, **kwargs: calls.append(kwargs),
    )

    router_execution.add_issue_comment(
        Path("/repo"), "kbs-router", "Kanbus Issue Router", "evidence"
    )

    assert calls == [{"regenerate_right_now": False}]
