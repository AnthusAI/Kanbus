from __future__ import annotations

from pathlib import Path
import runpy
import sys

import pytest

from kanbus import daemon
from kanbus import daemon_server


def test_parse_args_requires_root_and_parses_value() -> None:
    args = daemon.parse_args(["--root", "/tmp/project"])
    assert args.root == "/tmp/project"

    with pytest.raises(SystemExit):
        daemon.parse_args([])


def test_main_delegates_to_run_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: dict[str, Path] = {}
    monkeypatch.setattr(
        daemon, "run_daemon", lambda root: called.setdefault("root", root)
    )
    daemon.main(["--root", str(tmp_path)])
    assert called["root"] == tmp_path


def test_module_main_invocation_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: dict[str, Path] = {}
    monkeypatch.setattr(
        daemon_server, "run_daemon", lambda root: called.setdefault("root", root)
    )
    monkeypatch.setattr(sys, "argv", ["kanbus.daemon", "--root", str(tmp_path)])
    runpy.run_module("kanbus.daemon", run_name="__main__")
    assert called["root"] == tmp_path
