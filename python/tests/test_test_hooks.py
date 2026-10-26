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


def test_invalid_status_switch_is_ignored_without_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KANBUS_TEST_INVALID_STATUS", "1")
    monkeypatch.delenv("KANBUS_ENABLE_TEST_HOOKS")

    assert read_test_hook("KANBUS_TEST_INVALID_STATUS") is None


def test_service_switch_is_ignored_without_the_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from kanbus import issue_files

    monkeypatch.setenv("KANBUS_TEST_DISABLE_SERVICE", "1")
    monkeypatch.delenv("KANBUS_ENABLE_TEST_HOOKS")
    monkeypatch.delenv("KANBUS_NO_DAEMON", raising=False)
    (tmp_path / ".kanbus.yml").write_text("project_key: tst\n", encoding="utf-8")

    assert issue_files._use_service(tmp_path / "project" / "issues")


def test_every_test_switch_in_the_source_goes_through_the_gate() -> None:
    import importlib.util
    from pathlib import Path

    tool_path = (
        Path(__file__).resolve().parents[2] / "tools" / "check_test_switch_gating.py"
    )
    specification = importlib.util.spec_from_file_location("gating_tool", tool_path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    assert module.find_python_violations() == []
    assert module.find_rust_violations() == []
