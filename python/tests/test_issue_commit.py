"""Tests for issue commit workflow."""

from __future__ import annotations

import subprocess
from pathlib import Path

from kanbus.issue_commit import commit_project_issues


def _init_repo_with_project(tmp_path: Path) -> Path:
    root = tmp_path
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    issues_dir = root / "project" / "issues"
    events_dir = root / "project" / "events"
    issues_dir.mkdir(parents=True)
    events_dir.mkdir(parents=True)
    (issues_dir / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(
        ["git", "add", "project/issues"], cwd=root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / ".kanbus.yml").write_text("project_key: kanbus\n", encoding="utf-8")
    return root


def test_commit_project_issues_leaves_events_uncommitted(
    tmp_path: Path,
) -> None:
    root = _init_repo_with_project(tmp_path)
    (root / "project" / "issues" / "kanbus-test.json").write_text(
        '{"identifier":"kanbus-test","title":"Test"}',
        encoding="utf-8",
    )
    (root / "project" / "events" / "event-1.json").write_text(
        '{"event_id":"event-1"}',
        encoding="utf-8",
    )

    result = commit_project_issues(root)

    assert result.committed
    issues_status = subprocess.run(
        ["git", "status", "--porcelain", "--", "project/issues"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    staged_events = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "project/events"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    committed_files = subprocess.run(
        ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert not issues_status.stdout.strip()
    assert not staged_events.stdout.strip()
    assert all(
        path.startswith("project/issues/")
        for path in committed_files.stdout.splitlines()
        if path
    )
    assert (root / "project" / "events" / "event-1.json").is_file()
