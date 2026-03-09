from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import issue_update
from kanbus.hierarchy import InvalidHierarchyError
from kanbus.issue_lookup import IssueLookupError
from kanbus.workflows import InvalidTransitionError

from test_helpers import build_issue, build_project_configuration


def _setup(monkeypatch: pytest.MonkeyPatch, root: Path, issue=None, issue_path=None):
    project_dir = root / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    if issue is None:
        issue = build_issue("kanbus-1", title="Old", status="open", issue_type="task")
    if issue_path is None:
        issue_path = issues_dir / "kanbus-1.json"
    lookup = SimpleNamespace(issue=issue, issue_path=issue_path, project_dir=project_dir)
    cfg = build_project_configuration(project_directory="project")

    monkeypatch.setattr(issue_update, "load_issue_from_project", lambda *_a: lookup)
    monkeypatch.setattr(issue_update, "get_configuration_path", lambda _r: root / ".kanbus.yml")
    monkeypatch.setattr(issue_update, "load_project_configuration", lambda _p: cfg)
    monkeypatch.setattr(issue_update, "write_issue_to_file", lambda *_a: None)
    monkeypatch.setattr(issue_update, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(issue_update, "get_current_user", lambda: "dev")
    monkeypatch.setattr(issue_update, "build_update_events", lambda *_a: [SimpleNamespace(event_id="evt-1")])
    monkeypatch.setattr(issue_update, "events_dir_for_issue_path", lambda *_a: Path("/events"))
    monkeypatch.setattr(issue_update, "write_events_batch", lambda *_a: None)
    monkeypatch.setattr(issue_update, "publish_issue_mutation", lambda *_a: None)
    monkeypatch.setattr(issue_update, "validate_status_value", lambda *_a: None)
    monkeypatch.setattr(issue_update, "validate_status_transition", lambda *_a: None)
    monkeypatch.setattr(issue_update, "apply_transition_side_effects", lambda issue, _status, _now: issue)
    monkeypatch.setattr(issue_update, "_find_duplicate_title", lambda *_a: None)
    return lookup, cfg, issues_dir


def test_update_issue_wraps_lookup_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        issue_update,
        "load_issue_from_project",
        lambda *_a: (_ for _ in ()).throw(IssueLookupError("missing")),
    )
    with pytest.raises(issue_update.IssueUpdateError, match="missing"):
        issue_update.update_issue(tmp_path, "x", None, None, None, None, False)


def test_update_issue_no_updates_requested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(monkeypatch, tmp_path)
    with pytest.raises(issue_update.IssueUpdateError, match="no updates requested"):
        issue_update.update_issue(tmp_path, "kanbus-1", "Old", "", "open", None, False, validate=False)


def test_update_issue_title_duplicate_and_normalization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(issue_update, "_find_duplicate_title", lambda *_a: "kanbus-2")
    with pytest.raises(issue_update.IssueUpdateError, match="duplicate title"):
        issue_update.update_issue(tmp_path, "kanbus-1", "  New  ", None, None, None, False)



def test_update_issue_parent_resolution_and_validation_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lookup, cfg, issues_dir = _setup(monkeypatch, tmp_path)

    monkeypatch.setattr(
        issue_update,
        "resolve_issue_identifier",
        lambda *_a: (_ for _ in ()).throw(IssueLookupError("bad parent")),
    )
    with pytest.raises(issue_update.IssueUpdateError, match="bad parent"):
        issue_update.update_issue(tmp_path, "kanbus-1", "New", None, None, None, False, parent="p")

    monkeypatch.setattr(issue_update, "resolve_issue_identifier", lambda *_a: "kanbus-parent")
    monkeypatch.setattr(issue_update, "read_issue_from_file", lambda _p: build_issue("kanbus-parent", issue_type="epic"))
    monkeypatch.setattr(
        issue_update,
        "validate_parent_child_relationship",
        lambda *_a: (_ for _ in ()).throw(InvalidHierarchyError("bad hierarchy")),
    )
    with pytest.raises(issue_update.IssueUpdateError, match="bad hierarchy"):
        issue_update.update_issue(tmp_path, "kanbus-1", "New", None, None, None, False, parent="p")

    monkeypatch.setattr(issue_update, "validate_parent_child_relationship", lambda *_a: None)
    child_path = issues_dir / "child.json"
    child_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(issue_update.Path, "glob", lambda self, pattern: [child_path] if self == issues_dir else [])
    monkeypatch.setattr(issue_update, "read_issue_from_file", lambda _p: build_issue("child", issue_type="bug", parent="kanbus-1"))
    monkeypatch.setattr(
        issue_update,
        "validate_parent_child_relationship",
        lambda *_a: (_ for _ in ()).throw(InvalidHierarchyError("bad child")),
    )
    with pytest.raises(issue_update.IssueUpdateError, match="bad child"):
        issue_update.update_issue(tmp_path, "kanbus-1", "New", None, None, None, False, issue_type="story")


