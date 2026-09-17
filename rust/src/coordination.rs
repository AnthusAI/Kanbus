//! Git-backed soft claims and leases for coordination resources.

use std::fs;
use std::path::Path;

use chrono::{DateTime, Duration, SecondsFormat, Utc};
use serde_json::{json, Value};

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::event_history::{events_dir_for_project, write_events_batch, EventRecord, EventType};
use crate::file_io::{get_configuration_path, load_project_directory};
use crate::gossip::{
    coordination_gossip_envelope_is_valid, coordination_mqtt_available,
    publish_coordination_gossip, CoordinationGossipFields, GossipEnvelope,
};
use crate::models::{CoordinationConfiguration, ProjectConfiguration};
use crate::mutex_api::{self, MutexApiError, MutexLease};
use crate::overlay::load_coordination_overlay;

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
    /// Event ID for the selected durable claim.
    pub event_id: Option<String>,
    /// TTL supplied by the selected claim.
    pub lease_ttl_s: Option<u64>,
    /// Instant at which the selected epoch's contention window closes.
    pub contention_closes_at: Option<DateTime<Utc>>,
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
    occurred_at: DateTime<Utc>,
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
        occurred_at,
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
            event_id: Some(current.winner.event_id),
            lease_ttl_s: Some(
                (current.expires_at - current.winner.occurred_at)
                    .num_seconds()
                    .max(1) as u64,
            ),
            contention_closes_at: Some(current.started_at + duration(current.contention_window_s)),
        },
        _ => CoordinationLease {
            owner: None,
            claim_id: None,
            expires_at: None,
            event_id: None,
            lease_ttl_s: None,
            contention_closes_at: None,
        },
    }
}

fn load_coordination_events(
    project_dir: &Path,
    resource: &str,
    include_mqtt: bool,
    contention_window_s: u64,
    overlay_ttl_s: u64,
) -> Result<Vec<EventRecord>, KanbusError> {
    let events_dir = events_dir_for_project(project_dir);
    let mut paths = if events_dir.exists() {
        fs::read_dir(events_dir)
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| {
                path.extension().and_then(|extension| extension.to_str()) == Some("json")
            })
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };
    paths.sort();

    let mut events: Vec<EventRecord> = Vec::new();
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
    if include_mqtt {
        let mut seen_event_ids = events
            .iter()
            .map(|event| event.event_id.clone())
            .collect::<std::collections::HashSet<_>>();
        for envelope in load_coordination_overlay(project_dir, resource, overlay_ttl_s)? {
            if let Some(event) = coordination_gossip_event(envelope, contention_window_s) {
                if seen_event_ids.insert(event.event_id.clone()) {
                    events.push(event);
                }
            }
        }
    }
    Ok(events)
}

/// Convert a valid CLAIM, LEASE, or RELEASE envelope into the shared reducer's event shape.
pub fn coordination_gossip_event(
    envelope: GossipEnvelope,
    contention_window_s: u64,
) -> Option<EventRecord> {
    if !coordination_gossip_envelope_is_valid(&envelope) {
        return None;
    }
    let event_id = envelope.event_id.clone()?;
    let fields = envelope.coordination;
    let resource = fields.resource?;
    let owner = fields.owner?;
    let claim_id = fields.claim_id?;
    let (event_type, occurred_at, expires_at, ttl_payload) = match envelope.event_type.as_str() {
        "coordination.claim" => {
            let ttl_s = fields.lease_ttl_s?;
            let occurred_at = parse_timestamp(&envelope.ts)?;
            let expiry = occurred_at + duration(ttl_s);
            (EventType::CoordinationClaim, occurred_at, expiry, ttl_s)
        }
        "coordination.lease" => {
            let expiry = fields.expires_at?;
            fields.lease_ttl_s?;
            return Some(EventRecord {
                schema_version: crate::event_history::EVENT_SCHEMA_VERSION,
                event_id: format!("mqtt-{}", envelope.id),
                issue_id: resource,
                event_type: EventType::CoordinationRenew,
                occurred_at: envelope.ts,
                actor_id: owner.clone(),
                payload: json!({
                    "owner": owner,
                    "claim_id": claim_id,
                    "lease_expires_at": expiry,
                }),
            });
        }
        "coordination.release" => {
            return Some(EventRecord {
                schema_version: crate::event_history::EVENT_SCHEMA_VERSION,
                event_id,
                issue_id: resource,
                event_type: EventType::CoordinationRelease,
                occurred_at: envelope.ts,
                actor_id: owner.clone(),
                payload: json!({"owner": owner, "claim_id": claim_id}),
            });
        }
        _ => return None,
    };
    Some(EventRecord {
        schema_version: crate::event_history::EVENT_SCHEMA_VERSION,
        event_id,
        issue_id: resource,
        event_type,
        occurred_at: format_time(occurred_at),
        actor_id: owner.clone(),
        payload: json!({
            "owner": owner,
            "claim_id": claim_id,
            "lease_expires_at": format_time(expires_at),
            "contention_window_s": contention_window_s,
            "ttl_s": ttl_payload,
        }),
    })
}

