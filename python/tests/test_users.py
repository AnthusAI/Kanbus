"""Tests for user identification helpers."""

from __future__ import annotations

import getpass

import pytest

from taskulus.users import get_current_user


def test_get_current_user_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASKULUS_USER", "dev@example.com")
    assert get_current_user() == "dev@example.com"


def test_get_current_user_falls_back_to_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TASKULUS_USER", raising=False)
    monkeypatch.setattr(getpass, "getuser", lambda: "system-user")
    assert get_current_user() == "system-user"