def test_update_issue_type_status_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(monkeypatch, tmp_path)
    with pytest.raises(issue_update.IssueUpdateError, match="unknown issue type"):
        issue_update.update_issue(tmp_path, "kanbus-1", "New", None, None, None, False, issue_type="nope")

    monkeypatch.setattr(
        issue_update,
        "validate_status_value",
        lambda *_a: (_ for _ in ()).throw(InvalidTransitionError("bad status")),
    )
    with pytest.raises(issue_update.IssueUpdateError, match="bad status"):
        issue_update.update_issue(tmp_path, "kanbus-1", "New", None, "in_progress", None, False)


def test_update_issue_happy_path_with_labels_and_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    issue = build_issue("kanbus-1", title="Old", status="open", issue_type="task", labels=["a", "b"])
    lookup, _cfg, _issues_dir = _setup(monkeypatch, tmp_path, issue=issue)
    writes: list[object] = []
    monkeypatch.setattr(issue_update, "write_issue_to_file", lambda *_a: writes.append("w"))

    updated = issue_update.update_issue(
        tmp_path,
        "kanbus-1",
        title="New",
        description="desc",
        status=None,
        assignee="me",
        claim=True,
        priority=1,
        add_labels=["c"],
        remove_labels=["a"],
        parent=None,
        issue_type="story",
    )

    assert updated.title == "New"
    assert updated.assignee == "me"
    assert updated.status == "in_progress"
    assert set(updated.labels) == {"b", "c"}
    assert updated.issue_type == "story"
    assert len(writes) >= 1


def test_update_issue_normalization_and_parent_update_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = build_issue("kanbus-1", title="Old", status="open", issue_type="task")
    issue.assignee = "dev"
    issue.priority = 2
    lookup, _cfg, _issues_dir = _setup(monkeypatch, tmp_path, issue=issue)
    monkeypatch.setattr(issue_update, "resolve_issue_identifier", lambda *_a: "kanbus-parent")
    monkeypatch.setattr(issue_update, "write_issue_to_file", lambda *_a: None)

    updated = issue_update.update_issue(
        tmp_path,
        "kanbus-1",
        title="  New  ",
        description="  trimmed  ",
        status=None,
        assignee="dev",  # unchanged -> None path
        claim=False,
        validate=False,
        priority=2,  # unchanged -> None path
        set_labels=["x"],  # set_labels branch
        parent="kanbus-parent",  # updated_parent branch
        issue_type="  ",  # resolved_type empty -> None
    )
    assert updated.title == "New"
    assert updated.description == "trimmed"
    assert updated.parent == "kanbus-parent"
    assert updated.labels == ["x"]


def test_update_issue_parent_type_validation_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = build_issue("kanbus-1", title="Old", status="open", issue_type="task", parent="kanbus-parent")
    lookup, _cfg, issues_dir = _setup(monkeypatch, tmp_path, issue=issue)
    monkeypatch.setattr(issue_update, "write_issue_to_file", lambda *_a: None)
    parent_path = issues_dir / "kanbus-parent.json"
    parent_path.write_text("{}", encoding="utf-8")
    child_ok = issues_dir / "child-ok.json"
    child_skip = issues_dir / "child-skip.json"
    child_ok.write_text("{}", encoding="utf-8")
    child_skip.write_text("{}", encoding="utf-8")

    def fake_read(path: Path):
        if path == parent_path:
            return build_issue("kanbus-parent", issue_type="epic")
        if path == child_ok:
            return build_issue("child-ok", issue_type="bug", parent="kanbus-1")
        if path == child_skip:
            return build_issue("child-skip", issue_type="bug", parent="other")
        return build_issue("x")

    monkeypatch.setattr(issue_update, "read_issue_from_file", fake_read)
    monkeypatch.setattr(
        issue_update,
        "validate_parent_child_relationship",
        lambda *_a: (_ for _ in ()).throw(InvalidHierarchyError("bad parent type")),
    )
    with pytest.raises(issue_update.IssueUpdateError, match="bad parent type"):
        issue_update.update_issue(
            tmp_path,
            "kanbus-1",
            title="New",
            description=None,
            status=None,
            assignee=None,
            claim=False,
            issue_type="story",
        )


