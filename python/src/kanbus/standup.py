"""On-demand standup report generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from kanbus.config_loader import load_project_configuration
from kanbus.issue_lookup import IssueLookupError, load_issue_from_project
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.project import ProjectMarkerError, get_configuration_path
from kanbus.right_now import (
    RightNowError,
    ensure_right_now_summaries,
    is_persisted_mock_right_now_summary,
    require_display_right_now_summary,
)

MEETING_SCRIPT_PROFILE = "meeting-script"
DIRECTOR_BRIEF_PROFILE = "director-brief"
STANDUP_PROFILES = {MEETING_SCRIPT_PROFILE, DIRECTOR_BRIEF_PROFILE}
DEFAULT_STANDUP_LOOKBACK_HOURS = 24
MAX_STANDUP_BULLET_LENGTH = 120
FIRST_PERSON_INTRO = "Here is my standup update."
EXECUTIVE_BRIEF_INTRO = "Executive brief for stakeholders."
DONE_STATUSES = frozenset({"closed", "done"})


class StandupError(RuntimeError):
    """Raised when standup report generation fails."""


@dataclass(frozen=True)
class StandupSection:
    """Named standup report section with bullet lines.

    :param name: Section heading.
    :type name: str
    :param bullets: Bullet text lines without leading markers.
    :type bullets: List[str]
    """

    name: str
    bullets: List[str]


@dataclass
class StandupReport:
    """Structured standup report payload.

    :param profile: Standup profile identifier.
    :type profile: str
    :param sections: Ordered report sections.
    :type sections: List[StandupSection]
    :param source_issues: Fact-feed issue identifiers in display order.
    :type source_issues: List[str]
    :param right_now_texts: Right-now summary text keyed by issue identifier.
    :type right_now_texts: Dict[str, str]
    """

    profile: str
    sections: List[StandupSection]
    source_issues: List[str]
    right_now_texts: Dict[str, str] = field(default_factory=dict)


def resolve_standup_profile(profile_name: Optional[str]) -> str:
    """Resolve a standup profile name to a canonical identifier.

    :param profile_name: Optional profile name from CLI flags.
    :type profile_name: Optional[str]
    :return: Canonical profile identifier.
    :rtype: str
    :raises StandupError: When the profile name is unknown.
    """
    resolved = profile_name or MEETING_SCRIPT_PROFILE
    if resolved not in STANDUP_PROFILES:
        raise StandupError(f"unknown standup profile: {resolved}")
    return resolved


def load_standup_configuration(root: Path) -> ProjectConfiguration:
    """Load project configuration for standup generation.

    :param root: Repository root path.
    :type root: Path
    :return: Project configuration.
    :rtype: ProjectConfiguration
    :raises StandupError: When configuration cannot be loaded.
    """
    try:
        return load_project_configuration(get_configuration_path(root))
    except (ProjectMarkerError, RuntimeError) as error:
        raise StandupError(str(error)) from error


def resolve_standup_lookback_hours(configuration: ProjectConfiguration) -> int:
    """Return configured standup lookback hours.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Lookback window in hours.
    :rtype: int
    """
    return configuration.standup.lookback_hours


def load_issue_event_records(root: Path, issue_identifier: str) -> List[dict]:
    """Load event history records for an issue.

    :param root: Repository root path.
    :type root: Path
    :param issue_identifier: Issue identifier.
    :type issue_identifier: str
    :return: Parsed event payloads.
    :rtype: List[dict]
    """
    try:
        lookup = load_issue_from_project(root, issue_identifier)
    except IssueLookupError:
        return []
    project_dir = lookup.project_dir
    events_dirs = [project_dir / "events"]
    local_events = project_dir.parent / "project-local" / "events"
    if local_events.is_dir():
        events_dirs.append(local_events)
    records: List[dict] = []
    for events_dir in events_dirs:
        if not events_dir.is_dir():
            continue
        for path in events_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if payload.get("issue_id") == issue_identifier:
                records.append(payload)
    return records


def parse_rfc3339_timestamp(value: Optional[datetime | str]) -> Optional[datetime]:
    """Parse an RFC3339 timestamp into UTC.

    :param value: Timestamp value from issue or event data.
    :type value: Optional[datetime | str]
    :return: Parsed UTC datetime, or None when absent.
    :rtype: Optional[datetime]
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_within_lookback(
    timestamp: Optional[datetime | str],
    report_time: datetime,
    lookback_hours: int,
) -> bool:
    """Return whether a timestamp falls within the lookback window.

    :param timestamp: Timestamp to evaluate.
    :type timestamp: Optional[datetime | str]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param lookback_hours: Lookback window in hours.
    :type lookback_hours: int
    :return: True when the timestamp is within the lookback window.
    :rtype: bool
    """
    parsed = parse_rfc3339_timestamp(timestamp)
    if parsed is None:
        return False
    window_start = report_time - timedelta(hours=lookback_hours)
    return window_start <= parsed <= report_time


