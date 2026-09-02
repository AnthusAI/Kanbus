from __future__ import annotations

from pathlib import Path

import pytest

from kanbus.event_history import create_event
from kanbus.issue_files import read_issue_from_file, write_issue_to_file
from kanbus.issue_mutation import (
    PersistIssueMutationRequest,
    persist_issue_deletion,
    persist_issue_mutation,
)
from kanbus.models import IssueData

from test_helpers import build_issue


def _event(issue_id: str):
    return create_event(
        issue_id=issue_id,
        event_type="issue_created",
        actor_id="dev",
        payload={"ok": True},
        occurred_at="2026-03-09T00:00:00.000Z",
    )


def _request(
    tmp_path: Path,
    issue: IssueData,
    issue_path: Path,
    *,
    before_issue: IssueData | None = None,
    relocate_to: Path | None = None,
    regenerate_right_now: bool = False,
) -> PersistIssueMutationRequest:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    return PersistIssueMutationRequest(
        project_dir=project_dir,
        issue_path=issue_path,
        issue=issue,
        actor_id="dev",
        events=[_event(issue.identifier)],
        root=tmp_path,
        before_issue=before_issue,
        relocate_to=relocate_to,
        regenerate_right_now=regenerate_right_now,
    )


def test_persist_issue_mutation_writes_issue_and_events(tmp_path: Path) -> None:
    issue = build_issue("kanbus-1", title="Created")
    issue_path = tmp_path / "project" / "issues" / "kanbus-1.json"
    result = persist_issue_mutation(_request(tmp_path, issue, issue_path))

    stored = read_issue_from_file(issue_path)
    assert stored.title == "Created"
    assert stored.identifier == result.issue.identifier
    assert list((tmp_path / "project" / "events").glob("*.json"))


def test_persist_issue_mutation_unlinks_create_when_events_fail(
    tmp_path: Path,
) -> None:
    issue = build_issue("kanbus-new", title="Created")
    issue_path = tmp_path / "project" / "issues" / "kanbus-new.json"
    request = _request(tmp_path, issue, issue_path)
    (tmp_path / "project" / "events").write_text("not-a-directory", encoding="utf-8")

    with pytest.raises(RuntimeError):
        persist_issue_mutation(request)

    assert not issue_path.exists()


def test_persist_issue_mutation_restores_before_issue_when_events_fail(
    tmp_path: Path,
) -> None:
    before = build_issue("kanbus-1", title="Before")
    after = build_issue("kanbus-1", title="After")
    issue_path = tmp_path / "project" / "issues" / "kanbus-1.json"
    request = _request(tmp_path, after, issue_path, before_issue=before)
    write_issue_to_file(before, issue_path)
    (tmp_path / "project" / "events").write_text("not-a-directory", encoding="utf-8")

    with pytest.raises(RuntimeError):
        persist_issue_mutation(request)

    restored = read_issue_from_file(issue_path)
    assert restored.title == "Before"


def test_persist_issue_mutation_relocates_then_rolls_back(
    tmp_path: Path,
) -> None:
    issue = build_issue("kanbus-1", title="Moved")
    source = tmp_path / "project-local" / "issues" / "kanbus-1.json"
    target = tmp_path / "project" / "issues" / "kanbus-1.json"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    write_issue_to_file(issue, source)
    (tmp_path / "project-local").mkdir(exist_ok=True)
    request = _request(
        tmp_path,
        issue,
        source,
        before_issue=issue,
        relocate_to=target,
    )
    (tmp_path / "project" / "events").write_text("not-a-directory", encoding="utf-8")

    with pytest.raises(RuntimeError):
        persist_issue_mutation(request)

    assert source.exists()
    assert not target.exists()


def test_persist_issue_mutation_skips_regen_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "kanbus.issue_mutation.regenerate_right_now_for_issue_and_ancestors",
        lambda *_a: calls.append("regen"),
    )
    issue = build_issue("kanbus-1")
    issue_path = tmp_path / "project" / "issues" / "kanbus-1.json"
    persist_issue_mutation(
        _request(tmp_path, issue, issue_path, regenerate_right_now=False)
    )
    assert calls == []


def test_persist_issue_mutation_calls_regen_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "kanbus.issue_mutation.regenerate_right_now_for_issue_and_ancestors",
        lambda *_a: calls.append("regen"),
    )
    issue = build_issue("kanbus-1")
    issue_path = tmp_path / "project" / "issues" / "kanbus-1.json"
    persist_issue_mutation(
        _request(tmp_path, issue, issue_path, regenerate_right_now=True)
    )
    assert calls == ["regen"]


def test_persist_issue_deletion_removes_file_and_writes_audit(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    issue = build_issue("kanbus-1")
    issue_path = issues_dir / "kanbus-1.json"
    write_issue_to_file(issue, issue_path)

    result = persist_issue_deletion(
        tmp_path,
        project_dir,
        issue_path,
        issue,
        "dev",
        retain_audit_event=True,
        regenerate_right_now=False,
    )

    assert not issue_path.exists()
    assert result.event is not None
    assert result.event.event_type == "issue_deleted"
    assert list((project_dir / "events").glob("*.json"))


def test_persist_issue_deletion_restores_file_when_events_fail(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    issue = build_issue("kanbus-1")
    issue_path = issues_dir / "kanbus-1.json"
    write_issue_to_file(issue, issue_path)
    (project_dir / "events").write_text("not-a-directory", encoding="utf-8")

    with pytest.raises(RuntimeError):
        persist_issue_deletion(
            tmp_path,
            project_dir,
            issue_path,
            issue,
            "dev",
            retain_audit_event=True,
            regenerate_right_now=False,
        )

    restored = read_issue_from_file(issue_path)
    assert restored.identifier == "kanbus-1"


def test_persist_issue_deletion_skips_audit_and_regen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "kanbus.issue_mutation.regenerate_right_now_ancestors",
        lambda *_a: calls.append("regen"),
    )
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    issue = build_issue("kanbus-1", parent="kanbus-parent")
    issue_path = issues_dir / "kanbus-1.json"
    write_issue_to_file(issue, issue_path)

    result = persist_issue_deletion(
        tmp_path,
        project_dir,
        issue_path,
        issue,
        "dev",
        retain_audit_event=False,
        regenerate_right_now=False,
    )
    assert result.event is None
    assert calls == []
    assert not issue_path.exists()
