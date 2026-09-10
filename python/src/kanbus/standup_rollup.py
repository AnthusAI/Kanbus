"""Standup rollup shapes and WIP close-out helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.standup_window import (
    CALENDAR_WINDOW,
    StandupWindowSettings,
    parse_rfc3339_timestamp,
    start_of_report_calendar_day,
)

MAX_STANDUP_BULLET_LENGTH = 120


class StandupRollupError(ValueError):
    """Raised when standup rollup configuration is invalid."""


def truncate_bullet(text: str, max_length: int = MAX_STANDUP_BULLET_LENGTH) -> str:
    """Truncate bullet text to the configured maximum length.

    :param text: Bullet text.
    :type text: str
    :param max_length: Maximum allowed length.
    :type max_length: int
    :return: Truncated bullet text.
    :rtype: str
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def is_stale_in_progress(
    issue: IssueData,
    report_time: datetime,
    window_settings: StandupWindowSettings,
) -> bool:
    """Return whether an in-progress issue is stale relative to lookback.

    :param issue: Issue to evaluate.
    :type issue: IssueData
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param window_settings: Resolved standup window settings.
    :type window_settings: StandupWindowSettings
    :return: True when the issue is in progress and older than lookback.
    :rtype: bool
    """
    if issue.status != "in_progress":
        return False
    if window_settings.window == CALENDAR_WINDOW:
        report_day_start = start_of_report_calendar_day(report_time, window_settings)
        updated_at = parse_rfc3339_timestamp(issue.updated_at)
        if updated_at is None:
            return True
        return updated_at < report_day_start
    from datetime import timedelta

    window_start = report_time - timedelta(hours=window_settings.lookback_hours)
    updated_at = parse_rfc3339_timestamp(issue.updated_at)
    if updated_at is None:
        return True
    return updated_at < window_start


ROLLUP_FLAT = "flat"
ROLLUP_PROJECT = "project"
ROLLUP_TREE = "tree"
STANDUP_ROLLUP_CHOICES = frozenset({ROLLUP_FLAT, ROLLUP_PROJECT, ROLLUP_TREE})

CLOSE_OUT_SECTION = "Close-out"
EMPTY_YESTERDAY_BULLET = "No completions yesterday."

_TREE_INDENT = "  "


@dataclass(frozen=True)
class StandupRollupSettings:
    """Resolved standup rollup mode for report assembly.

    :param mode: Rollup mode identifier.
    :type mode: str
    """

    mode: str


def resolve_standup_rollup(
    rollup: Optional[str],
    configuration: ProjectConfiguration,
    explicit_issue_scope: bool,
) -> StandupRollupSettings:
    """Resolve standup rollup mode from CLI flag and board shape.

    :param rollup: Optional rollup mode from CLI.
    :type rollup: Optional[str]
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :param explicit_issue_scope: Whether the user named issue identifiers.
    :type explicit_issue_scope: bool
    :return: Resolved rollup settings.
    :rtype: StandupRollupSettings
    :raises StandupRollupError: When the rollup mode is unknown.
    """
    if rollup is not None:
        if rollup not in STANDUP_ROLLUP_CHOICES:
            raise StandupRollupError(f"unknown standup rollup: {rollup}")
        return StandupRollupSettings(mode=rollup)
    if configuration.virtual_projects:
        return StandupRollupSettings(mode=ROLLUP_PROJECT)
    if explicit_issue_scope:
        return StandupRollupSettings(mode=ROLLUP_TREE)
    return StandupRollupSettings(mode=ROLLUP_FLAT)


