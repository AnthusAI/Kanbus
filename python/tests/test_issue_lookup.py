from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import issue_lookup
from kanbus.models import OverlayConfig

from test_helpers import build_issue, build_project_configuration


def _fake_context(root: Path, labeled=()) -> SimpleNamespace:
    configuration = build_project_configuration()
    return SimpleNamespace(
        root=root,
        repository_root=root,
        configuration=configuration,
        labeled_projects=lambda: list(labeled),
        configuration_at_root=lambda: configuration,
    )


def write_issue(path: Path, issue_id: str) -> None:
    issue = build_issue(issue_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(issue.model_dump(by_alias=True, mode="json")),
        encoding="utf-8",
    )


def test_search_and_matching_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    local_dir = tmp_path / "project-local"
    monkeypatch.setattr(
        issue_lookup, "find_project_local_directory", lambda _p: local_dir
    )
    dirs = issue_lookup._search_directories(project_dir)
    assert dirs == [project_dir / "issues", local_dir / "issues"]

    monkeypatch.setattr(
        issue_lookup,
        "list_issue_identifiers",
        lambda _d: ["kanbus-abc123", "kanbus-def456"],
    )
    matches = issue_lookup._find_matching_issues(project_dir / "issues", "kanbus-abc")
    assert matches == [("kanbus-abc123", project_dir / "issues" / "kanbus-abc123.json")]


def test_resolve_issue_identifier_exact_unique_missing_and_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues_dir = tmp_path / "issues"
    write_issue(issues_dir / "kanbus-111aaa.json", "kanbus-111aaa")

    assert (
        issue_lookup.resolve_issue_identifier(issues_dir, "kanbus", "kanbus-111aaa")
        == "kanbus-111aaa"
    )

    monkeypatch.setattr(
        issue_lookup,
        "list_issue_identifiers",
        lambda _d: ["kanbus-111aaa", "kanbus-222bbb"],
    )
    assert (
        issue_lookup.resolve_issue_identifier(issues_dir, "kanbus", "kanbus-111")
        == "kanbus-111aaa"
    )

    monkeypatch.setattr(issue_lookup, "list_issue_identifiers", lambda _d: [])
    with pytest.raises(issue_lookup.IssueLookupError, match="not found"):
        issue_lookup.resolve_issue_identifier(issues_dir, "kanbus", "kanbus-zzz")

    monkeypatch.setattr(
        issue_lookup,
        "list_issue_identifiers",
        lambda _d: ["kanbus-111aaa", "kanbus-111bbb"],
    )
    with pytest.raises(issue_lookup.IssueLookupError, match="ambiguous short id"):
        issue_lookup.resolve_issue_identifier(issues_dir, "kanbus", "kanbus-111")


def test_overlay_config_for_project_with_root_configuration() -> None:
    config = build_project_configuration()
    overlay = OverlayConfig(enabled=True, ttl_s=123)
    config = config.model_copy(update={"overlay": overlay})
    result = issue_lookup._overlay_config_for_project(Path("/tmp/project"), config)
    assert result.enabled is True
    assert result.ttl_s == 123


def test_overlay_config_for_project_without_root_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    # no .kanbus.yml => disabled
    result = issue_lookup._overlay_config_for_project(project_dir, None)
    assert result.enabled is False

    config_path = tmp_path / ".kanbus.yml"
    config_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        issue_lookup,
        "load_project_configuration",
        lambda _p: build_project_configuration().model_copy(
            update={"overlay": OverlayConfig(enabled=True, ttl_s=77)}
        ),
    )
    result = issue_lookup._overlay_config_for_project(project_dir, None)
    assert result.enabled is True
    assert result.ttl_s == 77

    monkeypatch.setattr(
        issue_lookup,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(RuntimeError("bad config")),
    )
    with pytest.raises(RuntimeError, match="bad config"):
        issue_lookup._overlay_config_for_project(project_dir, None)


