from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import project
from kanbus.config_loader import ConfigurationError

from test_helpers import build_project_configuration


def test_discover_project_directories_from_root_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".kanbus.yml").write_text("x", encoding="utf-8")
    p1 = tmp_path / "project"
    p1.mkdir()
    monkeypatch.setattr(project, "_resolve_project_directories_from_config", lambda _cfg: [p1])

    discovered = project.discover_project_directories(tmp_path)
    assert discovered == [p1.resolve()]


def test_discover_project_directories_wraps_is_file_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_is_file = Path.is_file
    config_path = tmp_path / ".kanbus.yml"

    def fake_is_file(path_self: Path) -> bool:
        if path_self == config_path:
            raise OSError("cannot stat config")
        return original_is_file(path_self)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    with pytest.raises(project.ProjectMarkerError, match="cannot stat config"):
        project.discover_project_directories(tmp_path)


def test_discover_project_directories_raises_for_missing_configured_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".kanbus.yml").write_text("x", encoding="utf-8")
    missing = tmp_path / "missing"
    monkeypatch.setattr(project, "_resolve_project_directories_from_config", lambda _cfg: [missing])

    with pytest.raises(project.ProjectMarkerError, match="kanbus path not found"):
        project.discover_project_directories(tmp_path)


def test_discover_project_directories_workspace_config_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = workspace / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")
    proj = workspace / "project"
    proj.mkdir()

    monkeypatch.setattr(project, "_discover_workspace_config_paths", lambda _root: [cfg])
    monkeypatch.setattr(project, "_resolve_project_directories_from_config", lambda _cfg: [proj])

    discovered = project.discover_project_directories(tmp_path)
    assert discovered == [proj.resolve()]


def test_discover_project_directories_handles_workspace_config_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "workspace" / ".kanbus.yml"
    monkeypatch.setattr(project, "_discover_workspace_config_paths", lambda _root: [cfg])
    monkeypatch.setattr(
        project,
        "_resolve_project_directories_from_config",
        lambda _cfg: (_ for _ in ()).throw(project.ProjectMarkerError("bad config")),
    )
    monkeypatch.setattr(project, "_discover_legacy_project_directories", lambda _root: [])

    assert project.discover_project_directories(tmp_path) == []


def test_discover_project_directories_uses_legacy_when_no_workspace_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = tmp_path / "nested" / "project"
    legacy.mkdir(parents=True)
    monkeypatch.setattr(project, "_discover_workspace_config_paths", lambda _root: [])
    monkeypatch.setattr(project, "_discover_legacy_project_directories", lambda _root: [legacy])

    discovered = project.discover_project_directories(tmp_path)
    assert discovered == [legacy.resolve()]


def test_discover_kanbus_projects_empty_without_config(tmp_path: Path) -> None:
    assert project.discover_kanbus_projects(tmp_path) == []


def test_discover_kanbus_projects_from_root_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")
    p1 = tmp_path / "project"
    p1.mkdir()
    monkeypatch.setattr(project, "_resolve_project_directories_from_config", lambda _cfg: [p1])

    discovered = project.discover_kanbus_projects(tmp_path)
    assert discovered == [p1.resolve()]


def test_resolve_labeled_projects_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")
    primary = tmp_path / "project"
    primary.mkdir()
    virtual = tmp_path / "other"
    virtual.mkdir()
    configuration = build_project_configuration(
        project_directory="project", virtual_projects={"ops": {"path": "other"}}
    )

    monkeypatch.setattr(project, "get_configuration_path", lambda _root: cfg)
    monkeypatch.setattr(project, "load_project_configuration", lambda _cfg: configuration)

    resolved = project.resolve_labeled_projects(tmp_path)
    labels = [p.label for p in resolved]
    assert labels == [configuration.project_key, "ops"]


def test_resolve_labeled_projects_wraps_config_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")
    monkeypatch.setattr(project, "get_configuration_path", lambda _root: cfg)
    monkeypatch.setattr(project, "load_project_configuration", lambda _cfg: (_ for _ in ()).throw(RuntimeError("bad")))

    with pytest.raises(project.ProjectMarkerError, match="bad"):
        project.resolve_labeled_projects(tmp_path)


def test_resolve_labeled_project_directories_raises_for_missing_virtual(tmp_path: Path) -> None:
    configuration = build_project_configuration(
        project_directory="project", virtual_projects={"ops": {"path": "missing"}}
    )

    with pytest.raises(project.ProjectMarkerError, match="virtual project path not found"):
        project._resolve_labeled_project_directories(tmp_path, configuration)


