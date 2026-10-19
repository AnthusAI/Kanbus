from __future__ import annotations

import pytest

from kanbus.test_hooks import read_test_hook, are_test_hooks_enabled


def test_hook_values_are_ignored_unless_hooks_are_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KANBUS_TEST_HOOK_SELF_CHECK", "on")

    monkeypatch.delenv("KANBUS_ENABLE_TEST_HOOKS")
    assert not are_test_hooks_enabled()
    assert read_test_hook("KANBUS_TEST_HOOK_SELF_CHECK") is None
    assert read_test_hook("KANBUS_TEST_HOOK_SELF_CHECK", "fallback") == "fallback"

    monkeypatch.setenv("KANBUS_ENABLE_TEST_HOOKS", "1")
    assert are_test_hooks_enabled()
    assert read_test_hook("KANBUS_TEST_HOOK_SELF_CHECK") == "on"
