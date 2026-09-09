//! Standup time window resolution (rolling vs calendar).

use std::env;

use chrono::{DateTime, Datelike, Duration, TimeZone, Utc};
use chrono_tz::{Tz, UTC};
use regex::Regex;
use std::sync::OnceLock;

use crate::error::KanbusError;
use crate::models::{ProjectConfiguration, StandupConfiguration};
use crate::standup::{DIRECTOR_BRIEF_PROFILE, MEETING_SCRIPT_PROFILE};

pub const ROLLING_WINDOW: &str = "rolling";
pub const CALENDAR_WINDOW: &str = "calendar";
pub const DEFAULT_STANDUP_LOOKBACK: &str = "24h";
pub const STANDUP_REPORT_TIME_ENV: &str = "KANBUS_STANDUP_REPORT_TIME";

/// Optional CLI or API overrides for standup window settings.
#[derive(Debug, Clone, Default)]
pub struct StandupWindowOverrides {
    /// Optional window mode override.
    pub window: Option<String>,
    /// Optional lookback duration override.
    pub lookback: Option<String>,
    /// Optional skip-weekends override.
    pub skip_weekends: Option<bool>,
}

/// Resolved standup window settings for report generation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StandupWindowSettings {
    /// Window mode (`rolling` or `calendar`).
    pub window: String,
    /// Canonical lookback duration string.
    pub lookback: String,
    /// Lookback duration in hours.
    pub lookback_hours: u32,
    /// Whether calendar mode bundles weekends on Monday.
    pub skip_weekends: bool,
    /// Resolved standup timezone.
    pub timezone: Tz,
}

fn lookback_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r"^(\d+)([hd])$").expect("lookback regex"))
}

/// Parse a standup lookback duration into hours.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when the duration format is invalid.
pub fn parse_standup_lookback_hours(lookback: &str) -> Result<u32, KanbusError> {
    let normalized = lookback.trim().to_ascii_lowercase();
    let captures = lookback_pattern().captures(&normalized).ok_or_else(|| {
        KanbusError::IssueOperation(format!("invalid standup lookback: {lookback}"))
    })?;
    let amount = captures
        .get(1)
        .and_then(|value| value.as_str().parse::<u32>().ok())
        .filter(|value| *value > 0)
        .ok_or_else(|| {
            KanbusError::IssueOperation(format!("invalid standup lookback: {lookback}"))
        })?;
    let unit = captures.get(2).map(|value| value.as_str()).unwrap_or("h");
    if unit == "d" {
        return Ok(amount * 24);
    }
    Ok(amount)
}

/// Resolve the standup timezone from configuration.
pub fn resolve_standup_timezone(configuration: &ProjectConfiguration) -> Tz {
    if let Some(timezone_name) = configuration.standup.timezone.as_deref() {
        if let Ok(timezone) = timezone_name.parse::<Tz>() {
            return timezone;
        }
    }
    let local_name = iana_time_zone::get_timezone().unwrap_or_else(|_| String::from("UTC"));
    local_name.parse::<Tz>().unwrap_or(UTC)
}

/// Resolve standup window settings from config, profile, and overrides.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when settings are invalid.
pub fn resolve_standup_window_settings(
    configuration: &ProjectConfiguration,
    profile: Option<&str>,
    overrides: &StandupWindowOverrides,
) -> Result<StandupWindowSettings, KanbusError> {
    let standup = &configuration.standup;
    let mut window = standup.window.clone();
    let mut lookback = standup.lookback.clone();
    let mut skip_weekends = standup.skip_weekends;

    if profile == Some(MEETING_SCRIPT_PROFILE) {
        window = CALENDAR_WINDOW.to_string();
        skip_weekends = true;
    } else if profile == Some(DIRECTOR_BRIEF_PROFILE) {
        window = ROLLING_WINDOW.to_string();
        lookback = DEFAULT_STANDUP_LOOKBACK.to_string();
        skip_weekends = false;
    }

    if let Some(override_window) = overrides.window.as_deref() {
        window = override_window.to_string();
    }
    if let Some(override_lookback) = overrides.lookback.as_deref() {
        lookback = override_lookback.to_string();
    }
    if let Some(override_skip_weekends) = overrides.skip_weekends {
        skip_weekends = override_skip_weekends;
    }

    if window != ROLLING_WINDOW && window != CALENDAR_WINDOW {
        return Err(KanbusError::IssueOperation(format!(
            "invalid standup window: {window}"
        )));
    }

    let lookback_hours = parse_standup_lookback_hours(&lookback)?;
    Ok(StandupWindowSettings {
        window,
        lookback,
        lookback_hours,
        skip_weekends,
        timezone: resolve_standup_timezone(configuration),
    })
}

/// Resolve the standup report generation timestamp.
///
/// # Errors
///
/// Returns `KanbusError::IssueOperation` when the override is invalid.
pub fn resolve_standup_report_time() -> Result<DateTime<Utc>, KanbusError> {
    if let Ok(override_value) = env::var(STANDUP_REPORT_TIME_ENV) {
        let normalized = override_value.replace('Z', "+00:00");
        let parsed = DateTime::parse_from_rfc3339(&normalized)
            .map_err(|_| {
                KanbusError::IssueOperation(format!(
                    "invalid {STANDUP_REPORT_TIME_ENV}: {override_value}"
                ))
            })?
            .with_timezone(&Utc);
        return Ok(parsed);
    }
    Ok(Utc::now())
}

/// Return calendar dates that qualify for the completed bucket.
pub fn completed_calendar_dates(
    report_time: DateTime<Utc>,
    settings: &StandupWindowSettings,
) -> Vec<chrono::NaiveDate> {
    let local_report_time = report_time.with_timezone(&settings.timezone);
    let report_day = local_report_time.date_naive();
    if settings.skip_weekends && report_day.weekday() == chrono::Weekday::Mon {
        return vec![
            report_day - Duration::days(3),
            report_day - Duration::days(2),
            report_day - Duration::days(1),
        ];
    }
    vec![report_day - Duration::days(1)]
}

fn timestamp_calendar_date(
    timestamp: Option<&DateTime<Utc>>,
    settings: &StandupWindowSettings,
) -> Option<chrono::NaiveDate> {
    timestamp.map(|value| value.with_timezone(&settings.timezone).date_naive())
}

/// Return whether a timestamp falls on a completed calendar day.
pub fn is_on_completed_calendar_day(
    timestamp: Option<&DateTime<Utc>>,
    report_time: DateTime<Utc>,
    settings: &StandupWindowSettings,
) -> bool {
    let Some(local_date) = timestamp_calendar_date(timestamp, settings) else {
        return false;
    };
    completed_calendar_dates(report_time, settings).contains(&local_date)
}

/// Return the UTC instant for the start of the report calendar day.
pub fn start_of_report_calendar_day(
    report_time: DateTime<Utc>,
    settings: &StandupWindowSettings,
) -> DateTime<Utc> {
    let local_report_time = report_time.with_timezone(&settings.timezone);
    let report_day = local_report_time.date_naive();
    settings
        .timezone
        .from_local_datetime(
            &report_day
                .and_hms_opt(0, 0, 0)
                .expect("midnight should be valid"),
        )
        .single()
        .map(|value| value.with_timezone(&Utc))
        .unwrap_or(report_time)
}

/// Return default standup configuration values.
pub fn default_standup_configuration() -> StandupConfiguration {
    StandupConfiguration::default()
}
