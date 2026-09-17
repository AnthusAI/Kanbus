//! Git-backed soft claims and leases for coordination resources.

use std::fs;
use std::path::Path;

use chrono::{DateTime, Duration, SecondsFormat, Utc};
use serde_json::{json, Value};

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::event_history::{events_dir_for_project, write_events_batch, EventRecord, EventType};
use crate::file_io::{get_configuration_path, load_project_directory};
use crate::models::{CoordinationConfiguration, ProjectConfiguration};

/// Parse a positive integer duration expressed in seconds, minutes, or hours.
///
/// # Errors
/// Returns the shared configuration/CLI duration error for zero, malformed, or
/// unsupported values.
pub fn parse_duration_seconds(value: &str) -> Result<u64, String> {
    if value.len() < 2 {
        return Err("duration must be a positive integer followed by s, m, or h".to_string());
    }
    let (digits, unit) = value.split_at(value.len() - 1);
    if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("duration must be a positive integer followed by s, m, or h".to_string());
    }
    let amount = digits
        .parse::<u64>()
        .map_err(|_| "duration must be a positive integer followed by s, m, or h".to_string())?;
    let multiplier = match unit {
        "s" => 1,
        "m" => 60,
        "h" => 3_600,
        _ => return Err("duration must be a positive integer followed by s, m, or h".to_string()),
    };
    let seconds = amount
        .checked_mul(multiplier)
        .filter(|seconds| *seconds > 0)
        .ok_or_else(|| "duration must be a positive integer followed by s, m, or h".to_string())?;
    Ok(seconds)
}

/// Derived soft ownership for a resource at a given instant.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CoordinationLease {
    /// Selected claim owner, absent when the resource is eligible.
    pub owner: Option<String>,
    /// Selected claim identifier, absent when the resource is eligible.
    pub claim_id: Option<String>,
    /// Lease expiry, absent when the resource is eligible.
    pub expires_at: Option<DateTime<Utc>>,
}

impl CoordinationLease {
    /// Return true if a live soft owner exists at the supplied instant.
    pub fn is_active(&self) -> bool {
        self.owner.is_some() && self.claim_id.is_some() && self.expires_at.is_some()
    }
}

#[derive(Debug, Clone)]
struct Candidate {
    claim_id: String,
    owner: String,
    event_id: String,
    lease_expires_at: DateTime<Utc>,
}

#[derive(Debug, Clone)]
struct Epoch {
    started_at: DateTime<Utc>,
    contention_window_s: u64,
    candidates: Vec<Candidate>,
    winner: Candidate,
    expires_at: DateTime<Utc>,
}

fn parse_timestamp(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|timestamp| timestamp.with_timezone(&Utc))
}

fn duration(seconds: u64) -> Duration {
    Duration::seconds(i64::try_from(seconds).unwrap_or(i64::MAX))
}

fn coordination_now() -> DateTime<Utc> {
    #[cfg(debug_assertions)]
    if let Ok(value) = std::env::var("KANBUS_TEST_COORDINATION_NOW") {
        if let Some(timestamp) = parse_timestamp(&value) {
            return timestamp;
        }
    }
    Utc::now()
}

fn payload_string<'a>(event: &'a EventRecord, field: &str) -> Option<&'a str> {
    event.payload.get(field).and_then(Value::as_str)
}

fn event_kind(event: &EventRecord) -> Option<&'static str> {
    serde_json::to_value(&event.event_type)
        .ok()?
        .as_str()
        .and_then(|kind| match kind {
            "coordination.claim" => Some("claim"),
            "coordination.renew" => Some("renew"),
            "coordination.release" => Some("release"),
            _ => None,
        })
}

fn candidate_from_event(event: &EventRecord, occurred_at: DateTime<Utc>) -> Option<Candidate> {
    Some(Candidate {
        claim_id: payload_string(event, "claim_id")?.to_string(),
        owner: payload_string(event, "owner")?.to_string(),
        event_id: event.event_id.clone(),
        lease_expires_at: parse_timestamp(payload_string(event, "lease_expires_at")?)
            .unwrap_or(occurred_at),
    })
}

fn candidate_order(candidate: &Candidate) -> (&str, &str, &str) {
    (
        candidate.claim_id.as_str(),
        candidate.owner.as_str(),
        candidate.event_id.as_str(),
    )
}

