from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import dependencies
from kanbus.models import DependencyLink

from test_helpers import build_issue


def test_dependency_type_and_lookup_helpers() -> None:
    dependencies._validate_dependency_type("blocked-by")
    dependencies._validate_dependency_type("relates-to")
    with pytest.raises(dependencies.DependencyError, match="invalid dependency type"):
        dependencies._validate_dependency_type("bad")

    issue = build_issue("kanbus-1")
    issue.dependencies = [
        DependencyLink.model_validate({"target": "kanbus-2", "type": "blocked-by"})
    ]
    assert dependencies._has_dependency(issue, "kanbus-2", "blocked-by") is True
    assert dependencies._has_dependency(issue, "kanbus-3", "blocked-by") is False
    assert dependencies._blocked_by_dependency(issue) is True


def test_detect_cycle_and_ensure_no_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = dependencies.DependencyGraph(edges={"a": ["b"], "b": ["c"], "c": ["a"]})
    assert dependencies._detect_cycle(graph, "a") is True

    acyclic = dependencies.DependencyGraph(edges={"a": ["b"], "b": []})
    assert dependencies._detect_cycle(acyclic, "a") is False

    monkeypatch.setattr(
        dependencies,
        "_build_dependency_graph",
        lambda _p: dependencies.DependencyGraph(edges={"a": ["b"], "b": []}),
    )
    dependencies._ensure_no_cycle(Path("/tmp"), "a", "c")

    monkeypatch.setattr(
        dependencies,
        "_build_dependency_graph",
        lambda _p: dependencies.DependencyGraph(edges={"a": ["b"], "b": ["a"]}),
    )
    with pytest.raises(dependencies.DependencyError, match="cycle detected"):
        dependencies._ensure_no_cycle(Path("/tmp"), "a", "c")


def test_build_dependency_graph_reads_blocked_by_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues_dir = tmp_path / "project" / "issues"
    issues_dir.mkdir(parents=True)
    (issues_dir / "a.json").write_text("{}", encoding="utf-8")
    (issues_dir / "b.json").write_text("{}", encoding="utf-8")

    a = build_issue("a")
    a.dependencies = [
        DependencyLink.model_validate({"target": "b", "type": "blocked-by"}),
        DependencyLink.model_validate({"target": "c", "type": "relates-to"}),
    ]
    b = build_issue("b")
    monkeypatch.setattr(
        dependencies,
        "read_issue_from_file",
        lambda p: a if p.name == "a.json" else b,
    )

    graph = dependencies._build_dependency_graph(tmp_path / "project")
    assert graph.edges == {"a": ["b"]}


def test_add_dependency_happy_path_and_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = Path("/repo/project")
    issue_path = project_dir / "issues" / "kanbus-1.json"
    source = build_issue("kanbus-1")
    lookup = SimpleNamespace(
        issue=source, project_dir=project_dir, issue_path=issue_path
    )

    monkeypatch.setattr(dependencies, "load_issue_from_project", lambda _r, _id: lookup)
    monkeypatch.setattr(dependencies, "_ensure_no_cycle", lambda *_a: None)
    writes: list[object] = []
    monkeypatch.setattr(
        dependencies, "write_issue_to_file", lambda issue, _path: writes.append(issue)
    )
    monkeypatch.setattr(dependencies, "now_timestamp", lambda: source.updated_at)
    monkeypatch.setattr(dependencies, "get_current_user", lambda: "dev")
    monkeypatch.setattr(
        dependencies,
        "create_event",
        lambda **_kwargs: SimpleNamespace(event_id="evt-1"),
    )
    monkeypatch.setattr(
        dependencies, "dependency_payload", lambda _t, _id: {"ok": True}
    )
    monkeypatch.setattr(
        dependencies, "events_dir_for_issue_path", lambda *_a: Path("/events")
    )
    monkeypatch.setattr(dependencies, "write_events_batch", lambda *_a: None)
    published: list[str] = []
    monkeypatch.setattr(
        dependencies,
        "publish_issue_mutation",
        lambda *_a: published.append("published"),
    )

    updated = dependencies.add_dependency(
        Path("/repo"), "kanbus-1", "kanbus-2", "blocked-by"
    )
    assert any(dep.target == "kanbus-2" for dep in updated.dependencies)
    assert len(writes) == 1
    assert published == ["published"]

    lookup.issue = updated
    same = dependencies.add_dependency(
        Path("/repo"), "kanbus-1", "kanbus-2", "blocked-by"
    )
    assert same is updated


