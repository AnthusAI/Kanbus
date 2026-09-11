from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from kanbus import cli
from kanbus.console_screenshot import (
    ConsoleScreenshotError,
    _MOCK_PNG_BYTES,
    capture_console_screenshot,
    is_console_server_running,
    locate_capture_script,
    resolve_console_port,
)


def _run(args: list[str]) -> object:
    runner = CliRunner()
    return runner.invoke(cli.cli, args)


def test_resolve_console_port_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONSOLE_PORT", "4242")
    assert resolve_console_port(tmp_path) == 4242


def test_resolve_console_port_invalid_env_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONSOLE_PORT", "not-a-port")
    assert resolve_console_port(tmp_path) == 5174


def test_resolve_console_port_from_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CONSOLE_PORT", raising=False)
    monkeypatch.setattr(
        "kanbus.console_screenshot.get_configuration_path",
        lambda _root: tmp_path / ".kanbus.yml",
    )
    monkeypatch.setattr(
        "kanbus.console_screenshot.load_project_configuration",
        lambda _path: SimpleNamespace(console_port=4451),
    )
    assert resolve_console_port(tmp_path) == 4451


def test_is_console_server_running_handles_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONSOLE_PORT", "1")
    assert is_console_server_running(tmp_path) is False
    assert is_console_server_running(tmp_path, port=1) is False


def test_is_console_server_running_http_200(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Response:
        status = 200

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        "kanbus.console_screenshot.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(),
    )
    assert is_console_server_running(tmp_path, port=9999) is True


def test_locate_capture_script_in_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "scripts" / "capture_console_screenshot.mjs"
    script.parent.mkdir()
    script.write_text("export {}", encoding="utf-8")
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT", str(tmp_path))
    assert locate_capture_script(tmp_path) == script


def test_locate_capture_script_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT", str(tmp_path))
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT", "1")
    with pytest.raises(ConsoleScreenshotError, match="capture script not found"):
        locate_capture_script(tmp_path)


def test_mock_mode_unknown_reaches_live_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_MOCK", "other")
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING", "1")
    monkeypatch.setattr(
        "kanbus.console_screenshot.is_console_server_running", lambda _root: True
    )
    with pytest.raises(ConsoleScreenshotError, match="Node.js"):
        capture_console_screenshot(tmp_path)


def test_live_capture_playwright_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "scripts" / "capture_console_screenshot.mjs"
    script.parent.mkdir()
    script.write_text("export {}", encoding="utf-8")
    monkeypatch.delenv("KANBUS_TEST_SCREENSHOT_MOCK", raising=False)
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "kanbus.console_screenshot.is_console_server_running", lambda _root: True
    )
    monkeypatch.setattr(
        "kanbus.console_screenshot.shutil.which", lambda _name: "/usr/bin/node"
    )
    monkeypatch.setattr(
        "kanbus.console_screenshot.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stderr="Cannot find module 'playwright'", stdout=""
        ),
    )
    with pytest.raises(ConsoleScreenshotError, match="playwright"):
        capture_console_screenshot(tmp_path)


def test_live_capture_generic_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "scripts" / "capture_console_screenshot.mjs"
    script.parent.mkdir()
    script.write_text("export {}", encoding="utf-8")
    monkeypatch.delenv("KANBUS_TEST_SCREENSHOT_MOCK", raising=False)
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "kanbus.console_screenshot.is_console_server_running", lambda _root: True
    )
    monkeypatch.setattr(
        "kanbus.console_screenshot.shutil.which", lambda _name: "/usr/bin/node"
    )
    monkeypatch.setattr(
        "kanbus.console_screenshot.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stderr="boom", stdout=""
        ),
    )
    with pytest.raises(ConsoleScreenshotError, match="headless browser capture failed"):
        capture_console_screenshot(tmp_path)


def test_live_capture_missing_output_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "scripts" / "capture_console_screenshot.mjs"
    script.parent.mkdir()
    script.write_text("export {}", encoding="utf-8")
    monkeypatch.delenv("KANBUS_TEST_SCREENSHOT_MOCK", raising=False)
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "kanbus.console_screenshot.is_console_server_running", lambda _root: True
    )
    monkeypatch.setattr(
        "kanbus.console_screenshot.shutil.which", lambda _name: "/usr/bin/node"
    )
    monkeypatch.setattr(
        "kanbus.console_screenshot.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    with pytest.raises(ConsoleScreenshotError, match="did not produce an output file"):
        capture_console_screenshot(tmp_path)


def test_live_capture_writes_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "scripts" / "capture_console_screenshot.mjs"
    script.parent.mkdir()
    script.write_text("export {}", encoding="utf-8")
    output = tmp_path / "exports" / "board.png"

    def _run_capture(args: list[str], **_kwargs: object) -> SimpleNamespace:
        Path(args[3]).write_bytes(_MOCK_PNG_BYTES)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.delenv("KANBUS_TEST_SCREENSHOT_MOCK", raising=False)
    monkeypatch.setenv("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "kanbus.console_screenshot.is_console_server_running", lambda _root: True
    )
    monkeypatch.setattr(
        "kanbus.console_screenshot.shutil.which", lambda _name: "/usr/bin/node"
    )
    monkeypatch.setattr("kanbus.console_screenshot.subprocess.run", _run_capture)
    path = capture_console_screenshot(
        tmp_path,
        output="exports/board.png",
        appearance_mode="dark",
        view="all",
        expand_all=True,
        expand_columns=["backlog"],
        collapse_columns=["closed"],
    )
    assert path == output
    assert path.is_file()


def test_console_screenshot_cli_success_and_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(
        cli,
        "capture_console_screenshot",
        lambda *_args, **_kwargs: tmp_path / "kanbus-board.png",
    )
    result = _run(["console", "screenshot", "--output", "board.png"])
    assert result.exit_code == 0
    assert "kanbus-board.png" in result.output

    monkeypatch.setattr(
        cli,
        "capture_console_screenshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ConsoleScreenshotError("no console")
        ),
    )
    result_error = _run(["console", "screenshot"])
    assert result_error.exit_code != 0
    assert "no console" in result_error.output
