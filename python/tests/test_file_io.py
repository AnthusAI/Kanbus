from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import file_io
from kanbus.config_loader import ConfigurationError
from kanbus.project import ProjectMarkerError

from test_helpers import build_project_configuration


def test_ensure_git_repository_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        file_io.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="true\n"),
    )
    file_io.ensure_git_repository(tmp_path)

    monkeypatch.setattr(
        file_io.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="false\n"),
    )
    with pytest.raises(file_io.InitializationError, match="not a git repository"):
        file_io.ensure_git_repository(tmp_path)


def test_initialize_project_creates_structure_and_files(tmp_path: Path) -> None:
    file_io.initialize_project(tmp_path, create_local=False)

    assert (tmp_path / "project" / "issues").is_dir()
    assert (tmp_path / "project" / "events").is_dir()
    assert (tmp_path / ".kanbus.yml").exists()
    assert (tmp_path / ".cursorignore").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".vscode" / "settings.json").exists()
    assert (tmp_path / ".gitignore").read_text(
        encoding="utf-8"
    ).strip() == "project/.overlay/"
    assert (tmp_path / file_io.DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME).exists()
    assert (
        tmp_path / "project" / "wiki" / file_io.DEFAULT_WIKI_INDEX_FILENAME
    ).exists()
    assert (
        tmp_path / "project" / "wiki" / file_io.DEFAULT_WIKI_WHATS_NEXT_FILENAME
    ).exists()


def test_initialize_project_with_existing_project_or_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project").mkdir()
    with pytest.raises(file_io.InitializationError, match="already initialized"):
        file_io.initialize_project(tmp_path)

    tmp2 = tmp_path / "two"
    tmp2.mkdir()
    called: list[Path] = []
    monkeypatch.setattr(
        file_io,
        "ensure_project_local_directory",
        lambda project_dir: called.append(project_dir),
    )
    file_io.initialize_project(tmp2, create_local=True)
    assert called == [tmp2 / "project"]


def test_ensure_gitignore_entry_appends_and_dedupes(tmp_path: Path) -> None:
    file_io._ensure_gitignore_entry(tmp_path, "project/.overlay/")
    file_io._ensure_gitignore_entry(tmp_path, "project/.overlay/")
    assert (tmp_path / ".gitignore").read_text(
        encoding="utf-8"
    ) == "project/.overlay/\n"


def test_guard_file_writers(tmp_path: Path) -> None:
    subdir = tmp_path / "issues"
    subdir.mkdir()
    file_io._write_guard_files_in_subdir(subdir, "issues")
    assert (subdir / "AGENTS.md").exists()
    assert (subdir / "DO_NOT_EDIT").exists()

    project_dir = tmp_path / "project"
    (project_dir / "issues").mkdir(parents=True)
    (project_dir / "events").mkdir(parents=True)
    file_io._write_project_guard_files(project_dir)
    assert (project_dir / "AGENTS.md").exists()


def test_write_project_guard_files_if_missing_paths(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    (project_dir / "issues").mkdir(parents=True)
    (project_dir / "events").mkdir(parents=True)

    file_io._write_project_guard_files_if_missing(project_dir)
    assert (project_dir / "issues" / "AGENTS.md").exists()
    assert (project_dir / "events" / "DO_NOT_EDIT").exists()
    assert (project_dir / "AGENTS.md").exists()

    partial_dir = tmp_path / "partial"
    (partial_dir / "issues").mkdir(parents=True)
    file_io._write_project_guard_files_if_missing(partial_dir)
    assert (partial_dir / "issues" / "AGENTS.md").exists()


def test_write_tool_block_files_create_and_preserve_existing(tmp_path: Path) -> None:
    file_io._write_tool_block_files(tmp_path)

    claude_settings = tmp_path / ".claude" / "settings.json"
    vscode_settings = tmp_path / ".vscode" / "settings.json"
    assert json.loads(claude_settings.read_text(encoding="utf-8"))["permissions"][
        "deny"
    ]
    assert json.loads(vscode_settings.read_text(encoding="utf-8"))["files.exclude"]

    (tmp_path / ".cursorignore").write_text("custom\n", encoding="utf-8")
    claude_settings.write_text("custom", encoding="utf-8")
    vscode_settings.write_text("custom", encoding="utf-8")
    file_io._write_tool_block_files(tmp_path)
    assert (tmp_path / ".cursorignore").read_text(encoding="utf-8") == "custom\n"
    assert claude_settings.read_text(encoding="utf-8") == "custom"
    assert vscode_settings.read_text(encoding="utf-8") == "custom"


def test_detect_repairable_project_issues_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        file_io,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("missing")),
    )
    assert (
        file_io.detect_repairable_project_issues(tmp_path, allow_uninitialized=True)
        is None
    )
    with pytest.raises(ProjectMarkerError, match="missing"):
        file_io.detect_repairable_project_issues(tmp_path, allow_uninitialized=False)

    monkeypatch.setattr(
        file_io,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ConfigurationError("bad cfg")),
    )
    with pytest.raises(ConfigurationError, match="bad cfg"):
        file_io.detect_repairable_project_issues(tmp_path, allow_uninitialized=False)

    config = build_project_configuration(project_directory="project")
    config_path = tmp_path / ".kanbus.yml"
    monkeypatch.setattr(file_io, "get_configuration_path", lambda _root: config_path)
    monkeypatch.setattr(file_io, "load_project_configuration", lambda _path: config)

    missing_project = file_io.detect_repairable_project_issues(
        tmp_path, allow_uninitialized=False
    )
    assert missing_project is not None
    assert missing_project.missing_project_dir is True

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    missing_subdirs = file_io.detect_repairable_project_issues(
        tmp_path, allow_uninitialized=False
    )
    assert missing_subdirs is not None
    assert missing_subdirs.missing_issues_dir is True
    assert missing_subdirs.missing_events_dir is True

    (project_dir / "issues").mkdir()
    (project_dir / "events").mkdir()
    assert (
        file_io.detect_repairable_project_issues(tmp_path, allow_uninitialized=False)
        is None
    )


def test_repair_project_structure_and_existing_vscode(tmp_path: Path) -> None:
    plan = file_io.RepairPlan(
        project_dir=tmp_path / "project",
        missing_project_dir=True,
        missing_issues_dir=True,
        missing_events_dir=True,
    )
    file_io.repair_project_structure(tmp_path, plan)

    assert (tmp_path / "project" / "issues").is_dir()
    assert (tmp_path / "project" / "events").is_dir()
    assert (tmp_path / "project" / "AGENTS.md").exists()
    assert (tmp_path / ".vscode" / "settings.json").exists()

    existing = tmp_path / ".vscode" / "settings.json"
    existing.write_text("custom", encoding="utf-8")
    file_io.repair_project_structure(
        tmp_path,
        file_io.RepairPlan(
            project_dir=tmp_path / "project",
            missing_project_dir=False,
            missing_issues_dir=False,
            missing_events_dir=False,
        ),
    )
    assert existing.read_text(encoding="utf-8") == "custom"
