from __future__ import annotations

import json
from pathlib import Path

import pytest

from kanbus import maintenance
from kanbus.maintenance import ProjectStatsError, ProjectValidationError
from kanbus.models import DependencyLink, IssueData
from kanbus.project import ProjectMarkerError

from test_helpers import build_issue, build_project_configuration


def _write_issue(path: Path, issue: IssueData) -> None:
    path.write_text(json.dumps(issue.model_dump(mode="json", by_alias=True)), encoding="utf-8")


def test_validate_project_raises_for_missing_project_and_missing_issues_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        maintenance,
        "load_project_directory",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("project not initialized")),
    )
    with pytest.raises(ProjectValidationError, match="project not initialized"):
        maintenance.validate_project(tmp_path)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.setattr(maintenance, "load_project_directory", lambda _root: project_dir)
    with pytest.raises(ProjectValidationError, match="issues directory missing"):
        maintenance.validate_project(tmp_path)


def test_validate_project_wraps_configuration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    (project_dir / "issues").mkdir(parents=True)

    monkeypatch.setattr(maintenance, "load_project_directory", lambda _root: project_dir)
    monkeypatch.setattr(maintenance, "get_configuration_path", lambda _dir: project_dir / "config.yaml")
    monkeypatch.setattr(
        maintenance,
        "load_project_configuration",
        lambda _path: (_ for _ in ()).throw(maintenance.ConfigurationError("bad config")),
    )

    with pytest.raises(ProjectValidationError, match="bad config"):
        maintenance.validate_project(tmp_path)


def test_validate_project_reports_duplicate_and_field_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    cfg = build_project_configuration()

    bad = build_issue("kanbus-dup", issue_type="unknown", status="weird", priority=99)
    _write_issue(issues_dir / "kanbus-dup.json", bad)
    _write_issue(issues_dir / "other-name.json", bad)

    monkeypatch.setattr(maintenance, "load_project_directory", lambda _root: project_dir)
    monkeypatch.setattr(maintenance, "get_configuration_path", lambda _dir: project_dir / "config.yaml")
    monkeypatch.setattr(maintenance, "load_project_configuration", lambda _path: cfg)

    with pytest.raises(ProjectValidationError) as error:
        maintenance.validate_project(tmp_path)

    text = str(error.value)
    assert "validation failed" in text
    assert "duplicate issue id 'kanbus-dup'" in text or "does not match filename" in text


def test_validate_project_continues_after_unreadable_issue_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    cfg = build_project_configuration()

    (issues_dir / "broken.json").write_text("{", encoding="utf-8")
    valid = build_issue("kanbus-good")
    _write_issue(issues_dir / "kanbus-good.json", valid)

    monkeypatch.setattr(maintenance, "load_project_directory", lambda _root: project_dir)
    monkeypatch.setattr(maintenance, "get_configuration_path", lambda _dir: project_dir / "config.yaml")
    monkeypatch.setattr(maintenance, "load_project_configuration", lambda _path: cfg)

    with pytest.raises(ProjectValidationError) as error:
        maintenance.validate_project(tmp_path)
    assert "broken.json: invalid json" in str(error.value)


def test_validate_issue_fields_and_workflow_collection_helpers() -> None:
    cfg = build_project_configuration()
    issue = build_issue("kanbus-1", issue_type="task", status="closed", priority=2)
    issue.closed_at = None
    issue.dependencies = [DependencyLink.model_validate({"target": "x", "type": "invalid"})]

    errors: list[str] = []
    maintenance._validate_issue_fields("kanbus-1.json", issue, cfg, errors)
    assert any("closed issues must have closed_at set" in e for e in errors)
    assert any("invalid dependency type" in e for e in errors)

    issue.status = "open"
    issue.closed_at = issue.updated_at
    errors2: list[str] = []
    maintenance._validate_issue_fields("kanbus-1.json", issue, cfg, errors2)
    assert any("non-closed issues must not set closed_at" in e for e in errors2)
    assert any("does not match filename" in e for e in errors2) is False

    errors_name: list[str] = []
    maintenance._validate_issue_fields("other-name.json", issue, cfg, errors_name)
    assert any("does not match filename" in e for e in errors_name)

    errors3: list[str] = []
    statuses = maintenance._collect_workflow_statuses(cfg, "task", errors3)
    assert statuses is not None
    assert "open" in statuses

    cfg_no_default = cfg.model_copy(update={"workflows": {}})
    errors4: list[str] = []
    statuses_none = maintenance._collect_workflow_statuses(
        cfg_no_default, "not-a-type", errors4
    )
    assert statuses_none is None
    assert errors4


