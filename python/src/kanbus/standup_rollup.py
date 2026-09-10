"""Standup rollup shapes and WIP close-out helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.standup_rollup_reduce import reduce_summaries_for_standup_rollup
from kanbus.standup_window import is_within_lookback
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
CLOSE_OUT_MAX_BULLETS = 6

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


def resolve_standup_partition_key(
    raw_label: str,
    configuration: ProjectConfiguration,
) -> str:
    """Normalize a raw project label to a congregation partition key.

    :param raw_label: Label from issue metadata or configuration.
    :type raw_label: str
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Canonical partition key for grouping.
    :rtype: str
    """
    trimmed = raw_label.strip()
    if not trimmed:
        return configuration.project_key
    if trimmed == configuration.project_key:
        return configuration.project_key
    if trimmed in configuration.virtual_projects:
        return trimmed
    lowered = trimmed.lower()
    if configuration.name and lowered == configuration.name.strip().lower():
        return configuration.project_key
    if lowered == configuration.project_key.lower():
        return configuration.project_key
    for partition_key, virtual_project in configuration.virtual_projects.items():
        if partition_key.lower() == lowered:
            return partition_key
        display_name = virtual_project.display_name
        if display_name and display_name.strip().lower() == lowered:
            return partition_key
    return trimmed


def canonical_standup_project_display_label(
    partition_key: str,
    configuration: ProjectConfiguration,
) -> str:
    """Return the stable human display label for a congregation partition.

    :param partition_key: Canonical partition key.
    :type partition_key: str
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Display label used in standup bracket prefixes.
    :rtype: str
    """
    if partition_key == configuration.project_key:
        if configuration.name and configuration.name.strip():
            return configuration.name.strip()
        return configuration.project_key
    virtual_project = configuration.virtual_projects.get(partition_key)
    if virtual_project is None:
        return partition_key
    if virtual_project.display_name and virtual_project.display_name.strip():
        return virtual_project.display_name.strip()
    return partition_key


def issue_project_partition_key(
    issue: IssueData,
    configuration: ProjectConfiguration,
) -> str:
    """Return the congregation partition key for an issue.

    :param issue: Issue to label.
    :type issue: IssueData
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Partition key string.
    :rtype: str
    """
    custom = issue.custom or {}
    label = custom.get("project_label")
    if isinstance(label, str) and label.strip():
        return resolve_standup_partition_key(label.strip(), configuration)
    return configuration.project_key


def issue_project_label(issue: IssueData, configuration: ProjectConfiguration) -> str:
    """Return the congregation project display label for an issue.

    :param issue: Issue to label.
    :type issue: IssueData
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Project label string.
    :rtype: str
    """
    partition_key = issue_project_partition_key(issue, configuration)
    return canonical_standup_project_display_label(partition_key, configuration)


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


def _compute_issue_rollup_summary(
    root: Path,
    issue: IssueData,
    children_by_parent: Dict[str, List[IssueData]],
    right_now_texts: Dict[str, str],
    cache: Dict[str, str],
) -> str:
    cached = cache.get(issue.identifier)
    if cached is not None:
        return cached
    own_summary = right_now_texts[issue.identifier]
    children = children_by_parent.get(issue.identifier, [])
    if not children:
        cache[issue.identifier] = own_summary
        return own_summary
    child_summaries = [
        _compute_issue_rollup_summary(
            root,
            child,
            children_by_parent,
            right_now_texts,
            cache,
        )
        for child in children
    ]
    child_summaries = dedupe_summary_list(child_summaries)
    if len(child_summaries) == 1 and summaries_near_identical(
        child_summaries[0], own_summary
    ):
        cache[issue.identifier] = own_summary
        return own_summary
    combined = dedupe_summary_list([own_summary, *child_summaries])
    if len(combined) == 1:
        result = combined[0]
    else:
        result = reduce_summaries_for_standup_rollup(root, combined)
    cache[issue.identifier] = result
    return result


def _emit_tree_lines(
    root: Path,
    issue: IssueData,
    depth: int,
    children_by_parent: Dict[str, List[IssueData]],
    right_now_texts: Dict[str, str],
    rollup_cache: Dict[str, str],
    parent_summary: Optional[str],
    lines: List[str],
) -> None:
    summary = _compute_issue_rollup_summary(
        root,
        issue,
        children_by_parent,
        right_now_texts,
        rollup_cache,
    )
    include = parent_summary is None or not summaries_near_identical(
        summary, parent_summary
    )
    if include:
        indent = _TREE_INDENT * depth
        lines.append(truncate_bullet(f"{indent}{summary}"))
    for child in children_by_parent.get(issue.identifier, []):
        _emit_tree_lines(
            root,
            child,
            depth + 1,
            children_by_parent,
            right_now_texts,
            rollup_cache,
            summary if include else parent_summary,
            lines,
        )


def roll_up_active_bullets(
    root: Path,
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

    by_partition: Dict[str, List[IssueData]] = {}
    for issue in active_issues:
        partition_key = issue_project_partition_key(issue, configuration)
        by_partition.setdefault(partition_key, []).append(issue)

    bullets: List[str] = []
    for partition_key in sorted(by_partition.keys()):
        display_label = canonical_standup_project_display_label(
            partition_key, configuration
        )
        project_issues = by_partition[partition_key]
        roots = forest_roots(project_issues)
        children_by_parent = _children_map(project_issues)
        rollup_cache: Dict[str, str] = {}

        if rollup_settings.mode == ROLLUP_PROJECT:
            root_summaries = dedupe_summary_list(
                [
                    _compute_issue_rollup_summary(
                        root,
                        forest_root,
                        children_by_parent,
                        right_now_texts,
                        rollup_cache,
                    )
                    for forest_root in roots
                ]
            )
            if len(root_summaries) == 1:
                project_summary = root_summaries[0]
            else:
                project_summary = reduce_summaries_for_standup_rollup(
                    root, root_summaries
                )
            bullets.append(truncate_bullet(f"[{display_label}] {project_summary}"))
            continue

        prefix = f"[{display_label}] "
        for forest_root in roots:
            tree_lines: List[str] = []
            _emit_tree_lines(
                root,
                forest_root,
                0,
                children_by_parent,
                right_now_texts,
                rollup_cache,
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
_FINISHABLE_STALE_PATTERN = re.compile(
    r"waiting on review|waiting for review|awaiting review|"
    r"waiting on deploy|waiting for deploy|deploy toggle|"
    r"\bmerged\b|ready to merge",
    re.IGNORECASE,
)


def _children_by_parent_for_issues(
    issues: List[IssueData],
) -> Dict[str, List[IssueData]]:
    identifiers = {issue.identifier for issue in issues}
    children: Dict[str, List[IssueData]] = {}
    for issue in issues:
        if issue.parent is None or issue.parent not in identifiers:
            continue
        children.setdefault(issue.parent, []).append(issue)
    for child_list in children.values():
        child_list.sort(key=lambda item: item.identifier)
    return children


def _collect_descendant_identifiers(
    root_identifier: str,
    children_by_parent: Dict[str, List[IssueData]],
) -> Set[str]:
    descendants: Set[str] = set()
    stack = list(children_by_parent.get(root_identifier, []))
    while stack:
        child = stack.pop()
        if child.identifier in descendants:
            continue
        descendants.add(child.identifier)
        stack.extend(children_by_parent.get(child.identifier, []))
    return descendants


def _issue_had_activity_within_lookback(
    issue: IssueData,
    events: List[dict],
    report_time: datetime,
    window_settings: StandupWindowSettings,
) -> bool:
    lookback_hours = window_settings.lookback_hours
    if is_within_lookback(issue.updated_at, report_time, lookback_hours):
        return True
    for event in events:
        timestamp = event.get("timestamp") or event.get("created_at")
        if isinstance(timestamp, str) and is_within_lookback(
            timestamp, report_time, lookback_hours
        ):
            return True
    return False


def has_recent_descendant_activity(
    issue: IssueData,
    issues: List[IssueData],
    events_by_issue: Dict[str, List[dict]],
    report_time: datetime,
    window_settings: StandupWindowSettings,
) -> bool:
    """Return whether any descendant issue had activity within the lookback window.

    :param issue: Parent issue to inspect.
    :type issue: IssueData
    :param issues: Fact-feed issues that define the descendant graph.
    :type issues: List[IssueData]
    :param events_by_issue: Event records keyed by issue identifier.
    :type events_by_issue: Dict[str, List[dict]]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param window_settings: Resolved standup window settings.
    :type window_settings: StandupWindowSettings
    :return: True when a descendant had recent activity.
    :rtype: bool
    """
    children_by_parent = _children_by_parent_for_issues(issues)
    descendants = _collect_descendant_identifiers(issue.identifier, children_by_parent)
    issues_by_identifier = {item.identifier: item for item in issues}
    for descendant_identifier in descendants:
        descendant = issues_by_identifier.get(descendant_identifier)
        if descendant is None:
            continue
        events = events_by_issue.get(descendant_identifier, [])
        if _issue_had_activity_within_lookback(
            descendant, events, report_time, window_settings
        ):
            return True
    return False


def qualifies_for_close_out_stale(
    issue: IssueData,
    summary: str,
    issues: List[IssueData],
    events_by_issue: Dict[str, List[dict]],
    report_time: datetime,
    window_settings: StandupWindowSettings,
) -> bool:
    """Return whether a stale in-progress issue belongs in Close-out.

    :param issue: Issue to evaluate.
    :type issue: IssueData
    :param summary: Right-now summary text.
    :type summary: str
    :param issues: Fact-feed issues for descendant activity checks.
    :type issues: List[IssueData]
    :param events_by_issue: Event records keyed by issue identifier.
    :type events_by_issue: Dict[str, List[dict]]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param window_settings: Resolved standup window settings.
    :type window_settings: StandupWindowSettings
    :return: True when the issue is a narrow stale close-out candidate.
    :rtype: bool
    """
    if not is_stale_in_progress(issue, report_time, window_settings):
        return False
    if not _FINISHABLE_STALE_PATTERN.search(summary):
        return False
    return not has_recent_descendant_activity(
        issue,
        issues,
        events_by_issue,
        report_time,
        window_settings,
    )


def close_out_issue_identifiers(bullets: List[str]) -> Set[str]:
    """Extract issue identifiers referenced in Close-out bullets.

    :param bullets: Rendered Close-out bullet lines.
    :type bullets: List[str]
    :return: Issue identifiers mentioned in Close-out.
    :rtype: Set[str]
    """
    identifiers: Set[str] = set()
    for bullet in bullets:
        prefix = bullet.split(":", 1)[0].strip()
        if prefix:
            identifiers.add(prefix)
    return identifiers


def build_close_out_bullets(
    issues: List[IssueData],
    right_now_texts: Dict[str, str],
    events_by_issue: Dict[str, List[dict]],
    report_time,
    window_settings: StandupWindowSettings,
) -> List[str]:
    """Build Close-out bullets for WIP cards that should finish soon.

    :param issues: Fact-feed issues.
    :type issues: List[IssueData]
    :param right_now_texts: Right-now summary text keyed by issue identifier.
    :type right_now_texts: Dict[str, str]
    :param events_by_issue: Event records keyed by issue identifier.
    :type events_by_issue: Dict[str, List[dict]]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param window_settings: Resolved standup window settings.
    :type window_settings: StandupWindowSettings
    :return: Close-out bullet lines.
    :rtype: List[str]
    """
    ranked_candidates: List[tuple[int, str]] = []
    seen: Set[str] = set()
    for issue in issues:
        summary = right_now_texts.get(issue.identifier, "")
        if not summary:
            continue
        candidate: Optional[str] = None
        priority = 99
        if issue.status == "in_progress":
            if _MERGED_STILL_OPEN_PATTERN.search(summary):
                candidate = (
                    f"{issue.identifier}: merged but still in progress — "
                    f"{truncate_bullet(summary)}"
                )
                priority = 0
            elif _READY_TO_CLOSE_PATTERN.search(summary):
                candidate = f"{issue.identifier}: {truncate_bullet(summary)}"
                priority = 1
            elif qualifies_for_close_out_stale(
                issue,
                summary,
                issues,
                events_by_issue,
                report_time,
                window_settings,
            ):
                candidate = (
                    f"{issue.identifier}: stale WIP — {truncate_bullet(summary)}"
                )
                priority = 3
        elif issue.status == "blocked" and _EXTERNAL_BLOCK_PATTERN.search(summary):
            candidate = f"{issue.identifier}: {truncate_bullet(summary)}"
            priority = 2
        if candidate is None:
            continue
        normalized = normalize_summary_text(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        ranked_candidates.append((priority, truncate_bullet(candidate)))
    ranked_candidates.sort(key=lambda item: (item[0], item[1]))
    return [bullet for _priority, bullet in ranked_candidates[:CLOSE_OUT_MAX_BULLETS]]


def count_section_bullets(section_text: str) -> int:
    """Count bullet lines in a rendered standup section body.

    :param section_text: Section body text from CLI output.
    :type section_text: str
    :return: Number of bullet lines.
    :rtype: int
    """
    return sum(1 for line in section_text.splitlines() if line.strip().startswith("- "))
