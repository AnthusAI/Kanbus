from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus.issue_files import read_issue_from_file, write_issue_to_file
from kanbus.models import AiConfiguration, IssueComment, RightNowConfiguration
from kanbus.overlay import load_overlay_issue, write_overlay_issue
from kanbus.right_now import (
    AI_PROVIDER_NOT_CONFIGURED_MESSAGE,
    RightNowError,
    _bound_activity_text,
    _build_right_now_prompt,
    _ensure_litellm_provider,
    _resolve_right_now_model,
    _select_recent_non_summary_comments,
    _truncate_to_max_length,
    build_bounded_raw_child_summary,
    build_right_now_context,
    generate_right_now_summary,
    get_child_full_summary,
    get_right_now_summary,
    mock_right_now_summary_text,
    persist_right_now_summary,
    regenerate_right_now_ancestors,
    regenerate_right_now_for_issue,
    resolve_child_summary,
    summary_contains_status_keyword,
)

from test_helpers import build_issue, build_project_configuration


def _comment(text: str, author: str = "dev") -> IssueComment:
    return IssueComment.model_validate(
        {
            "id": "abc12345",
            "author": author,
            "text": text,
            "created_at": datetime(2026, 3, 9, tzinfo=timezone.utc).isoformat(),
        }
    )


def test_mock_and_get_right_now_summary_helpers() -> None:
    issue = build_issue("kanbus-rn1")
    assert get_right_now_summary(issue) is None
    issue.right_now_summary = "Ship the panel."
    assert get_right_now_summary(issue) == "Ship the panel."
    assert mock_right_now_summary_text("kanbus-rn1") == (
        "Mock right-now summary for kanbus-rn1."
    )
    assert get_child_full_summary(issue) is None


def test_resolve_child_summary_prefers_right_now_then_raw() -> None:
    cached = build_issue("kanbus-child")
    cached.right_now_summary = "Child is implementing the tree."
    assert resolve_child_summary(cached) == "Child is implementing the tree."

    raw = build_issue("kanbus-raw", title="Raw child")
    raw.description = "Details"
    raw.comments = [_comment("working on it")]
    rendered = resolve_child_summary(raw)
    assert "Title: Raw child" in rendered
    assert "working on it" in rendered


def test_build_right_now_context_leaf_and_parent() -> None:
    leaf = build_issue("kanbus-leaf", title="Leaf")
    leaf.description = "Leaf body"
    leaf.comments = [_comment("Summary: ignore me"), _comment("real activity")]
    leaf_context = build_right_now_context(leaf, [])
    assert leaf_context.title == "Leaf"
    assert "real activity" in leaf_context.recent_activity
    assert "Summary:" not in leaf_context.recent_activity
    assert leaf_context.child_summaries is None

    parent = build_issue("kanbus-parent", title="Parent")
    child = build_issue("kanbus-child", title="Child")
    child.right_now_summary = "Child is mid-implementation."
    parent_context = build_right_now_context(parent, [child])
    assert parent_context.child_summaries is not None
    assert parent_context.child_summaries[0].identifier == "kanbus-child"
    assert parent_context.child_summaries[0].summary == "Child is mid-implementation."


def test_summary_contains_status_keyword_and_truncation() -> None:
    assert summary_contains_status_keyword("Still open after review") is True
    assert summary_contains_status_keyword("Opening the panel now") is False
    assert _truncate_to_max_length("short", 20) == "short"
    assert _truncate_to_max_length("Mock right-now summary for x.", 20) == (
        "Mock right-now"
    )
    assert _truncate_to_max_length("abcdefghij", 4) == "abcd"
    long_text = "x" * 2500
    bounded = _bound_activity_text(long_text)
    assert len(bounded) == 2000


def test_select_recent_comments_and_prompt() -> None:
    comments = [_comment(f"note {index}") for index in range(7)]
    selected = _select_recent_non_summary_comments(comments)
    assert len(selected) == 5
    assert selected[0].text == "note 2"
    context = build_right_now_context(build_issue("kanbus-1", title="T"), [])
    context.child_summaries = None
    prompt = _build_right_now_prompt(context, 120)
    assert "Title: T" in prompt
    assert "Maximum 120 characters" in prompt


def test_resolve_model_and_provider_guards() -> None:
    configuration = build_project_configuration()
    with pytest.raises(RightNowError, match=AI_PROVIDER_NOT_CONFIGURED_MESSAGE):
        _ensure_litellm_provider(configuration)
    with pytest.raises(RightNowError, match=AI_PROVIDER_NOT_CONFIGURED_MESSAGE):
        _resolve_right_now_model(configuration)

    configuration.ai = AiConfiguration(provider="openai", model="gpt-4o")
    with pytest.raises(RightNowError, match=AI_PROVIDER_NOT_CONFIGURED_MESSAGE):
        _ensure_litellm_provider(configuration)

    configuration.ai = AiConfiguration(provider="litellm", model="gpt-4o")
    _ensure_litellm_provider(configuration)
    assert _resolve_right_now_model(configuration) == "gpt-4o"
    configuration.right_now = RightNowConfiguration(model="gpt-5.6-luna")
    assert _resolve_right_now_model(configuration) == "gpt-5.6-luna"


