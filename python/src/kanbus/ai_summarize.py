"""AI summarization for wiki templates."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

from kanbus.models import AiConfiguration

AI_SUMMARIES_CACHE = "ai_summaries.json"
AI_CALLS_LOG = "ai_calls.log"


def _cache_key(issue: Dict[str, Any], detail: str) -> str:
    identifier = str(issue.get("id") or issue.get("identifier", ""))
    updated = str(issue.get("updated_at", ""))
    return hashlib.sha256(f"{identifier}:{updated}:{detail}".encode()).hexdigest()


def _log_call(cache_dir: Path) -> None:
    log_path = cache_dir / AI_CALLS_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("1\n")


def _read_cache(cache_dir: Path, key: str) -> str | None:
    path = cache_dir / AI_SUMMARIES_CACHE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get(key)
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(cache_dir: Path, key: str, value: str) -> None:
    path = cache_dir / AI_SUMMARIES_CACHE
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    data[key] = value
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def summarize_issue(
    issue: Dict[str, Any], detail: str, ai_config: AiConfiguration | None
) -> str:
    """Summarize an issue for wiki templates.

    :param issue: Serialized issue dict (from issue() in templates).
    :type issue: Dict[str, Any]
    :param detail: Detail level (e.g. short, medium).
    :type detail: str
    :param ai_config: AI configuration from project, or None.
    :type ai_config: AiConfiguration | None
    :return: Summary text.
    :rtype: str
    """
    if ai_config is None:
        return "(AI summarization not configured)"

    if os.environ.get("KANBUS_TEST_AI_MOCK") == "1":
        identifier = issue.get("id") or issue.get("identifier", "unknown")
        return f"Generated summary for {identifier}"

    return f"Summary: {issue.get('title', 'untitled')}"


def make_ai_summarize(
    issues_by_id: Dict[str, Dict[str, Any]],
    ai_config: AiConfiguration | None,
    cache_dir: Path | None,
):
    """Build ai_summarize callable for wiki template context.

    :param issues_by_id: Map of issue id to serialized issue.
    :type issues_by_id: Dict[str, Dict[str, Any]]
    :param ai_config: AI configuration or None.
    :type ai_config: AiConfiguration | None
    :param cache_dir: Directory for AI cache (project/.cache) or None to skip cache.
    :type cache_dir: Path | None
    :return: Callable(issue_or_id, detail) for templates.
    :rtype: Callable
    """

    def ai_summarize(issue_or_id: Any, detail: str = "short") -> str:
        if isinstance(issue_or_id, dict):
            issue = issue_or_id
        else:
            identifier = str(issue_or_id)
            issue = issues_by_id.get(identifier)
            if issue is None:
                return "(issue not found)"
        if ai_config is None:
            return "(AI summarization not configured)"
        if cache_dir is not None:
            key = _cache_key(issue, detail)
            cached = _read_cache(cache_dir, key)
            if cached is not None:
                return cached
        result = summarize_issue(issue, detail, ai_config)
        if cache_dir is not None:
            key = _cache_key(issue, detail)
            _write_cache(cache_dir, key, result)
            if os.environ.get("KANBUS_TEST_AI_MOCK") == "1":
                _log_call(cache_dir)
        return result

    return ai_summarize