def test_load_issue_from_project_exact_match_and_overlay_virtual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    write_issue(project_dir / "issues" / "kanbus-1.json", "kanbus-1")
    monkeypatch.setattr(
        issue_lookup,
        "discover_project_directories_from_configuration",
        lambda _r, _c: [project_dir],
    )
    context = _fake_context(
        root, labeled=[SimpleNamespace(project_dir=project_dir, label="alpha")]
    )
    monkeypatch.setattr(issue_lookup, "load_overlay_issue", lambda *_args: None)
    monkeypatch.setattr(issue_lookup, "load_tombstone", lambda *_args: None)
    monkeypatch.setattr(
        issue_lookup,
        "resolve_issue_with_overlay",
        lambda _p, issue, *_args, **_kwargs: issue,
    )

    result = issue_lookup.load_issue_from_project_with_context(
        root, context, "kanbus-1"
    )
    assert result.issue.identifier == "kanbus-1"
    assert result.project_dir == project_dir

    # overlay-only issue path when base issue does not exist
    overlay_issue = build_issue("kanbus-overlay")
    monkeypatch.setattr(
        issue_lookup,
        "load_overlay_issue",
        lambda *_args: SimpleNamespace(issue=overlay_issue),
    )
    monkeypatch.setattr(
        issue_lookup,
        "resolve_issue_with_overlay",
        lambda _p, _base, _overlay, *_args, **_kwargs: overlay_issue,
    )
    result = issue_lookup.load_issue_from_project_with_context(
        root, context, "kanbus-overlay"
    )
    assert result.issue.identifier == "kanbus-overlay"
    assert result.issue_path.name == "kanbus-overlay.json"
    assert ".overlay" in str(result.issue_path)

    # exact shared file exists but overlay resolution suppresses it (e.g. tombstone)
    write_issue(project_dir / "issues" / "kanbus-suppressed.json", "kanbus-suppressed")
    monkeypatch.setattr(issue_lookup, "load_overlay_issue", lambda *_args: None)
    monkeypatch.setattr(issue_lookup, "load_tombstone", lambda *_args: object())
    monkeypatch.setattr(
        issue_lookup,
        "resolve_issue_with_overlay",
        lambda _p, issue, _overlay, tombstone, *_args, **_kwargs: (
            None if tombstone else issue
        ),
    )
    monkeypatch.setattr(issue_lookup, "list_issue_identifiers", lambda _d: [])
    with pytest.raises(issue_lookup.IssueLookupError, match="not found"):
        issue_lookup.load_issue_from_project_with_context(
            root, context, "kanbus-suppressed"
        )


def test_load_issue_from_project_not_found_ambiguous_and_single_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    issues_dir = project_dir / "issues"
    write_issue(issues_dir / "kanbus-abc111.json", "kanbus-abc111")
    write_issue(issues_dir / "kanbus-abc222.json", "kanbus-abc222")
    monkeypatch.setattr(
        issue_lookup,
        "discover_project_directories_from_configuration",
        lambda _r, _c: [project_dir],
    )
    context = None
    monkeypatch.setattr(issue_lookup, "load_overlay_issue", lambda *_args: None)
    monkeypatch.setattr(issue_lookup, "load_tombstone", lambda *_args: None)

    with pytest.raises(issue_lookup.IssueLookupError, match="ambiguous identifier"):
        issue_lookup.load_issue_from_project_with_context(root, context, "kanbus-abc")

    write_issue(issues_dir / "kanbus-only123.json", "kanbus-only123")
    monkeypatch.setattr(
        issue_lookup,
        "list_issue_identifiers",
        lambda _d: ["kanbus-only123"],
    )
    single = issue_lookup.load_issue_from_project_with_context(
        root, context, "kanbus-only"
    )
    assert single.issue.identifier == "kanbus-only123"

    monkeypatch.setattr(issue_lookup, "list_issue_identifiers", lambda _d: [])
    with pytest.raises(issue_lookup.IssueLookupError, match="not found"):
        issue_lookup.load_issue_from_project_with_context(root, context, "missing")


def test_load_issue_from_project_project_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        issue_lookup,
        "discover_project_directories_from_configuration",
        lambda _r, _c: (_ for _ in ()).throw(
            issue_lookup.ProjectMarkerError("no marker")
        ),
    )
    with pytest.raises(issue_lookup.IssueLookupError, match="no marker"):
        issue_lookup.load_issue_from_project_with_context(tmp_path, None, "kanbus-1")

    monkeypatch.setattr(
        issue_lookup,
        "discover_project_directories_from_configuration",
        lambda _r, _c: [],
    )
    with pytest.raises(issue_lookup.IssueLookupError, match="project not initialized"):
        issue_lookup.load_issue_from_project_with_context(tmp_path, None, "kanbus-1")


def test_overlay_config_lookup_fails_on_malformed_workspace_configuration(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (tmp_path / ".kanbus.yml").write_text("project_key: [unterminated\n")
    with pytest.raises(Exception):
        issue_lookup._overlay_config_for_project(project_dir, None)
