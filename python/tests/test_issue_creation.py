from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import issue_creation
from kanbus.hierarchy import InvalidHierarchyError
from kanbus.issue_lookup import IssueLookupError
from kanbus.workflows import InvalidTransitionError

from test_helpers import build_issue, build_project_configuration


def _setup_common(monkeypatch: pytest.MonkeyPatch, root: Path, *, local_dir: Path | None = None):
    project_dir = root / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    cfg = build_project_configuration(project_directory="project")

    monkeypatch.setattr(issue_creation, "load_project_directory", lambda _r: project_dir)
    monkeypatch.setattr(issue_creation, "find_project_local_directory", lambda _p: local_dir)
    monkeypatch.setattr(issue_creation, "get_configuration_path", lambda _r: root / ".kanbus.yml")
    monkeypatch.setattr(issue_creation, "load_project_configuration", lambda _p: cfg)
    monkeypatch.setattr(issue_creation, "list_issue_identifiers", lambda _d: set())
    monkeypatch.setattr(issue_creation, "generate_issue_identifier", lambda _req: SimpleNamespace(identifier="kanbus-new"))
    monkeypatch.setattr(issue_creation, "get_current_user", lambda: "dev")
    monkeypatch.setattr(issue_creation, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(issue_creation, "create_event", lambda **_kwargs: SimpleNamespace(event_id="evt-1"))
    monkeypatch.setattr(issue_creation, "issue_created_payload", lambda _issue: {"ok": True})
    return project_dir, issues_dir, cfg


def test_create_issue_success_non_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path
    project_dir, _issues_dir, _cfg = _setup_common(monkeypatch, root)

    written: dict[str, object] = {}
    monkeypatch.setattr(issue_creation, "write_issue_to_file", lambda issue, path: written.update({"issue": issue, "path": path}))
    monkeypatch.setattr(issue_creation, "events_dir_for_project", lambda _p: project_dir / "events")
    monkeypatch.setattr(issue_creation, "write_events_batch", lambda *_a: None)
    published: list[str] = []
    monkeypatch.setattr(issue_creation, "publish_issue_mutation", lambda *_a: published.append("pub"))

    result = issue_creation.create_issue(
        root,
        title="Hello",
        issue_type=None,
        priority=None,
        assignee=None,
        parent=None,
        labels=["a"],
        description="desc",
        local=False,
        validate=False,
    )
    assert result.issue.identifier == "kanbus-new"
    assert written["path"] == project_dir / "issues" / "kanbus-new.json"
    assert published == ["pub"]


def test_create_issue_success_local_uses_local_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path
    local_dir = root / "project-local"
    local_issues = local_dir / "issues"
    local_issues.mkdir(parents=True)
    project_dir, _issues_dir, _cfg = _setup_common(monkeypatch, root, local_dir=local_dir)

    monkeypatch.setattr(issue_creation, "ensure_project_local_directory", lambda _p: local_dir)
    target_paths: list[Path] = []
    monkeypatch.setattr(issue_creation, "write_issue_to_file", lambda _issue, path: target_paths.append(path))
    monkeypatch.setattr(issue_creation, "events_dir_for_local", lambda _p: project_dir / "project-local-events")
    monkeypatch.setattr(issue_creation, "write_events_batch", lambda *_a: None)
    monkeypatch.setattr(issue_creation, "publish_issue_mutation", lambda *_a: (_ for _ in ()).throw(RuntimeError("should not publish")))

    result = issue_creation.create_issue(
        root,
        title="Hello",
        issue_type=None,
        priority=None,
        assignee=None,
        parent=None,
        labels=[],
        description=None,
        local=True,
        validate=False,
    )
    assert result.issue.identifier == "kanbus-new"
    assert target_paths == [local_issues / "kanbus-new.json"]


def test_create_issue_wraps_project_or_config_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        issue_creation,
        "load_project_directory",
        lambda _r: (_ for _ in ()).throw(issue_creation.ProjectMarkerError("bad root")),
    )
    with pytest.raises(issue_creation.IssueCreationError, match="bad root"):
        issue_creation.create_issue(tmp_path, "t", None, None, None, None, [], None)

    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    monkeypatch.setattr(issue_creation, "load_project_directory", lambda _r: project_dir)
    monkeypatch.setattr(issue_creation, "find_project_local_directory", lambda _p: None)
    monkeypatch.setattr(issue_creation, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(
        issue_creation,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(issue_creation.ConfigurationError("bad cfg")),
    )
    with pytest.raises(issue_creation.IssueCreationError, match="bad cfg"):
        issue_creation.create_issue(tmp_path, "t", None, None, None, None, [], None)


def test_create_issue_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path
    _project_dir, issues_dir, cfg = _setup_common(monkeypatch, root)
    monkeypatch.setattr(issue_creation, "write_issue_to_file", lambda *_a: None)
    monkeypatch.setattr(issue_creation, "events_dir_for_project", lambda _p: root / "events")
    monkeypatch.setattr(issue_creation, "write_events_batch", lambda *_a: None)
    monkeypatch.setattr(issue_creation, "publish_issue_mutation", lambda *_a: None)

    with pytest.raises(issue_creation.IssueCreationError, match="unknown issue type"):
        issue_creation.create_issue(root, "t", "invalid", None, None, None, [], None, validate=True)

    with pytest.raises(issue_creation.IssueCreationError, match="invalid priority"):
        issue_creation.create_issue(root, "t", "task", 999, None, None, [], None, validate=True)

    monkeypatch.setattr(
        issue_creation,
        "resolve_issue_identifier",
        lambda *_a: (_ for _ in ()).throw(IssueLookupError("parent missing")),
    )
    with pytest.raises(issue_creation.IssueCreationError, match="parent missing"):
        issue_creation.create_issue(root, "t", "task", None, None, "p", [], None, validate=True)

    monkeypatch.setattr(issue_creation, "resolve_issue_identifier", lambda *_a: "kanbus-parent")
    with pytest.raises(issue_creation.IssueCreationError, match="not found"):
        issue_creation.create_issue(root, "t", "task", None, None, "p", [], None, validate=True)

    parent_path = issues_dir / "kanbus-parent.json"
    parent_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(issue_creation, "read_issue_from_file", lambda _p: build_issue("kanbus-parent", issue_type="epic"))
    monkeypatch.setattr(
        issue_creation,
        "validate_parent_child_relationship",
        lambda *_a: (_ for _ in ()).throw(InvalidHierarchyError("bad hierarchy")),
    )
    with pytest.raises(issue_creation.IssueCreationError, match="bad hierarchy"):
        issue_creation.create_issue(root, "t", "task", None, None, "p", [], None, validate=True)

    monkeypatch.setattr(issue_creation, "validate_parent_child_relationship", lambda *_a: None)
    monkeypatch.setattr(issue_creation, "_find_duplicate_title", lambda *_a: "kanbus-dup")
    with pytest.raises(issue_creation.IssueCreationError, match="duplicate title"):
        issue_creation.create_issue(root, "t", "task", None, None, None, [], None, validate=True)

    monkeypatch.setattr(issue_creation, "_find_duplicate_title", lambda *_a: None)
    monkeypatch.setattr(
        issue_creation,
        "validate_status_value",
        lambda *_a: (_ for _ in ()).throw(InvalidTransitionError("bad status")),
    )
    with pytest.raises(issue_creation.IssueCreationError, match="bad status"):
        issue_creation.create_issue(root, "t", "task", None, None, None, [], None, validate=True)



def test_create_issue_policy_violation_and_event_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path
    project_dir, issues_dir, cfg = _setup_common(monkeypatch, root)
    monkeypatch.setattr(issue_creation, "validate_status_value", lambda *_a: None)
    monkeypatch.setattr(issue_creation, "_find_duplicate_title", lambda *_a: None)
    monkeypatch.setattr(issue_creation, "write_issue_to_file", lambda issue, path: path.write_text(issue.model_dump_json(), encoding="utf-8"))
    monkeypatch.setattr(issue_creation, "events_dir_for_project", lambda _p: project_dir / "events")
    monkeypatch.setattr(
        issue_creation,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event write fail")),
    )
    monkeypatch.setattr(issue_creation, "publish_issue_mutation", lambda *_a: None)

    policies_dir = project_dir / "policies"
    policies_dir.mkdir(parents=True, exist_ok=True)

    import kanbus.policy_loader as policy_loader
    import kanbus.policy_evaluator as policy_evaluator
    import kanbus.issue_listing as issue_listing

    monkeypatch.setattr(policy_loader, "load_policies", lambda _p: [("x", object())])
    monkeypatch.setattr(issue_listing, "load_issues_from_directory", lambda _d: [])

    import kanbus.policy_context as policy_context

    monkeypatch.setattr(
        policy_evaluator,
        "evaluate_policies",
        lambda *_a: (_ for _ in ()).throw(
            policy_context.PolicyViolationError(
                "policy.policy",
                "Scenario",
                "Given something",
                "policy violated",
                "kanbus-new",
            )
        ),
    )

    with pytest.raises(issue_creation.IssueCreationError, match="policy violated"):
        issue_creation.create_issue(root, "t", "task", None, None, None, [], None, validate=True)

    monkeypatch.setattr(policy_loader, "load_policies", lambda _p: [])

    with pytest.raises(issue_creation.IssueCreationError, match="event write fail"):
        issue_creation.create_issue(root, "t", "task", None, None, None, [], None, validate=True)

    assert not (issues_dir / "kanbus-new.json").exists()


def test_find_duplicate_title_handles_invalid_and_casefold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    (issues_dir / "a.json").write_text("{}", encoding="utf-8")
    (issues_dir / "b.json").write_text("{}", encoding="utf-8")

    calls = {"n": 0}

    def fake_read(path: Path):
        calls["n"] += 1
        if path.name == "a.json":
            raise ValueError("bad")
        return build_issue("kanbus-2", title="  HeLLo  ")

    monkeypatch.setattr(issue_creation, "read_issue_from_file", fake_read)
    duplicate = issue_creation._find_duplicate_title(issues_dir, "hello")
    assert duplicate == "kanbus-2"

    monkeypatch.setattr(issue_creation, "read_issue_from_file", lambda _p: build_issue("x", title="other"))
    assert issue_creation._find_duplicate_title(issues_dir, "hello") is None