def test_persist_right_now_summary_updates_canonical_and_overlay(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    issue = build_issue("kanbus-rn1", title="Canonical")
    issue_path = issues_dir / "kanbus-rn1.json"
    write_issue_to_file(issue, issue_path)
    write_overlay_issue(
        project_dir,
        issue,
        "2099-01-01T00:00:00.000Z",
        "evt-overlay",
    )
    updated_at = datetime(2026, 9, 2, tzinfo=timezone.utc)
    persist_right_now_summary(
        project_dir,
        issue_path,
        "kanbus-rn1",
        "Canonical work continues.",
        updated_at,
    )
    stored = read_issue_from_file(issue_path)
    assert stored.right_now_summary == "Canonical work continues."
    overlay = load_overlay_issue(project_dir, "kanbus-rn1")
    assert overlay is not None
    assert overlay.issue.right_now_summary == "Canonical work continues."
    assert overlay.overlay_ts == "2099-01-01T00:00:00.000Z"


def test_generate_right_now_summary_mock_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = build_project_configuration()
    configuration.ai = AiConfiguration(provider="litellm", model="gpt-5.6-luna")
    configuration.right_now = RightNowConfiguration(max_length=80)
    monkeypatch.setattr(
        "kanbus.right_now._load_configuration", lambda _root: configuration
    )
    monkeypatch.setenv("KANBUS_TEST_AI_MOCK", "1")
    issue = build_issue("kanbus-mock")
    summary = generate_right_now_summary(
        tmp_path, issue, build_right_now_context(issue, [])
    )
    assert summary == "Mock right-now summary for kanbus-mock."
    usage_log = tmp_path / "project" / "events" / "llm_usage.jsonl"
    assert usage_log.exists()


def test_generate_right_now_summary_completion_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = build_project_configuration()
    configuration.ai = AiConfiguration(provider="litellm", model="gpt-5.6-luna")
    monkeypatch.setattr(
        "kanbus.right_now._load_configuration", lambda _root: configuration
    )
    monkeypatch.delenv("KANBUS_TEST_AI_MOCK", raising=False)
    monkeypatch.setattr(
        "kanbus.right_now._completion",
        lambda **_k: (
            "  Agents are wiring the write gate.  ",
            {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "cost": 0.0,
            },
        ),
    )
    issue = build_issue("kanbus-live")
    summary = generate_right_now_summary(
        tmp_path, issue, build_right_now_context(issue, [])
    )
    assert summary == "Agents are wiring the write gate."


def test_regenerate_right_now_skips_when_disabled_or_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    disabled = build_project_configuration()
    disabled.right_now = RightNowConfiguration(enabled=False)
    monkeypatch.setattr("kanbus.right_now._load_configuration", lambda _root: disabled)
    regenerate_right_now_for_issue(tmp_path, "kanbus-missing")

    monkeypatch.setattr(
        "kanbus.right_now._load_configuration",
        lambda _root: (_ for _ in ()).throw(RightNowError("no config")),
    )
    regenerate_right_now_for_issue(tmp_path, "kanbus-missing")
    regenerate_right_now_ancestors(tmp_path, None)


def test_load_configuration_wraps_missing_project_marker(
    tmp_path: Path,
) -> None:
    with pytest.raises(RightNowError, match="project not initialized"):
        from kanbus.right_now import _load_configuration

        _load_configuration(tmp_path)


def test_regenerate_right_now_persists_generated_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = build_project_configuration()
    configuration.ai = AiConfiguration(provider="litellm", model="gpt-5.6-luna")
    monkeypatch.setattr(
        "kanbus.right_now._load_configuration", lambda _root: configuration
    )
    issue = build_issue("kanbus-regen")
    issue_path = tmp_path / "project" / "issues" / "kanbus-regen.json"
    issue_path.parent.mkdir(parents=True)
    write_issue_to_file(issue, issue_path)
    lookup = SimpleNamespace(
        issue=issue,
        issue_path=issue_path,
        project_dir=tmp_path / "project",
    )
    monkeypatch.setattr("kanbus.right_now.load_issue_from_project", lambda *_a: lookup)
    monkeypatch.setattr("kanbus.right_now.load_child_issues", lambda *_a: [])
    monkeypatch.setattr(
        "kanbus.right_now.generate_right_now_summary",
        lambda *_a: "Regenerated summary.",
    )
    regenerate_right_now_for_issue(tmp_path, "kanbus-regen")
    stored = read_issue_from_file(issue_path)
    assert stored.right_now_summary == "Regenerated summary."


def test_build_bounded_raw_child_summary_includes_title() -> None:
    issue = build_issue("kanbus-raw", title="Bounded")
    issue.description = "Body"
    rendered = build_bounded_raw_child_summary(issue)
    assert "Title: Bounded" in rendered
    assert "Description: Body" in rendered