def test_add_dependency_wraps_lookup_and_event_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependencies,
        "load_issue_from_project",
        lambda *_a: (_ for _ in ()).throw(dependencies.IssueLookupError("missing")),
    )
    with pytest.raises(dependencies.DependencyError, match="missing"):
        dependencies.add_dependency(Path("/repo"), "a", "b", "blocked-by")

    project_dir = Path("/repo/project")
    issue_path = project_dir / "local" / "kanbus-1.json"
    source = build_issue("kanbus-1")
    lookup = SimpleNamespace(
        issue=source, project_dir=project_dir, issue_path=issue_path
    )
    monkeypatch.setattr(dependencies, "load_issue_from_project", lambda *_a: lookup)
    monkeypatch.setattr(dependencies, "_ensure_no_cycle", lambda *_a: None)
    writes: list[str] = []
    monkeypatch.setattr(
        dependencies, "write_issue_to_file", lambda *_a: writes.append("w")
    )
    monkeypatch.setattr(dependencies, "now_timestamp", lambda: source.updated_at)
    monkeypatch.setattr(dependencies, "get_current_user", lambda: "dev")
    monkeypatch.setattr(
        dependencies,
        "create_event",
        lambda **_kwargs: SimpleNamespace(event_id="evt-1"),
    )
    monkeypatch.setattr(
        dependencies, "dependency_payload", lambda _t, _id: {"ok": True}
    )
    monkeypatch.setattr(
        dependencies, "events_dir_for_issue_path", lambda *_a: Path("/events")
    )
    monkeypatch.setattr(
        dependencies,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event fail")),
    )

    with pytest.raises(dependencies.DependencyError, match="event fail"):
        dependencies.add_dependency(Path("/repo"), "kanbus-1", "kanbus-2", "relates-to")
    assert len(writes) == 2


def test_remove_dependency_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = Path("/repo/project")
    issue_path = project_dir / "issues" / "kanbus-1.json"
    issue = build_issue("kanbus-1")
    issue.dependencies = [
        DependencyLink.model_validate({"target": "kanbus-2", "type": "blocked-by"})
    ]
    lookup = SimpleNamespace(
        issue=issue, project_dir=project_dir, issue_path=issue_path
    )

    monkeypatch.setattr(dependencies, "load_issue_from_project", lambda *_a: lookup)
    monkeypatch.setattr(dependencies, "write_issue_to_file", lambda *_a: None)
    monkeypatch.setattr(dependencies, "now_timestamp", lambda: issue.updated_at)
    monkeypatch.setattr(dependencies, "get_current_user", lambda: "dev")
    monkeypatch.setattr(
        dependencies,
        "create_event",
        lambda **_kwargs: SimpleNamespace(event_id="evt-2"),
    )
    monkeypatch.setattr(
        dependencies, "dependency_payload", lambda _t, _id: {"ok": True}
    )
    monkeypatch.setattr(
        dependencies, "events_dir_for_issue_path", lambda *_a: Path("/events")
    )
    monkeypatch.setattr(dependencies, "write_events_batch", lambda *_a: None)
    calls: list[str] = []
    monkeypatch.setattr(
        dependencies,
        "publish_issue_mutation",
        lambda *_a: calls.append("pub"),
    )

    updated = dependencies.remove_dependency(
        Path("/repo"), "kanbus-1", "kanbus-2", "blocked-by"
    )
    assert updated.dependencies == []
    assert calls == ["pub"]

    monkeypatch.setattr(
        dependencies,
        "load_issue_from_project",
        lambda *_a: (_ for _ in ()).throw(dependencies.IssueLookupError("missing")),
    )
    with pytest.raises(dependencies.DependencyError, match="missing"):
        dependencies.remove_dependency(Path("/repo"), "a", "b", "blocked-by")


def test_remove_dependency_rolls_back_on_event_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = Path("/repo/project")
    issue_path = project_dir / "local" / "kanbus-1.json"
    issue = build_issue("kanbus-1")
    lookup = SimpleNamespace(
        issue=issue, project_dir=project_dir, issue_path=issue_path
    )

    monkeypatch.setattr(dependencies, "load_issue_from_project", lambda *_a: lookup)
    writes: list[str] = []
    monkeypatch.setattr(
        dependencies, "write_issue_to_file", lambda *_a: writes.append("w")
    )
    monkeypatch.setattr(dependencies, "now_timestamp", lambda: issue.updated_at)
    monkeypatch.setattr(dependencies, "get_current_user", lambda: "dev")
    monkeypatch.setattr(
        dependencies,
        "create_event",
        lambda **_kwargs: SimpleNamespace(event_id="evt-2"),
    )
    monkeypatch.setattr(
        dependencies, "dependency_payload", lambda _t, _id: {"ok": True}
    )
    monkeypatch.setattr(
        dependencies, "events_dir_for_issue_path", lambda *_a: Path("/events")
    )
    monkeypatch.setattr(
        dependencies,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event fail")),
    )

    with pytest.raises(dependencies.DependencyError, match="event fail"):
        dependencies.remove_dependency(
            Path("/repo"), "kanbus-1", "kanbus-2", "blocked-by"
        )
    assert len(writes) == 2


