from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import issue_comment
from kanbus.models import IssueComment

from test_helpers import build_issue


def _c(text: str, cid: str | None = None, author: str = "dev") -> IssueComment:
    return IssueComment.model_validate(
        {
            "id": cid,
            "author": author,
            "text": text,
            "created_at": datetime(2026, 3, 9, tzinfo=timezone.utc).isoformat(),
        }
    )


def test_normalize_prefix_and_find_comment_index() -> None:
    with pytest.raises(issue_comment.IssueCommentError, match="comment id is required"):
        issue_comment._normalize_prefix("  ")
    assert issue_comment._normalize_prefix(" AbC ") == "abc"

    issue = build_issue("kanbus-1")
    issue.comments = [_c("a", "abcdef"), _c("b", "abc999"), _c("c", "fff111")]

    with pytest.raises(issue_comment.IssueCommentError, match="ambiguous"):
        issue_comment._find_comment_index(issue, "abc")
    with pytest.raises(issue_comment.IssueCommentError, match="comment not found"):
        issue_comment._find_comment_index(issue, "zzz")
    assert issue_comment._find_comment_index(issue, "fff") == 2


def test_generate_comment_id_shape() -> None:
    generated = issue_comment._generate_comment_id()
    assert isinstance(generated, str)
    assert len(generated) >= 8


def test_ensure_comment_ids_changed_and_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    issue = build_issue("kanbus-1")
    issue.comments = [_c("a", None), _c("b", "bb")]
    monkeypatch.setattr(issue_comment, "_generate_comment_id", lambda: "gen-1")

    updated, changed = issue_comment._ensure_comment_ids(issue)
    assert changed is True
    assert updated.comments[0].id == "gen-1"

    unchanged, changed2 = issue_comment._ensure_comment_ids(updated)
    assert changed2 is False
    assert unchanged is updated


def test_add_comment_success_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path("/repo")
    project_dir = Path("/repo/project")
    issue_path = project_dir / "issues" / "kanbus-1.json"
    issue = build_issue("kanbus-1")
    issue.comments = [_c("old", None)]
    lookup = SimpleNamespace(issue=issue, issue_path=issue_path, project_dir=project_dir)

    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: lookup)
    ids = iter(["existing-id", "new-id"])
    monkeypatch.setattr(issue_comment, "_generate_comment_id", lambda: next(ids))
    writes: list[object] = []
    monkeypatch.setattr(issue_comment, "write_issue_to_file", lambda *_a: writes.append("w"))
    monkeypatch.setattr(issue_comment, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(issue_comment, "get_current_user", lambda: "dev")
    monkeypatch.setattr(issue_comment, "comment_payload", lambda _id, _author: {"ok": True})
    monkeypatch.setattr(issue_comment, "create_event", lambda **_kwargs: SimpleNamespace(event_id="evt-1"))
    monkeypatch.setattr(issue_comment, "events_dir_for_issue_path", lambda *_a: Path("/events"))
    monkeypatch.setattr(issue_comment, "write_events_batch", lambda *_a: None)
    published: list[str] = []
    monkeypatch.setattr(issue_comment, "publish_issue_mutation", lambda *_a: published.append("pub"))

    result = issue_comment.add_comment(root, "kanbus-1", "dev", "new")
    assert result.comment.id == "new-id"
    assert len(result.issue.comments) == 2
    assert published == ["pub"]

    monkeypatch.setattr(
        issue_comment,
        "load_issue_from_project",
        lambda *_a: (_ for _ in ()).throw(issue_comment.IssueLookupError("missing")),
    )
    with pytest.raises(issue_comment.IssueCommentError, match="missing"):
        issue_comment.add_comment(root, "x", "dev", "x")

    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: lookup)
    monkeypatch.setattr(issue_comment, "_generate_comment_id", lambda: "id-x")
    monkeypatch.setattr(
        issue_comment,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event fail")),
    )
    with pytest.raises(issue_comment.IssueCommentError, match="event fail"):
        issue_comment.add_comment(root, "kanbus-1", "dev", "new")
    assert len(writes) >= 2

    monkeypatch.setattr(issue_comment, "_generate_comment_id", lambda: None)
    monkeypatch.setattr(issue_comment, "write_events_batch", lambda *_a: None)
    with pytest.raises(issue_comment.IssueCommentError, match="comment id is required"):
        issue_comment.add_comment(root, "kanbus-1", "dev", "new")


def test_ensure_issue_comment_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    issue = build_issue("kanbus-1")
    issue.comments = [_c("old", None)]
    lookup = SimpleNamespace(issue=issue, issue_path=Path("/repo/project/issues/kanbus-1.json"))
    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: lookup)
    monkeypatch.setattr(issue_comment, "_generate_comment_id", lambda: "id-1")
    wrote: list[str] = []
    monkeypatch.setattr(issue_comment, "write_issue_to_file", lambda *_a: wrote.append("w"))

    updated = issue_comment.ensure_issue_comment_ids(Path("/repo"), "kanbus-1")
    assert updated.comments[0].id == "id-1"
    assert wrote == ["w"]

    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: (_ for _ in ()).throw(issue_comment.IssueLookupError("missing")))
    with pytest.raises(issue_comment.IssueCommentError, match="missing"):
        issue_comment.ensure_issue_comment_ids(Path("/repo"), "x")