/// Build the deterministic LEASE gossip message once the contention window closes.
pub fn coordination_lease_gossip_if_closed(
    events: &[EventRecord],
    now: DateTime<Utc>,
    resource: &str,
) -> Option<(String, CoordinationGossipFields)> {
    let lease = reduce_coordination_events(events, now);
    if !lease.is_active() || lease.contention_closes_at? > now {
        return None;
    }
    let event_id = lease.event_id.clone()?;
    Some((
        event_id,
        CoordinationGossipFields {
            resource: Some(resource.to_string()),
            owner: lease.owner,
            claim_id: lease.claim_id,
            lease_ttl_s: lease.lease_ttl_s,
            expires_at: lease.expires_at.map(format_time),
        },
    ))
}

/// Publish a LEASE announcement when this process observes a closed MQTT epoch.
/// Multiple workers may publish equivalent announcements; the durable claim
/// event ID and reducer ordering make the selected owner deterministic.
pub fn publish_coordination_lease_if_ready(
    root: &Path,
    resource: &str,
    now: DateTime<Utc>,
) -> Result<bool, KanbusError> {
    let configuration_path = get_configuration_path(root)?;
    let configuration = load_project_configuration(&configuration_path)?;
    let coordination = &configuration.coordination;
    let (contention_window_s, _) = validate_runtime_configuration(coordination)?;
    if !coordination
        .providers
        .iter()
        .any(|provider| provider == "mqtt")
    {
        return Ok(true);
    }
    let project_dir = load_project_directory(root)?;
    let events = load_coordination_events(
        &project_dir,
        resource,
        true,
        contention_window_s,
        configuration.overlay.ttl_s,
    )?;
    let Some((event_id, fields)) = coordination_lease_gossip_if_closed(&events, now, resource)
    else {
        return Ok(true);
    };
    if load_coordination_overlay(&project_dir, resource, configuration.overlay.ttl_s)?
        .iter()
        .any(|envelope| {
            envelope.event_type == "coordination.lease"
                && envelope.event_id.as_deref() == Some(event_id.as_str())
                && envelope.coordination.expires_at == fields.expires_at
        })
    {
        return Ok(true);
    }
    Ok(publish_coordination_gossip(
        root,
        &project_dir,
        "coordination.lease",
        &event_id,
        None,
        fields,
    ))
}

fn append_event(
    project_dir: &Path,
    resource: &str,
    owner: &str,
    kind: EventType,
    payload: Value,
) -> Result<EventRecord, KanbusError> {
    let record = EventRecord::new(
        resource,
        kind,
        owner,
        payload,
        format_time(coordination_now()),
    );
    write_events_batch(&events_dir_for_project(project_dir), &[record.clone()])?;
    Ok(record)
}