def test_update_issue_same_type_becomes_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    issue = build_issue("kanbus-1", title="Old", status="open", issue_type="task")
    _setup(monkeypatch, tmp_path, issue=issue)
    monkeypatch.setattr(issue_update, "write_issue_to_file", lambda *_a: None)
    updated = issue_update.update_issue(
        tmp_path,
        "kanbus-1",
        title="New",
        description=None,
        status=None,
        assignee=None,
        claim=False,
        issue_type="task",  # line 106 path
    )
    assert updated.issue_type == "task"
    assert updated.title == "New"


def test_update_issue_child_non_match_continue_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue = build_issue("kanbus-1", title="Old", status="open", issue_type="task")
    _lookup, _cfg, issues_dir = _setup(monkeypatch, tmp_path, issue=issue)
    child_skip = issues_dir / "child-skip.json"
    child_skip.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        issue_update,
        "read_issue_from_file",
        lambda _p: build_issue("child-skip", issue_type="bug", parent="other"),
    )
    monkeypatch.setattr(issue_update, "validate_parent_child_relationship", lambda *_a: None)
    monkeypatch.setattr(issue_update, "write_issue_to_file", lambda *_a: None)

    updated = issue_update.update_issue(
        tmp_path,
        "kanbus-1",
        title="New",
        description=None,
        status=None,
        assignee=None,
        claim=False,
        issue_type="story",
    )
    assert updated.issue_type == "story"

def test_update_issue_event_write_failure_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup(monkeypatch, tmp_path)
    writes: list[str] = []
    monkeypatch.setattr(issue_update, "write_issue_to_file", lambda *_a: writes.append("w"))
    monkeypatch.setattr(
        issue_update,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event fail")),
    )
    with pytest.raises(issue_update.IssueUpdateError, match="event fail"):
        issue_update.update_issue(tmp_path, "kanbus-1", "New", None, None, None, False)
    assert len(writes) >= 2


def test_update_issue_policy_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lookup, _cfg, issues_dir = _setup(monkeypatch, tmp_path)
    policies_dir = lookup.project_dir / "policies"
    policies_dir.mkdir(parents=True)

    import kanbus.policy_loader as policy_loader
    import kanbus.policy_evaluator as policy_evaluator
    import kanbus.policy_context as policy_context
    import kanbus.issue_listing as issue_listing

    monkeypatch.setattr(policy_loader, "load_policies", lambda _p: [("x", object())])
    monkeypatch.setattr(issue_listing, "load_issues_from_directory", lambda _d: [])
    monkeypatch.setattr(
        policy_evaluator,
        "evaluate_policies",
        lambda *_a: (_ for _ in ()).throw(
            policy_context.PolicyViolationError(
                "policy.policy",
                "Scenario",
                "Given step",
                "policy violated",
                "kanbus-1",
            )
        ),
    )

    with pytest.raises(issue_update.IssueUpdateError, match="policy violated"):
        issue_update.update_issue(tmp_path, "kanbus-1", "New", None, None, None, False)


def test_find_duplicate_title_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    (issues_dir / "kanbus-1.json").write_text("{}", encoding="utf-8")
    (issues_dir / "kanbus-2.json").write_text("{}", encoding="utf-8")

    def fake_read(path: Path):
        if path.stem == "kanbus-1":
            return build_issue("kanbus-1", title="same")
        raise ValueError("bad")

    monkeypatch.setattr(issue_update, "read_issue_from_file", fake_read)
    assert issue_update._find_duplicate_title(issues_dir, "same", "kanbus-current") == "kanbus-1"
    assert issue_update._find_duplicate_title(issues_dir, "same", "kanbus-1") is None
