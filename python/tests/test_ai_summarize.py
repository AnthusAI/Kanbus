from __future__ import annotations

from pathlib import Path

from kanbus import ai_summarize
from kanbus.models import AiConfiguration


def _ai_config() -> AiConfiguration:
    return AiConfiguration(provider="test", model="gpt-test")


def test_cache_key_uses_identifier_updated_at_and_detail() -> None:
    issue = {"id": "kanbus-1", "updated_at": "2026-01-01T00:00:00Z"}
    key_a = ai_summarize._cache_key(issue, "short")
    key_b = ai_summarize._cache_key(issue, "long")
    assert key_a != key_b


def test_read_cache_returns_none_for_missing_and_invalid_json(tmp_path: Path) -> None:
    assert ai_summarize._read_cache(tmp_path, "k") is None
    (tmp_path / ai_summarize.AI_SUMMARIES_CACHE).write_text("{bad", encoding="utf-8")
    assert ai_summarize._read_cache(tmp_path, "k") is None


def test_write_cache_persists_and_updates_entries(tmp_path: Path) -> None:
    ai_summarize._write_cache(tmp_path, "k1", "v1")
    ai_summarize._write_cache(tmp_path, "k2", "v2")
    assert ai_summarize._read_cache(tmp_path, "k1") == "v1"
    assert ai_summarize._read_cache(tmp_path, "k2") == "v2"


def test_summarize_issue_returns_not_configured_when_ai_absent() -> None:
    issue = {"identifier": "kanbus-2", "title": "Title"}
    assert (
        ai_summarize.summarize_issue(issue, "short", None)
        == "(AI summarization not configured)"
    )


def test_make_ai_summarize_handles_missing_issue_and_cache_hits(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("KANBUS_TEST_AI_MOCK", raising=False)
    issue = {"identifier": "kanbus-3", "title": "A title", "updated_at": "2026-01-01"}
    fn = ai_summarize.make_ai_summarize(
        {"kanbus-3": issue},
        _ai_config(),
        tmp_path,
    )

    assert fn("missing") == "(issue not found)"
    first = fn("kanbus-3", "short")
    second = fn("kanbus-3", "short")
    assert first == "Summary: A title"
    assert second == first


def test_make_ai_summarize_mock_mode_logs_calls(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KANBUS_TEST_AI_MOCK", "1")
    issue = {"identifier": "kanbus-4", "title": "B title", "updated_at": "2026-01-02"}
    fn = ai_summarize.make_ai_summarize(
        {"kanbus-4": issue},
        _ai_config(),
        tmp_path,
    )
    result = fn("kanbus-4", "short")
    assert result == "Generated summary for kanbus-4"
    log_path = tmp_path / ai_summarize.AI_CALLS_LOG
    assert log_path.exists()
    assert log_path.read_text(encoding="utf-8").strip() == "1"
