"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Never let unit tests read the developer's real home directory.

    Without this, a test that calls ``Path.home()`` (directly, or via
    ``congregation_env_path()``, ``load_repository_environment()``,
    ``resolve_api_key_source()``, gossip socket path helpers, etc.) without
    explicitly redirecting HOME would pick up the real machine's
    ``~/.kanbus.env`` or other home-directory state. Individual tests may
    still call ``monkeypatch.setenv("HOME", ...)`` themselves to point at a
    specific fixture directory; that simply overrides this default for the
    remainder of the test.
    """
    home_dir = tmp_path / "isolated-home"
    home_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home_dir))


@pytest.fixture(autouse=True)
def _reset_router_worktree_bases():
    """Claim ids repeat across tests; never let one repo's base leak into another."""
    from kanbus import router_execution

    router_execution._WORKTREE_BASES.clear()
    yield
    router_execution._WORKTREE_BASES.clear()