def had_state_transition_within_lookback(
    events: List[dict],
    target_statuses: Set[str],
    report_time: datetime,
    lookback_hours: int,
) -> bool:
    """Return whether an issue had a qualifying state transition in lookback.

    :param events: Issue event records.
    :type events: List[dict]
    :param target_statuses: Destination statuses to match.
    :type target_statuses: Set[str]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param lookback_hours: Lookback window in hours.
    :type lookback_hours: int
    :return: True when a matching transition occurred within lookback.
    :rtype: bool
    """
    for event in events:
        if event.get("event_type") != "state_transition":
            continue
        payload = event.get("payload", {})
        to_status = payload.get("to_status")
        if to_status not in target_statuses:
            continue
        if is_within_lookback(event.get("occurred_at"), report_time, lookback_hours):
            return True
    return False


def qualifies_for_yesterday(
    issue: IssueData,
    events: List[dict],
    report_time: datetime,
    lookback_hours: int,
) -> bool:
    """Return whether an issue belongs in the Yesterday section.

    :param issue: Issue to evaluate.
    :type issue: IssueData
    :param events: Issue event records.
    :type events: List[dict]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param lookback_hours: Lookback window in hours.
    :type lookback_hours: int
    :return: True when the issue qualifies for Yesterday.
    :rtype: bool
    """
    if is_within_lookback(issue.closed_at, report_time, lookback_hours):
        return True
    return had_state_transition_within_lookback(
        events,
        DONE_STATUSES,
        report_time,
        lookback_hours,
    )


def is_stale_in_progress(
    issue: IssueData,
    report_time: datetime,
    lookback_hours: int,
) -> bool:
    """Return whether an in-progress issue is stale relative to lookback.

    :param issue: Issue to evaluate.
    :type issue: IssueData
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param lookback_hours: Lookback window in hours.
    :type lookback_hours: int
    :return: True when the issue is in progress and older than lookback.
    :rtype: bool
    """
    if issue.status != "in_progress":
        return False
    return not is_within_lookback(issue.updated_at, report_time, lookback_hours)


def qualifies_for_momentum(
    issue: IssueData,
    events: List[dict],
    report_time: datetime,
    lookback_hours: int,
) -> bool:
    """Return whether an issue belongs in the Momentum section.

    :param issue: Issue to evaluate.
    :type issue: IssueData
    :param events: Issue event records.
    :type events: List[dict]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param lookback_hours: Lookback window in hours.
    :type lookback_hours: int
    :return: True when the issue qualifies for Momentum.
    :rtype: bool
    """
    if had_state_transition_within_lookback(
        events,
        {"in_progress"},
        report_time,
        lookback_hours,
    ):
        return True
    if had_state_transition_within_lookback(
        events,
        DONE_STATUSES,
        report_time,
        lookback_hours,
    ):
        return True
    if issue.status in DONE_STATUSES and is_within_lookback(
        issue.closed_at, report_time, lookback_hours
    ):
        return True
    if issue.status == "in_progress" and is_within_lookback(
        issue.updated_at, report_time, lookback_hours
    ):
        return True
    return False


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


def derive_blocked_question(summary: str) -> str:
    """Derive a likely question from blocked-issue summary text.

    :param summary: Right-now summary for a blocked issue.
    :type summary: str
    :return: Question text referencing summary keywords.
    :rtype: str
    """
    lowered = summary.lower()
    if "blocked on" in lowered:
        fragment = summary.split("Blocked on", 1)[1].strip().rstrip(".")
        return truncate_bullet(f"What is the status of {fragment}?")
    return truncate_bullet(f"What is blocking progress on {summary.rstrip('.')}? ")


def derive_stale_question(identifier: str) -> str:
    """Derive a staleness question for an in-progress issue.

    :param identifier: Issue identifier.
    :type identifier: str
    :return: Staleness question text.
    :rtype: str
    """
    return truncate_bullet(f"Why is {identifier} still in progress?")


