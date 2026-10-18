"""LLM usage cost reporting from the project usage log."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from kanbus.config_loader import load_project_configuration
from kanbus.project import get_configuration_path

LLM_USAGE_LOG = "llm_usage.jsonl"
NO_LLM_USAGE_MESSAGE = "No LLM usage logs found."


class LlmCostTotals(BaseModel):
    """Aggregated LLM usage totals.

    :param total_tokens: Tokens consumed across every counted call.
    :type total_tokens: int
    :param total_cost: Summed cost in USD of calls with a known price.
    :type total_cost: float
    :param unpriced_calls: Calls whose cost is unknown and excluded from the total.
    :type unpriced_calls: int
    """

    total_tokens: int = 0
    total_cost: float = 0.0
    unpriced_calls: int = 0


def aggregate_llm_usage(log_path: Path, days: int | None) -> LlmCostTotals:
    """Aggregate tokens and cost from an LLM usage log.

    :param log_path: Path to ``llm_usage.jsonl``.
    :type log_path: Path
    :param days: Only count entries from the last ``days`` days when set.
    :type days: Optional[int]
    :return: Aggregated totals.
    :rtype: LlmCostTotals
    """
    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    totals = LlmCostTotals()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        timestamp = datetime.fromisoformat(entry["timestamp"])
        if cutoff is not None and timestamp < cutoff:
            continue
        totals.total_tokens += int(entry.get("total_tokens", 0))
        cost = entry.get("cost")
        if cost is None:
            totals.unpriced_calls += 1
        else:
            totals.total_cost += float(cost)
    return totals


def build_llm_cost_report(root: Path, days: int | None) -> str:
    """Build the ``kanbus cost`` report text.

    :param root: Repository root path.
    :type root: Path
    :param days: Only count entries from the last ``days`` days when set.
    :type days: Optional[int]
    :return: Report text without a trailing newline.
    :rtype: str
    """
    configuration = load_project_configuration(get_configuration_path(root))
    log_path = root / configuration.project_directory / "events" / LLM_USAGE_LOG
    if not log_path.exists():
        return NO_LLM_USAGE_MESSAGE
    totals = aggregate_llm_usage(log_path, days)
    return "\n".join(
        [
            f"Total Tokens:   {totals.total_tokens}",
            f"Total Cost:     ${totals.total_cost:.4f}",
            f"Unpriced Calls: {totals.unpriced_calls}",
        ]
    )
