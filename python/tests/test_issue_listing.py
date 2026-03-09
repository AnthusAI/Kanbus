from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import issue_listing
from kanbus.models import OverlayConfig

from test_helpers import build_issue, build_project_configuration


def test_list_issues_rejects_invalid_flag_combinations(tmp_path: Path) -> None:
    with pytest.raises(issue_listing.IssueListingError, match="local-only conflicts"):
        issue_listing.list_issues(tmp_path, include_local=False, local_only=True)

    with pytest.raises(issue_listing.IssueListingError, match="beads mode does not support"):
        issue_listing.list_issues(tmp_path, beads_mode=True, local_only=True)


def test_list_issues_beads_mode_filters_closed_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_issue = build_issue("kanbus-open", status="open")
    closed_issue = build_issue("kanbus-closed", status="closed")
    monkeypatch.setattr(issue_listing, "load_beads_issues", lambda _r: [open_issue, closed_issue])

    issues_default = issue_listing.list_issues(tmp_path, beads_mode=True)
    assert [issue.identifier for issue in issues_default] == ["kanbus-open"]

    issues_with_status = issue_listing.list_issues(tmp_path, beads_mode=True, status="closed")
    assert any(issue.identifier == "kanbus-closed" for issue in issues_with_status)


def test_list_issues_with_project_filter_unknown_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        issue_listing,
        "resolve_labeled_projects",
        lambda _r: [SimpleNamespace(label="alpha", project_dir=tmp_path / "project")],
    )
    with pytest.raises(issue_listing.IssueListingError, match="unknown project: beta"):
        issue_listing._list_with_project_filter(
            tmp_path, ["beta"], None, None, None, None, None, None, True, False
        )


def test_render_project_path_and_tag_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    project = root / "project"
    other = tmp_path / "elsewhere"
    monkeypatch.setattr(issue_listing, "resolve_project_path", lambda p: p)
    assert issue_listing._render_project_path(root, project) == "project"
    assert issue_listing._render_project_path(root, other) == str(other)

    issue = build_issue("kanbus-1")
    tagged_source = issue_listing._tag_issue_source(issue, "shared")
    assert tagged_source.custom["source"] == "shared"
    tagged_project = issue_listing._tag_issue_project(issue, root, project)
    assert tagged_project.custom["project_path"] == "project"


def test_overlay_config_resolution_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = tmp_path / "project"
    config = build_project_configuration().model_copy(
        update={"overlay": OverlayConfig(enabled=True, ttl_s=22)}
    )
    assert issue_listing._overlay_config_for_project(project_dir, config).ttl_s == 22

    # without root config and no .kanbus.yml => disabled
    assert issue_listing._overlay_config_for_project(project_dir, None).enabled is False

    config_path = tmp_path / ".kanbus.yml"
    config_path.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        issue_listing,
        "load_project_configuration",
        lambda _p: build_project_configuration().model_copy(
            update={"overlay": OverlayConfig(enabled=True, ttl_s=77)}
        ),
    )
    assert issue_listing._overlay_config_for_project(project_dir, None).ttl_s == 77

    monkeypatch.setattr(
        issue_listing,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(RuntimeError("bad")),
    )
    assert issue_listing._overlay_config_for_project(project_dir, None).enabled is False

    resolved = issue_listing._resolve_overlay_configs([project_dir], config)
    assert resolved[project_dir].enabled is True


def test_list_issues_for_project_cache_and_missing_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    with pytest.raises(issue_listing.IssueListingError, match="issues directory not found"):
        issue_listing._list_issues_for_project(project_dir)

    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    cached_issue = build_issue("kanbus-cache")
    cached_index = SimpleNamespace(by_id={"kanbus-cache": cached_issue})
    monkeypatch.setattr(issue_listing, "load_cache_if_valid", lambda *_a: cached_index)
    cached = issue_listing._list_issues_for_project(project_dir)
    assert [issue.identifier for issue in cached] == ["kanbus-cache"]


def test_list_issues_for_project_builds_index_when_cache_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    built_issue = build_issue("kanbus-index")
    index = SimpleNamespace(by_id={"kanbus-index": built_issue})
    monkeypatch.setattr(issue_listing, "load_cache_if_valid", lambda *_a: None)
    monkeypatch.setattr(issue_listing, "build_index_from_directory", lambda _d: index)
    monkeypatch.setattr(issue_listing, "collect_issue_file_mtimes", lambda _d: {"a": 1.0})
    called: dict[str, bool] = {}
    monkeypatch.setattr(
        issue_listing, "write_cache", lambda *_a: called.setdefault("write_cache", True)
    )
    issues = issue_listing._list_issues_for_project(project_dir)
    assert [issue.identifier for issue in issues] == ["kanbus-index"]
    assert called.get("write_cache") is True


def test_list_issues_with_local_and_across_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    local_dir = root / "project-local"
    (local_dir / "issues").mkdir(parents=True, exist_ok=True)
    shared_issue = build_issue("kanbus-shared")
    local_issue = build_issue("kanbus-local")
    monkeypatch.setattr(
        issue_listing,
        "_list_issues_for_project",
        lambda _p: [shared_issue],
    )
    monkeypatch.setattr(
        issue_listing,
        "_load_issues_from_directory",
        lambda _d: [local_issue],
    )
    monkeypatch.setattr(
        issue_listing, "apply_overlay_to_issues", lambda _p, issues, *_a, **_k: issues
    )

    both = issue_listing._list_issues_with_local(
        project_dir,
        local_dir,
        include_local=True,
        local_only=False,
        overlay_config=OverlayConfig(enabled=False),
        project_label=None,
    )
    assert {issue.custom.get("source") for issue in both} == {"shared", "local"}

    local_only = issue_listing._list_issues_with_local(
        project_dir,
        local_dir,
        include_local=True,
        local_only=True,
        overlay_config=OverlayConfig(enabled=False),
        project_label=None,
    )
    assert len(local_only) == 1
    assert local_only[0].custom["source"] == "local"

    monkeypatch.setattr(issue_listing, "find_project_local_directory", lambda _p: None)
    across = issue_listing._list_issues_across_projects(
        root=root,
        project_dirs=[project_dir],
        include_local=False,
        local_only=False,
        overlay_configs={project_dir: OverlayConfig(enabled=False)},
        project_labels={project_dir: "alpha"},
    )
    assert len(across) == 1
    assert across[0].custom["project_path"] == "project"
