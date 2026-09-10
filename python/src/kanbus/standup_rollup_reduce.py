"""Upward LLM summarization for standup rollup."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from kanbus.config_loader import load_repository_environment
from kanbus.models import ProjectConfiguration
from kanbus.project import ProjectMarkerError, get_configuration_path
from kanbus.right_now import (
    AI_PROVIDER_NOT_CONFIGURED_MESSAGE,
    RightNowError,
    _completion,
    _curated_litellm_failure_message,
    _ensure_litellm_provider,
    _load_configuration,
    _resolve_right_now_model,
)
from kanbus.standup_rollup import (
    StandupRollupError,
    dedupe_summary_list,
    truncate_bullet,
)

TEST_STANDUP_ROLLUP_COMPLETION_ENV = "KANBUS_TEST_STANDUP_ROLLUP_COMPLETION"
STANDUP_ROLLUP_MAX_LENGTH = 120


def _build_standup_rollup_reduce_prompt(summaries: List[str], max_length: int) -> str:
    lines = "\n".join(f"- {summary}" for summary in summaries)
    return (
        "Write exactly one short sentence a director can act on that summarizes "
        "the active work below. State what is in flight and any obvious close-out "
        "signal when present. Do not use semicolons, bullet lists, or issue IDs.\n"
        f"Maximum {max_length} characters.\n\n"
        f"Facts:\n{lines}\n"
    )


def _mock_standup_rollup_reduce(summaries: List[str]) -> str:
    stub = os.environ.get(TEST_STANDUP_ROLLUP_COMPLETION_ENV)
    if stub is not None and stub.strip():
        return truncate_bullet(stub.strip(), STANDUP_ROLLUP_MAX_LENGTH)
    first = summaries[0].rstrip(".")
    return truncate_bullet(
        f"{first} and related delivery tracks remain in flight.",
        STANDUP_ROLLUP_MAX_LENGTH,
    )


def reduce_summaries_for_standup_rollup(
    root: Path,
    summaries: List[str],
) -> str:
    """Synthesize one upward standup summary from child fact lines.

    :param root: Repository root path.
    :type root: Path
    :param summaries: Distinct right-now or child rollup lines.
    :type summaries: List[str]
    :return: One synthesized summary sentence.
    :rtype: str
    :raises StandupRollupError: When AI is required and reduction fails.
    """
    deduped = dedupe_summary_list([summary for summary in summaries if summary.strip()])
    if not deduped:
        raise StandupRollupError("standup rollup reduce requires at least one summary")
    if len(deduped) == 1:
        return truncate_bullet(deduped[0], STANDUP_ROLLUP_MAX_LENGTH)

    load_repository_environment(root)
    try:
        configuration = _load_configuration(root)
    except RightNowError as error:
        raise StandupRollupError(str(error)) from error

    stub = os.environ.get(TEST_STANDUP_ROLLUP_COMPLETION_ENV)
    if stub is not None and stub.strip():
        return truncate_bullet(stub.strip(), STANDUP_ROLLUP_MAX_LENGTH)

    if os.environ.get("KANBUS_TEST_AI_MOCK") == "1":
        return _mock_standup_rollup_reduce(deduped)

    try:
        _ensure_litellm_provider(configuration)
    except RightNowError as error:
        raise StandupRollupError(str(error)) from error

    model = _resolve_right_now_model(configuration)
    prompt = _build_standup_rollup_reduce_prompt(deduped, STANDUP_ROLLUP_MAX_LENGTH)
    try:
        completion_text, _usage = _completion(model=model, prompt=prompt)
    except RightNowError as error:
        raise StandupRollupError(str(error)) from error
    except Exception as error:
        message = _curated_litellm_failure_message(error)
        if message == AI_PROVIDER_NOT_CONFIGURED_MESSAGE:
            raise StandupRollupError(message) from error
        raise StandupRollupError(f"standup rollup reduce failed: {message}") from error

    trimmed = completion_text.strip()
    if not trimmed:
        raise StandupRollupError("standup rollup reduce returned empty content")
    return truncate_bullet(trimmed, STANDUP_ROLLUP_MAX_LENGTH)


def load_configuration_for_standup_rollup(root: Path) -> ProjectConfiguration:
    """Load project configuration for standup rollup helpers.

    :param root: Repository root path.
    :type root: Path
    :return: Project configuration.
    :rtype: ProjectConfiguration
    :raises StandupRollupError: When configuration cannot be loaded.
    """
    from kanbus.config_loader import load_project_configuration

    try:
        return load_project_configuration(get_configuration_path(root))
    except (ProjectMarkerError, RuntimeError) as error:
        raise StandupRollupError(str(error)) from error
