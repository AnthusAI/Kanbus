from __future__ import annotations

from kanbus.router_state import (
    ROUTER_GIT_NETWORK_TIMEOUT_SECONDS,
    _git_timeout_seconds,
)


def test_network_git_subcommands_are_bounded_by_a_timeout() -> None:
    for arguments in (
        ("fetch", "--no-tags", "origin", "+refs/a:refs/b"),
        ("push", "origin", "main"),
        ("ls-remote", "--heads", "origin"),
        ("-c", "user.name=Router", "fetch", "origin"),
    ):
        assert _git_timeout_seconds(arguments) == ROUTER_GIT_NETWORK_TIMEOUT_SECONDS


def test_local_git_subcommands_are_not_given_a_timeout() -> None:
    for arguments in (
        ("rev-parse", "HEAD"),
        ("-c", "user.name=Router", "merge", "--no-edit", "origin/main"),
        ("worktree", "add", "path"),
    ):
        assert _git_timeout_seconds(arguments) is None
