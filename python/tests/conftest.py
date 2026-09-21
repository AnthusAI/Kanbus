"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_router_worktree_bases():
    """Claim ids repeat across tests; never let one repo's base leak into another."""
    from kanbus import router_execution

    router_execution._WORKTREE_BASES.clear()
    yield
    router_execution._WORKTREE_BASES.clear()
