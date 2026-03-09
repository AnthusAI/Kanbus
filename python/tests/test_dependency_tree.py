from __future__ import annotations

import json
from pathlib import Path

import pytest

from kanbus import dependency_tree
from kanbus.models import DependencyLink

from test_helpers import build_issue


def test_dependency_tree_node_to_dict() -> None:
    child = dependency_tree.DependencyTreeNode(
        identifier="kanbus-2",
        title="Child",
        dependency_type="blocked-by",
        dependencies=[],
    )
    root = dependency_tree.DependencyTreeNode(
        identifier="kanbus-1", title="Root", dependency_type=None, dependencies=[child]
    )
    payload = root.to_dict()
    assert payload["id"] == "kanbus-1"
    assert payload["dependencies"][0]["dependency_type"] == "blocked-by"


def test_build_dependency_tree_wraps_project_errors_and_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        dependency_tree,
        "load_project_directory",
        lambda _r: (_ for _ in ()).throw(
            dependency_tree.ProjectMarkerError("bad project")
        ),
    )
    with pytest.raises(dependency_tree.DependencyTreeError, match="bad project"):
        dependency_tree.build_dependency_tree(tmp_path, "kanbus-1", None)

    monkeypatch.setattr(
        dependency_tree, "load_project_directory", lambda _r: tmp_path / "project"
    )
    monkeypatch.setattr(dependency_tree, "_load_issues", lambda _d: {})
    with pytest.raises(dependency_tree.DependencyTreeError, match="not found"):
        dependency_tree.build_dependency_tree(tmp_path, "kanbus-1", None)


def test_build_dependency_tree_and_depth_and_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = build_issue("a", title="A")
    b = build_issue("b", title="B")
    c = build_issue("c", title="C")
    a.dependencies = [
        DependencyLink.model_validate({"target": "b", "type": "blocked-by"})
    ]
    b.dependencies = [
        DependencyLink.model_validate({"target": "c", "type": "relates-to"})
    ]
    c.dependencies = [
        DependencyLink.model_validate({"target": "a", "type": "blocked-by"})
    ]

    monkeypatch.setattr(
        dependency_tree, "load_project_directory", lambda _r: Path("/project")
    )
    monkeypatch.setattr(
        dependency_tree, "_load_issues", lambda _d: {"a": a, "b": b, "c": c}
    )

    tree = dependency_tree.build_dependency_tree(Path("/repo"), "a", None)
    assert tree.identifier == "a"
    assert tree.dependencies[0].identifier == "b"
    assert tree.dependencies[0].dependencies[0].identifier == "c"
    # cycle returns node with no children
    assert tree.dependencies[0].dependencies[0].dependencies[0].dependencies == []

    depth_limited = dependency_tree.build_dependency_tree(Path("/repo"), "a", 1)
    assert depth_limited.dependencies[0].dependencies == []


def test_build_dependency_raises_for_missing_target() -> None:
    dep = DependencyLink.model_validate({"target": "missing", "type": "blocked-by"})
    with pytest.raises(dependency_tree.DependencyTreeError, match="does not exist"):
        dependency_tree._build_dependency(dep, {"a": build_issue("a")}, None, 1, set())


def test_render_dependency_tree_formats_and_invalid() -> None:
    node = dependency_tree.DependencyTreeNode(
        identifier="root",
        title="Root",
        dependency_type=None,
        dependencies=[
            dependency_tree.DependencyTreeNode(
                identifier="child",
                title="Child",
                dependency_type="blocked-by",
                dependencies=[],
            )
        ],
    )

    json_output = dependency_tree.render_dependency_tree(node, "json")
    assert json.loads(json_output)["id"] == "root"

    dot_output = dependency_tree.render_dependency_tree(node, "dot")
    assert '"root" -> "child";' in dot_output

    text_output = dependency_tree.render_dependency_tree(node, "text")
    assert "root Root" in text_output

    with pytest.raises(dependency_tree.DependencyTreeError, match="invalid format"):
        dependency_tree.render_dependency_tree(node, "bad")


def test_render_ascii_truncation_and_dot() -> None:
    chain = dependency_tree.DependencyTreeNode(
        identifier="n0",
        title="0",
        dependency_type=None,
        dependencies=[],
    )
    current = chain
    for index in range(1, 6):
        nxt = dependency_tree.DependencyTreeNode(
            identifier=f"n{index}",
            title=str(index),
            dependency_type=None,
            dependencies=[],
        )
        current.dependencies.append(nxt)
        current = nxt

    rendered = dependency_tree._render_ascii(chain, max_nodes=3)
    assert "additional nodes omitted" in rendered

    dot = dependency_tree._render_dot(chain)
    assert "digraph dependencies" in dot


def test_load_issues_reads_sorted_json_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    (issues_dir / "b.json").write_text("{}", encoding="utf-8")
    (issues_dir / "a.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        dependency_tree,
        "read_issue_from_file",
        lambda p: build_issue("a") if p.name == "a.json" else build_issue("b"),
    )
    loaded = dependency_tree._load_issues(issues_dir)
    assert list(loaded.keys()) == ["a", "b"]
