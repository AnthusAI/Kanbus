from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kanbus.issue_files import write_issue_to_file
from kanbus.lifecycle import run_lifecycle_compaction
from kanbus.models import AiConfiguration, IssueComment

from test_helpers import build_issue, build_project_configuration


def test_run_lifecycle_compaction_requires_litellm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration = build_project_configuration()
    configuration.ai = AiConfiguration(provider="mock", model="test")
    config_path = tmp_path / ".kanbus.yml"
    config_path.write_text("project_directory: project\n", encoding="utf-8")
    monkeypatch.setattr(
        "kanbus.lifecycle.get_configuration_path",
        lambda _root: config_path,
    )
    monkeypatch.setattr(
        "kanbus.lifecycle.load_project_configuration",
        lambda _path: configuration,
    )
    with pytest.raises(RuntimeError, match="litellm"):
        run_lifecycle_compaction(tmp_path)


def test_run_lifecycle_compaction_archived_only_and_usage_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    configuration = build_project_configuration()
    configuration.ai = AiConfiguration(provider="litellm", model="test")
    issues_dir = tmp_path / "project" / "issues"
    issues_dir.mkdir(parents=True)
    recent = build_issue("kanbus-recent", status="closed")
    recent.updated_at = datetime.now(timezone.utc) - timedelta(days=1)
    write_issue_to_file(recent, issues_dir / "kanbus-recent.json")
    old = build_issue("kanbus-old", status="closed")
    old.updated_at = datetime.now(timezone.utc) - timedelta(days=40)
    write_issue_to_file(old, issues_dir / "kanbus-old.json")
    summarized = build_issue("kanbus-summary", status="closed")
    summarized.comments = [
        IssueComment.model_validate(
            {
                "id": "1",
                "author": "dev",
                "text": "summary",
                "created_at": "2026-03-09T00:00:00Z",
                "comment_type": "summary",
            }
        )
    ]
    write_issue_to_file(summarized, issues_dir / "kanbus-summary.json")
    config_path = tmp_path / ".kanbus.yml"
    config_path.write_text("project_directory: project\n", encoding="utf-8")
    monkeypatch.setattr(
        "kanbus.lifecycle.get_configuration_path",
        lambda _root: config_path,
    )
    monkeypatch.setattr(
        "kanbus.lifecycle.load_project_configuration",
        lambda _path: configuration,
    )

    def compaction_side_effect(
        _root: Path, issue_identifier: str, dry_run: bool = False
    ) -> None:
        if issue_identifier == "kanbus-old":
            raise SystemExit(0)

    monkeypatch.setattr(
        "kanbus.lifecycle.compaction_summarize",
        compaction_side_effect,
    )
    events_dir = tmp_path / "project" / "events"
    events_dir.mkdir(parents=True)
    (events_dir / "llm_usage.jsonl").write_text(
        json.dumps({"cost": "0.25"}) + "\n" + "not-json\n",
        encoding="utf-8",
    )
    run_lifecycle_compaction(tmp_path, archived_only=True, max_items=5)
    output = capsys.readouterr().out
    assert "Summary saved for kanbus-old" in output
    assert "Processed 1 issues" in output
    assert "Total cost: $0.2500" in output
