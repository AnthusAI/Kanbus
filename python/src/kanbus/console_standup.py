"""Console standup API service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from kanbus.standup import (
    build_standup_report,
    collect_right_now_texts,
    ensure_standup_summaries,
    format_standup_text,
    load_issue_event_records,
    load_standup_configuration,
    resolve_standup_lookback_hours,
    resolve_standup_profile,
    DEFAULT_STANDUP_LOOKBACK_HOURS,
)
from kanbus.standup_command import StandupCommandOptions, select_standup_fact_feed


class StandupGenerateRequest(BaseModel):
    """Request body for generating a standup report from the console API.

    :param profile: Optional standup profile identifier.
    :type profile: Optional[str]
    """

    profile: Optional[str] = None


@dataclass(frozen=True)
class StandupSectionResponse:
    """Standup report section in console API responses.

    :param name: Section heading.
    :type name: str
    :param bullets: Bullet text lines without leading markers.
    :type bullets: List[str]
    """

    name: str
    bullets: List[str]


@dataclass(frozen=True)
class StandupGenerateResponse:
    """Response payload for console standup generation.

    :param profile: Standup profile identifier.
    :type profile: str
    :param sections: Ordered report sections.
    :type sections: List[StandupSectionResponse]
    :param text: Human-readable standup report text.
    :type text: str
    :param source_issues: Fact-feed issue identifiers in display order.
    :type source_issues: List[str]
    :param right_now_texts: Right-now summary text keyed by issue identifier.
    :type right_now_texts: Dict[str, str]
    """

    profile: str
    sections: List[StandupSectionResponse]
    text: str
    source_issues: List[str]
    right_now_texts: Dict[str, str]


class StandupGenerateResponseModel(BaseModel):
    """Serialized standup API response model.

    :param profile: Standup profile identifier.
    :type profile: str
    :param sections: Ordered report sections.
    :type sections: List[dict]
    :param text: Human-readable standup report text.
    :type text: str
    :param source_issues: Fact-feed issue identifiers in display order.
    :type source_issues: List[str]
    :param right_now_texts: Right-now summary text keyed by issue identifier.
    :type right_now_texts: Dict[str, str]
    """

    profile: str
    sections: List[dict] = Field(default_factory=list)
    text: str
    source_issues: List[str] = Field(default_factory=list)
    right_now_texts: Dict[str, str] = Field(default_factory=dict)


def generate_standup_report(
    root: Path,
    request: StandupGenerateRequest,
) -> StandupGenerateResponse:
    """Generate a board-wide standup report for the console API.

    :param root: Repository root path.
    :type root: Path
    :param request: Standup generation request.
    :type request: StandupGenerateRequest
    :return: Standup generation response.
    :rtype: StandupGenerateResponse
    :raises StandupError: When profile resolution or generation fails fail-closed.
    """
    profile = resolve_standup_profile(request.profile)
    configuration = load_standup_configuration(root)
    lookback_hours = resolve_standup_lookback_hours(configuration)
    if lookback_hours <= 0:
        lookback_hours = DEFAULT_STANDUP_LOOKBACK_HOURS
    options = StandupCommandOptions()
    issues = select_standup_fact_feed(root, options)
    issues = ensure_standup_summaries(root, issues)
    right_now_texts = collect_right_now_texts(issues)
    events_by_issue = {
        issue.identifier: load_issue_event_records(root, issue.identifier)
        for issue in issues
    }
    report_time = datetime.now(timezone.utc)
    report = build_standup_report(
        profile,
        issues,
        right_now_texts,
        events_by_issue,
        report_time,
        lookback_hours,
        False,
    )
    text = format_standup_text(report)
    return StandupGenerateResponse(
        profile=report.profile,
        sections=[
            StandupSectionResponse(name=section.name, bullets=list(section.bullets))
            for section in report.sections
        ],
        text=text,
        source_issues=list(report.source_issues),
        right_now_texts=dict(report.right_now_texts),
    )
