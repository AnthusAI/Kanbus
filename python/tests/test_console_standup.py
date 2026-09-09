from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from kanbus.console_standup import StandupGenerateRequest, generate_standup_report
from kanbus.models import IssueData
from kanbus.standup import MEETING_SCRIPT_PROFILE
from kanbus.standup_command import StandupCommandOptions

from test_helpers import build_issue, build_project_configuration


def test_generate_standup_report_returns_sections(tmp_path: Path) -> None:
    issue = build_issue(identifier="kanbus-std-ui", status="in_progress").model_copy(
        update={"right_now_summary": "Console standup work."}
    )
    with (
        patch(
            "kanbus.console_standup.select_standup_fact_feed",
            return_value=[issue],
        ),
        patch(
            "kanbus.console_standup.ensure_standup_summaries",
            side_effect=lambda _root, issues: issues,
        ),
        patch(
            "kanbus.console_standup.load_standup_configuration",
            return_value=build_project_configuration(),
        ),
        patch(
            "kanbus.console_standup.load_issue_event_records",
            return_value=[],
        ),
    ):
        response = generate_standup_report(
            tmp_path,
            StandupGenerateRequest(profile=MEETING_SCRIPT_PROFILE),
        )
    assert response.profile == MEETING_SCRIPT_PROFILE
    assert any(section.name == "Today" for section in response.sections)
    assert "Console standup work." in response.text
