from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import console_snapshot
from kanbus.config_loader import ConfigurationError
from kanbus.models import OverlayConfig
from kanbus.project import ProjectMarkerError

from test_helpers import build_issue, build_project_configuration


def write_issue_file(project_dir: Path, issue_id: str, title: str) -> None:
    issue = build_issue(issue_id, title=title)
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    payload = issue.model_dump(by_alias=True, mode="json")
    (issues_dir / f"{issue_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_tag_issue_adds_project_and_source() -> None:
    issue = build_issue("kanbus-001")

    tagged = console_snapshot._tag_issue(issue, project_label="alpha", source="shared")

    assert tagged.custom["project_label"] == "alpha"
    assert tagged.custom["source"] == "shared"


def test_read_issues_from_dir_sorts_and_ignores_non_json(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    write_issue_file(project_dir, "kanbus-b", "Issue B")
    write_issue_file(project_dir, "kanbus-a", "Issue A")
    (project_dir / "issues" / "notes.txt").write_text("skip", encoding="utf-8")

    issues = console_snapshot._read_issues_from_dir(project_dir / "issues")

    assert [issue.identifier for issue in issues] == ["kanbus-a", "kanbus-b"]


def test_load_console_issues_includes_shared_and_local(tmp_path: Path) -> None:
    root = tmp_path
    project_dir = root / "project"
    local_dir = root / "project-local"
    write_issue_file(project_dir, "kanbus-shared", "Shared issue")
    write_issue_file(local_dir, "kanbus-local", "Local issue")
    configuration = build_project_configuration()

    issues = console_snapshot._load_console_issues(root, project_dir, configuration)

    by_id = {issue.identifier: issue for issue in issues}
    assert by_id["kanbus-shared"].custom["source"] == "shared"
    assert by_id["kanbus-local"].custom["source"] == "local"


def test_load_console_issues_raises_when_project_issues_missing(tmp_path: Path) -> None:
    configuration = build_project_configuration()

    try:
        console_snapshot._load_console_issues(
            tmp_path, tmp_path / "missing", configuration
        )
    except console_snapshot.ConsoleSnapshotError as error:
        assert "project/issues directory not found" in str(error)
    else:
        raise AssertionError("expected ConsoleSnapshotError")


def test_format_timestamp_uses_utc_z_suffix() -> None:
    from datetime import datetime, timezone

    value = datetime(2026, 3, 6, 12, 0, 0, 123456, tzinfo=timezone.utc)

    assert console_snapshot._format_timestamp(value) == "2026-03-06T12:00:00.123Z"


def test_build_console_snapshot_includes_config_issues_and_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = build_issue("kanbus-1")
    config = build_project_configuration()
    monkeypatch.setattr(
        console_snapshot,
        "_load_project_context",
        lambda _root: (tmp_path / "project", config),
    )
    monkeypatch.setattr(
        console_snapshot,
        "_load_console_issues",
        lambda _root, _project, _config: [issue],
    )

    snapshot = console_snapshot.build_console_snapshot(tmp_path)

    assert snapshot["config"]["project_key"] == "kanbus"
    assert snapshot["issues"][0]["id"] == "kanbus-1"
    assert snapshot["updated_at"].endswith("Z")


def test_load_project_context_wraps_configuration_lookup_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        console_snapshot,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("missing config")),
    )

    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="missing config"):
        console_snapshot._load_project_context(tmp_path)


def test_load_project_context_wraps_configuration_validation_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / ".kanbus.yml"
    monkeypatch.setattr(
        console_snapshot, "get_configuration_path", lambda _root: config_path
    )
    monkeypatch.setattr(
        console_snapshot,
        "load_project_configuration",
        lambda _path: (_ for _ in ()).throw(ConfigurationError("bad config")),
    )

    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="bad config"):
        console_snapshot._load_project_context(tmp_path)


