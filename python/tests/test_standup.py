from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from kanbus.issue_lookup import IssueLookupError
from kanbus.models import StandupConfiguration
from kanbus.project import ProjectMarkerError
from kanbus.right_now import RightNowError
from kanbus.standup import (
    MEETING_SCRIPT_PROFILE,
    StandupError,
    build_standup_report,
    collect_right_now_texts,
    ensure_standup_summaries,
    extract_section_text,
    load_issue_event_records,
    load_standup_configuration,
    parse_rfc3339_timestamp,
    qualifies_for_momentum,
    report_uses_first_person_voice,
    report_uses_third_person_executive_voice,
    resolve_standup_lookback_hours,
    truncate_bullet,
)
from kanbus.standup_command import (
    StandupCommandError,
    StandupCommandOptions,
    load_standup_report_from_json,
    run_standup_command,
)

from test_helpers import build_issue, build_project_configuration


def test_load_standup_configuration_raises_on_marker_error(tmp_path: Path) -> None:
    with patch(
        "kanbus.standup.get_configuration_path",
        side_effect=ProjectMarkerError("missing"),
    ):
        with pytest.raises(StandupError, match="missing"):
            load_standup_configuration(tmp_path)


def test_resolve_standup_lookback_hours_reads_configuration() -> None:
    configuration = build_project_configuration()
    configuration = configuration.model_copy(
        update={"standup": StandupConfiguration(lookback="12h")}
    )
    assert resolve_standup_lookback_hours(configuration) == 12


def test_load_issue_event_records_handles_missing_issue(tmp_path: Path) -> None:
    with patch(
        "kanbus.standup.load_issue_from_project",
        side_effect=IssueLookupError("missing"),
    ):
        assert load_issue_event_records(tmp_path, "kanbus-missing") == []


