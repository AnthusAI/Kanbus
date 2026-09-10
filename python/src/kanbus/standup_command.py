"""Standup CLI command orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from kanbus.config_loader import load_repository_environment
from kanbus.issue_listing import IssueListingError
from kanbus.models import IssueData
from kanbus.right_now_command import (
    RightNowCommandError,
    RightNowCommandOptions,
    RightNowOutputFormat,
    select_right_now_issues,
)
from kanbus.standup import (
    StandupReport,
    StandupSection,
    build_standup_report,
    collect_right_now_texts,
    ensure_standup_summaries,
    format_standup_json,
    format_standup_text,
    load_issue_event_records,
    load_standup_configuration,
    resolve_standup_profile,
)
from kanbus.standup_rollup import (
    StandupRollupError,
    expand_issues_with_ancestors,
    resolve_standup_rollup,
)
from kanbus.standup_window import (
    StandupWindowError,
    StandupWindowOverrides,
    resolve_standup_report_time,
    resolve_standup_window_settings,
)

STANDUP_DEFAULT_STATUS_FILTER = "in_progress,blocked"
NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS = (
    "--no-recursive requires one or more issue identifiers"
)


@dataclass(frozen=True)
class StandupCommandOptions:
    """Options for the standup CLI command.

    :param issue_ids: Optional issue identifiers to scope the report.
    :type issue_ids: tuple[str, ...]
    :param profile: Optional standup profile name.
    :type profile: Optional[str]
    :param as_json: Whether to emit JSON output.
    :type as_json: bool
    :param recursive: Whether to include descendants of selected issues.
    :type recursive: bool
    :param window: Optional window mode override.
    :type window: Optional[str]
    :param lookback: Optional lookback duration override.
    :type lookback: Optional[str]
    :param skip_weekends: Optional skip-weekends override.
    :type skip_weekends: Optional[bool]
    :param rollup: Optional rollup mode override.
    :type rollup: Optional[str]
    """

    issue_ids: tuple[str, ...] = ()
    profile: Optional[str] = None
    as_json: bool = False
    recursive: bool = True
    window: Optional[str] = None
    lookback: Optional[str] = None
    skip_weekends: Optional[bool] = None
    rollup: Optional[str] = None


class StandupCommandError(RuntimeError):
    """Raised when standup CLI options or execution fail."""


def validate_standup_options(options: StandupCommandOptions) -> None:
    """Validate standup CLI options.

    :param options: Standup command options.
    :type options: StandupCommandOptions
    :raises StandupCommandError: When options are invalid.
    """
    if not options.recursive and not options.issue_ids:
        raise StandupCommandError(NO_RECURSIVE_REQUIRES_ISSUE_IDENTIFIERS)


def build_standup_right_now_options(
    options: StandupCommandOptions,
) -> RightNowCommandOptions:
    """Build right-now selection options for standup fact-feed gathering.

    :param options: Standup command options.
    :type options: StandupCommandOptions
    :return: Right-now selection options equivalent to standup defaults.
    :rtype: RightNowCommandOptions
    """
    status = None if options.issue_ids else STANDUP_DEFAULT_STATUS_FILTER
    return RightNowCommandOptions(
        limit=None,
        tree=False,
        raw=False,
        output_format=RightNowOutputFormat.YAML,
        show_all=False,
        recursive=options.recursive,
        issue_ids=options.issue_ids,
        status=status,
    )


def select_standup_fact_feed(
    root: Path,
    options: StandupCommandOptions,
) -> List[IssueData]:
    """Select standup fact-feed issues using right-now congregation scope.

    :param root: Repository root path.
    :type root: Path
    :param options: Standup command options.
    :type options: StandupCommandOptions
    :return: Selected issues sorted by updated_at descending.
    :rtype: List[IssueData]
    :raises StandupCommandError: When selection fails.
    """
    right_now_options = build_standup_right_now_options(options)
    try:
        return select_right_now_issues(root, right_now_options)
    except RightNowCommandError as error:
        raise StandupCommandError(str(error)) from error


def run_standup_command(root: Path, options: StandupCommandOptions) -> str:
    """Generate an on-demand standup report.

    :param root: Repository root path.
    :type root: Path
    :param options: Standup command options.
    :type options: StandupCommandOptions
    :return: Formatted CLI output.
    :rtype: str
    :raises StandupCommandError: When options or selection fail.
    :raises StandupError: When report generation fails fail-closed.
    """
    validate_standup_options(options)
    load_repository_environment(root)
    profile = resolve_standup_profile(options.profile)
    configuration = load_standup_configuration(root)
    try:
        rollup_settings = resolve_standup_rollup(
            options.rollup,
            configuration,
            bool(options.issue_ids),
        )
    except StandupRollupError as error:
        raise StandupCommandError(str(error)) from error
    window_overrides = StandupWindowOverrides(
        window=options.window,
        lookback=options.lookback,
        skip_weekends=options.skip_weekends,
    )
    try:
        window_settings = resolve_standup_window_settings(
            configuration,
            profile,
            window_overrides,
        )
    except StandupWindowError as error:
        raise StandupCommandError(str(error)) from error
    try:
        issues = select_standup_fact_feed(root, options)
    except IssueListingError as error:
        raise StandupCommandError(str(error)) from error
    issues_for_summaries = expand_issues_with_ancestors(root, issues)
    issues_for_summaries = ensure_standup_summaries(root, issues_for_summaries)
    summary_by_identifier = {issue.identifier: issue for issue in issues_for_summaries}
    issues = [summary_by_identifier.get(issue.identifier, issue) for issue in issues]
    right_now_texts = collect_right_now_texts(issues_for_summaries)
    events_by_issue = {
        issue.identifier: load_issue_event_records(root, issue.identifier)
        for issue in issues
    }
    report_time = resolve_standup_report_time()
    report = build_standup_report(
        profile,
        issues,
        right_now_texts,
        events_by_issue,
        report_time,
        window_settings,
        configuration,
        rollup_settings,
        bool(options.issue_ids),
    )
    if options.as_json:
        return format_standup_json(report)
    return format_standup_text(report)


def load_standup_report_from_json(stdout: str) -> StandupReport:
    """Parse a standup JSON report from CLI stdout.

    :param stdout: Standup CLI stdout.
    :type stdout: str
    :return: Parsed standup report.
    :rtype: StandupReport
    """
    payload = json.loads(stdout)
    sections = [
        StandupSection(name=item["name"], bullets=list(item.get("bullets", [])))
        for item in payload.get("sections", [])
    ]
    return StandupReport(
        profile=payload["profile"],
        sections=sections,
        source_issues=list(payload.get("source_issues", [])),
        right_now_texts=dict(payload.get("right_now_texts", {})),
    )
