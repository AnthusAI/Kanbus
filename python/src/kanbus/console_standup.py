"""Console standup API service."""

from __future__ import annotations

from dataclasses import dataclass
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
    resolve_standup_profile,
)
from kanbus.standup_command import StandupCommandOptions, select_standup_fact_feed
from kanbus.standup_rollup import expand_issues_with_ancestors, resolve_standup_rollup
from kanbus.standup_window import (
    StandupWindowOverrides,
    resolve_standup_report_time,
    resolve_standup_window_settings,
)


class StandupGenerateRequest(BaseModel):
    """Request body for generating a standup report from the console API.

    :param profile: Optional standup profile identifier.
    :type profile: Optional[str]
    :param window: Optional standup window mode override.
    :type window: Optional[str]
    :param lookback: Optional rolling lookback duration override.
    :type lookback: Optional[str]
    :param skip_weekends: Optional skip-weekends override.
    :type skip_weekends: Optional[bool]
    """

    profile: Optional[str] = None
    window: Optional[str] = None
    lookback: Optional[str] = None
    skip_weekends: Optional[bool] = None


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
    window_overrides = StandupWindowOverrides(
        window=request.window,
        lookback=request.lookback,
        skip_weekends=request.skip_weekends,
    )
    window_settings = resolve_standup_window_settings(
        configuration,
        profile,
        window_overrides,
    )
    options = StandupCommandOptions()
    rollup_settings = resolve_standup_rollup(None, configuration, False)
    issues = select_standup_fact_feed(root, options)
    issues_for_summaries = expand_issues_with_ancestors(root, issues)
    issues_for_summaries = ensure_standup_summaries(root, issues_for_summaries)
    right_now_texts = collect_right_now_texts(issues_for_summaries)
    events_by_issue = {
        issue.identifier: load_issue_event_records(root, issue.identifier)
        for issue in issues
    }
    report_time = resolve_standup_report_time()
    report = build_standup_report(
        root,
        profile,
        issues,
        right_now_texts,
        events_by_issue,
        report_time,
        window_settings,
        configuration,
        rollup_settings,
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