def test_resolve_project_directories_raises_for_missing_virtual(tmp_path: Path) -> None:
    configuration = build_project_configuration(
        project_directory="project", virtual_projects={"ops": {"path": "missing"}}
    )

    with pytest.raises(project.ProjectMarkerError, match="virtual project path not found"):
        project._resolve_project_directories(tmp_path, configuration)


def test_resolve_project_directories_includes_existing_virtual(tmp_path: Path) -> None:
    (tmp_path / "project").mkdir()
    (tmp_path / "vp").mkdir()
    configuration = build_project_configuration(
        project_directory="project", virtual_projects={"ops": {"path": "vp"}}
    )

    resolved = project._resolve_project_directories(tmp_path, configuration)
    assert resolved == [tmp_path / "project", (tmp_path / "vp").resolve()]


def test_resolve_project_directories_from_config_wraps_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / ".kanbus.yml"
    monkeypatch.setattr(project, "_load_configuration", lambda _cfg: (_ for _ in ()).throw(RuntimeError("oops")))

    with pytest.raises(project.ProjectMarkerError, match="oops"):
        project._resolve_project_directories_from_config(cfg)


def test_resolve_project_directories_from_config_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")
    configuration = build_project_configuration()
    expected = [tmp_path / "project"]
    monkeypatch.setattr(project, "_load_configuration", lambda _cfg: configuration)
    monkeypatch.setattr(project, "_resolve_project_directories", lambda _base, _c: expected)

    resolved = project._resolve_project_directories_from_config(cfg)
    assert resolved == expected


def test_apply_ignore_paths_for_config(tmp_path: Path) -> None:
    keep = tmp_path / "project"
    drop = tmp_path / "drop"
    keep.mkdir()
    drop.mkdir()
    configuration = build_project_configuration(project_directory="project")
    configuration.ignore_paths = ["drop"]

    filtered = project._apply_ignore_paths_for_config(tmp_path, configuration, [keep, drop])
    assert filtered == [keep]