def issue_project_label(issue: IssueData, configuration: ProjectConfiguration) -> str:
    """Return the congregation project label for an issue.

    :param issue: Issue to label.
    :type issue: IssueData
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Project label string.
    :rtype: str
    """
    custom = issue.custom or {}
    label = custom.get("project_label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return configuration.project_key


def expand_issues_with_ancestors(
    root: Path,
    issues: List[IssueData],
) -> List[IssueData]:
    """Include ancestor issues needed for tree and project rollups.

    :param root: Repository root path.
    :type root: Path
    :param issues: Fact-feed issues.
    :type issues: List[IssueData]
    :return: Issues plus any missing ancestors.
    :rtype: List[IssueData]
    """
    by_identifier: Dict[str, IssueData] = {issue.identifier: issue for issue in issues}
    for issue in issues:
        parent_identifier = issue.parent
        while parent_identifier:
            if parent_identifier in by_identifier:
                break
            try:
                lookup = load_issue_from_project(root, parent_identifier)
            except IssueLookupError:
                break
            by_identifier[parent_identifier] = lookup.issue
            parent_identifier = lookup.issue.parent
    return list(by_identifier.values())


def normalize_summary_text(text: str) -> str:
    """Normalize summary text for deduplication comparisons.

    :param text: Raw summary text.
    :type text: str
    :return: Normalized summary text.
    :rtype: str
    """
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    return collapsed.rstrip(".")


def summaries_near_identical(first: str, second: str) -> bool:
    """Return whether two summaries are identical or near duplicates.

    :param first: First summary text.
    :type first: str
    :param second: Second summary text.
    :type second: str
    :return: True when the summaries should be deduplicated.
    :rtype: bool
    """
    normalized_first = normalize_summary_text(first)
    normalized_second = normalize_summary_text(second)
    if normalized_first == normalized_second:
        return True
    shorter, longer = sorted((normalized_first, normalized_second), key=len)
    if not shorter:
        return False
    if shorter in longer and len(shorter) >= 12:
        return True
    return False


def dedupe_summary_list(summaries: List[str]) -> List[str]:
    """Remove near-duplicate summary strings preserving order.

    :param summaries: Summary strings in display order.
    :type summaries: List[str]
    :return: Deduplicated summaries.
    :rtype: List[str]
    """
    kept: List[str] = []
    for summary in summaries:
        if any(summaries_near_identical(summary, existing) for existing in kept):
            continue
        kept.append(summary)
    return kept


def forest_roots(issues: List[IssueData]) -> List[IssueData]:
    """Return issues that are roots within the provided issue set.

    :param issues: Issues sharing a partition (for example one project).
    :type issues: List[IssueData]
    :return: Root issues whose parent is outside the set.
    :rtype: List[IssueData]
    """
    identifiers = {issue.identifier for issue in issues}
    roots = [
        issue
        for issue in issues
        if issue.parent is None or issue.parent not in identifiers
    ]
    return sorted(roots, key=lambda item: item.identifier)


def _children_map(issues: List[IssueData]) -> Dict[str, List[IssueData]]:
    identifiers = {issue.identifier for issue in issues}
    children: Dict[str, List[IssueData]] = {}
    for issue in issues:
        if issue.parent is None or issue.parent not in identifiers:
            continue
        children.setdefault(issue.parent, []).append(issue)
    for child_list in children.values():
        child_list.sort(key=lambda item: item.identifier)
    return children


def _emit_tree_lines(
    issue: IssueData,
    depth: int,
    children_by_parent: Dict[str, List[IssueData]],
    right_now_texts: Dict[str, str],
    parent_summary: Optional[str],
    lines: List[str],
) -> None:
    summary = right_now_texts[issue.identifier]
    include = parent_summary is None or not summaries_near_identical(
        summary, parent_summary
    )
    if include:
        indent = _TREE_INDENT * depth
        lines.append(truncate_bullet(f"{indent}{summary}"))
    for child in children_by_parent.get(issue.identifier, []):
        _emit_tree_lines(
            child,
            depth + 1,
            children_by_parent,
            right_now_texts,
            summary if include else parent_summary,
            lines,
        )


def roll_up_active_bullets(
    active_issues: List[IssueData],
    right_now_texts: Dict[str, str],
    configuration: ProjectConfiguration,
    rollup_settings: StandupRollupSettings,
    *,
    prefix_issue_identifiers: bool = False,
) -> List[str]:
    """Build Today (or Momentum) bullets for the requested rollup mode.

    :param active_issues: Issues that belong in the active WIP section.
    :type active_issues: List[IssueData]
    :param right_now_texts: Right-now summary text keyed by issue identifier.
    :type right_now_texts: Dict[str, str]
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :param rollup_settings: Resolved rollup settings.
    :type rollup_settings: StandupRollupSettings
    :param prefix_issue_identifiers: Whether flat bullets include issue identifiers.
    :type prefix_issue_identifiers: bool
    :return: Rolled-up bullet lines.
    :rtype: List[str]
    """
    if not active_issues:
        return []
    if rollup_settings.mode == ROLLUP_FLAT:
        bullets: List[str] = []
        for issue in active_issues:
            summary = right_now_texts[issue.identifier]
            if prefix_issue_identifiers:
                bullets.append(truncate_bullet(f"{issue.identifier}: {summary}"))
            else:
                bullets.append(truncate_bullet(summary))
        return bullets

    by_project: Dict[str, List[IssueData]] = {}
    for issue in active_issues:
        label = issue_project_label(issue, configuration)
        by_project.setdefault(label, []).append(issue)

    bullets: List[str] = []
    for label in sorted(by_project.keys()):
        project_issues = by_project[label]
        roots = forest_roots(project_issues)
        children_by_parent = _children_map(project_issues)

        if rollup_settings.mode == ROLLUP_PROJECT:
            root_summaries = dedupe_summary_list(
                [right_now_texts[root.identifier] for root in roots]
            )
            joined = "; ".join(root_summaries)
            bullets.append(truncate_bullet(f"[{label}] {joined}"))
            continue

        prefix = f"[{label}] "
        for root in roots:
            tree_lines: List[str] = []
            _emit_tree_lines(
                root,
                0,
                children_by_parent,
                right_now_texts,
                None,
                tree_lines,
            )
            if not tree_lines:
                continue
            first_line = tree_lines[0]
            if first_line.startswith(_TREE_INDENT):
                tree_lines[0] = truncate_bullet(f"{prefix}{first_line.lstrip()}")
            else:
                tree_lines[0] = truncate_bullet(f"{prefix}{first_line}")
            bullets.extend(tree_lines)
    return bullets


def ensure_yesterday_bullets(yesterday_bullets: List[str]) -> List[str]:
    """Ensure Yesterday always has an explicit empty-state bullet.

    :param yesterday_bullets: Yesterday bullets before empty handling.
    :type yesterday_bullets: List[str]
    :return: Yesterday bullets with empty-state handling applied.
    :rtype: List[str]
    """
    if yesterday_bullets:
        return yesterday_bullets
    return [EMPTY_YESTERDAY_BULLET]


_READY_TO_CLOSE_PATTERN = re.compile(
    r"ready to close|ready for close|can be closed|close out|close-out",
    re.IGNORECASE,
)
_MERGED_STILL_OPEN_PATTERN = re.compile(
    r"\bmerged\b",
    re.IGNORECASE,
)
_EXTERNAL_BLOCK_PATTERN = re.compile(
    r"waiting on|blocked on|awaiting",
    re.IGNORECASE,
)


def build_close_out_bullets(
    issues: List[IssueData],
    right_now_texts: Dict[str, str],
    report_time,
    window_settings: StandupWindowSettings,
) -> List[str]:
    """Build Close-out bullets for WIP cards that should finish soon.

    :param issues: Fact-feed issues.
    :type issues: List[IssueData]
    :param right_now_texts: Right-now summary text keyed by issue identifier.
    :type right_now_texts: Dict[str, str]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param window_settings: Resolved standup window settings.
    :type window_settings: StandupWindowSettings
    :return: Close-out bullet lines.
    :rtype: List[str]
    """
    bullets: List[str] = []
    seen: Set[str] = set()
    for issue in issues:
        summary = right_now_texts.get(issue.identifier, "")
        if not summary:
            continue
        candidate: Optional[str] = None
        if issue.status == "in_progress":
            if _MERGED_STILL_OPEN_PATTERN.search(summary):
                candidate = (
                    f"{issue.identifier}: merged but still in progress — "
                    f"{truncate_bullet(summary)}"
                )
            elif _READY_TO_CLOSE_PATTERN.search(summary):
                candidate = f"{issue.identifier}: {truncate_bullet(summary)}"
            elif is_stale_in_progress(issue, report_time, window_settings):
                candidate = (
                    f"{issue.identifier}: stale WIP — {truncate_bullet(summary)}"
                )
        elif issue.status == "blocked" and _EXTERNAL_BLOCK_PATTERN.search(summary):
            candidate = f"{issue.identifier}: {truncate_bullet(summary)}"
        if candidate is None:
            continue
        normalized = normalize_summary_text(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        bullets.append(truncate_bullet(candidate))
    return bullets


def count_section_bullets(section_text: str) -> int:
    """Count bullet lines in a rendered standup section body.

    :param section_text: Section body text from CLI output.
    :type section_text: str
    :return: Number of bullet lines.
    :rtype: int
    """
    return sum(1 for line in section_text.splitlines() if line.strip().startswith("- "))