/// Reduce immutable coordination event records into current lease state.
///
/// Claims inside an epoch's contention window are ordered by `(claim_id,
/// owner, event_id)`. Later claims do not change a live, closed-window winner.
///
/// # Arguments
/// * `events` - Coordination records for one resource.
/// * `now` - Instant at which the derived lease should be inspected.
pub fn reduce_coordination_events(events: &[EventRecord], now: DateTime<Utc>) -> CoordinationLease {
    let mut ordered: Vec<&EventRecord> = events
        .iter()
        .filter(|event| event_kind(event).is_some())
        .collect();
    ordered.sort_by(|left, right| {
        left.occurred_at
            .cmp(&right.occurred_at)
            .then_with(|| left.event_id.cmp(&right.event_id))
    });

    let mut epoch: Option<Epoch> = None;
    for event in ordered {
        let Some(occurred_at) = parse_timestamp(&event.occurred_at) else {
            continue;
        };
        if occurred_at > now {
            continue;
        }
        if epoch
            .as_ref()
            .is_some_and(|current| current.expires_at <= occurred_at)
        {
            epoch = None;
        }

        match event_kind(event) {
            Some("claim") => {
                let Some(candidate) = candidate_from_event(event, occurred_at) else {
                    continue;
                };
                let contention_window_s = event
                    .payload
                    .get("contention_window_s")
                    .and_then(Value::as_u64)
                    .unwrap_or(5);
                match epoch.as_mut() {
                    None => {
                        epoch = Some(Epoch {
                            started_at: occurred_at,
                            contention_window_s,
                            expires_at: candidate.lease_expires_at,
                            winner: candidate.clone(),
                            candidates: vec![candidate],
                        });
                    }
                    Some(current)
                        if occurred_at
                            <= current.started_at + duration(current.contention_window_s) =>
                    {
                        current.candidates.push(candidate);
                        if let Some(winner) = current.candidates.iter().min_by(|left, right| {
                            candidate_order(left).cmp(&candidate_order(right))
                        }) {
                            current.winner = winner.clone();
                            current.expires_at = winner.lease_expires_at;
                        }
                    }
                    Some(_) => {}
                }
            }
            Some("renew") | Some("release") => {
                let Some(current) = epoch.as_mut() else {
                    continue;
                };
                if current.expires_at <= occurred_at
                    || payload_string(event, "owner") != Some(current.winner.owner.as_str())
                    || payload_string(event, "claim_id") != Some(current.winner.claim_id.as_str())
                {
                    continue;
                }
                match event_kind(event) {
                    Some("renew") => {
                        if let Some(expiry) =
                            parse_timestamp(payload_string(event, "lease_expires_at").unwrap_or(""))
                        {
                            current.expires_at = expiry;
                        }
                    }
                    Some("release") => epoch = None,
                    _ => {}
                }
            }
            _ => {}
        }
    }

    match epoch {
        Some(current) if current.expires_at > now => CoordinationLease {
            owner: Some(current.winner.owner),
            claim_id: Some(current.winner.claim_id),
            expires_at: Some(current.expires_at),
        },
        _ => CoordinationLease {
            owner: None,
            claim_id: None,
            expires_at: None,
        },
    }
}

fn load_coordination_events(
    project_dir: &Path,
    resource: &str,
) -> Result<Vec<EventRecord>, KanbusError> {
    let events_dir = events_dir_for_project(project_dir);
    if !events_dir.exists() {
        return Ok(Vec::new());
    }
    let mut paths = fs::read_dir(events_dir)
        .map_err(|error| KanbusError::Io(error.to_string()))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|extension| extension.to_str()) == Some("json"))
        .collect::<Vec<_>>();
    paths.sort();

    let mut events = Vec::new();
    for path in paths {
        let bytes = fs::read(&path).map_err(|error| KanbusError::Io(error.to_string()))?;
        let value: Value = match serde_json::from_slice(&bytes) {
            Ok(value) => value,
            Err(_) => continue,
        };
        if value.get("issue_id").and_then(Value::as_str) != Some(resource) {
            continue;
        }
        let Some(kind) = value.get("event_type").and_then(Value::as_str) else {
            continue;
        };
        if !matches!(
            kind,
            "coordination.claim" | "coordination.renew" | "coordination.release"
        ) {
            continue;
        }
        if let Ok(event) = serde_json::from_value(value) {
            events.push(event);
        }
    }
    Ok(events)
}