def test_load_issue_event_records_skips_invalid_payloads(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    events_dir = project_dir / "events"
    events_dir.mkdir(parents=True)
    (events_dir / "bad.json").write_text("{not json", encoding="utf-8")
    (events_dir / "other.json").write_text(
        json.dumps({"issue_id": "kanbus-other", "event_type": "comment"}),
        encoding="utf-8",
    )
    lookup = type(
        "Lookup",
        (),
        {"project_dir": project_dir},
    )()
    with patch("kanbus.standup.load_issue_from_project", return_value=lookup):
        records = load_issue_event_records(tmp_path, "kanbus-target")
    assert records == []


def test_load_issue_event_records_collects_matching_events(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    events_dir = project_dir / "events"
    events_dir.mkdir(parents=True)
    payload = {
        "issue_id": "kanbus-target",
        "event_type": "state_transition",
        "occurred_at": "2026-03-06T12:00:00Z",
        "payload": {"to_status": "in_progress"},
    }
    (events_dir / "event.json").write_text(json.dumps(payload), encoding="utf-8")
    lookup = type(
        "Lookup",
        (),
        {"project_dir": project_dir},
    )()
    with patch("kanbus.standup.load_issue_from_project", return_value=lookup):
        records = load_issue_event_records(tmp_path, "kanbus-target")
    assert records == [payload]


def test_parse_rfc3339_timestamp_handles_naive_datetime() -> None:
    naive = datetime(2026, 3, 6, 12, 0, 0)
    parsed = parse_rfc3339_timestamp(naive)
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc


def test_truncate_bullet_adds_ellipsis() -> None:
    assert truncate_bullet("short") == "short"
    assert truncate_bullet("x" * 121).endswith("...")


def test_qualifies_for_momentum_uses_transitions_and_updates() -> None:
    from kanbus.standup_window import StandupWindowSettings
    from zoneinfo import ZoneInfo

    window_settings = StandupWindowSettings(
        window="rolling",
        lookback="24h",
        lookback_hours=24,
        skip_weekends=False,
        timezone=ZoneInfo("UTC"),
    )
    report_time = datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    issue = build_issue("kanbus-momentum", status="in_progress").model_copy(
        update={"updated_at": report_time - timedelta(hours=1)}
    )
    events = [
        {
            "event_type": "state_transition",
            "occurred_at": (report_time - timedelta(hours=2)).isoformat(),
            "payload": {"to_status": "in_progress"},
        }
    ]
    assert qualifies_for_momentum(issue, events, report_time, window_settings) is True

    closed_issue = build_issue("kanbus-done", status="closed").model_copy(
        update={"closed_at": report_time - timedelta(hours=1)}
    )
    done_events = [
        {
            "event_type": "state_transition",
            "occurred_at": (report_time - timedelta(hours=2)).isoformat(),
            "payload": {"to_status": "closed"},
        }
    ]
    assert (
        qualifies_for_momentum(closed_issue, done_events, report_time, window_settings)
        is True
    )


def test_collect_right_now_texts_wraps_right_now_errors() -> None:
    issue = build_issue("kanbus-missing-summary").model_copy(
        update={"right_now_summary": None}
    )
    with pytest.raises(StandupError):
        collect_right_now_texts([issue])


def test_ensure_standup_summaries_empty_list_returns_empty(tmp_path: Path) -> None:
    assert ensure_standup_summaries(tmp_path, []) == []


def test_ensure_standup_summaries_wraps_right_now_errors(tmp_path: Path) -> None:
    issue = build_issue("kanbus-offline")
    with patch(
        "kanbus.standup.ensure_right_now_summaries",
        side_effect=RightNowError("offline"),
    ):
        with pytest.raises(StandupError, match="offline"):
            ensure_standup_summaries(tmp_path, [issue])


def test_ensure_standup_summaries_keeps_issue_when_reload_fails(
    tmp_path: Path,
) -> None:
    issue = build_issue("kanbus-stale")
    with patch("kanbus.standup.ensure_right_now_summaries"):
        with patch(
            "kanbus.standup.load_issue_from_project",
            side_effect=IssueLookupError("missing"),
        ):
            reloaded = ensure_standup_summaries(tmp_path, [issue])
    assert reloaded == [issue]


def test_extract_section_text_stops_at_next_header() -> None:
    report = (
        "Standup (meeting-script)\n"
        "Yesterday\n"
        "- shipped feature\n"
        "Today\n"
        "- continue work\n"
    )
    section = extract_section_text(report, "Yesterday")
    assert "shipped feature" in section
    assert "Today" not in section


def test_report_voice_helpers() -> None:
    assert report_uses_first_person_voice("I shipped the standup work.") is True
    assert (
        report_uses_third_person_executive_voice("Executive brief for stakeholders.")
        is True
    )


def test_build_standup_report_meeting_script_sections() -> None:
    report_time = datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    issue = build_issue(
        "kanbus-active",
        status="in_progress",
        title="Active work",
    ).model_copy(
        update={
            "right_now_summary": "Shipping standup.",
            "updated_at": report_time - timedelta(hours=1),
        }
    )
    from kanbus.standup_window import StandupWindowSettings
    from zoneinfo import ZoneInfo

    window_settings = StandupWindowSettings(
        window="calendar",
        lookback="24h",
        lookback_hours=24,
        skip_weekends=True,
        timezone=ZoneInfo("UTC"),
    )
    configuration = build_project_configuration()
    from kanbus.standup_rollup import StandupRollupSettings

    report = build_standup_report(
        Path("."),
        MEETING_SCRIPT_PROFILE,
        [issue],
        {"kanbus-active": "Shipping standup."},
        {"kanbus-active": []},
        report_time,
        window_settings,
        configuration,
        StandupRollupSettings(mode="flat"),
        explicit_scope=True,
    )
    assert report.profile == "meeting-script"
    assert any(section.name == "Today" for section in report.sections)


def test_load_standup_report_from_json_round_trip() -> None:
    payload = {
        "profile": "director-brief",
        "sections": [{"name": "Health", "bullets": ["1 blocked"]}],
        "source_issues": ["kanbus-1"],
        "right_now_texts": {"kanbus-1": "Working."},
    }
    report = load_standup_report_from_json(json.dumps(payload))
    assert report.profile == "director-brief"
    assert report.sections[0].name == "Health"
    assert report.source_issues == ["kanbus-1"]


def test_run_standup_command_rejects_invalid_lookback(tmp_path: Path) -> None:
    from kanbus.standup_command import StandupCommandError

    configuration = build_project_configuration()
    configuration = configuration.model_copy(
        update={"standup": StandupConfiguration(lookback="0h")}
    )
    with patch(
        "kanbus.standup_command.load_standup_configuration", return_value=configuration
    ):
        with pytest.raises(StandupCommandError, match="invalid standup lookback"):
            run_standup_command(
                tmp_path,
                StandupCommandOptions(issue_ids=["kanbus-active"]),
            )


def test_run_standup_command_wraps_issue_listing_error(tmp_path: Path) -> None:
    from kanbus.issue_listing import IssueListingError

    configuration = build_project_configuration()
    with patch(
        "kanbus.standup_command.load_standup_configuration", return_value=configuration
    ):
        with patch(
            "kanbus.standup_command.select_standup_fact_feed",
            side_effect=IssueListingError("listing failed"),
        ):
            with pytest.raises(StandupCommandError, match="listing failed"):
                run_standup_command(tmp_path, StandupCommandOptions())