def build_meeting_script_sections(
    issues: List[IssueData],
    right_now_texts: Dict[str, str],
    events_by_issue: Dict[str, List[dict]],
    report_time: datetime,
    lookback_hours: int,
    explicit_scope: bool = False,
) -> List[StandupSection]:
    """Build meeting-script profile sections from fact-feed issues.

    :param issues: Fact-feed issues.
    :type issues: List[IssueData]
    :param right_now_texts: Right-now summary text keyed by issue identifier.
    :type right_now_texts: Dict[str, str]
    :param events_by_issue: Event records keyed by issue identifier.
    :type events_by_issue: Dict[str, List[dict]]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param lookback_hours: Lookback window in hours.
    :type lookback_hours: int
    :return: Ordered meeting-script sections.
    :rtype: List[StandupSection]
    """
    yesterday_identifiers: Set[str] = set()
    yesterday_bullets: List[str] = []
    today_bullets: List[str] = []
    blocker_bullets: List[str] = []
    question_bullets: List[str] = []

    for issue in issues:
        events = events_by_issue.get(issue.identifier, [])
        summary = right_now_texts[issue.identifier]
        if qualifies_for_yesterday(issue, events, report_time, lookback_hours):
            yesterday_identifiers.add(issue.identifier)
            yesterday_bullets.append(truncate_bullet(summary))
        if issue.status == "blocked":
            blocker_bullets.append(truncate_bullet(f"{issue.identifier}: {summary}"))
            question_bullets.append(derive_blocked_question(summary))
        if is_stale_in_progress(issue, report_time, lookback_hours):
            question_bullets.append(derive_stale_question(issue.identifier))

    for issue in issues:
        if issue.identifier in yesterday_identifiers:
            continue
        active_statuses = {"in_progress", "blocked"}
        if explicit_scope:
            active_statuses.add("open")
        if issue.status in active_statuses:
            today_bullets.append(truncate_bullet(right_now_texts[issue.identifier]))

    return [
        StandupSection("Yesterday", yesterday_bullets),
        StandupSection("Today", today_bullets),
        StandupSection("Blockers", blocker_bullets),
        StandupSection("Likely questions", question_bullets),
    ]


def build_director_brief_sections(
    issues: List[IssueData],
    right_now_texts: Dict[str, str],
    events_by_issue: Dict[str, List[dict]],
    report_time: datetime,
    lookback_hours: int,
) -> List[StandupSection]:
    """Build director-brief profile sections from fact-feed issues.

    :param issues: Fact-feed issues.
    :type issues: List[IssueData]
    :param right_now_texts: Right-now summary text keyed by issue identifier.
    :type right_now_texts: Dict[str, str]
    :param events_by_issue: Event records keyed by issue identifier.
    :type events_by_issue: Dict[str, List[dict]]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param lookback_hours: Lookback window in hours.
    :type lookback_hours: int
    :return: Ordered director-brief sections.
    :rtype: List[StandupSection]
    """
    in_progress_count = sum(1 for issue in issues if issue.status == "in_progress")
    blocked_count = sum(1 for issue in issues if issue.status == "blocked")
    health_bullets = [
        f"{in_progress_count} in-progress issues, {blocked_count} blocked issue"
        + ("s" if blocked_count != 1 else "")
    ]

    momentum_bullets: List[str] = []
    risk_bullets: List[str] = []
    blocker_bullets: List[str] = []

    for issue in issues:
        events = events_by_issue.get(issue.identifier, [])
        summary = right_now_texts[issue.identifier]
        if qualifies_for_momentum(issue, events, report_time, lookback_hours):
            momentum_bullets.append(truncate_bullet(f"{issue.identifier}: {summary}"))
        if issue.status == "blocked":
            risk_bullets.append(truncate_bullet(issue.identifier))
            blocker_bullets.append(truncate_bullet(f"{issue.identifier}: {summary}"))
        elif is_stale_in_progress(issue, report_time, lookback_hours):
            risk_bullets.append(truncate_bullet(f"{issue.identifier}: {summary}"))

    return [
        StandupSection("Health", health_bullets),
        StandupSection("Momentum", momentum_bullets),
        StandupSection("Risks", risk_bullets),
        StandupSection("Blockers", blocker_bullets),
    ]


def build_standup_report(
    profile: str,
    issues: List[IssueData],
    right_now_texts: Dict[str, str],
    events_by_issue: Dict[str, List[dict]],
    report_time: datetime,
    lookback_hours: int,
    explicit_scope: bool = False,
) -> StandupReport:
    """Build a structured standup report for the requested profile.

    :param profile: Standup profile identifier.
    :type profile: str
    :param issues: Fact-feed issues in display order.
    :type issues: List[IssueData]
    :param right_now_texts: Right-now summary text keyed by issue identifier.
    :type right_now_texts: Dict[str, str]
    :param events_by_issue: Event records keyed by issue identifier.
    :type events_by_issue: Dict[str, List[dict]]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param lookback_hours: Lookback window in hours.
    :type lookback_hours: int
    :return: Structured standup report.
    :rtype: StandupReport
    """
    if profile == DIRECTOR_BRIEF_PROFILE:
        sections = build_director_brief_sections(
            issues,
            right_now_texts,
            events_by_issue,
            report_time,
            lookback_hours,
        )
    else:
        sections = build_meeting_script_sections(
            issues,
            right_now_texts,
            events_by_issue,
            report_time,
            lookback_hours,
            explicit_scope,
        )
    return StandupReport(
        profile=profile,
        sections=sections,
        source_issues=[issue.identifier for issue in issues],
        right_now_texts=right_now_texts,
    )