fn append_event(
    project_dir: &Path,
    resource: &str,
    owner: &str,
    kind: EventType,
    payload: Value,
) -> Result<(), KanbusError> {
    let record = EventRecord::new(
        resource,
        kind,
        owner,
        payload,
        format_time(coordination_now()),
    );
    write_events_batch(&events_dir_for_project(project_dir), &[record])?;
    Ok(())
}

fn format_time(value: DateTime<Utc>) -> String {
    value.to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn active_output(resource: &str, lease: &CoordinationLease) -> String {
    format!(
        "provider: git\nresource: {resource}\nstate: active soft ownership\nowner: {}\nclaim_id: {}\nexpires_at: {}\n",
        lease.owner.as_deref().unwrap_or_default(),
        lease.claim_id.as_deref().unwrap_or_default(),
        format_time(lease.expires_at.expect("active lease expiry")),
    )
}

fn basic_output(resource: &str, state: &str) -> String {
    format!("provider: git\nresource: {resource}\nstate: {state}\n")
}

fn validate_runtime_configuration(
    config: &CoordinationConfiguration,
) -> Result<(u64, u64), KanbusError> {
    let contention = parse_duration_seconds(&config.contention_window).map_err(|error| {
        KanbusError::Configuration(format!("coordination.contention_window: {error}"))
    })?;
    let ttl = parse_duration_seconds(&config.default_lease_ttl).map_err(|error| {
        KanbusError::Configuration(format!("coordination.default_lease_ttl: {error}"))
    })?;
    if config.providers.len() != 1 || config.providers[0] != "git" {
        return Err(KanbusError::IssueOperation(
            "coordination providers must be exactly git".to_string(),
        ));
    }
    Ok((contention, ttl))
}

/// Run one coordination operation and return its human-readable output.
///
/// # Arguments
/// * `root` - Repository root containing the Kanbus project.
/// * `operation` - Requested claim, renewal, release, or inspection.
///
/// # Errors
/// Returns configuration, event-store, or lease-owner errors.
pub fn run_coordination(
    root: &Path,
    operation: CoordinationOperation,
) -> Result<String, KanbusError> {
    let configuration_path = get_configuration_path(root)?;
    let project_configuration = load_project_configuration(&configuration_path)?;
    let coordination = &project_configuration.coordination;
    let (contention_window_s, default_ttl_s) = validate_runtime_configuration(coordination)?;
    let project_dir = load_project_directory(root)?;
    match operation {
        CoordinationOperation::Claim {
            resource,
            owner,
            claim_id,
        } => {
            let now = coordination_now();
            let expires_at = now + duration(default_ttl_s);
            append_event(
                &project_dir,
                &resource,
                &owner,
                EventType::CoordinationClaim,
                json!({
                    "owner": owner,
                    "claim_id": claim_id,
                    "lease_expires_at": format_time(expires_at),
                    "contention_window_s": contention_window_s,
                    "ttl_s": default_ttl_s,
                }),
            )?;
            let events = load_coordination_events(&project_dir, &resource)?;
            let lease = reduce_coordination_events(&events, coordination_now());
            Ok(if lease.is_active() {
                active_output(&resource, &lease)
            } else {
                basic_output(&resource, "eligible")
            })
        }
        CoordinationOperation::Renew {
            resource,
            owner,
            claim_id,
            extend,
        } => {
            let now = coordination_now();
            let events = load_coordination_events(&project_dir, &resource)?;
            let lease = reduce_coordination_events(&events, now);
            if lease.owner.as_deref() != Some(&owner)
                || lease.claim_id.as_deref() != Some(&claim_id)
            {
                return Err(KanbusError::IssueOperation(
                    "lease owner mismatch".to_string(),
                ));
            }
            let ttl_s = match extend {
                Some(value) => {
                    parse_duration_seconds(&value).map_err(KanbusError::IssueOperation)?
                }
                None => default_ttl_s,
            };
            let base_expiry = lease.expires_at.expect("validated active lease").max(now);
            let expires_at = base_expiry + duration(ttl_s);
            append_event(
                &project_dir,
                &resource,
                &owner,
                EventType::CoordinationRenew,
                json!({
                    "owner": owner,
                    "claim_id": claim_id,
                    "lease_expires_at": format_time(expires_at),
                }),
            )?;
            let events = load_coordination_events(&project_dir, &resource)?;
            Ok(active_output(
                &resource,
                &reduce_coordination_events(&events, coordination_now()),
            ))
        }
        CoordinationOperation::Release {
            resource,
            owner,
            claim_id,
        } => {
            let events = load_coordination_events(&project_dir, &resource)?;
            let lease = reduce_coordination_events(&events, coordination_now());
            if lease.owner.as_deref() != Some(&owner)
                || lease.claim_id.as_deref() != Some(&claim_id)
            {
                return Err(KanbusError::IssueOperation(
                    "lease owner mismatch".to_string(),
                ));
            }
            append_event(
                &project_dir,
                &resource,
                &owner,
                EventType::CoordinationRelease,
                json!({ "owner": owner, "claim_id": claim_id }),
            )?;
            Ok(basic_output(&resource, "released"))
        }
        CoordinationOperation::Inspect { resource } => {
            let events = load_coordination_events(&project_dir, &resource)?;
            let lease = reduce_coordination_events(&events, coordination_now());
            Ok(if lease.is_active() {
                active_output(&resource, &lease)
            } else {
                basic_output(&resource, "eligible")
            })
        }
    }
}

/// A supported operation on a coordination resource.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CoordinationOperation {
    /// Append a soft claim event using the configured default lease TTL.
    Claim {
        /// Resource key to claim.
        resource: String,
        /// Claim owner identifier.
        owner: String,
        /// Stable claim identifier.
        claim_id: String,
    },
    /// Extend the currently selected owner's lease.
    Renew {
        /// Resource key to renew.
        resource: String,
        /// Claim owner identifier.
        owner: String,
        /// Stable claim identifier.
        claim_id: String,
        /// Optional replacement TTL; omitted uses the configured default.
        extend: Option<String>,
    },
    /// Append a release event for the selected owner.
    Release {
        /// Resource key to release.
        resource: String,
        /// Claim owner identifier.
        owner: String,
        /// Stable claim identifier.
        claim_id: String,
    },
    /// Inspect current soft ownership without writing an event.
    Inspect {
        /// Resource key to inspect.
        resource: String,
    },
}

