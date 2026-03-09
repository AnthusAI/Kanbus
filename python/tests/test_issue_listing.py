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

    with pytest.raises(
        issue_listing.IssueListingError, match="beads mode does not support"
    ):
        issue_listing.list_issues(tmp_path, beads_mode=True, local_only=True)


def test_list_issues_beads_mode_filters_closed_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_issue = build_issue("kanbus-open", status="open")
    closed_issue = build_issue("kanbus-closed", status="closed")
    monkeypatch.setattr(
        issue_listing, "load_beads_issues", lambda _r: [open_issue, closed_issue]
    )

    issues_default = issue_listing.list_issues(tmp_path, beads_mode=True)
    assert [issue.identifier for issue in issues_default] == ["kanbus-open"]

    issues_with_status = issue_listing.list_issues(
        tmp_path, beads_mode=True, status="closed"
    )
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


def test_list_issues_delegates_project_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = build_issue("kanbus-pf")
    monkeypatch.setattr(
        issue_listing, "_list_with_project_filter", lambda *_a, **_k: [issue]
    )
    result = issue_listing.list_issues(tmp_path, project_filter=["alpha"])
    assert result == [issue]


def test_render_project_path_and_tag_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_overlay_config_resolution_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    with pytest.raises(
        issue_listing.IssueListingError, match="issues directory not found"
    ):
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
    monkeypatch.setattr(
        issue_listing, "collect_issue_file_mtimes", lambda _d: {"a": 1.0}
    )
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


def test_list_issues_beads_mode_wraps_migration_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        issue_listing,
        "load_beads_issues",
        lambda _r: (_ for _ in ()).throw(issue_listing.MigrationError("bad beads")),
    )
    with pytest.raises(issue_listing.IssueListingError, match="bad beads"):
        issue_listing.list_issues(tmp_path, beads_mode=True)


def test_list_issues_project_discovery_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        issue_listing,
        "discover_project_directories",
        lambda _r: (_ for _ in ()).throw(issue_listing.ProjectMarkerError("bad root")),
    )
    with pytest.raises(issue_listing.IssueListingError, match="bad root"):
        issue_listing.list_issues(tmp_path)

    monkeypatch.setattr(issue_listing, "discover_project_directories", lambda _r: [])
    with pytest.raises(
        issue_listing.IssueListingError, match="project not initialized"
    ):
        issue_listing.list_issues(tmp_path)


def test_list_issues_multiple_projects_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p1 = tmp_path / "a" / "project"
    p2 = tmp_path / "b" / "project"
    p1.mkdir(parents=True)
    p2.mkdir(parents=True)
    issue = build_issue("kanbus-1")
    monkeypatch.setattr(
        issue_listing, "discover_project_directories", lambda _r: [p1, p2]
    )
    monkeypatch.setattr(
        issue_listing,
        "load_project_configuration",
        lambda _p: build_project_configuration().model_copy(
            update={"overlay": OverlayConfig(enabled=False)}
        ),
    )
    monkeypatch.setattr(
        issue_listing, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        issue_listing,
        "resolve_labeled_projects",
        lambda _r: [
            SimpleNamespace(project_dir=p1, label="alpha"),
            SimpleNamespace(project_dir=p2, label="beta"),
        ],
    )
    monkeypatch.setattr(
        issue_listing,
        "_list_issues_across_projects",
        lambda *_a, **_k: [issue],
    )
    assert issue_listing.list_issues(tmp_path) == [issue]