def test_validate_references_covers_missing_parent_invalid_hierarchy_and_dependency() -> None:
    cfg = build_project_configuration().model_copy(
        update={"hierarchy": ["epic", "task"], "types": []}
    )
    parent = build_issue("kanbus-epic", issue_type="epic")
    child = build_issue("kanbus-task", issue_type="task", parent="kanbus-epic")
    bad_child = build_issue("kanbus-bad", issue_type="epic", parent="kanbus-task")
    missing_parent = build_issue("kanbus-missing", parent="missing-id")
    with_dep = build_issue("kanbus-dep")
    with_dep.dependencies = [DependencyLink.model_validate({"target": "nope", "type": "blocks"})]

    issues = {
        parent.identifier: parent,
        child.identifier: child,
        bad_child.identifier: bad_child,
        missing_parent.identifier: missing_parent,
        with_dep.identifier: with_dep,
    }

    errors: list[str] = []
    maintenance._validate_references(issues, cfg, errors)

    assert any("parent 'missing-id' does not exist" in e for e in errors)
    assert any("invalid child type" in e.lower() or "cannot" in e.lower() for e in errors)
    assert any("dependency target 'nope' does not exist" in e for e in errors)


def test_load_issue_handles_read_json_and_model_validation_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    errors: list[str] = []
    missing = tmp_path / "missing.json"
    assert maintenance._load_issue(missing, errors) is None
    assert any("unable to read issue" in e for e in errors)

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")
    errors2: list[str] = []
    assert maintenance._load_issue(bad_json, errors2) is None
    assert any("invalid json" in e for e in errors2)

    bad_model = tmp_path / "bad-model.json"
    bad_model.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    errors3: list[str] = []
    assert maintenance._load_issue(bad_model, errors3) is None
    assert any("invalid issue data" in e for e in errors3)


def test_collect_project_stats_success_and_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)

    open_issue = build_issue("kanbus-open", issue_type="task", status="open")
    closed_issue = build_issue("kanbus-closed", issue_type="bug", status="closed")
    closed_issue.closed_at = closed_issue.updated_at

    _write_issue(issues_dir / "kanbus-open.json", open_issue)
    _write_issue(issues_dir / "kanbus-closed.json", closed_issue)

    monkeypatch.setattr(maintenance, "load_project_directory", lambda _root: project_dir)

    stats = maintenance.collect_project_stats(tmp_path)
    assert stats.total == 2
    assert stats.open_count == 1
    assert stats.closed_count == 1
    assert stats.type_counts == {"task": 1, "bug": 1}

    monkeypatch.setattr(
        maintenance,
        "load_project_directory",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("project not initialized")),
    )
    with pytest.raises(ProjectStatsError, match="project not initialized"):
        maintenance.collect_project_stats(tmp_path)

    monkeypatch.setattr(maintenance, "load_project_directory", lambda _root: project_dir)
    missing_issues = tmp_path / "no-issues"
    missing_issues.mkdir()
    monkeypatch.setattr(maintenance, "load_project_directory", lambda _root: missing_issues)
    with pytest.raises(ProjectStatsError, match="issues directory missing"):
        maintenance.collect_project_stats(tmp_path)

    bad_dir = tmp_path / "bad-project"
    bad_issues = bad_dir / "issues"
    bad_issues.mkdir(parents=True)
    (bad_issues / "a.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(maintenance, "load_project_directory", lambda _root: bad_dir)
    with pytest.raises(ProjectStatsError, match="invalid json"):
        maintenance.collect_project_stats(tmp_path)

    (bad_issues / "a.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    with pytest.raises(ProjectStatsError, match="invalid issue data"):
        maintenance.collect_project_stats(tmp_path)


def test_format_errors_prefix() -> None:
    assert maintenance._format_errors(["a", "b"]) == "validation failed:\na\nb"