def test_load_issues_with_virtual_projects_uses_beads_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    project_dir = repo_root / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    beads_dir = repo_root / ".beads"
    beads_dir.mkdir(parents=True, exist_ok=True)
    (beads_dir / "issues.jsonl").write_text("", encoding="utf-8")
    issue = build_issue("kanbus-bdx")
    labeled = [SimpleNamespace(label="alpha", project_dir=project_dir)]
    config = build_project_configuration(
        project_key="kanbus",
        virtual_projects={"alpha": {"path": "project"}},
    )
    config = config.model_copy(
        update={"overlay": OverlayConfig(enabled=True, ttl_s=86400)}
    )

    monkeypatch.setattr(
        console_snapshot, "resolve_labeled_projects", lambda _root: labeled
    )
    monkeypatch.setattr(console_snapshot, "load_beads_issues", lambda _repo: [issue])

    issues = console_snapshot._load_issues_with_virtual_projects(repo_root, config)

    assert len(issues) == 1
    assert issues[0].identifier == "kanbus-bdx"
    assert issues[0].custom["project_label"] == "alpha"
    assert issues[0].custom["source"] == "shared"


def test_get_issues_for_root_delegates_to_console_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = build_issue("kanbus-42")
    config = build_project_configuration()
    monkeypatch.setattr(
        console_snapshot,
        "_load_project_context",
        lambda _root: (tmp_path / "project", config),
    )
    monkeypatch.setattr(
        console_snapshot,
        "_load_console_issues",
        lambda _root, _project_dir, _cfg: [issue],
    )

    issues = console_snapshot.get_issues_for_root(tmp_path)

    assert len(issues) == 1
    assert issues[0].identifier == "kanbus-42"


def test_load_console_issues_uses_beads_mode_and_sorts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    configuration = build_project_configuration(beads_compatibility=True)
    issue_b = build_issue("kanbus-b")
    issue_a = build_issue("kanbus-a")
    monkeypatch.setattr(
        console_snapshot, "load_beads_issues", lambda _root: [issue_b, issue_a]
    )

    issues = console_snapshot._load_console_issues(tmp_path, project_dir, configuration)

    assert [issue.identifier for issue in issues] == ["kanbus-a", "kanbus-b"]


def test_load_console_issues_wraps_beads_migration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    configuration = build_project_configuration(beads_compatibility=True)
    monkeypatch.setattr(
        console_snapshot,
        "load_beads_issues",
        lambda _root: (_ for _ in ()).throw(
            console_snapshot.MigrationError("beads broken")
        ),
    )

    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="beads broken"):
        console_snapshot._load_console_issues(tmp_path, project_dir, configuration)


def test_load_console_issues_wraps_invalid_issue_file_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    (project_dir / "issues").mkdir(parents=True, exist_ok=True)
    configuration = build_project_configuration()
    monkeypatch.setattr(
        console_snapshot,
        "_read_issues_from_dir",
        lambda _path: (_ for _ in ()).throw(ValueError("bad issue file")),
    )

    with pytest.raises(
        console_snapshot.ConsoleSnapshotError, match="issue file is invalid"
    ):
        console_snapshot._load_console_issues(tmp_path, project_dir, configuration)


def test_load_issues_with_virtual_projects_wraps_resolve_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = build_project_configuration(
        virtual_projects={"alpha": {"path": "project"}}
    )
    monkeypatch.setattr(
        console_snapshot,
        "resolve_labeled_projects",
        lambda _root: (_ for _ in ()).throw(RuntimeError("resolve failed")),
    )

    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="resolve failed"):
        console_snapshot._load_issues_with_virtual_projects(tmp_path, config)