def test_list_issues_single_project_permission_and_local_only_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    monkeypatch.setattr(
        issue_listing, "discover_project_directories", lambda _r: [project_dir]
    )
    monkeypatch.setattr(
        issue_listing,
        "load_project_configuration",
        lambda _p: build_project_configuration(),
    )
    monkeypatch.setattr(
        issue_listing, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        issue_listing, "os", SimpleNamespace(access=lambda *_a: False, R_OK=4, X_OK=1)
    )
    with pytest.raises(issue_listing.IssueListingError, match="Permission denied"):
        issue_listing.list_issues(tmp_path)

    monkeypatch.setattr(issue_listing, "os", __import__("os"))
    monkeypatch.setattr(
        issue_listing,
        "_list_issues_with_local",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("local boom")),
    )
    with pytest.raises(issue_listing.IssueListingError, match="local boom"):
        issue_listing.list_issues(tmp_path, local_only=True)


def test_list_issues_single_project_local_only_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    issue = build_issue("kanbus-local-only")
    monkeypatch.setattr(
        issue_listing, "discover_project_directories", lambda _r: [project_dir]
    )
    monkeypatch.setattr(
        issue_listing, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        issue_listing,
        "load_project_configuration",
        lambda _p: build_project_configuration(),
    )
    monkeypatch.setattr(issue_listing, "resolve_labeled_projects", lambda _r: [])
    monkeypatch.setattr(
        issue_listing,
        "find_project_local_directory",
        lambda _p: tmp_path / "project-local",
    )
    monkeypatch.setattr(
        issue_listing, "_list_issues_with_local", lambda *_a, **_k: [issue]
    )
    monkeypatch.setattr(issue_listing, "_apply_query", lambda issues, *_a: issues)
    assert issue_listing.list_issues(tmp_path, local_only=True) == [issue]


def test_list_issues_daemon_and_local_merge_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    local_dir = tmp_path / "project-local"
    (local_dir / "issues").mkdir(parents=True, exist_ok=True)
    shared = build_issue("kanbus-shared")
    local = build_issue("kanbus-local")
    monkeypatch.setattr(
        issue_listing, "discover_project_directories", lambda _r: [project_dir]
    )
    monkeypatch.setattr(
        issue_listing, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        issue_listing,
        "load_project_configuration",
        lambda _p: build_project_configuration().model_copy(
            update={"overlay": OverlayConfig(enabled=False)}
        ),
    )
    monkeypatch.setattr(issue_listing, "resolve_labeled_projects", lambda _r: [])
    monkeypatch.setattr(
        issue_listing, "find_project_local_directory", lambda _p: local_dir
    )
    monkeypatch.setattr(
        issue_listing, "apply_overlay_to_issues", lambda *_a, **_k: [shared]
    )
    monkeypatch.setattr(
        issue_listing, "_load_issues_from_directory", lambda _d: [local]
    )

    monkeypatch.setattr(issue_listing, "is_daemon_enabled", lambda: True)
    monkeypatch.setattr(
        issue_listing,
        "request_index_list",
        lambda _r: [shared.model_dump(by_alias=True, mode="json")],
    )
    daemon_issues = issue_listing.list_issues(tmp_path)
    assert {issue.identifier for issue in daemon_issues} == {
        "kanbus-shared",
        "kanbus-local",
    }

    monkeypatch.setattr(
        issue_listing,
        "request_index_list",
        lambda _r: (_ for _ in ()).throw(RuntimeError("daemon boom")),
    )
    with pytest.raises(issue_listing.IssueListingError, match="daemon boom"):
        issue_listing.list_issues(tmp_path)

    monkeypatch.setattr(issue_listing, "is_daemon_enabled", lambda: False)
    monkeypatch.setattr(
        issue_listing,
        "_list_issues_locally",
        lambda _r: (_ for _ in ()).throw(RuntimeError("local list boom")),
    )
    with pytest.raises(issue_listing.IssueListingError, match="local list boom"):
        issue_listing.list_issues(tmp_path)

    monkeypatch.setattr(issue_listing, "_list_issues_locally", lambda _r: [shared])
    monkeypatch.setattr(
        issue_listing,
        "_load_issues_from_directory",
        lambda _d: (_ for _ in ()).throw(RuntimeError("bad local read")),
    )
    with pytest.raises(issue_listing.IssueListingError, match="bad local read"):
        issue_listing.list_issues(tmp_path)


