from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from kanbus import console_ui_state


def test_get_console_state_path_uses_project_cache_dir(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    monkeypatch.setattr(
        console_ui_state, "load_project_directory", lambda _root: project_dir
    )

    path = console_ui_state.get_console_state_path(tmp_path)

    assert path == project_dir / ".cache" / "console_state.json"


def test_fetch_console_ui_state_uses_explicit_port_and_parses_json(
    tmp_path: Path,
) -> None:
    payload = {"route": "/board", "view": "kanban"}
    stream = io.BytesIO(json.dumps(payload).encode("utf-8"))
    with patch("urllib.request.urlopen", return_value=stream) as mocked:
        result = console_ui_state.fetch_console_ui_state(tmp_path, port=6123)

    mocked.assert_called_once_with("http://127.0.0.1:6123/api/ui-state", timeout=3)
    assert result == payload


def test_fetch_console_ui_state_uses_configured_console_port(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "kanbus.project.get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        "kanbus.config_loader.load_project_configuration",
        lambda _path: type("Cfg", (), {"console_port": 6011})(),
    )
    stream = io.BytesIO(b'{"ok": true}')
    with patch("urllib.request.urlopen", return_value=stream) as mocked:
        result = console_ui_state.fetch_console_ui_state(tmp_path)

    mocked.assert_called_once_with("http://127.0.0.1:6011/api/ui-state", timeout=3)
    assert result == {"ok": True}


def test_fetch_console_ui_state_falls_back_to_default_port_on_config_error(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "kanbus.project.get_configuration_path",
        lambda _root: (_ for _ in ()).throw(RuntimeError("missing config")),
    )
    stream = io.BytesIO(b'{"ok": true}')
    with patch("urllib.request.urlopen", return_value=stream) as mocked:
        result = console_ui_state.fetch_console_ui_state(tmp_path)

    mocked.assert_called_once_with("http://127.0.0.1:5174/api/ui-state", timeout=3)
    assert result == {"ok": True}


def test_fetch_console_ui_state_returns_none_on_network_or_decode_errors(
    tmp_path: Path,
) -> None:
    with patch("urllib.request.urlopen", side_effect=URLError("down")):
        assert console_ui_state.fetch_console_ui_state(tmp_path, port=5174) is None

    bad_json = io.BytesIO(b"{bad")
    with patch("urllib.request.urlopen", return_value=bad_json):
        assert console_ui_state.fetch_console_ui_state(tmp_path, port=5174) is None

    with patch("urllib.request.urlopen", side_effect=OSError("socket closed")):
        assert console_ui_state.fetch_console_ui_state(tmp_path, port=5174) is None