def test_update_comment_success_and_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path("/repo")
    project_dir = Path("/repo/project")
    issue_path = project_dir / "issues" / "kanbus-1.json"
    issue = build_issue("kanbus-1")
    issue.comments = [_c("old", "abc123")]
    lookup = SimpleNamespace(issue=issue, issue_path=issue_path, project_dir=project_dir)

    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: lookup)
    monkeypatch.setattr(issue_comment, "write_issue_to_file", lambda *_a: None)
    monkeypatch.setattr(issue_comment, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(issue_comment, "get_current_user", lambda: "dev")
    monkeypatch.setattr(issue_comment, "comment_updated_payload", lambda *_a: {"ok": True})
    monkeypatch.setattr(issue_comment, "create_event", lambda **_kwargs: SimpleNamespace(event_id="evt-2"))
    monkeypatch.setattr(issue_comment, "events_dir_for_issue_path", lambda *_a: Path("/events"))
    monkeypatch.setattr(issue_comment, "write_events_batch", lambda *_a: None)
    monkeypatch.setattr(issue_comment, "publish_issue_mutation", lambda *_a: None)

    updated = issue_comment.update_comment(root, "kanbus-1", "abc", "new text")
    assert updated.comments[0].text == "new text"

    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: (_ for _ in ()).throw(issue_comment.IssueLookupError("missing")))
    with pytest.raises(issue_comment.IssueCommentError, match="missing"):
        issue_comment.update_comment(root, "x", "abc", "new")

    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: lookup)
    no_id_issue = build_issue("kanbus-1")
    no_id_issue.comments = [_c("old", None)]
    monkeypatch.setattr(issue_comment, "_ensure_comment_ids", lambda _issue: (no_id_issue, False))
    monkeypatch.setattr(issue_comment, "_find_comment_index", lambda *_a: 0)
    with pytest.raises(issue_comment.IssueCommentError, match="comment id is required"):
        issue_comment.update_comment(root, "kanbus-1", "abc", "new")


def test_update_delete_comment_event_failure_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path("/repo")
    project_dir = Path("/repo/project")
    issue_path = project_dir / "local" / "kanbus-1.json"
    issue = build_issue("kanbus-1")
    issue.comments = [_c("old", "abc123")]
    lookup = SimpleNamespace(issue=issue, issue_path=issue_path, project_dir=project_dir)

    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: lookup)
    writes: list[str] = []
    monkeypatch.setattr(issue_comment, "write_issue_to_file", lambda *_a: writes.append("w"))
    monkeypatch.setattr(issue_comment, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(issue_comment, "get_current_user", lambda: "dev")
    monkeypatch.setattr(issue_comment, "comment_updated_payload", lambda *_a: {"ok": True})
    monkeypatch.setattr(issue_comment, "comment_payload", lambda *_a: {"ok": True})
    monkeypatch.setattr(issue_comment, "create_event", lambda **_kwargs: SimpleNamespace(event_id="evt-3"))
    monkeypatch.setattr(issue_comment, "events_dir_for_issue_path", lambda *_a: Path("/events"))
    monkeypatch.setattr(
        issue_comment,
        "write_events_batch",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("event fail")),
    )
    monkeypatch.setattr(issue_comment, "publish_issue_mutation", lambda *_a: (_ for _ in ()).throw(RuntimeError("should not publish")))

    with pytest.raises(issue_comment.IssueCommentError, match="event fail"):
        issue_comment.update_comment(root, "kanbus-1", "abc", "new")
    with pytest.raises(issue_comment.IssueCommentError, match="event fail"):
        issue_comment.delete_comment(root, "kanbus-1", "abc")
    assert len(writes) >= 4


def test_delete_comment_success_lookup_error_and_missing_id(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path("/repo")
    project_dir = Path("/repo/project")
    issue_path = project_dir / "issues" / "kanbus-1.json"
    issue = build_issue("kanbus-1")
    issue.comments = [_c("old", "abc123")]
    lookup = SimpleNamespace(issue=issue, issue_path=issue_path, project_dir=project_dir)

    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: lookup)
    monkeypatch.setattr(issue_comment, "write_issue_to_file", lambda *_a: None)
    monkeypatch.setattr(issue_comment, "now_timestamp", lambda: "2026-03-09T00:00:00.000Z")
    monkeypatch.setattr(issue_comment, "get_current_user", lambda: "dev")
    monkeypatch.setattr(issue_comment, "comment_payload", lambda *_a: {"ok": True})
    monkeypatch.setattr(issue_comment, "create_event", lambda **_kwargs: SimpleNamespace(event_id="evt-4"))
    monkeypatch.setattr(issue_comment, "events_dir_for_issue_path", lambda *_a: Path("/events"))
    monkeypatch.setattr(issue_comment, "write_events_batch", lambda *_a: None)
    published: list[str] = []
    monkeypatch.setattr(issue_comment, "publish_issue_mutation", lambda *_a: published.append("pub"))

    updated = issue_comment.delete_comment(root, "kanbus-1", "abc")
    assert updated.comments == []
    assert published == ["pub"]

    monkeypatch.setattr(
        issue_comment,
        "load_issue_from_project",
        lambda *_a: (_ for _ in ()).throw(issue_comment.IssueLookupError("missing")),
    )
    with pytest.raises(issue_comment.IssueCommentError, match="missing"):
        issue_comment.delete_comment(root, "x", "abc")

    monkeypatch.setattr(issue_comment, "load_issue_from_project", lambda *_a: lookup)
    no_id_issue = build_issue("kanbus-1")
    no_id_issue.comments = [_c("old", None)]
    monkeypatch.setattr(issue_comment, "_ensure_comment_ids", lambda _issue: (no_id_issue, False))
    monkeypatch.setattr(issue_comment, "_find_comment_index", lambda *_a: 0)
    with pytest.raises(issue_comment.IssueCommentError, match="comment id is required"):
        issue_comment.delete_comment(root, "kanbus-1", "abc")