def test_load_issues_with_virtual_projects_wraps_beads_migration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    project_dir = repo_root / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    beads_dir = repo_root / ".beads"
    beads_dir.mkdir(parents=True, exist_ok=True)
    (beads_dir / "issues.jsonl").write_text("", encoding="utf-8")
    labeled = [SimpleNamespace(label="alpha", project_dir=project_dir)]
    config = build_project_configuration(
        virtual_projects={"alpha": {"path": "project"}}
    )

    monkeypatch.setattr(
        console_snapshot, "resolve_labeled_projects", lambda _root: labeled
    )
    monkeypatch.setattr(
        console_snapshot,
        "load_beads_issues",
        lambda _repo: (_ for _ in ()).throw(
            console_snapshot.MigrationError("bad beads")
        ),
    )

    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="bad beads"):
        console_snapshot._load_issues_with_virtual_projects(repo_root, config)


def test_load_project_context_success_and_config_path_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / ".kanbus.yml"
    config = build_project_configuration(project_directory="project")
    monkeypatch.setattr(
        console_snapshot, "get_configuration_path", lambda _root: config_path
    )
    monkeypatch.setattr(
        console_snapshot, "load_project_configuration", lambda _p: config
    )
    project_dir, loaded = console_snapshot._load_project_context(tmp_path)
    assert project_dir == tmp_path / "project"
    assert loaded.project_key == config.project_key

    monkeypatch.setattr(
        console_snapshot,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ConfigurationError("bad path")),
    )
    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="bad path"):
        console_snapshot._load_project_context(tmp_path)


def test_load_console_issues_virtual_and_not_dir_and_permission_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    cfg_virtual = build_project_configuration(
        virtual_projects={"alpha": {"path": "project"}}
    )
    issue = build_issue("kanbus-v")
    monkeypatch.setattr(
        console_snapshot, "_load_issues_with_virtual_projects", lambda *_a: [issue]
    )
    assert console_snapshot._load_console_issues(
        tmp_path, project_dir, cfg_virtual
    ) == [issue]

    issues_path = project_dir / "issues"
    issues_path.write_text("not a dir", encoding="utf-8")
    cfg = build_project_configuration()
    with pytest.raises(
        console_snapshot.ConsoleSnapshotError,
        match="project/issues directory not found",
    ):
        console_snapshot._load_console_issues(tmp_path, project_dir, cfg)

    issues_path.unlink()
    issues_path.mkdir()
    monkeypatch.setattr(
        console_snapshot,
        "_read_issues_from_dir",
        lambda _p: (_ for _ in ()).throw(PermissionError("no read")),
    )
    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="no read"):
        console_snapshot._load_console_issues(tmp_path, project_dir, cfg)


def test_load_console_issues_local_read_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    local_dir = tmp_path / "project-local"
    (project_dir / "issues").mkdir(parents=True)
    (local_dir / "issues").mkdir(parents=True)
    cfg = build_project_configuration()
    shared_issue = build_issue("kanbus-shared")

    def fake_read(path: Path):
        if "project-local" in str(path):
            raise PermissionError("local denied")
        return [shared_issue]

    monkeypatch.setattr(console_snapshot, "_read_issues_from_dir", fake_read)
    monkeypatch.setattr(
        console_snapshot, "find_project_local_directory", lambda _p: local_dir
    )

    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="local denied"):
        console_snapshot._load_console_issues(tmp_path, project_dir, cfg)


def test_load_console_issues_local_read_invalid_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    local_dir = tmp_path / "project-local"
    (project_dir / "issues").mkdir(parents=True)
    (local_dir / "issues").mkdir(parents=True)
    cfg = build_project_configuration()
    shared_issue = build_issue("kanbus-shared")

    def fake_read(path: Path):
        if "project-local" in str(path):
            raise ValueError("bad local")
        return [shared_issue]

    monkeypatch.setattr(console_snapshot, "_read_issues_from_dir", fake_read)
    monkeypatch.setattr(
        console_snapshot, "find_project_local_directory", lambda _p: local_dir
    )

    with pytest.raises(
        console_snapshot.ConsoleSnapshotError, match="issue file is invalid"
    ):
        console_snapshot._load_console_issues(tmp_path, project_dir, cfg)


