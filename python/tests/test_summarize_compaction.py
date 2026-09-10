from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import summarize
from kanbus.models import AiConfiguration, DependencyLink, IssueComment

from test_helpers import build_issue, build_project_configuration


def test_resolve_compaction_profile_and_description_budget() -> None:
    active = build_issue("kanbus-a")
    assert (
        summarize.resolve_compaction_profile(active)
        == summarize.COMPACTION_PROFILE_ACTIVE
    )

    recent = build_issue("kanbus-closed", status="closed")
    recent.updated_at = datetime.now(timezone.utc)
    assert (
        summarize.resolve_compaction_profile(recent)
        == summarize.COMPACTION_PROFILE_RECENT_CLOSED
    )

    archived = build_issue("kanbus-archived", status="closed")
    archived.updated_at = datetime.now(timezone.utc) - timedelta(days=40)
    assert (
        summarize.resolve_compaction_profile(archived)
        == summarize.COMPACTION_PROFILE_ARCHIVED
    )

    deep = build_issue("kanbus-deep", status="done")
    deep.updated_at = datetime.now(timezone.utc) - timedelta(days=100)
    assert (
        summarize.resolve_compaction_profile(deep)
        == summarize.COMPACTION_PROFILE_DEEP_ARCHIVE
    )

    assert summarize._description_character_budget("   ", "active") is None
    assert summarize._description_character_budget("x" * 200, "active") > 80


def test_build_description_and_activity_context_with_relations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = build_issue("kanbus-parent")
    parent.description = "Parent goal line"
    child = build_issue("kanbus-child", parent="kanbus-parent")
    child.description = "Child work"
    child.comments = [
        IssueComment.model_validate(
            {
                "id": "c1",
                "author": "dev",
                "text": "progress note",
                "created_at": datetime(2026, 3, 9, tzinfo=timezone.utc).isoformat(),
            }
        ),
        IssueComment.model_validate(
            {
                "id": "s1",
                "author": "system:summary",
                "created_at": datetime(2026, 3, 9, tzinfo=timezone.utc).isoformat(),
                "comment_type": "summary",
                "data": {
                    "rewritten_description": "previous rewrite",
                    "activity_summary": "child activity",
                },
            }
        ),
    ]
    sibling = build_issue("kanbus-dep")
    child.dependencies = [
        DependencyLink.model_validate({"target": "kanbus-dep", "type": "blocks"})
    ]
    sibling.comments = [
        IssueComment.model_validate(
            {
                "id": "s2",
                "author": "system:summary",
                "created_at": datetime(2026, 3, 9, tzinfo=timezone.utc).isoformat(),
                "comment_type": "summary",
                "data": {
                    "rewritten_description": "dep goal",
                    "activity_summary": "dep activity",
                },
            }
        )
    ]
    all_issues = [parent, child, sibling]
    description = summarize._build_description_context(
        child, all_issues, summarize.COMPACTION_PROFILE_ACTIVE
    )
    assert "Parent goal" in description
    assert "previous rewrite" in description

    dry_child = build_issue("kanbus-open-child", parent="kanbus-parent")
    activity = summarize._build_activity_context(
        parent, [parent, dry_child], tmp_path, "kanbus-parent", True
    )
    assert "Would be summarized" in activity

    with_summary = summarize._append_child_activity_context(
        tmp_path, "kanbus-parent", "base", [parent, child], False
    )
    assert "child activity" in with_summary

    unsynced = build_issue("kanbus-unsynced", parent="kanbus-parent")
    monkeypatch.setattr(summarize, "compaction_summarize", lambda *_a, **_k: None)
    monkeypatch.setattr(
        summarize,
        "load_issue_from_project",
        lambda *_a: SimpleNamespace(issue=unsynced),
    )
    generated = summarize._append_child_activity_context(
        tmp_path, "kanbus-parent", "base", [parent, unsynced], False
    )
    assert "(none)" in generated

    dependency_context = summarize._append_dependency_activity_context(
        "base", child, all_issues
    )
    assert "dep activity" in dependency_context
    missing_dep = summarize._append_dependency_activity_context(
        "base",
        SimpleNamespace(
            dependencies=[
                DependencyLink.model_validate({"target": "missing", "type": "blocks"})
            ]
        ),
        all_issues,
    )
    assert "Dependency Activity" in missing_dep


def test_apply_virtualized_issue_view_and_compaction_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    issue = build_issue("kanbus-1")
    issue.description = "original"
    older = IssueComment.model_validate(
        {
            "id": "s1",
            "author": "system:summary",
            "created_at": datetime(2026, 3, 8, tzinfo=timezone.utc).isoformat(),
            "comment_type": "summary",
            "data": {
                "rewritten_description": "compacted",
                "activity_summary": "activity",
            },
        }
    )
    newer = IssueComment.model_validate(
        {
            "id": "c2",
            "author": "dev",
            "text": "after summary",
            "created_at": datetime(2026, 3, 10, tzinfo=timezone.utc).isoformat(),
        }
    )
    issue.comments = [older, newer]
    summarize.apply_virtualized_issue_view(issue, raw=True)
    assert issue.description == "original"
    summarize.apply_virtualized_issue_view(issue, raw=False)
    assert issue.description == "compacted"
    assert issue.comments[0].id == "s1"
    assert issue.comments[-1].id == "c2"

    config = build_project_configuration()
    config.ai = AiConfiguration(provider="litellm", model="mock")
    monkeypatch.setattr(
        summarize, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(summarize, "load_project_configuration", lambda _p: config)
    monkeypatch.setattr(
        summarize,
        "load_issue_from_project",
        lambda *_a: SimpleNamespace(issue=issue),
    )
    monkeypatch.setattr(summarize, "load_issues_from_directory", lambda _d: [issue])
    result = summarize.compaction_summarize(tmp_path, "kanbus-1", dry_run=True)
    assert result is None
    output = capsys.readouterr().out
    assert "dry-run" in output

    no_ai = build_project_configuration()
    monkeypatch.setattr(summarize, "load_project_configuration", lambda _p: no_ai)
    with pytest.raises(RuntimeError, match="litellm"):
        summarize.compaction_summarize(tmp_path, "kanbus-1")


def test_completion_missing_package_and_response_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("KANBUS_TEST_AI_MOCK", raising=False)
    monkeypatch.setattr(summarize, "litellm", None)
    with pytest.raises(RuntimeError, match="litellm package is not installed"):
        summarize._completion(
            "model",
            [{"role": "user", "content": "hi"}],
            "kanbus-1",
            "compaction_activity",
            tmp_path,
            "project",
            temperature=0.2,
        )

    class Usage:
        total_tokens = 9

    class Message:
        content = "ok"

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]
        usage = Usage()

    class Lite:
        @staticmethod
        def completion(**_kwargs):
            return Response()

        @staticmethod
        def completion_cost(completion_response=None):
            raise RuntimeError("cost unavailable")

    recorded: list[object] = []
    monkeypatch.setattr(summarize, "litellm", Lite)
    monkeypatch.setattr(
        summarize,
        "_record_llm_usage",
        lambda *args: recorded.append(args),
    )
    text = summarize._completion(
        "model",
        [{"role": "user", "content": "hi"}],
        "kanbus-1",
        "compaction_activity",
        tmp_path,
        "project",
        temperature=0.1,
    )
    assert text == "ok"
    assert recorded
