from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import doctor, hierarchy, issue_files, policy_loader, users, workflows
from kanbus.models import IssueData, StatusDefinition

from test_helpers import build_issue, build_project_configuration


def test_get_current_user_prefers_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KANBUS_USER", "agent")
    monkeypatch.setenv("USER", "fallback")
    assert users.get_current_user() == "agent"


def test_get_current_user_falls_back_to_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KANBUS_USER", raising=False)
    monkeypatch.setenv("USER", "fallback")
    assert users.get_current_user() == "fallback"


def test_get_current_user_defaults_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KANBUS_USER", raising=False)
    monkeypatch.delenv("USER", raising=False)
    assert users.get_current_user() == "unknown"


def test_issue_file_roundtrip(tmp_path: Path) -> None:
    issue_path = tmp_path / "kanbus-1.json"
    issue = build_issue("kanbus-1", title="Roundtrip", status="open")

    issue_files.write_issue_to_file(issue, issue_path)
    loaded = issue_files.read_issue_from_file(issue_path)

    assert loaded.identifier == "kanbus-1"
    assert loaded.title == "Roundtrip"


def test_list_issue_identifiers_from_json_files(tmp_path: Path) -> None:
    (tmp_path / "kanbus-1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "kanbus-2.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")

    assert issue_files.list_issue_identifiers(tmp_path) == {"kanbus-1", "kanbus-2"}


def test_run_doctor_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected_dir = tmp_path / "project"
    monkeypatch.setattr(doctor, "ensure_git_repository", lambda _root: None)
    monkeypatch.setattr(doctor, "load_project_directory", lambda _root: expected_dir)
    monkeypatch.setattr(doctor, "get_configuration_path", lambda _root: tmp_path / "config.yaml")
    monkeypatch.setattr(doctor, "load_project_configuration", lambda _path: object())

    result = doctor.run_doctor(tmp_path)
    assert result.project_dir == expected_dir


@pytest.mark.parametrize(
    "attr,exc_type,message",
    [
        ("ensure_git_repository", doctor.InitializationError, "no git"),
        ("load_project_directory", doctor.ProjectMarkerError, "no project"),
        ("load_project_configuration", doctor.ConfigurationError, "bad config"),
    ],
)
def test_run_doctor_wraps_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attr: str,
    exc_type: type[Exception],
    message: str,
) -> None:
    monkeypatch.setattr(doctor, "ensure_git_repository", lambda _root: None)
    monkeypatch.setattr(doctor, "load_project_directory", lambda _root: tmp_path / "project")
    monkeypatch.setattr(doctor, "get_configuration_path", lambda _root: tmp_path / "config.yaml")

    def raise_error(_arg):
        raise exc_type(message)

    monkeypatch.setattr(doctor, attr, raise_error)

    with pytest.raises(doctor.DoctorError, match=message):
        doctor.run_doctor(tmp_path)


def test_hierarchy_allowed_types_for_known_parent() -> None:
    configuration = build_project_configuration()
    allowed = hierarchy.get_allowed_child_types(configuration, "epic")
    assert allowed[0] == "task"
    assert "bug" in allowed


def test_hierarchy_returns_empty_for_unknown_or_terminal_parent() -> None:
    configuration = build_project_configuration()
    assert hierarchy.get_allowed_child_types(configuration, "unknown") == []
    assert hierarchy.get_allowed_child_types(configuration, "sub-task") == []


def test_validate_parent_child_relationship_rejects_invalid_pair() -> None:
    configuration = build_project_configuration()
    with pytest.raises(hierarchy.InvalidHierarchyError, match="cannot have child"):
        hierarchy.validate_parent_child_relationship(configuration, "epic", "initiative")


def test_load_policies_returns_empty_for_missing_directory(tmp_path: Path) -> None:
    assert policy_loader.load_policies(tmp_path / "missing") == []


def test_load_policies_parses_documents(tmp_path: Path) -> None:
    policies_dir = tmp_path / "policies"
    policies_dir.mkdir()
    (policies_dir / "one.policy").write_text(
        "Feature: F\n  Scenario: S\n    Given setup\n", encoding="utf-8"
    )

    docs = policy_loader.load_policies(policies_dir)
    assert len(docs) == 1
    name, document = docs[0]
    assert name == "one.policy"
    assert document.feature.name == "F"


def test_load_policies_wraps_parse_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policies_dir = tmp_path / "policies"
    policies_dir.mkdir()
    (policies_dir / "bad.policy").write_text("Feature: X", encoding="utf-8")

    class BrokenParser:
        def parse(self, _content: str):
            raise RuntimeError("boom")

    monkeypatch.setattr(policy_loader, "Parser", BrokenParser)

    with pytest.raises(policy_loader.PolicyLoadError, match="failed to parse bad.policy"):
        policy_loader.load_policies(policies_dir)


def test_to_namespace_recurses() -> None:
    value = policy_loader._to_namespace({"a": [{"b": 1}]})
    assert value.a[0].b == 1


def _workflow_issue(status: str) -> IssueData:
    return build_issue("kanbus-7", status=status)


def test_get_workflow_for_issue_type_prefers_specific_type() -> None:
    configuration = build_project_configuration()
    configuration.workflows["bug"] = {"open": ["closed"]}

    assert workflows.get_workflow_for_issue_type(configuration, "bug") == {
        "open": ["closed"]
    }


def test_get_workflow_for_issue_type_requires_default() -> None:
    configuration = build_project_configuration()
    configuration.workflows = {}

    with pytest.raises(ValueError, match="default workflow not defined"):
        workflows.get_workflow_for_issue_type(configuration, "task")


def test_validate_status_transition_rejects_invalid_target() -> None:
    configuration = build_project_configuration()
    with pytest.raises(workflows.InvalidTransitionError, match="invalid transition"):
        workflows.validate_status_transition(
            configuration, "task", "open", "nonexistent"
        )


def test_validate_status_value_checks_known_and_allowed_statuses() -> None:
    configuration = build_project_configuration()
    configuration.statuses = [
        StatusDefinition(key="open", name="Open", category="Backlog"),
        StatusDefinition(key="in_progress", name="In Progress", category="In Progress"),
        StatusDefinition(key="closed", name="Closed", category="Done"),
    ]

    with pytest.raises(workflows.InvalidTransitionError, match="unknown status"):
        workflows.validate_status_value(configuration, "task", "nope")

    configuration.workflows["task"] = {"open": ["in_progress"]}
    with pytest.raises(workflows.InvalidTransitionError, match="invalid transition"):
        workflows.validate_status_value(configuration, "task", "closed")


def test_apply_transition_side_effects_sets_and_clears_closed_at() -> None:
    issue_open = _workflow_issue("open")
    issue_closed = _workflow_issue("closed")
    now = issue_open.updated_at

    closed = workflows.apply_transition_side_effects(issue_open, "closed", now)
    reopened = workflows.apply_transition_side_effects(issue_closed, "open", now)

    assert closed.closed_at == now
    assert reopened.closed_at is None