fn format_time(value: DateTime<Utc>) -> String {
    value.to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn active_output(provider: &str, resource: &str, lease: &CoordinationLease) -> String {
    format!(
        "provider: {provider}\nresource: {resource}\nstate: active soft ownership\nowner: {}\nclaim_id: {}\nexpires_at: {}\n",
        lease.owner.as_deref().unwrap_or_default(),
        lease.claim_id.as_deref().unwrap_or_default(),
        format_time(lease.expires_at.expect("active lease expiry")),
    )
}

fn hard_lease_output(resource: &str, lease: &MutexLease) -> String {
    format!(
        "provider: mutex_api\nresource: {resource}\nstate: active hard mutex\nowner: {}\nclaim_id: {}\nrevision: {}\nclaimed_at: {}\nexpires_at: {}\n",
        lease.owner,
        lease.claim_id,
        lease.revision,
        format_time(lease.claimed_at),
        format_time(lease.expires_at),
    )
}

fn mutex_error(error: MutexApiError) -> KanbusError {
    match error {
        MutexApiError::Unavailable(message) | MutexApiError::Rejected { message, .. } => {
            KanbusError::IssueOperation(message)
        }
    }
}

fn append_hard_claim_event(
    project_dir: &Path,
    resource: &str,
    lease: &MutexLease,
    contention_window_s: u64,
    ttl_s: u64,
) -> Result<(), KanbusError> {
    let event = EventRecord::new(
        resource,
        EventType::CoordinationClaim,
        &lease.owner,
        json!({
            "owner": lease.owner,
            "claim_id": lease.claim_id,
            "revision": lease.revision,
            "lease_expires_at": format_time(lease.expires_at),
            "contention_window_s": contention_window_s,
            "ttl_s": ttl_s,
        }),
        format_time(lease.claimed_at),
    );
    write_events_batch(&events_dir_for_project(project_dir), &[event]).map(|_| ())
}

fn basic_output(provider: &str, resource: &str, state: &str) -> String {
    format!("provider: {provider}\nresource: {resource}\nstate: {state}\n")
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
    if !validate_coordination_provider_settings(config).is_empty() {
        return Err(KanbusError::IssueOperation(
            "coordination providers must be one of: git; mqtt,git; mutex_api,mqtt,git".to_string(),
        ));
    }
    Ok((contention, ttl))
}

fn validate_identifiers(resource: &str, owner: &str, claim_id: &str) -> Result<(), KanbusError> {
    if resource.trim().is_empty() {
        return Err(KanbusError::IssueOperation(
            "resource must not be empty".to_string(),
        ));
    }
    if owner.trim().is_empty() {
        return Err(KanbusError::IssueOperation(
            "owner must not be empty".to_string(),
        ));
    }
    if claim_id.trim().is_empty() {
        return Err(KanbusError::IssueOperation(
            "claim id must not be empty".to_string(),
        ));
    }
    Ok(())
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
    let mqtt_configured = coordination
        .providers
        .iter()
        .any(|provider| provider == "mqtt");
    let mutex_api_configured = coordination
        .providers
        .iter()
        .any(|provider| provider == "mutex_api")
        && mutex_api::is_configured(&coordination.mutex_api);
    let project_dir = load_project_directory(root)?;
    match operation {
        CoordinationOperation::Claim {
            resource,
            owner,
            claim_id,
            revision,
        } => {
            validate_identifiers(&resource, &owner, &claim_id)?;
            if revision == 0 {
                return Err(KanbusError::IssueOperation(
                    "revision must be a positive integer".to_string(),
                ));
            }
            if mutex_api_configured {
                match mutex_api::acquire(
                    &coordination.mutex_api,
                    &resource,
                    &owner,
                    &claim_id,
                    revision,
                    default_ttl_s,
                ) {
                    Ok(lease) => {
                        if let Err(error) = append_hard_claim_event(
                            &project_dir,
                            &resource,
                            &lease,
                            contention_window_s,
                            default_ttl_s,
                        ) {
                            let _ = mutex_api::release(
                                &coordination.mutex_api,
                                &resource,
                                &owner,
                                &claim_id,
                            );
                            return Err(KanbusError::IssueOperation(format!(
                                "durable Git claim could not be recorded: {error}"
                            )));
                        }
                        return Ok(hard_lease_output(&resource, &lease));
                    }
                    Err(MutexApiError::Unavailable(_)) => {}
                    Err(error) => return Err(mutex_error(error)),
                }
            }
            let now = coordination_now();
            let expires_at = now + duration(default_ttl_s);
            let claim_event = append_event(
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
                    "revision": revision,
                }),
            )?;
            let provider = if mqtt_configured
                && publish_coordination_gossip(
                    root,
                    &project_dir,
                    "coordination.claim",
                    &claim_event.event_id,
                    Some(&claim_event.occurred_at),
                    CoordinationGossipFields {
                        resource: Some(resource.clone()),
                        owner: Some(owner.clone()),
                        claim_id: Some(claim_id.clone()),
                        lease_ttl_s: Some(default_ttl_s),
                        expires_at: None,
                    },
                ) {
                "mqtt"
            } else {
                "git"
            };
            let events = load_coordination_events(
                &project_dir,
                &resource,
                mqtt_configured,
                contention_window_s,
                project_configuration.overlay.ttl_s,
            )?;
            let lease = reduce_coordination_events(&events, coordination_now());
            Ok(if lease.is_active() {
                active_output(provider, &resource, &lease)
            } else {
                basic_output(provider, &resource, "eligible")
            })
        }
        CoordinationOperation::Renew {
            resource,
            owner,
            claim_id,
            extend,
        } => {
            validate_identifiers(&resource, &owner, &claim_id)?;
            if mutex_api_configured {
                let ttl_s = match extend.as_deref() {
                    Some(value) => {
                        parse_duration_seconds(value).map_err(KanbusError::IssueOperation)?
                    }
                    None => default_ttl_s,
                };
                match mutex_api::renew(&coordination.mutex_api, &resource, &owner, &claim_id, ttl_s)
                {
                    Ok(lease) => {
                        append_event(
                            &project_dir,
                            &resource,
                            &owner,
                            EventType::CoordinationRenew,
                            json!({
                                "owner": owner,
                                "claim_id": claim_id,
                                "lease_expires_at": format_time(lease.expires_at),
                                "revision": lease.revision,
                            }),
                        )?;
                        return Ok(hard_lease_output(&resource, &lease));
                    }
                    Err(MutexApiError::Unavailable(_)) => {}
                    Err(error) => return Err(mutex_error(error)),
                }
            }
            let now = coordination_now();
            let events = load_coordination_events(
                &project_dir,
                &resource,
                mqtt_configured,
                contention_window_s,
                project_configuration.overlay.ttl_s,
            )?;
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
            let renewed_lease = {
                let events = load_coordination_events(
                    &project_dir,
                    &resource,
                    mqtt_configured,
                    contention_window_s,
                    project_configuration.overlay.ttl_s,
                )?;
                reduce_coordination_events(&events, coordination_now())
            };
            let mqtt_available =
                mqtt_configured && coordination_mqtt_available(&project_configuration.realtime);
            let lease_gossip_sent = if mqtt_available {
                publish_coordination_lease_if_ready(root, &resource, coordination_now())?
            } else {
                false
            };
            let provider = if mqtt_available && lease_gossip_sent {
                "mqtt"
            } else {
                "git"
            };
            Ok(active_output(provider, &resource, &renewed_lease))
        }
        CoordinationOperation::Release {
            resource,
            owner,
            claim_id,
        } => {
            validate_identifiers(&resource, &owner, &claim_id)?;
            if mutex_api_configured {
                match mutex_api::release(&coordination.mutex_api, &resource, &owner, &claim_id) {
                    Ok(()) => {
                        append_event(
                            &project_dir,
                            &resource,
                            &owner,
                            EventType::CoordinationRelease,
                            json!({ "owner": owner, "claim_id": claim_id }),
                        )?;
                        return Ok(basic_output("mutex_api", &resource, "released"));
                    }
                    Err(MutexApiError::Unavailable(_)) => {}
                    Err(error) => return Err(mutex_error(error)),
                }
            }
            let events = load_coordination_events(
                &project_dir,
                &resource,
                mqtt_configured,
                contention_window_s,
                project_configuration.overlay.ttl_s,
            )?;
            let lease = reduce_coordination_events(&events, coordination_now());
            if lease.owner.as_deref() != Some(&owner)
                || lease.claim_id.as_deref() != Some(&claim_id)
            {
                return Err(KanbusError::IssueOperation(
                    "lease owner mismatch".to_string(),
                ));
            }
            let release_event = EventRecord::new(
                &resource,
                EventType::CoordinationRelease,
                &owner,
                json!({ "owner": owner, "claim_id": claim_id }),
                format_time(coordination_now()),
            );
            let provider = if mqtt_configured
                && publish_coordination_gossip(
                    root,
                    &project_dir,
                    "coordination.release",
                    &release_event.event_id,
                    Some(&release_event.occurred_at),
                    CoordinationGossipFields {
                        resource: Some(resource.clone()),
                        owner: Some(owner.clone()),
                        claim_id: Some(claim_id.clone()),
                        lease_ttl_s: None,
                        expires_at: None,
                    },
                ) {
                "mqtt"
            } else {
                "git"
            };
            write_events_batch(&events_dir_for_project(&project_dir), &[release_event])?;
            Ok(basic_output(provider, &resource, "released"))
        }
        CoordinationOperation::Inspect { resource } => {
            if mutex_api_configured {
                match mutex_api::inspect(&coordination.mutex_api, &resource) {
                    Ok(Some(lease)) => return Ok(hard_lease_output(&resource, &lease)),
                    Ok(None) => return Ok(basic_output("mutex_api", &resource, "eligible")),
                    Err(MutexApiError::Unavailable(_)) => {}
                    Err(error) => return Err(mutex_error(error)),
                }
            }
            let mqtt_available =
                mqtt_configured && coordination_mqtt_available(&project_configuration.realtime);
            let lease_gossip_sent = if mqtt_available {
                publish_coordination_lease_if_ready(root, &resource, coordination_now())?
            } else {
                false
            };
            let events = load_coordination_events(
                &project_dir,
                &resource,
                mqtt_configured,
                contention_window_s,
                project_configuration.overlay.ttl_s,
            )?;
            let lease = reduce_coordination_events(&events, coordination_now());
            let provider = if mqtt_available && lease_gossip_sent {
                "mqtt"
            } else {
                "git"
            };
            Ok(if lease.is_active() {
                active_output(provider, &resource, &lease)
            } else {
                basic_output(provider, &resource, "eligible")
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
        /// Positive logical revision supplied by the router.
        revision: u64,
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
    if let Some(endpoint) = config.coordination.mutex_api.endpoint.as_deref() {
        let endpoint = endpoint.trim();
        if !endpoint.is_empty()
            && !reqwest::Url::parse(endpoint).is_ok_and(|url| {
                matches!(url.scheme(), "http" | "https") && url.host_str().is_some()
            })
        {
            errors.push(
                "coordination.mutex_api.endpoint: must be an absolute http(s) URL".to_string(),
            );
        }
    }
    errors.extend(validate_coordination_provider_settings(
        &config.coordination,
    ));
    errors
}

/// Validate coordination settings without loading files.
pub fn validate_coordination_provider_settings(config: &CoordinationConfiguration) -> Vec<String> {
    if config.providers == ["git"]
        || config.providers == ["mqtt", "git"]
        || config.providers == ["mutex_api", "mqtt", "git"]
    {
        Vec::new()
    } else {
        vec!["coordination providers must be one of: git; mqtt,git; mutex_api,mqtt,git".to_string()]
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

    fn gossip(
        message_id: &str,
        event_type: &str,
        event_id: &str,
        ts: &str,
        owner: &str,
        claim_id: &str,
        ttl_s: Option<u64>,
    ) -> GossipEnvelope {
        let expires_at =
            ttl_s.map(|ttl| format_time(parse_timestamp(ts).expect("timestamp") + duration(ttl)));
        let mut envelope = crate::gossip::build_coordination_gossip_envelope(
            "KAN",
            event_type,
            event_id,
            CoordinationGossipFields {
                resource: Some("job:unit-test".to_string()),
                owner: Some(owner.to_string()),
                claim_id: Some(claim_id.to_string()),
                lease_ttl_s: ttl_s,
                expires_at,
            },
        );
        envelope.id = message_id.to_string();
        envelope.ts = ts.to_string();
        envelope
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
    fn accepts_only_canonical_strongest_first_provider_chains() {
        let mut configuration = CoordinationConfiguration::default();
        assert!(validate_coordination_provider_settings(&configuration).is_empty());
        for providers in [vec!["mqtt", "git"], vec!["mutex_api", "mqtt", "git"]] {
            configuration.providers = providers.into_iter().map(str::to_string).collect();
            assert!(validate_coordination_provider_settings(&configuration).is_empty());
        }
        for providers in [
            vec!["git", "mqtt"],
            vec!["mutex_api", "git"],
            vec!["mqtt"],
            vec!["git", "mutex_api", "mqtt"],
            vec!["mutex_api", "mqtt"],
        ] {
            configuration.providers = providers.into_iter().map(str::to_string).collect();
            assert_eq!(
                validate_coordination_provider_settings(&configuration),
                vec!["coordination providers must be one of: git; mqtt,git; mutex_api,mqtt,git"]
            );
        }
    }

    #[test]
    fn closed_contention_window_emits_winning_claim_identity_and_expiry() {
        let events = vec![
            claim("claim-b", "worker-a", "event-b", "2026-01-01T00:00:00Z"),
            claim("claim-a", "worker-b", "event-a", "2026-01-01T00:00:02Z"),
        ];
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 6).unwrap();
        let (event_id, fields) = coordination_lease_gossip_if_closed(&events, now, "job:unit-test")
            .expect("closed window lease");

        assert_eq!(event_id, "event-a");
        assert_eq!(fields.resource.as_deref(), Some("job:unit-test"));
        assert_eq!(fields.owner.as_deref(), Some("worker-b"));
        assert_eq!(fields.claim_id.as_deref(), Some("claim-a"));
        assert_eq!(fields.lease_ttl_s, Some(300));
        assert_eq!(
            fields.expires_at.as_deref(),
            Some("2026-01-01T00:05:02.000Z")
        );
    }

    #[test]
    fn coordination_lease_is_not_announced_before_window_closes() {
        let events = vec![claim(
            "claim-a",
            "worker-a",
            "event-a",
            "2026-01-01T00:00:00Z",
        )];
        let before_close = Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 4).unwrap();
        assert!(
            coordination_lease_gossip_if_closed(&events, before_close, "job:unit-test").is_none()
        );
    }

    #[test]
    fn coordination_gossip_claim_requires_contract_fields_and_reuses_durable_event_id() {
        let envelope = GossipEnvelope {
            id: "envelope-1".to_string(),
            ts: "2026-01-01T00:00:00.000Z".to_string(),
            project: "KAN".to_string(),
            event_type: "coordination.claim".to_string(),
            issue_id: None,
            event_id: Some("event-1".to_string()),
            producer_id: "producer-1".to_string(),
            origin_cluster_id: None,
            issue: None,
            coordination: CoordinationGossipFields {
                resource: Some("job:unit-test".to_string()),
                owner: Some("worker-a".to_string()),
                claim_id: Some("claim-a".to_string()),
                lease_ttl_s: Some(300),
                expires_at: None,
            },
        };
        let event = coordination_gossip_event(envelope, 3).expect("valid claim message");
        assert_eq!(event.event_id, "event-1");
        assert_eq!(event.issue_id, "job:unit-test");
        assert_eq!(event_kind(&event), Some("claim"));
        assert_eq!(event.payload["contention_window_s"], 3);
        assert_eq!(
            event.payload["lease_expires_at"],
            "2026-01-01T00:05:00.000Z"
        );
    }

    #[test]
    fn mqtt_overlay_candidates_participate_only_when_mqtt_is_configured_and_durable_ids_dedupe() {
        let temp = tempfile::TempDir::new().expect("temp dir");
        let project_dir = temp.path().join("project");
        let events_dir = events_dir_for_project(&project_dir);
        fs::create_dir_all(&events_dir).expect("events dir");
        let now = Utc::now();
        let timestamp = format_time(now);
        let durable = EventRecord::new(
            "job:unit-test",
            EventType::CoordinationClaim,
            "worker-a",
            json!({
                "owner": "worker-a",
                "claim_id": "claim-a",
                "lease_expires_at": format_time(now + Duration::seconds(300)),
                "contention_window_s": 5,
                "ttl_s": 300,
            }),
            timestamp.clone(),
        );
        write_events_batch(&events_dir, std::slice::from_ref(&durable)).expect("write Git event");
        let duplicate = gossip(
            "mqtt-claim-message",
            "coordination.claim",
            &durable.event_id,
            &timestamp,
            "worker-a",
            "claim-a",
            Some(300),
        );
        crate::overlay::write_coordination_overlay(&project_dir, &duplicate, 3600)
            .expect("write MQTT overlay");

        let loaded = load_coordination_events(&project_dir, "job:unit-test", true, 5, 3600)
            .expect("load Git plus MQTT events");
        assert_eq!(loaded.len(), 1, "MQTT must not duplicate durable event IDs");
        assert_eq!(
            load_coordination_events(&project_dir, "job:unit-test", false, 5, 3600)
                .expect("load Git only")
                .len(),
            1
        );
    }

    #[test]
    fn mqtt_release_overlay_clears_soft_ownership_before_git_release() {
        let temp = tempfile::TempDir::new().expect("temp dir");
        let project_dir = temp.path().join("project");
        let now = Utc::now();
        let claim_ts = format_time(now - Duration::seconds(1));
        let release_ts = format_time(now);
        crate::overlay::write_coordination_overlay(
            &project_dir,
            &gossip(
                "claim-message",
                "coordination.claim",
                "claim-event",
                &claim_ts,
                "worker-a",
                "claim-a",
                Some(300),
            ),
            3600,
        )
        .expect("write claim overlay");
        crate::overlay::write_coordination_overlay(
            &project_dir,
            &gossip(
                "release-message",
                "coordination.release",
                "release-event",
                &release_ts,
                "worker-a",
                "claim-a",
                None,
            ),
            3600,
        )
        .expect("write release overlay");

        let events = load_coordination_events(&project_dir, "job:unit-test", true, 5, 3600)
            .expect("load overlay events");
        assert!(!reduce_coordination_events(&events, now).is_active());
        assert!(!events_dir_for_project(&project_dir).exists());
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

    #[test]
    fn invalid_mutex_api_endpoint_reports_the_matching_field_qualified_error() {
        let mut configuration = crate::config::default_project_configuration();
        configuration.coordination.mutex_api.endpoint = Some("not-a-url".to_string());

        assert_eq!(
            validate_coordination_configuration(&configuration),
            vec!["coordination.mutex_api.endpoint: must be an absolute http(s) URL".to_string()]
        );
    }

    #[test]
    fn claim_identifiers_reject_empty_values_with_python_parity_errors() {
        assert_eq!(
            validate_identifiers("", "worker-a", "claim-a")
                .unwrap_err()
                .to_string(),
            "resource must not be empty"
        );
        assert_eq!(
            validate_identifiers("job:one", "  ", "claim-a")
                .unwrap_err()
                .to_string(),
            "owner must not be empty"
        );
        assert_eq!(
            validate_identifiers("job:one", "worker-a", "\t")
                .unwrap_err()
                .to_string(),
            "claim id must not be empty"
        );
    }
}
