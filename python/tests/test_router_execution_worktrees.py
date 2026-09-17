"""Isolation and recovery tests for router-owned Git worktrees."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus.issue_router import IssueRouterError
from kanbus.router_execution import (
    _commit_isolated_worktree,
    _create_isolated_worktree,
    _worktree_base_commit,
)


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
    _commit_isolated_worktree(first, "kbs-1", 1)
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

    _commit_isolated_worktree(tmp_path, "kbs-1", 4)
    assert _git(tmp_path, "log", "-1", "--format=%s") == "initial"

    (tmp_path / "untracked.txt").write_text("agent output\n", encoding="utf-8")
    _commit_isolated_worktree(tmp_path, "kbs-1", 4)

    assert _git(tmp_path, "log", "-1", "--format=%s") == "[kbs-1] router checkpoint r4"
    assert _git(tmp_path, "show", "HEAD:untracked.txt") == "agent output"
