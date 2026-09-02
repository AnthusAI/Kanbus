"""Right-now summary helpers."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.models import IssueComment, IssueData, ProjectConfiguration
from kanbus.project import get_configuration_path

RIGHT_NOW_SUMMARY_OPERATION = "right_now_summary"
LLM_USAGE_LOG = "llm_usage.jsonl"
MOCK_PROMPT_TOKENS = 42
MOCK_COMPLETION_TOKENS = 12
MOCK_TOTAL_TOKENS = 54
MOCK_COST = 0.0
MAX_RECENT_COMMENTS = 5
MAX_RECENT_ACTIVITY_CHARACTERS = 2000
STATUS_KEYWORDS = ("done", "in progress", "blocked", "closed", "open")
AI_PROVIDER_NOT_CONFIGURED_MESSAGE = (
    "Right-now summary generation requires ai.provider litellm in .kanbus.yml"
)


class RightNowError(RuntimeError):
    """Raised when right-now summary generation fails."""


@dataclass
class RightNowChildSummary:
    """Child issue summary for parent context assembly.

    :param identifier: Child issue identifier.
    :type identifier: str
    :param summary: Child right-now summary text.
    :type summary: str
    """

    identifier: str
    summary: str


@dataclass
class RightNowContext:
    """Structured context for right-now summary generation.

    :param title: Issue title.
    :type title: str
    :param description: Issue description.
    :type description: str
    :param recent_activity: Recent non-summary comment text.
    :type recent_activity: str
    :param child_summaries: Optional child summaries for parent roll-up.
    :type child_summaries: Optional[List[RightNowChildSummary]]
    """

    title: str
    description: str
    recent_activity: str
    child_summaries: Optional[List[RightNowChildSummary]] = field(default=None)


def get_right_now_summary(issue: IssueData) -> Optional[str]:
    """Return the right-now summary for an issue.

    :param issue: Issue data to read.
    :type issue: IssueData
    :return: The right-now summary text, or None when absent.
    :rtype: Optional[str]
    """
    return issue.right_now_summary


def mock_right_now_summary_text(identifier: str) -> str:
    """Return the deterministic mock right-now summary for an issue.

    :param identifier: Issue identifier.
    :type identifier: str
    :return: Mock summary text.
    :rtype: str
    """
    return f"Mock right-now summary for {identifier}."


def build_leaf_right_now_context(issue: IssueData) -> RightNowContext:
    """Assemble leaf-issue context from title, description, and recent comments.

    :param issue: Issue to build context for.
    :type issue: IssueData
    :return: Structured right-now context.
    :rtype: RightNowContext
    """
    recent_comments = _select_recent_non_summary_comments(issue.comments)
    activity_lines = [
        f"{comment.author}: {comment.text}" for comment in recent_comments
    ]
    recent_activity = _bound_activity_text("\n".join(activity_lines))
    return RightNowContext(
        title=issue.title,
        description=issue.description,
        recent_activity=recent_activity,
        child_summaries=None,
    )


def generate_right_now_summary(
    root: Path,
    issue: IssueData,
    context: RightNowContext,
) -> str:
    """Generate a right-now summary for an issue using configured AI.

    :param root: Repository root path.
    :type root: Path
    :param issue: Issue to summarize.
    :type issue: IssueData
    :param context: Assembled right-now context.
    :type context: RightNowContext
    :return: One-sentence right-now summary text.
    :rtype: str
    :raises RightNowError: When AI is not configured or generation fails.
    """
    configuration = _load_configuration(root)
    _ensure_litellm_provider(configuration)
    max_length = configuration.right_now.max_length
    model = _resolve_right_now_model(configuration)

    if os.environ.get("KANBUS_TEST_AI_MOCK") == "1":
        summary = mock_right_now_summary_text(issue.identifier)
        _record_llm_usage(
            root=root,
            configuration=configuration,
            issue_identifier=issue.identifier,
            model=model,
            prompt_tokens=MOCK_PROMPT_TOKENS,
            completion_tokens=MOCK_COMPLETION_TOKENS,
            total_tokens=MOCK_TOTAL_TOKENS,
            cost=MOCK_COST,
            mock=True,
        )
        return _truncate_to_max_length(summary, max_length)

    prompt = _build_right_now_prompt(context, max_length)
    completion_text, usage = _completion(model=model, prompt=prompt)
    _record_llm_usage(
        root=root,
        configuration=configuration,
        issue_identifier=issue.identifier,
        model=model,
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
        cost=usage["cost"],
        mock=False,
    )
    return _truncate_to_max_length(completion_text.strip(), max_length)


def summary_contains_status_keyword(summary: str) -> bool:
    """Return whether a summary contains a bare status keyword.

    :param summary: Summary text to inspect.
    :type summary: str
    :return: True when a status keyword appears as a standalone token.
    :rtype: bool
    """
    lowered = summary.lower()
    for keyword in STATUS_KEYWORDS:
        pattern = rf"\b{re.escape(keyword)}\b"
        if re.search(pattern, lowered):
            return True
    return False


def _load_configuration(root: Path) -> ProjectConfiguration:
    try:
        return load_project_configuration(get_configuration_path(root))
    except ConfigurationError as error:
        raise RightNowError(str(error)) from error


def _ensure_litellm_provider(configuration: ProjectConfiguration) -> None:
    if configuration.ai is None or configuration.ai.provider != "litellm":
        raise RightNowError(AI_PROVIDER_NOT_CONFIGURED_MESSAGE)


def _resolve_right_now_model(configuration: ProjectConfiguration) -> str:
    if configuration.ai is None:
        raise RightNowError(AI_PROVIDER_NOT_CONFIGURED_MESSAGE)
    if configuration.right_now.model:
        return configuration.right_now.model
    return configuration.ai.model


def _select_recent_non_summary_comments(
    comments: List[IssueComment],
) -> List[IssueComment]:
    filtered = [
        comment
        for comment in comments
        if not comment.text.strip().lower().startswith("summary:")
    ]
    return filtered[-MAX_RECENT_COMMENTS:]


def _bound_activity_text(activity_text: str) -> str:
    if len(activity_text) <= MAX_RECENT_ACTIVITY_CHARACTERS:
        return activity_text
    return activity_text[-MAX_RECENT_ACTIVITY_CHARACTERS:]


def _build_right_now_prompt(context: RightNowContext, max_length: int) -> str:
    child_section = ""
    if context.child_summaries:
        lines = [
            f"- {child.identifier}: {child.summary}"
            for child in context.child_summaries
        ]
        child_section = "Child summaries:\n" + "\n".join(lines) + "\n\n"
    return (
        "Write exactly one short sentence describing what is happening with this "
        "issue right now. Use plain, direct language in Hemingway style. "
        f"Do not mention issue status labels such as open, closed, blocked, done, "
        f"or in progress. Maximum {max_length} characters.\n\n"
        f"Title: {context.title}\n"
        f"Description: {context.description}\n"
        f"Recent activity:\n{context.recent_activity}\n\n"
        f"{child_section}"
    )


def _completion(model: str, prompt: str) -> tuple[str, dict[str, float | int]]:
    try:
        import litellm
    except ImportError as error:
        raise RightNowError(
            "litellm is required for right-now summary generation"
        ) from error

    os.environ["KANBUS_RIGHT_NOW_LITELLM_CALLED"] = "1"
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    message = response.choices[0].message.content
    if not message:
        raise RightNowError("right-now summary generation returned empty content")
    usage = response.usage
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(
        getattr(usage, "total_tokens", prompt_tokens + completion_tokens)
    )
    cost = float(
        getattr(response, "_hidden_params", {}).get("response_cost", 0.0) or 0.0
    )
    return message, {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost": cost,
    }


def _record_llm_usage(
    root: Path,
    configuration: ProjectConfiguration,
    issue_identifier: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost: float,
    mock: bool,
) -> None:
    events_dir = root.joinpath(configuration.project_directory, "events")
    events_dir.mkdir(parents=True, exist_ok=True)
    log_path = events_dir / LLM_USAGE_LOG
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": RIGHT_NOW_SUMMARY_OPERATION,
        "issue_id": issue_identifier,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost": cost,
        "mock": mock,
    }
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _truncate_to_max_length(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        return truncated[:last_space].rstrip()
    return truncated.rstrip()
