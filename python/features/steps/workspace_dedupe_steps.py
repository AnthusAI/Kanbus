"""Behave steps for workspace issue deduplication scenarios."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from behave import given, then

from features.steps.shared import (
    build_issue,
    ensure_git_repository,
    read_issue_file,
    write_default_kanbus_config,
    write_issue_file,
)
from kanbus.ids import format_issue_key

DEDUP_IDENTIFIER = "kanbus-dedup"
DEDUP_TITLE = "Deduped work"
DEDUP_EDITED_TITLE = "Worktree edited copy"
TIE_IDENTIFIER = "kanbus-tie"
TIE_ALPHA_TITLE = "Tie copy alpha"
TIE_ZETA_TITLE = "Tie copy zeta"


def _git(arguments: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _commit_all(repo: Path) -> None:
    _git(["add", "-A"], cwd=repo)
    _git(
        [
            "-c",
            "user.name=Kanbus Spec",
            "-c",
            "user.email=spec@kanbus.local",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=repo,
    )


def _add_worktree(workspace: Path, repo: Path, name: str) -> Path:
    worktree = workspace / name
    _git(["worktree", "add", str(worktree)], cwd=repo)
    return worktree


def _write_project_issue(project_dir: Path, identifier: str, title: str) -> None:
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    issue = build_issue(identifier, title, "task", "open", None, [])
    write_issue_file(project_dir, issue)


def _workspace(context: object) -> Path:
    workspace = Path(context.temp_dir) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@given(
    "a workspace root containing a repository with a committed Kanbus project and two linked git worktrees"
)
def given_workspace_repo_with_two_worktrees(context: object) -> None:
    workspace = _workspace(context)
    repo = workspace / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repo)
    _write_project_issue(repo / "project", DEDUP_IDENTIFIER, DEDUP_TITLE)
    write_default_kanbus_config(repo)
    _commit_all(repo)
    _add_worktree(workspace, repo, "repo-wt1")
    _add_worktree(workspace, repo, "repo-wt2")
    context.workspace_root = workspace
    context.working_directory = workspace
    context.dedup_issue_key = format_issue_key(DEDUP_IDENTIFIER, project_context=False)
    context.dedup_issue_title = DEDUP_TITLE
    context.dedup_edited_title = DEDUP_EDITED_TITLE
    context.workspace_issue_keys = [context.dedup_issue_key]


@given("the copy in one worktree was changed most recently")
def given_worktree_copy_changed_most_recently(context: object) -> None:
    worktree = Path(context.workspace_root) / "repo-wt2"
    issue = read_issue_file(worktree / "project", DEDUP_IDENTIFIER)
    edited = issue.model_copy(
        update={
            "title": DEDUP_EDITED_TITLE,
            "updated_at": datetime(2026, 2, 12, tzinfo=timezone.utc),
        }
    )
    write_issue_file(worktree / "project", edited)


@given("a workspace root containing two Kanbus projects with distinct issues")
def given_workspace_two_projects_distinct_issues(context: object) -> None:
    workspace = _workspace(context)
    for repo_name, identifier, title in [
        ("proj-one", "kanbus-one", "One project task"),
        ("proj-two", "kanbus-two", "Two project task"),
    ]:
        repo = workspace / repo_name
        repo.mkdir(parents=True, exist_ok=True)
        ensure_git_repository(repo)
        _write_project_issue(repo / "project", identifier, title)
        write_default_kanbus_config(repo)
    context.working_directory = workspace
    context.distinct_issue_keys = [
        format_issue_key("kanbus-one", project_context=False),
        format_issue_key("kanbus-two", project_context=False),
    ]
    context.workspace_issue_keys = list(context.distinct_issue_keys)


@given(
    "a workspace root containing a repository and a linked worktree with tied copies of the same issue"
)
def given_workspace_tied_copies(context: object) -> None:
    workspace = _workspace(context)
    repo = workspace / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repo)
    _write_project_issue(repo / "project", TIE_IDENTIFIER, TIE_ALPHA_TITLE)
    write_default_kanbus_config(repo)
    _commit_all(repo)
    worktree = _add_worktree(workspace, repo, "repo-wt")
    issue = read_issue_file(worktree / "project", TIE_IDENTIFIER)
    tied = issue.model_copy(update={"title": TIE_ZETA_TITLE})
    write_issue_file(worktree / "project", tied)
    context.working_directory = workspace
    context.dedup_issue_key = format_issue_key(TIE_IDENTIFIER, project_context=False)
    context.tie_alpha_title = TIE_ALPHA_TITLE
    context.tie_zeta_title = TIE_ZETA_TITLE
    context.workspace_issue_keys = [
        format_issue_key(TIE_IDENTIFIER, project_context=False)
    ]


@given("a single Kanbus project with one issue and no duplicate copies")
def given_single_project_no_duplicates(context: object) -> None:
    repo = Path(context.temp_dir) / "single-project"
    repo.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repo)
    _write_project_issue(repo / "project", DEDUP_IDENTIFIER, DEDUP_TITLE)
    write_default_kanbus_config(repo)
    context.working_directory = repo
    context.dedup_issue_key = format_issue_key(DEDUP_IDENTIFIER, project_context=False)
    context.workspace_issue_keys = [context.dedup_issue_key]


@then("the issue appears exactly once")
def then_issue_appears_exactly_once(context: object) -> None:
    stdout = context.result.stdout
    assert stdout is not None
    assert (
        stdout.count(context.dedup_issue_key) == 1
    ), f"expected {context.dedup_issue_key} exactly once, got: {stdout}"


@then("the listed entry is the most recently changed version of the issue")
def then_listed_entry_is_most_recent(context: object) -> None:
    stdout = context.result.stdout
    assert context.dedup_edited_title in stdout, f"edited version missing: {stdout}"
    assert context.dedup_issue_title not in stdout, f"stale version listed: {stdout}"


@then("each distinct issue appears exactly once")
def then_each_distinct_issue_appears_once(context: object) -> None:
    stdout = context.result.stdout
    for key in context.distinct_issue_keys:
        assert stdout.count(key) == 1, f"expected {key} exactly once, got: {stdout}"


@then("the deterministic tie-break winner is listed")
def then_tie_break_winner_listed(context: object) -> None:
    stdout = context.result.stdout
    assert context.tie_zeta_title in stdout, f"zeta copy missing: {stdout}"
    assert context.tie_alpha_title not in stdout, f"alpha copy listed: {stdout}"


@then("the single-project listing shows the issue exactly once")
def then_single_project_listing_shows_issue_once(context: object) -> None:
    stdout = context.result.stdout
    short_key = format_issue_key(DEDUP_IDENTIFIER, project_context=True)
    assert stdout is not None
    assert (
        stdout.count(short_key) == 1
    ), f"expected {short_key} exactly once, got: {stdout}"


@then("no issue identity appears more than once")
def then_no_identity_appears_more_than_once(context: object) -> None:
    stdout = context.result.stdout
    for key in context.workspace_issue_keys:
        assert stdout.count(key) <= 1, f"identity {key} duplicated: {stdout}"