/// Validate coordination duration fields in a loaded project configuration.
pub fn validate_coordination_configuration(config: &ProjectConfiguration) -> Vec<String> {
    let mut errors = Vec::new();
    if parse_duration_seconds(&config.coordination.contention_window).is_err() {
        errors.push(
            "coordination.contention_window: duration must be a positive integer followed by s, m, or h"
                .to_string(),
        );
    }
    if parse_duration_seconds(&config.coordination.default_lease_ttl).is_err() {
        errors.push(
            "coordination.default_lease_ttl: duration must be a positive integer followed by s, m, or h"
                .to_string(),
        );
    }
    errors.extend(validate_coordination_provider_settings(
        &config.coordination,
    ));
    errors
}

/// Validate coordination settings without loading files.
pub fn validate_coordination_provider_settings(config: &CoordinationConfiguration) -> Vec<String> {
    if config.providers.len() == 1 && config.providers[0] == "git" {
        Vec::new()
    } else {
        vec!["coordination providers must be exactly git".to_string()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn record(
        resource: &str,
        event_type: EventType,
        event_id: &str,
        occurred_at: &str,
        payload: Value,
    ) -> EventRecord {
        let mut event = EventRecord::new(resource, event_type, "test", payload, occurred_at.into());
        event.event_id = event_id.to_string();
        event
    }

    fn claim(id: &str, owner: &str, event_id: &str, at: &str) -> EventRecord {
        let occurred = parse_timestamp(at).expect("timestamp");
        record(
            "job:unit-test",
            EventType::CoordinationClaim,
            event_id,
            at,
            json!({
                "owner": owner,
                "claim_id": id,
                "lease_expires_at": format_time(occurred + Duration::seconds(300)),
                "contention_window_s": 5,
                "ttl_s": 300,
            }),
        )
    }

    #[test]
    fn duration_parser_accepts_positive_seconds_minutes_and_hours() {
        assert_eq!(parse_duration_seconds("5s"), Ok(5));
        assert_eq!(parse_duration_seconds("2m"), Ok(120));
        assert_eq!(parse_duration_seconds("1h"), Ok(3_600));
        for invalid in ["0s", "-1s", "1d", "1.5m", "s", "5"] {
            assert!(parse_duration_seconds(invalid).is_err(), "{invalid}");
        }
    }

    #[test]
    fn claims_in_window_choose_stable_tuple_winner_and_later_claims_do_not_displace() {
        let events = vec![
            claim("claim-2", "worker-b", "event-1", "2026-01-01T00:00:00Z"),
            claim("claim-1", "worker-a", "event-2", "2026-01-01T00:00:03Z"),
            claim("claim-0", "worker-c", "event-3", "2026-01-01T00:00:06Z"),
        ];
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 10).unwrap();
        let lease = reduce_coordination_events(&events, now);
        assert_eq!(lease.owner.as_deref(), Some("worker-a"));
        assert_eq!(lease.claim_id.as_deref(), Some("claim-1"));
    }

    #[test]
    fn event_id_breaks_otherwise_identical_claim_ties() {
        let first = claim("same-claim", "worker", "z-event", "2026-01-01T00:00:00Z");
        let mut second = claim("same-claim", "worker", "a-event", "2026-01-01T00:00:01Z");
        second.payload["lease_expires_at"] = json!("2026-01-01T00:10:01.000Z");
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 10).unwrap();

        let lease = reduce_coordination_events(&[first, second], now);

        assert_eq!(lease.owner.as_deref(), Some("worker"));
        assert_eq!(lease.claim_id.as_deref(), Some("same-claim"));
        assert_eq!(
            lease.expires_at,
            parse_timestamp("2026-01-01T00:10:01.000Z")
        );
    }

    #[test]
    fn a_later_claim_after_expiry_starts_a_new_epoch() {
        let first = claim("old", "worker-old", "event-1", "2026-01-01T00:00:00Z");
        let mut second = claim("new", "worker-new", "event-2", "2026-01-01T00:06:00Z");
        second.payload["lease_expires_at"] = json!("2026-01-01T00:11:00.000Z");
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 7, 0).unwrap();
        let lease = reduce_coordination_events(&[first, second], now);
        assert_eq!(lease.owner.as_deref(), Some("worker-new"));
    }

    #[test]
    fn renewal_and_release_are_applied_only_for_the_current_winner() {
        let first = claim("claim-a", "worker-a", "event-1", "2026-01-01T00:00:00Z");
        let renewal = record(
            "job:unit-test",
            EventType::CoordinationRenew,
            "event-2",
            "2026-01-01T00:01:00Z",
            json!({
                "owner": "worker-a",
                "claim_id": "claim-a",
                "lease_expires_at": "2026-01-01T00:10:00.000Z",
            }),
        );
        let wrong_release = record(
            "job:unit-test",
            EventType::CoordinationRelease,
            "event-3",
            "2026-01-01T00:02:00Z",
            json!({ "owner": "worker-b", "claim_id": "claim-b" }),
        );
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 5, 0).unwrap();
        let lease = reduce_coordination_events(&[first.clone(), renewal, wrong_release], now);
        assert_eq!(lease.owner.as_deref(), Some("worker-a"));
        assert_eq!(
            lease.expires_at,
            parse_timestamp("2026-01-01T00:10:00.000Z")
        );

        let release = record(
            "job:unit-test",
            EventType::CoordinationRelease,
            "event-4",
            "2026-01-01T00:06:00Z",
            json!({ "owner": "worker-a", "claim_id": "claim-a" }),
        );
        let lease = reduce_coordination_events(&[first, release], now);
        assert!(!lease.is_active());
    }

    #[test]
    fn expired_lease_is_eligible() {
        let event = claim("stale", "worker", "event-1", "2026-01-01T00:00:00Z");
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 6, 0).unwrap();
        assert!(!reduce_coordination_events(&[event], now).is_active());
    }

    #[test]
    fn future_events_do_not_affect_inspection_before_they_occur() {
        let future = claim("future", "worker", "event-1", "2026-01-01T00:05:00Z");
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 4, 59).unwrap();
        assert!(!reduce_coordination_events(&[future], now).is_active());
    }

    #[test]
    fn only_git_is_an_allowed_level_one_provider_configuration() {
        let mut configuration = CoordinationConfiguration::default();
        assert!(validate_coordination_provider_settings(&configuration).is_empty());
        configuration.providers = vec!["git".to_string(), "mqtt".to_string()];
        assert_eq!(
            validate_coordination_provider_settings(&configuration),
            vec!["coordination providers must be exactly git"]
        );
    }

    #[test]
    fn invalid_duration_reports_the_matching_field_qualified_error() {
        let mut configuration = crate::config::default_project_configuration();
        configuration.coordination.contention_window = "0s".to_string();

        assert_eq!(
            validate_coordination_configuration(&configuration),
            vec![
                "coordination.contention_window: duration must be a positive integer followed by s, m, or h"
                    .to_string()
            ]
        );
    }
}
