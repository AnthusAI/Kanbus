from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kanbus import lifecycle
from kanbus.models import AiConfiguration, IssueComment

from test_helpers import build_issue, build_project_configuration


def test_run_lifecycle_compaction_covers_archive_and_cost_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_ai = build_project_configuration()
    monkeypatch.setattr(
        lifecycle, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(lifecycle, "load_project_configuration", lambda _p: missing_ai)
    with pytest.raises(RuntimeError, match="litellm"):
        lifecycle.run_lifecycle_compaction(tmp_path)

    config = build_project_configuration()
    config.ai = AiConfiguration(provider="litellm", model="mock")
    monkeypatch.setattr(lifecycle, "load_project_configuration", lambda _p: config)

    summarized = build_issue("kanbus-summarized")
    summarized.comments = [
        IssueComment.model_validate(
            {
                "id": "s1",
                "author": "system:summary",
                "created_at": datetime(2026, 3, 9, tzinfo=timezone.utc).isoformat(),
                "comment_type": "summary",
                "data": {
                    "rewritten_description": "goal",
                    "activity_summary": "activity",
                },
            }
        )
    ]
    too_new = build_issue("kanbus-new", status="closed")
    too_new.updated_at = datetime.now(timezone.utc)
    archived = build_issue("kanbus-old", status="closed")
    archived.updated_at = datetime.now(timezone.utc) - timedelta(days=40)
    open_issue = build_issue("kanbus-open")

    monkeypatch.setattr(
        lifecycle,
        "load_issues_from_directory",
        lambda _d: [summarized, too_new, archived, open_issue],
    )
    lifecycle.run_lifecycle_compaction(tmp_path, archived_only=True, dry_run=True)
    dry_output = capsys.readouterr().out
    assert "Would summarize kanbus-old" in dry_output
    assert "kanbus-new" not in dry_output

    calls: list[str] = []

    def fake_summarize(_root, identifier, dry_run=False):
        calls.append(identifier)
        if identifier == "kanbus-new":
            raise SystemExit(0)
        raise SystemExit(1)

    monkeypatch.setattr(lifecycle, "compaction_summarize", fake_summarize)
    with pytest.raises(SystemExit):
        lifecycle.run_lifecycle_compaction(tmp_path, max_items=2)
    assert calls[0] == "kanbus-new"

    events = tmp_path / "project" / "events"
    events.mkdir(parents=True, exist_ok=True)
    (events / "llm_usage.jsonl").write_text(
        "\n".join(["", "{bad json}", '{"cost":"0.25"}']) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(lifecycle, "compaction_summarize", lambda *_a, **_k: None)
    monkeypatch.setattr(
        lifecycle,
        "load_issues_from_directory",
        lambda _d: [archived],
    )
    lifecycle.run_lifecycle_compaction(tmp_path)
    cost_output = capsys.readouterr().out
    assert "Total cost: $0.2500" in cost_output