def test_apply_ignore_paths_tolerates_unresolvable_ignore_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keep = tmp_path / "project"
    keep.mkdir()
    configuration = build_project_configuration(project_directory="project")
    configuration.ignore_paths = ["broken"]
    original_resolve = Path.resolve
    broken = tmp_path / "broken"

    def fake_resolve(path_self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if path_self == broken:
            raise OSError("bad path")
        return original_resolve(path_self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    filtered = project._apply_ignore_paths_for_config(tmp_path, configuration, [keep])
    assert filtered == [keep]


def test_discover_workspace_config_paths_and_legacy_discovery(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    work = tmp_path / "work"
    work.mkdir()
    (work / ".kanbus.yml").write_text("x", encoding="utf-8")
    nested = work / "nested"
    nested.mkdir()
    (nested / "project").mkdir()

    configs = project._discover_workspace_config_paths(tmp_path)
    legacy = project._discover_legacy_project_directories(tmp_path)

    assert configs == [work / ".kanbus.yml"]
    assert nested / "project" in legacy


def test_discover_workspace_config_paths_raises_on_root_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    original_iterdir = Path.iterdir

    def fake_iterdir(path_self: Path):
        if path_self == root:
            raise OSError("cannot read root")
        return original_iterdir(path_self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)

    with pytest.raises(project.ProjectMarkerError, match="cannot read root"):
        project._discover_workspace_config_paths(root)


def test_discover_workspace_config_paths_skips_non_root_oserror_and_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    bad = root / "bad"
    bad.mkdir()
    (bad / ".kanbus.yml").write_text("x", encoding="utf-8")
    (root / "ok").mkdir()
    (root / "ok" / ".kanbus.yml").write_text("x", encoding="utf-8")
    (root / "sym").symlink_to(root / "ok", target_is_directory=True)
    original_iterdir = Path.iterdir

    def fake_iterdir(path_self: Path):
        if path_self == bad:
            raise OSError("cannot read nested")
        return original_iterdir(path_self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    configs = project._discover_workspace_config_paths(root)
    assert configs == [root / "ok" / ".kanbus.yml"]


def test_normalize_project_directories_deduplicates_and_sorts(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()

    normalized = project._normalize_project_directories([b, a, b])
    assert normalized == [a.resolve(), b.resolve()]


def test_resolve_project_path_tolerates_forced_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KANBUS_TEST_CANONICALIZE_FAILURE", "1")
    path = tmp_path / "x"
    assert project.resolve_project_path(path) == path


def test_find_configuration_file_walks_up(tmp_path: Path) -> None:
    cfg = tmp_path / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert project._find_configuration_file(nested) == cfg


def test_find_configuration_file_returns_none_at_filesystem_root() -> None:
    assert project._find_configuration_file(Path("/")) is None


def test_load_project_directory_from_config_and_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")
    primary = tmp_path / "project"
    primary.mkdir()
    configuration = build_project_configuration(project_directory="project")

    monkeypatch.setattr(project, "_find_configuration_file", lambda _root: cfg)
    monkeypatch.setattr(project, "_load_configuration", lambda _marker: configuration)

    assert project.load_project_directory(tmp_path) == primary.resolve()

    configuration.ignore_paths = ["project"]
    with pytest.raises(project.ProjectMarkerError, match="project not initialized"):
        project.load_project_directory(tmp_path)


def test_load_project_directory_wraps_configuration_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")
    monkeypatch.setattr(project, "_find_configuration_file", lambda _root: cfg)
    monkeypatch.setattr(
        project, "_load_configuration", lambda _marker: (_ for _ in ()).throw(RuntimeError("bad config"))
    )

    with pytest.raises(project.ProjectMarkerError, match="bad config"):
        project.load_project_directory(tmp_path)


def test_load_project_directory_discovery_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project, "_find_configuration_file", lambda _root: None)
    monkeypatch.setattr(project, "discover_project_directories", lambda _root: [])
    with pytest.raises(project.ProjectMarkerError, match="project not initialized"):
        project.load_project_directory(tmp_path)

    p1 = tmp_path / "a"
    p2 = tmp_path / "b"
    p1.mkdir()
    p2.mkdir()
    monkeypatch.setattr(project, "discover_project_directories", lambda _root: [p1, p2])
    with pytest.raises(project.ProjectMarkerError, match="multiple projects found"):
        project.load_project_directory(tmp_path)


def test_load_project_directory_discovery_single_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p1 = tmp_path / "project"
    p1.mkdir()
    monkeypatch.setattr(project, "_find_configuration_file", lambda _root: None)
    monkeypatch.setattr(project, "discover_project_directories", lambda _root: [p1])
    assert project.load_project_directory(tmp_path) == p1


def test_get_configuration_path_variants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")

    monkeypatch.setenv("KANBUS_TEST_CONFIGURATION_PATH_FAILURE", "1")
    with pytest.raises(ConfigurationError, match="configuration path lookup failed"):
        project.get_configuration_path(tmp_path)

    monkeypatch.delenv("KANBUS_TEST_CONFIGURATION_PATH_FAILURE", raising=False)
    monkeypatch.setattr(project, "_find_configuration_file", lambda _root: None)
    with pytest.raises(project.ProjectMarkerError, match="project not initialized"):
        project.get_configuration_path(tmp_path)

    monkeypatch.setattr(project, "_find_configuration_file", lambda _root: cfg)
    assert project.get_configuration_path(tmp_path) == cfg


def test_project_local_helpers(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    assert project.find_project_local_directory(project_dir) is None

    local_dir = project.ensure_project_local_directory(project_dir)
    assert local_dir == tmp_path / "project-local"
    assert (local_dir / "issues").is_dir()
    assert (local_dir / "events").is_dir()
    assert project.find_project_local_directory(project_dir) == local_dir

    gitignore = tmp_path / ".gitignore"
    contents = gitignore.read_text(encoding="utf-8")
    assert "project-local/" in contents


def test_ensure_gitignore_entry_is_idempotent(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("foo\nproject-local/\n", encoding="utf-8")

    project._ensure_gitignore_entry(tmp_path, "project-local/")
    assert gitignore.read_text(encoding="utf-8").count("project-local/") == 1


def test_legacy_discovery_handles_root_named_project_and_root_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_project = tmp_path / "project"
    root_project.mkdir()
    assert root_project in project._discover_legacy_project_directories(root_project)

    root = tmp_path / "broken"
    root.mkdir()
    original_iterdir = Path.iterdir

    def fake_iterdir(path_self: Path):
        if path_self == root:
            raise OSError("cannot read root")
        return original_iterdir(path_self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    with pytest.raises(project.ProjectMarkerError, match="cannot read root"):
        project._discover_legacy_project_directories(root)


def test_legacy_discovery_skips_symlink_and_non_root_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    child = root / "child"
    child.mkdir()
    (child / "project").mkdir()
    bad = root / "bad"
    bad.mkdir()
    (root / "sym").symlink_to(child, target_is_directory=True)
    original_iterdir = Path.iterdir

    def fake_iterdir(path_self: Path):
        if path_self == bad:
            raise OSError("nested read error")
        return original_iterdir(path_self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    projects = project._discover_legacy_project_directories(root)
    assert child / "project" in projects


def test_load_configuration_delegates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / ".kanbus.yml"
    cfg.write_text("x", encoding="utf-8")
    expected = build_project_configuration()
    monkeypatch.setattr(project, "load_project_configuration", lambda _p: expected)
    assert project._load_configuration(cfg) == expected
