from __future__ import annotations

from pathlib import Path

from kanbus import daemon_paths


def test_get_daemon_socket_path_uses_project_cache(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    calls: list[str] = []

    monkeypatch.setattr(
        daemon_paths, "get_configuration_path", lambda _r: calls.append("config") or tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        daemon_paths, "resolve_labeled_projects", lambda _r: calls.append("labels") or []
    )
    monkeypatch.setattr(daemon_paths, "load_project_directory", lambda _r: project_dir)

    path = daemon_paths.get_daemon_socket_path(tmp_path)
    assert path == project_dir / ".cache" / "kanbus.sock"
    assert calls == ["config", "labels"]


def test_get_daemon_socket_path_ignores_project_marker_error(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    monkeypatch.setattr(
        daemon_paths,
        "get_configuration_path",
        lambda _r: (_ for _ in ()).throw(daemon_paths.ProjectMarkerError("no marker")),
    )
    monkeypatch.setattr(daemon_paths, "resolve_labeled_projects", lambda _r: (_ for _ in ()).throw(RuntimeError("should not run")))
    monkeypatch.setattr(daemon_paths, "load_project_directory", lambda _r: project_dir)

    path = daemon_paths.get_daemon_socket_path(tmp_path)
    assert path == project_dir / ".cache" / "kanbus.sock"


def test_get_index_cache_path_uses_project_cache(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    monkeypatch.setattr(daemon_paths, "load_project_directory", lambda _r: project_dir)
    assert daemon_paths.get_index_cache_path(tmp_path) == project_dir / ".cache" / "index.json"
