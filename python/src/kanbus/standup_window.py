"""Standup time window resolution (rolling vs calendar)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Set
from zoneinfo import ZoneInfo

from kanbus.models import ProjectConfiguration, StandupConfiguration

MEETING_SCRIPT_PROFILE = "meeting-script"
DIRECTOR_BRIEF_PROFILE = "director-brief"
ROLLING_WINDOW = "rolling"
CALENDAR_WINDOW = "calendar"
DEFAULT_STANDUP_LOOKBACK = "24h"
DEFAULT_STANDUP_LOOKBACK_HOURS = 24
STANDUP_REPORT_TIME_ENV = "KANBUS_STANDUP_REPORT_TIME"
LOOKBACK_PATTERN = re.compile(r"^(\d+)([hd])$", re.IGNORECASE)


class StandupWindowError(ValueError):
    """Raised when standup window settings are invalid."""


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


@dataclass(frozen=True)
class StandupWindowOverrides:
    """Optional CLI or API overrides for standup window settings.

    :param window: Optional window mode override.
    :type window: Optional[str]
    :param lookback: Optional lookback duration override.
    :type lookback: Optional[str]
    :param skip_weekends: Optional skip-weekends override.
    :type skip_weekends: Optional[bool]
    """

    window: Optional[str] = None
    lookback: Optional[str] = None
    skip_weekends: Optional[bool] = None


@dataclass(frozen=True)
class StandupWindowSettings:
    """Resolved standup window settings for report generation.

    :param window: Window mode (`rolling` or `calendar`).
    :type window: str
    :param lookback: Canonical lookback duration string.
    :type lookback: str
    :param lookback_hours: Lookback duration in hours.
    :type lookback_hours: int
    :param skip_weekends: Whether calendar mode bundles weekends on Monday.
    :type skip_weekends: bool
    :param timezone: Resolved standup timezone.
    :type timezone: ZoneInfo
    """

    window: str
    lookback: str
    lookback_hours: int
    skip_weekends: bool
    timezone: ZoneInfo


def parse_standup_lookback_hours(lookback: str) -> int:
    """Parse a standup lookback duration into hours.

    :param lookback: Duration string such as `24h` or `1d`.
    :type lookback: str
    :return: Lookback duration in hours.
    :rtype: int
    :raises StandupWindowError: When the duration format is invalid.
    """
    normalized = lookback.strip().lower()
    match = LOOKBACK_PATTERN.fullmatch(normalized)
    if match is None:
        raise StandupWindowError(f"invalid standup lookback: {lookback}")
    amount = int(match.group(1))
    unit = match.group(2)
    if amount <= 0:
        raise StandupWindowError(f"invalid standup lookback: {lookback}")
    if unit == "d":
        return amount * 24
    return amount


def format_standup_lookback(hours: int) -> str:
    """Format lookback hours as a canonical duration string.

    :param hours: Lookback duration in hours.
    :type hours: int
    :return: Canonical lookback string.
    :rtype: str
    """
    if hours % 24 == 0 and hours >= 24:
        days = hours // 24
        return f"{days}d"
    return f"{hours}h"


def resolve_standup_timezone(configuration: ProjectConfiguration) -> ZoneInfo:
    """Resolve the standup timezone from configuration.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Resolved timezone.
    :rtype: ZoneInfo
    """
    timezone_name = configuration.standup.timezone
    if timezone_name:
        return ZoneInfo(timezone_name)
    local_timezone = datetime.now().astimezone().tzinfo
    if local_timezone is None:
        return ZoneInfo("UTC")
    if isinstance(local_timezone, ZoneInfo):
        return local_timezone
    return ZoneInfo(str(local_timezone))


def resolve_standup_window_settings(
    configuration: ProjectConfiguration,
    profile: Optional[str],
    overrides: Optional[StandupWindowOverrides] = None,
) -> StandupWindowSettings:
    """Resolve standup window settings from config, profile, and overrides.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :param profile: Optional standup profile identifier for profile defaults.
    :type profile: Optional[str]
    :param overrides: Optional CLI or API overrides.
    :type overrides: Optional[StandupWindowOverrides]
    :return: Resolved standup window settings.
    :rtype: StandupWindowSettings
    :raises StandupWindowError: When settings are invalid.
    """
    standup = configuration.standup
    window = standup.window
    lookback = standup.lookback
    skip_weekends = standup.skip_weekends

    if profile == MEETING_SCRIPT_PROFILE:
        window = CALENDAR_WINDOW
        skip_weekends = True
    elif profile == DIRECTOR_BRIEF_PROFILE:
        window = ROLLING_WINDOW
        lookback = DEFAULT_STANDUP_LOOKBACK
        skip_weekends = False

    if overrides is not None:
        if overrides.window is not None:
            window = overrides.window
        if overrides.lookback is not None:
            lookback = overrides.lookback
        if overrides.skip_weekends is not None:
            skip_weekends = overrides.skip_weekends

    if window not in {ROLLING_WINDOW, CALENDAR_WINDOW}:
        raise StandupWindowError(f"invalid standup window: {window}")

    lookback_hours = parse_standup_lookback_hours(lookback)
    return StandupWindowSettings(
        window=window,
        lookback=lookback,
        lookback_hours=lookback_hours,
        skip_weekends=skip_weekends,
        timezone=resolve_standup_timezone(configuration),
    )


def resolve_standup_report_time() -> datetime:
    """Resolve the standup report generation timestamp.

    :return: Report time in UTC.
    :rtype: datetime
    """
    override = os.environ.get(STANDUP_REPORT_TIME_ENV)
    if override:
        parsed = parse_rfc3339_timestamp(override)
        if parsed is None:
            raise StandupWindowError(
                f"invalid {STANDUP_REPORT_TIME_ENV}: {override}"
            )
        return parsed
    return datetime.now(timezone.utc)


def completed_calendar_dates(
    report_time: datetime,
    settings: StandupWindowSettings,
) -> Set[date]:
    """Return calendar dates that qualify for the completed bucket.

    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param settings: Resolved standup window settings.
    :type settings: StandupWindowSettings
    :return: Qualifying local calendar dates.
    :rtype: Set[date]
    """
    local_report_time = report_time.astimezone(settings.timezone)
    report_day = local_report_time.date()
    if settings.skip_weekends and report_day.weekday() == 0:
        return {
            report_day - timedelta(days=3),
            report_day - timedelta(days=2),
            report_day - timedelta(days=1),
        }
    return {report_day - timedelta(days=1)}


def timestamp_calendar_date(
    timestamp: Optional[datetime | str],
    settings: StandupWindowSettings,
) -> Optional[date]:
    """Convert a timestamp to a local calendar date in standup timezone.

    :param timestamp: Timestamp to convert.
    :type timestamp: Optional[datetime | str]
    :param settings: Resolved standup window settings.
    :type settings: StandupWindowSettings
    :return: Local calendar date, or None when absent.
    :rtype: Optional[date]
    """
    parsed = parse_rfc3339_timestamp(timestamp)
    if parsed is None:
        return None
    return parsed.astimezone(settings.timezone).date()


def is_on_completed_calendar_day(
    timestamp: Optional[datetime | str],
    report_time: datetime,
    settings: StandupWindowSettings,
) -> bool:
    """Return whether a timestamp falls on a completed calendar day.

    :param timestamp: Timestamp to evaluate.
    :type timestamp: Optional[datetime | str]
    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param settings: Resolved standup window settings.
    :type settings: StandupWindowSettings
    :return: True when the timestamp is on a qualifying calendar day.
    :rtype: bool
    """
    local_date = timestamp_calendar_date(timestamp, settings)
    if local_date is None:
        return False
    return local_date in completed_calendar_dates(report_time, settings)


def start_of_report_calendar_day(
    report_time: datetime,
    settings: StandupWindowSettings,
) -> datetime:
    """Return the UTC instant for the start of the report calendar day.

    :param report_time: Report generation time in UTC.
    :type report_time: datetime
    :param settings: Resolved standup window settings.
    :type settings: StandupWindowSettings
    :return: Start of report day in UTC.
    :rtype: datetime
    """
    local_report_time = report_time.astimezone(settings.timezone)
    start_local = datetime.combine(
        local_report_time.date(),
        time.min,
        tzinfo=settings.timezone,
    )
    return start_local.astimezone(timezone.utc)


def default_standup_configuration() -> StandupConfiguration:
    """Return default standup configuration values.

    :return: Default standup configuration.
    :rtype: StandupConfiguration
    """
    return StandupConfiguration()
