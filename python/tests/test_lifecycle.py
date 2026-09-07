from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kanbus import lifecycle
from kanbus.models import AiConfiguration

from test_helpers import build_issue, build_project_configuration


def test_run_lifecycle_compaction_requires_litellm(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = build_project_configuration()
    monkeypatch.setattr(
        lifecycle, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(lifecycle, "load_project_configuration", lambda _path: config)
    with pytest.raises(RuntimeError, match="litellm"):
        lifecycle.run_lifecycle_compaction(tmp_path)


def test_run_lifecycle_compaction_archived_summarize_and_usage_log(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = build_project_configuration().model_copy(
        update={"ai": AiConfiguration(provider="litellm", model="test")}
    )
    monkeypatch.setattr(
        lifecycle, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(lifecycle, "load_project_configuration", lambda _path: config)

    recent_closed = build_issue("kanbus-recent", status="closed")
    recent_closed = recent_closed.model_copy(
        update={"updated_at": datetime.now(timezone.utc)}
    )
    monkeypatch.setattr(
        lifecycle, "load_issues_from_directory", lambda _directory: [recent_closed]
    )
    lifecycle.run_lifecycle_compaction(tmp_path, archived_only=True, dry_run=True)

    open_issue = build_issue("kanbus-open")
    monkeypatch.setattr(
        lifecycle, "load_issues_from_directory", lambda _directory: [open_issue]
    )

    def raise_nonzero_exit(*_args: object, **_kwargs: object) -> None:
        raise SystemExit(2)

    monkeypatch.setattr(lifecycle, "compaction_summarize", raise_nonzero_exit)
    with pytest.raises(SystemExit):
        lifecycle.run_lifecycle_compaction(tmp_path)

    monkeypatch.setattr(
        lifecycle, "compaction_summarize", lambda *_args, **_kwargs: None
    )
    events_dir = tmp_path / "project" / "events"
    events_dir.mkdir(parents=True)
    (events_dir / "llm_usage.jsonl").write_text(
        '{not-json\n{"cost": 1.25}\n',
        encoding="utf-8",
    )
    lifecycle.run_lifecycle_compaction(tmp_path)