def test_list_with_project_filter_error_and_success_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p1 = tmp_path / "a" / "project"
    p1.mkdir(parents=True)
    labeled = [SimpleNamespace(label="alpha", project_dir=p1)]

    monkeypatch.setattr(
        issue_listing,
        "resolve_labeled_projects",
        lambda _r: (_ for _ in ()).throw(
            issue_listing.ProjectMarkerError("bad labels")
        ),
    )
    with pytest.raises(issue_listing.IssueListingError, match="bad labels"):
        issue_listing._list_with_project_filter(
            tmp_path, ["alpha"], None, None, None, None, None, None, True, False
        )

    monkeypatch.setattr(issue_listing, "resolve_labeled_projects", lambda _r: [])
    with pytest.raises(
        issue_listing.IssueListingError, match="project not initialized"
    ):
        issue_listing._list_with_project_filter(
            tmp_path, ["alpha"], None, None, None, None, None, None, True, False
        )

    monkeypatch.setattr(issue_listing, "resolve_labeled_projects", lambda _r: labeled)
    monkeypatch.setattr(
        issue_listing,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(issue_listing.ConfigurationError("bad cfg")),
    )
    monkeypatch.setattr(
        issue_listing, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml"
    )
    with pytest.raises(issue_listing.IssueListingError, match="bad cfg"):
        issue_listing._list_with_project_filter(
            tmp_path, ["alpha"], None, None, None, None, None, None, True, False
        )

    issue = build_issue("kanbus-1")
    monkeypatch.setattr(
        issue_listing,
        "load_project_configuration",
        lambda _p: build_project_configuration(),
    )
    monkeypatch.setattr(
        issue_listing, "_list_issues_across_projects", lambda *_a, **_k: [issue]
    )
    assert issue_listing._list_with_project_filter(
        tmp_path, ["alpha"], None, None, None, None, None, None, True, False
    ) == [issue]


def test_local_helpers_and_query_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "project"
    monkeypatch.setattr(issue_listing, "load_project_directory", lambda _r: project_dir)
    monkeypatch.setattr(
        issue_listing, "_list_issues_for_project", lambda _p: [build_issue("kanbus-1")]
    )
    assert issue_listing._list_issues_locally(tmp_path)[0].identifier == "kanbus-1"

    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    b = build_issue("kanbus-b")
    a = build_issue("kanbus-a")
    monkeypatch.setattr(
        issue_listing,
        "read_issue_from_file",
        lambda p: b if p.name.startswith("kanbus-b") else a,
    )
    (issues_dir / "kanbus-b.json").write_text("{}", encoding="utf-8")
    (issues_dir / "kanbus-a.json").write_text("{}", encoding="utf-8")
    loaded = issue_listing.load_issues_from_directory(issues_dir)
    assert [issue.identifier for issue in loaded] == ["kanbus-a", "kanbus-b"]

    monkeypatch.setattr(issue_listing, "filter_issues", lambda issues, *_a: issues[:1])
    monkeypatch.setattr(issue_listing, "search_issues", lambda issues, *_a: issues)
    monkeypatch.setattr(
        issue_listing, "sort_issues", lambda issues, *_a: list(reversed(issues))
    )
    out = issue_listing._apply_query(
        [build_issue("one"), build_issue("two")], None, None, None, None, None, None
    )
    assert [i.identifier for i in out] == ["one"]


def test_list_issues_across_projects_skips_missing_local_when_local_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(issue_listing, "find_project_local_directory", lambda _p: None)
    monkeypatch.setattr(
        issue_listing, "_list_issues_with_local", lambda *_a, **_k: [build_issue("x")]
    )
    result = issue_listing._list_issues_across_projects(
        root=root,
        project_dirs=[project_dir],
        include_local=True,
        local_only=True,
        overlay_configs={},
        project_labels={},
    )
    assert result == []
