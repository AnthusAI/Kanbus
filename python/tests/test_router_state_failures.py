"""Local-only router state lifecycle and fail-closed Git tests."""

from __future__ import annotations

import copy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.event_history import create_event
from kanbus.issue_router import IssueRouterError
from kanbus.router_state import (
    REMOTE_REF,
    _fetch_state,
    _merge_ref,
    publish_router_start_event,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _init_local_project(root: Path) -> None:
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.name", "Router State Test")
    _git(root, "config", "user.email", "router-state-test@example.invalid")
    project_dir = root / "project"
    (project_dir / "issues").mkdir(parents=True)
    (project_dir / "events").mkdir()
    (root / ".kanbus.yml").write_text(
        yaml.safe_dump(copy.deepcopy(DEFAULT_CONFIGURATION), sort_keys=False),
        encoding="utf-8",
    )
    _git(root, "add", ".kanbus.yml", "project")
    _git(root, "commit", "-m", "initial local project")


def test_start_event_is_published_locally_without_a_remote(tmp_path: Path) -> None:
    _init_local_project(tmp_path)
    event = create_event(
        issue_id="router:kbs-local",
        event_type="router.attempt",
        actor_id="worker-local",
        payload={
            "action": "started",
            "attempt": 1,
            "claim_id": "claim-local",
            "revision": 3,
            "provider_profile": "test-provider",
            "package_issue_ids": ["kbs-local"],
        },
    )
    validations = []

    def validate_claim(events_dir: Path) -> None:
        validations.append(events_dir)

    published = publish_router_start_event(
        tmp_path, event, validate_claim=validate_claim
    )

    assert published
    assert len(validations) == 1
    assert _git(tmp_path, "branch", "--show-current") == "main"
    assert _git(tmp_path, "rev-parse", "refs/heads/kanbus/router-state") == published
    state_root = tmp_path / ".git" / "kanbus-router-state-worktree"
    stored_events = list((state_root / "project" / "events").glob("*.json"))
    assert len(stored_events) == 1
    assert '"action": "started"' in stored_events[0].read_text(encoding="utf-8")


def test_state_fetch_failure_is_reported_without_prompting_for_credentials(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed_env = {}

    def fail_ls_remote(*_args, **kwargs):
        observed_env.update(kwargs["env"])
        raise subprocess.CalledProcessError(
            128, "git ls-remote", stderr="private detail"
        )

    monkeypatch.setattr(
        "kanbus.router_state._try_git",
        lambda _root, *args, **_kwargs: (
            "origin-url" if args == ("remote", "get-url", "origin") else None
        ),
    )
    monkeypatch.setattr("kanbus.router_state.subprocess.run", fail_ls_remote)

    with pytest.raises(
        IssueRouterError, match="could not fetch shared router state"
    ) as error:
        _fetch_state(tmp_path)

    assert observed_env["GIT_TERMINAL_PROMPT"] == "0"
    assert "private detail" not in str(error.value)


def test_state_fetch_failure_after_advertisement_is_closed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "kanbus.router_state._try_git",
        lambda _root, *args, **_kwargs: (
            "origin-url" if args == ("remote", "get-url", "origin") else 1
        ),
    )
    monkeypatch.setattr(
        "kanbus.router_state.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=f"abc123 {REMOTE_REF}\n"),
    )

    with pytest.raises(IssueRouterError, match="could not fetch shared router state"):
        _fetch_state(tmp_path)


def test_reconciliation_conflict_aborts_merge_and_prevents_router_start(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands = []

    def fail_merge(args, **kwargs):
        commands.append((args, kwargs))
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="CONFLICT in project/issues/kbs-1.json",
        )

    def record_abort(_root, *args, capture=False):
        commands.append((args, capture))
        return 0

    monkeypatch.setattr("kanbus.router_state.subprocess.run", fail_merge)
    monkeypatch.setattr("kanbus.router_state._try_git", record_abort)

    with pytest.raises(IssueRouterError, match="no package was started") as error:
        _merge_ref(tmp_path, REMOTE_REF)

    assert "CONFLICT in project/issues/kbs-1.json" in str(error.value)
    assert "-X" in commands[0][0]
    assert "theirs" in commands[0][0]
    assert commands[1] == (("merge", "--abort"), True)