def test_load_issues_with_virtual_projects_shared_local_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    p1 = repo / "alpha" / "project"
    p2 = repo / "beta" / "project"
    (p1 / "issues").mkdir(parents=True)
    (p1.parent / "project-local" / "issues").mkdir(parents=True)
    p2.mkdir(parents=True)
    (p2.parent / ".beads").mkdir(parents=True)
    (p2.parent / ".beads" / "issues.jsonl").write_text("", encoding="utf-8")

    labeled = [
        SimpleNamespace(label="alpha", project_dir=p1),
        SimpleNamespace(label="beta", project_dir=p2),
    ]
    cfg = build_project_configuration(
        virtual_projects={"alpha": {"path": str(p1)}, "beta": {"path": str(p2)}}
    )
    shared_issue = build_issue("kanbus-a1")
    local_issue = build_issue("kanbus-a2")
    beads_issue = build_issue("kanbus-b1")

    def fake_read(path: Path):
        if path == p1 / "issues":
            return [shared_issue]
        if path == p1.parent / "project-local" / "issues":
            return [local_issue]
        return []

    monkeypatch.setattr(
        console_snapshot, "resolve_labeled_projects", lambda _r: labeled
    )
    monkeypatch.setattr(console_snapshot, "_read_issues_from_dir", fake_read)
    monkeypatch.setattr(
        console_snapshot,
        "find_project_local_directory",
        lambda project: p1.parent / "project-local" if project == p1 else None,
    )
    monkeypatch.setattr(
        console_snapshot, "load_beads_issues", lambda _repo: [beads_issue]
    )

    issues = console_snapshot._load_issues_with_virtual_projects(repo, cfg)
    assert [issue.identifier for issue in issues] == [
        "kanbus-a1",
        "kanbus-a2",
        "kanbus-b1",
    ]
    assert {issue.custom.get("project_label") for issue in issues} == {"alpha", "beta"}

    monkeypatch.setattr(
        console_snapshot,
        "_read_issues_from_dir",
        lambda _p: (_ for _ in ()).throw(PermissionError("shared denied")),
    )
    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="shared denied"):
        console_snapshot._load_issues_with_virtual_projects(repo, cfg)

    monkeypatch.setattr(
        console_snapshot,
        "_read_issues_from_dir",
        lambda _p: (_ for _ in ()).throw(ValueError("shared invalid")),
    )
    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="shared invalid"):
        console_snapshot._load_issues_with_virtual_projects(repo, cfg)


def test_load_issues_with_virtual_projects_local_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    project_dir = repo / "alpha" / "project"
    (project_dir / "issues").mkdir(parents=True)
    local_issues_dir = project_dir.parent / "project-local" / "issues"
    local_issues_dir.mkdir(parents=True)

    labeled = [SimpleNamespace(label="alpha", project_dir=project_dir)]
    cfg = build_project_configuration(
        virtual_projects={"alpha": {"path": str(project_dir)}}
    )
    shared_issue = build_issue("kanbus-a1")

    def permission_local(path: Path):
        if path == local_issues_dir:
            raise PermissionError("local denied")
        return [shared_issue]

    monkeypatch.setattr(
        console_snapshot, "resolve_labeled_projects", lambda _r: labeled
    )
    monkeypatch.setattr(
        console_snapshot,
        "find_project_local_directory",
        lambda _p: project_dir.parent / "project-local",
    )
    monkeypatch.setattr(console_snapshot, "_read_issues_from_dir", permission_local)
    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="local denied"):
        console_snapshot._load_issues_with_virtual_projects(repo, cfg)

    def invalid_local(path: Path):
        if path == local_issues_dir:
            raise ValueError("local bad")
        return [shared_issue]

    monkeypatch.setattr(console_snapshot, "_read_issues_from_dir", invalid_local)
    with pytest.raises(console_snapshot.ConsoleSnapshotError, match="local bad"):
        console_snapshot._load_issues_with_virtual_projects(repo, cfg)