def format_standup_json(report: StandupReport) -> str:
    """Serialize a standup report as JSON.

    :param report: Standup report to serialize.
    :type report: StandupReport
    :return: Pretty-printed JSON with trailing newline.
    :rtype: str
    """
    payload = {
        "profile": report.profile,
        "sections": [
            {"name": section.name, "bullets": section.bullets}
            for section in report.sections
        ],
        "source_issues": report.source_issues,
        "right_now_texts": report.right_now_texts,
    }
    return json.dumps(payload, indent=2) + "\n"


def format_standup_text(report: StandupReport) -> str:
    """Render a standup report for terminal output.

    :param report: Standup report to render.
    :type report: StandupReport
    :return: Human-readable standup report text with trailing newline.
    :rtype: str
    """
    intro = (
        EXECUTIVE_BRIEF_INTRO
        if report.profile == DIRECTOR_BRIEF_PROFILE
        else FIRST_PERSON_INTRO
    )
    lines: List[str] = [f"Standup ({report.profile})", intro]
    for section in report.sections:
        lines.append("")
        lines.append(section.name)
        for bullet in section.bullets:
            lines.append(f"- {bullet}")
    lines.append("")
    return "\n".join(lines)


def standup_display_summary(issue: IssueData) -> str:
    """Return right-now summary text suitable for standup report output.

    :param issue: Issue whose summary is rendered in standup output.
    :type issue: IssueData
    :return: Non-empty standup summary text.
    :rtype: str
    :raises StandupError: When the summary is missing or invalid.
    """
    summary = require_display_right_now_summary(issue)
    if is_persisted_mock_right_now_summary(summary, issue.identifier):
        return truncate_bullet(f"Progress on {issue.title}.")
    return summary


def collect_right_now_texts(issues: List[IssueData]) -> Dict[str, str]:
    """Collect right-now summary text for fact-feed issues.

    :param issues: Fact-feed issues.
    :type issues: List[IssueData]
    :return: Right-now summary text keyed by issue identifier.
    :rtype: Dict[str, str]
    :raises StandupError: When a required summary is missing.
    """
    texts: Dict[str, str] = {}
    for issue in issues:
        try:
            texts[issue.identifier] = standup_display_summary(issue)
        except RightNowError as error:
            raise StandupError(str(error)) from error
    return texts


def ensure_standup_summaries(root: Path, issues: List[IssueData]) -> List[IssueData]:
    """Ensure right-now summaries exist for standup fact-feed issues.

    :param root: Repository root path.
    :type root: Path
    :param issues: Selected fact-feed issues.
    :type issues: List[IssueData]
    :return: Issues reloaded after summary backfill.
    :rtype: List[IssueData]
    :raises StandupError: When fail-closed summary generation cannot run.
    """
    if not issues:
        return []
    try:
        ensure_right_now_summaries(
            root,
            [issue.identifier for issue in issues],
            fail_closed=True,
        )
    except RightNowError as error:
        raise StandupError(str(error)) from error
    reloaded: List[IssueData] = []
    for issue in issues:
        try:
            reloaded.append(load_issue_from_project(root, issue.identifier).issue)
        except IssueLookupError:
            reloaded.append(issue)
    return reloaded


def extract_section_text(report_text: str, section_name: str) -> str:
    """Extract rendered text for a standup section from CLI output.

    :param report_text: Standup CLI stdout.
    :type report_text: str
    :param section_name: Section heading to locate.
    :type section_name: str
    :return: Section body text including bullets.
    :rtype: str
    """
    section_headers = {
        "Yesterday",
        "Today",
        "Blockers",
        "Likely questions",
        "Health",
        "Momentum",
        "Risks",
    }
    lines = report_text.splitlines()
    section_lines: List[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == section_name:
            in_section = True
            continue
        if in_section:
            if stripped in section_headers:
                break
            if line.startswith("Standup (") and section_lines:
                break
            section_lines.append(line)
    return "\n".join(section_lines)


def report_uses_first_person_voice(report_text: str) -> bool:
    """Return whether standup text uses first-person phrasing.

    :param report_text: Standup CLI stdout.
    :type report_text: str
    :return: True when first-person voice is present.
    :rtype: bool
    """
    return bool(re.search(r"\b(I|I'm|my|we|our)\b", report_text, re.IGNORECASE))


def report_uses_third_person_executive_voice(report_text: str) -> bool:
    """Return whether standup text uses third-person executive phrasing.

    :param report_text: Standup CLI stdout.
    :type report_text: str
    :return: True when executive voice markers are present.
    :rtype: bool
    """
    return bool(
        re.search(
            r"\b(in-progress issues|blocked issue|stakeholders|Executive brief)\b",
            report_text,
            re.IGNORECASE,
        )
    )