def test_list_ready_issues_modes_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(dependencies.DependencyError, match="local-only conflicts"):
        dependencies.list_ready_issues(
            Path("/repo"), include_local=False, local_only=True
        )
    with pytest.raises(
        dependencies.DependencyError, match="beads mode does not support"
    ):
        dependencies.list_ready_issues(Path("/repo"), beads_mode=True, local_only=True)

    open_issue = build_issue("kanbus-open", status="open")
    closed_issue = build_issue("kanbus-closed", status="closed")
    blocked = build_issue("kanbus-blocked", status="open")
    blocked.dependencies = [
        DependencyLink.model_validate({"target": "x", "type": "blocked-by"})
    ]
    monkeypatch.setattr(
        dependencies,
        "load_beads_issues",
        lambda _r: [open_issue, closed_issue, blocked],
    )
    ready = dependencies.list_ready_issues(Path("/repo"), beads_mode=True)
    assert [issue.identifier for issue in ready] == ["kanbus-open"]

    monkeypatch.setattr(
        dependencies,
        "load_beads_issues",
        lambda _r: (_ for _ in ()).throw(dependencies.MigrationError("bad beads")),
    )
    with pytest.raises(dependencies.DependencyError, match="bad beads"):
        dependencies.list_ready_issues(Path("/repo"), beads_mode=True)

    monkeypatch.setattr(
        dependencies,
        "discover_project_directories",
        lambda _r: (_ for _ in ()).throw(dependencies.ProjectMarkerError("bad root")),
    )
    with pytest.raises(dependencies.DependencyError, match="bad root"):
        dependencies.list_ready_issues(Path("/repo"))

    monkeypatch.setattr(dependencies, "discover_project_directories", lambda _r: [])
    with pytest.raises(dependencies.DependencyError, match="project not initialized"):
        dependencies.list_ready_issues(Path("/repo"))


def test_list_ready_issues_single_and_multi_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p1 = Path("/repo/a/project")
    p2 = Path("/repo/b/project")
    open_issue = build_issue("kanbus-open", status="open")
    closed_issue = build_issue("kanbus-closed", status="closed")

    monkeypatch.setattr(dependencies, "discover_project_directories", lambda _r: [p1])
    monkeypatch.setattr(
        dependencies,
        "_load_ready_issues_for_project",
        lambda *_a, **_k: [open_issue, closed_issue],
    )
    ready = dependencies.list_ready_issues(Path("/repo"))
    assert [issue.identifier for issue in ready] == ["kanbus-open"]

    monkeypatch.setattr(
        dependencies, "discover_project_directories", lambda _r: [p2, p1]
    )
    monkeypatch.setattr(
        dependencies,
        "_load_ready_issues_for_project",
        lambda _root, project_dir, *_a, **_k: [
            build_issue(f"{project_dir.parts[-2]}-1", status="open")
        ],
    )
    ready = dependencies.list_ready_issues(Path("/repo"))
    assert [issue.identifier for issue in ready] == ["a-1", "b-1"]


def test_load_ready_issues_for_project_and_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    project_dir = root / "project"
    local_dir = root / "project-local"
    (project_dir / "issues").mkdir(parents=True)
    (local_dir / "issues").mkdir(parents=True)

    shared = build_issue("kanbus-shared")
    local = build_issue("kanbus-local")
    monkeypatch.setattr(
        dependencies,
        "_load_issues_from_directory",
        lambda p: [shared] if "project-local" not in str(p) else [local],
    )
    monkeypatch.setattr(
        dependencies, "find_project_local_directory", lambda _p: local_dir
    )

    all_issues = dependencies._load_ready_issues_for_project(
        root,
        project_dir,
        include_local=True,
        local_only=False,
        tag_project=True,
    )
    assert {i.custom.get("source") for i in all_issues} == {"shared", "local"}
    assert {i.custom.get("project_path") for i in all_issues} == {"project"}

    local_only = dependencies._load_ready_issues_for_project(
        root,
        project_dir,
        include_local=True,
        local_only=True,
        tag_project=False,
    )
    assert [i.custom.get("source") for i in local_only] == ["local"]

    monkeypatch.setattr(dependencies, "find_project_local_directory", lambda _p: None)
    none_local = dependencies._load_ready_issues_for_project(
        root,
        project_dir,
        include_local=True,
        local_only=True,
        tag_project=False,
    )
    assert none_local == []

    shared_only = dependencies._load_ready_issues_for_project(
        root,
        project_dir,
        include_local=False,
        local_only=False,
        tag_project=False,
    )
    assert [i.custom.get("source") for i in shared_only] == ["shared"]


def test_render_project_path_and_load_from_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    project_dir = root / "project"
    project_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    rel = dependencies._render_project_path(root, project_dir)
    abs_path = dependencies._render_project_path(root, outside)
    assert rel == "project"
    assert abs_path == str(outside.resolve())

    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    (issues_dir / "b.json").write_text("{}", encoding="utf-8")
    (issues_dir / "a.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        dependencies,
        "read_issue_from_file",
        lambda p: build_issue("a") if p.name == "a.json" else build_issue("b"),
    )
    loaded = dependencies._load_issues_from_directory(issues_dir)
    assert [issue.identifier for issue in loaded] == ["a", "b"]


def test_detect_cycle_visited_short_circuit() -> None:
    graph = dependencies.DependencyGraph(edges={"a": ["b", "b"], "b": []})
    assert dependencies._detect_cycle(graph, "a") is False
