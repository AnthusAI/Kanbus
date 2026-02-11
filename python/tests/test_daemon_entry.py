"""Tests for daemon entrypoint helpers."""

from __future__ import annotations

from pathlib import Path

import runpy
import sys

from taskulus.daemon import main, parse_args


def test_parse_args_parses_root(tmp_path: Path) -> None:
    args = parse_args(["--root", str(tmp_path)])
    assert args.root == str(tmp_path)


def test_main_invokes_run_daemon(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_run_daemon(root: Path) -> None:
        calls.append(root)

    monkeypatch.setattr("taskulus.daemon.run_daemon", fake_run_daemon)
    main(["--root", str(tmp_path)])
    assert calls == [tmp_path]


def test_module_main_invokes_entrypoint(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class FakeServer:
        def __init__(self, root: Path) -> None:
            calls.append(root)

        def __enter__(self) -> "FakeServer":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def warm_start(self) -> None:
            calls.append("warm")

        def serve_forever(self) -> None:
            calls.append("serve")

    monkeypatch.setattr("taskulus.daemon_server.DaemonServer", FakeServer)
    monkeypatch.setattr(sys, "argv", ["taskulus.daemon", "--root", str(tmp_path)])
    runpy.run_module("taskulus.daemon", run_name="__main__")
    assert calls == [tmp_path, "warm", "serve"]
