//! Git-backed soft claims and leases for coordination resources.

use std::fs;
use std::path::Path;
use std::process::Command;
use std::sync::{Arc, Mutex};

use chrono::{DateTime, Duration, SecondsFormat, Utc};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::event_history::{
    events_dir_for_project, now_timestamp, write_events_batch, EventRecord, EventType,
};
use crate::file_io::{get_configuration_path, load_project_directory};
use crate::gossip::{
    collect_coordination_gossip_window_with, coordination_gossip_envelope_is_valid,
    coordination_mqtt_available, publish_coordination_gossip, CoordinationGossipFields,
    GossipEnvelope,
};
use crate::models::{
    validate_http_endpoint, CoordinationConfiguration, HttpEndpointError, ProjectConfiguration,
};
use crate::mutex_api::{self, MutexApiError, MutexLease};
use crate::overlay::load_coordination_overlay;
use crate::users::get_current_user;

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
    let mut digit_bytes = digits.bytes();
    if !digit_bytes
        .next()
        .is_some_and(|byte| (b'1'..=b'9').contains(&byte))
        || !digit_bytes.all(|byte| byte.is_ascii_digit())
    {
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

/// Return the additional seconds needed to keep a lease alive through `now + ttl`.
///
/// Router renewal loops use this to maintain a fixed lease horizon without
/// cumulatively extending the expiry on every heartbeat. A missing expiry or
/// an already-sufficient lease requires no renewal.
pub fn lease_renewal_extension_seconds(
    current_expiry: Option<DateTime<Utc>>,
    now: DateTime<Utc>,
    ttl_seconds: u64,
) -> u64 {
    let Some(current_expiry) = current_expiry else {
        return 0;
    };
    let target_expiry = now + duration(ttl_seconds);
    let remaining = target_expiry - current_expiry;
    if remaining <= Duration::zero() {
        return 0;
    }
    let seconds = remaining.num_seconds().max(0) as u64;
    seconds.saturating_add(u64::from(remaining.subsec_nanos() > 0))
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
    /// Logical order assigned to the selected claim/renewal event, when known.
    pub operation_sequence: Option<u64>,
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
    operation_sequence: Option<u64>,
}

#[derive(Debug, Clone)]
struct Epoch {
    started_at: DateTime<Utc>,
    contention_window_s: u64,
    candidates: Vec<Candidate>,
    winner: Candidate,
    expires_at: DateTime<Utc>,
    operation_sequence: Option<u64>,
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

fn with_optional_operation_sequence(mut payload: Value, sequence: Option<u64>) -> Value {
    if let Some(sequence) = sequence {
        payload["operation_sequence"] = json!(sequence);
    }
    payload
}

fn candidate_from_event(event: &EventRecord, occurred_at: DateTime<Utc>) -> Option<Candidate> {
    Some(Candidate {
        claim_id: payload_string(event, "claim_id")?.to_string(),
        owner: payload_string(event, "owner")?.to_string(),
        event_id: event.event_id.clone(),
        lease_expires_at: parse_timestamp(payload_string(event, "lease_expires_at")?)
            .unwrap_or(occurred_at),
        occurred_at,
        operation_sequence: event
            .payload
            .get("operation_sequence")
            .and_then(Value::as_u64)
            .filter(|sequence| *sequence > 0),
    })
}

fn effective_operation_sequence(event: &EventRecord) -> Option<u64> {
    match event.payload.get("operation_sequence") {
        None => Some(0),
        Some(value) => value.as_u64().filter(|sequence| *sequence > 0),
    }
}

fn observed_operation_sequence(project_dir: &Path, resource: &str) -> Result<u64, KanbusError> {
    let events_dir = events_dir_for_project(project_dir);
    let mut maximum = 0_u64;
    if !events_dir.exists() {
        return Ok(maximum);
    }
    for entry in fs::read_dir(events_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
        let path = entry
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .path();
        if path.extension().and_then(|extension| extension.to_str()) != Some("json") {
            continue;
        }
        let Ok(bytes) = fs::read(path) else {
            continue;
        };
        let Ok(event) = serde_json::from_slice::<EventRecord>(&bytes) else {
            continue;
        };
        if event.issue_id != resource || event_kind(&event).is_none() {
            continue;
        }
        if let Some(sequence) = event
            .payload
            .get("operation_sequence")
            .and_then(Value::as_u64)
            .filter(|sequence| *sequence > 0)
        {
            maximum = maximum.max(sequence);
        }
    }
    Ok(maximum)
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
        .filter(|event| {
            event_kind(event).is_some() && effective_operation_sequence(event).is_some()
        })
        .collect();
    ordered.sort_by(|left, right| {
        effective_operation_sequence(left)
            .cmp(&effective_operation_sequence(right))
            .then_with(|| left.occurred_at.cmp(&right.occurred_at))
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
                            operation_sequence: event
                                .payload
                                .get("operation_sequence")
                                .and_then(Value::as_u64)
                                .filter(|sequence| *sequence > 0),
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
                            current.operation_sequence = winner.operation_sequence;
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
                            current.operation_sequence = event
                                .payload
                                .get("operation_sequence")
                                .and_then(Value::as_u64)
                                .filter(|sequence| *sequence > 0);
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
            operation_sequence: current.operation_sequence,
        },
        _ => CoordinationLease {
            owner: None,
            claim_id: None,
            expires_at: None,
            event_id: None,
            lease_ttl_s: None,
            contention_closes_at: None,
            operation_sequence: None,
        },
    }
}

/// Reduce immutable result publication events to the greatest published revision.
///
/// # Arguments
/// * `events` - Event history that may include result publication records.
///
/// # Returns
/// The greatest positive revision represented by a valid publication event.
pub fn reduce_published_revision(events: &[EventRecord]) -> Option<u64> {
    events
        .iter()
        .filter(|event| matches!(&event.event_type, EventType::CoordinationResultPublished))
        .filter_map(|event| event.payload.get("revision").and_then(Value::as_u64))
        .filter(|revision| *revision > 0)
        .max()
}

fn published_artifact(events: &[EventRecord], revision: u64) -> Option<&str> {
    events
        .iter()
        .filter(|event| matches!(&event.event_type, EventType::CoordinationResultPublished))
        .filter(|event| event.payload.get("revision").and_then(Value::as_u64) == Some(revision))
        .max_by(|left, right| {
            left.occurred_at
                .cmp(&right.occurred_at)
                .then_with(|| left.event_id.cmp(&right.event_id))
        })
        .and_then(|event| event.payload.get("artifact").and_then(Value::as_str))
}

fn load_result_publication_events(
    project_dir: &Path,
    resource: &str,
) -> Result<Vec<EventRecord>, KanbusError> {
    let events_dir = events_dir_for_project(project_dir);
    let mut events = Vec::new();
    if events_dir.exists() {
        let mut paths = fs::read_dir(events_dir)
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| {
                path.extension().and_then(|extension| extension.to_str()) == Some("json")
            })
            .collect::<Vec<_>>();
        paths.sort();
        for path in paths {
            let bytes = fs::read(path).map_err(|error| KanbusError::Io(error.to_string()))?;
            let Ok(event) = serde_json::from_slice::<EventRecord>(&bytes) else {
                continue;
            };
            if event.issue_id == resource
                && matches!(&event.event_type, EventType::CoordinationResultPublished)
            {
                events.push(event);
            }
        }
    }
    if resource.starts_with("router:") {
        let root = Command::new("git")
            .args(["rev-parse", "--show-toplevel"])
            .current_dir(project_dir)
            .output()
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        if root.status.success() {
            let root = String::from_utf8_lossy(&root.stdout).trim().to_string();
            for event in crate::router::read_shared_router_events(Path::new(&root))? {
                if event.issue_id == resource
                    && matches!(&event.event_type, EventType::CoordinationResultPublished)
                    && !events
                        .iter()
                        .any(|existing| existing.event_id == event.event_id)
                {
                    events.push(event);
                }
            }
        }
    }
    Ok(events)
}

/// Return the greatest published revision for a coordination resource.
///
/// # Arguments
/// * `project_dir` - Project directory containing the immutable event history.
/// * `resource` - Coordination resource identifier.
///
/// # Errors
/// Returns `KanbusError::Io` when the event history cannot be read.
pub fn published_revision(project_dir: &Path, resource: &str) -> Result<Option<u64>, KanbusError> {
    Ok(reduce_published_revision(&load_result_publication_events(
        project_dir,
        resource,
    )?))
}

/// Publish an artifact reference unless a newer logical revision already exists.
///
/// The publication is stored as an immutable coordination event, and the
/// revision is reduced from event history rather than mutable local state.
///
/// # Arguments
/// * `project_dir` - Project directory containing the event history.
/// * `resource` - Coordination resource identifier.
/// * `revision` - Positive logical task revision.
/// * `artifact` - Artifact reference recorded with the publication.
///
/// # Errors
/// Returns `KanbusError` for invalid values, stale revisions, or event-store failures.
pub fn publish_coordination_result(
    project_dir: &Path,
    resource: &str,
    revision: u64,
    artifact: &str,
) -> Result<(), KanbusError> {
    if resource.trim().is_empty() {
        return Err(KanbusError::IssueOperation(
            "resource must not be empty".to_string(),
        ));
    }
    if revision == 0 {
        return Err(KanbusError::IssueOperation(
            "revision must be a positive integer".to_string(),
        ));
    }
    if artifact.trim().is_empty() {
        return Err(KanbusError::IssueOperation(
            "artifact must not be empty".to_string(),
        ));
    }
    let current_events = load_result_publication_events(project_dir, resource)?;
    if let Some(current_revision) = reduce_published_revision(&current_events) {
        if revision < current_revision {
            return Err(KanbusError::IssueOperation(format!(
                "stale revision {revision}; published revision is {current_revision}"
            )));
        }
        if revision == current_revision {
            if published_artifact(&current_events, current_revision) == Some(artifact) {
                return Ok(());
            }
            return Err(KanbusError::IssueOperation(format!(
                "revision {revision} already published with a different artifact"
            )));
        }
    }
    let event = EventRecord::new(
        resource,
        EventType::CoordinationResultPublished,
        get_current_user(),
        json!({"resource": resource, "revision": revision, "artifact": artifact}),
        now_timestamp(),
    );
    persist_router_coordination_event(project_dir, resource, &event)?;
    Ok(())
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

fn write_router_claim_observation(
    project_dir: &Path,
    resource: &str,
    claim_id: &str,
    overlay_ttl_s: u64,
) -> Result<(), KanbusError> {
    let peer_claim_ids = load_coordination_overlay(project_dir, resource, overlay_ttl_s)?
        .into_iter()
        .filter(|envelope| envelope.event_type == "coordination.claim")
        .filter_map(|envelope| envelope.coordination.claim_id)
        .filter(|observed_id| observed_id != claim_id)
        .collect::<std::collections::BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let mut observed_claim_ids = peer_claim_ids.clone();
    observed_claim_ids.push(claim_id.to_string());
    observed_claim_ids.sort();

    let directory = project_dir
        .join(".overlay")
        .join("coordination-observations")
        .join(sha256_hex(resource));
    fs::create_dir_all(&directory).map_err(|error| KanbusError::Io(error.to_string()))?;
    prune_router_claim_observations(&directory, overlay_ttl_s);
    let claim_hash = sha256_hex(claim_id);
    let destination = directory.join(format!("{claim_hash}.json"));
    let temporary = directory.join(format!(".{claim_hash}.{}.tmp", Uuid::new_v4()));
    let contents = serde_json::to_vec_pretty(&json!({
        "schema_version": 1,
        "resource": resource,
        "claim_id": claim_id,
        "local_claim_id": claim_id,
        "observed_claim_ids": observed_claim_ids,
        "peer_claim_ids": peer_claim_ids,
        "observed_at": format_time(coordination_now()),
    }))
    .map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::write(&temporary, contents).map_err(|error| KanbusError::Io(error.to_string()))?;
    if let Err(error) = fs::rename(&temporary, &destination) {
        let _ = fs::remove_file(&temporary);
        return Err(KanbusError::Io(error.to_string()));
    }
    Ok(())
}

fn prune_router_claim_observations(directory: &Path, ttl_s: u64) {
    let cutoff = coordination_now() - duration(ttl_s);
    let Ok(entries) = fs::read_dir(directory) else {
        return;
    };
    for entry in entries.filter_map(Result::ok) {
        let path = entry.path();
        if path.extension().and_then(|extension| extension.to_str()) != Some("json") {
            continue;
        }
        let Ok(contents) = fs::read(&path) else {
            continue;
        };
        let Ok(value) = serde_json::from_slice::<Value>(&contents) else {
            continue;
        };
        let Some(observed_at) = value.get("observed_at").and_then(Value::as_str) else {
            continue;
        };
        if parse_timestamp(observed_at).is_some_and(|timestamp| timestamp < cutoff) {
            let _ = fs::remove_file(path);
        }
    }
}

fn sha256_hex(value: &str) -> String {
    Sha256::digest(value.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
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
    let operation_sequence = fields.operation_sequence;
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
            let payload = with_optional_operation_sequence(
                json!({
                    "owner": owner,
                    "claim_id": claim_id,
                    "lease_expires_at": expiry,
                }),
                operation_sequence,
            );
            return Some(EventRecord {
                schema_version: crate::event_history::EVENT_SCHEMA_VERSION,
                event_id: format!("mqtt-{}", envelope.id),
                issue_id: resource,
                event_type: EventType::CoordinationRenew,
                occurred_at: envelope.ts,
                actor_id: owner.clone(),
                payload,
            });
        }
        "coordination.release" => {
            let payload = with_optional_operation_sequence(
                json!({"owner": owner, "claim_id": claim_id}),
                operation_sequence,
            );
            return Some(EventRecord {
                schema_version: crate::event_history::EVENT_SCHEMA_VERSION,
                event_id,
                issue_id: resource,
                event_type: EventType::CoordinationRelease,
                occurred_at: envelope.ts,
                actor_id: owner.clone(),
                payload,
            });
        }
        _ => return None,
    };
    let payload = with_optional_operation_sequence(
        json!({
            "owner": owner,
            "claim_id": claim_id,
            "lease_expires_at": format_time(expires_at),
            "contention_window_s": contention_window_s,
            "ttl_s": ttl_payload,
        }),
        operation_sequence,
    );
    Some(EventRecord {
        schema_version: crate::event_history::EVENT_SCHEMA_VERSION,
        event_id,
        issue_id: resource,
        event_type,
        occurred_at: format_time(occurred_at),
        actor_id: owner.clone(),
        payload,
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
            operation_sequence: lease.operation_sequence,
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
    append_event_at(
        project_dir,
        resource,
        owner,
        kind,
        payload,
        format_time(coordination_now()),
    )
}

fn append_event_at(
    project_dir: &Path,
    resource: &str,
    owner: &str,
    kind: EventType,
    payload: Value,
    occurred_at: String,
) -> Result<EventRecord, KanbusError> {
    let record = EventRecord::new(resource, kind, owner, payload, occurred_at);
    persist_router_coordination_event(project_dir, resource, &record)
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn append_soft_claim_event(
    project_dir: &Path,
    resource: &str,
    owner: &str,
    claim_id: &str,
    revision: u64,
    contention_window_s: u64,
    ttl_s: u64,
    occurred_at: DateTime<Utc>,
) -> Result<EventRecord, KanbusError> {
    let lease_expires_at = occurred_at + duration(ttl_s);
    append_event_at(
        project_dir,
        resource,
        owner,
        EventType::CoordinationClaim,
        json!({
            "owner": owner,
            "claim_id": claim_id,
            "lease_expires_at": format_time(lease_expires_at),
            "contention_window_s": contention_window_s,
            "ttl_s": ttl_s,
            "revision": revision,
        }),
        format_time(occurred_at),
    )
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

/// Persist an API-issued hard lease in the Git coordination event history.
///
/// # Arguments
/// * `project_dir` - Project directory containing immutable coordination events.
/// * `resource` - Resource key protected by the lease.
/// * `lease` - Lease returned by the hard mutex API.
/// * `contention_window_s` - Soft coordination comparison window.
/// * `ttl_s` - Lease lifetime in seconds.
///
/// # Errors
/// Returns `KanbusError` if the durable event cannot be written.
pub fn append_hard_claim_event(
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
    persist_router_coordination_event(project_dir, resource, &event).map(|_| ())
}

/// Persist a release event for a successfully released API-issued hard lease.
///
/// # Arguments
/// * `project_dir` - Project directory containing immutable coordination events.
/// * `resource` - Resource key protected by the lease.
/// * `owner` - Owner that released the lease.
/// * `claim_id` - Stable claim identifier.
///
/// # Errors
/// Returns `KanbusError` if the release event cannot be written.
pub fn append_hard_release_event(
    project_dir: &Path,
    resource: &str,
    owner: &str,
    claim_id: &str,
) -> Result<(), KanbusError> {
    let event = EventRecord::new(
        resource,
        EventType::CoordinationRelease,
        owner,
        json!({"owner": owner, "claim_id": claim_id}),
        format_time(coordination_now()),
    );
    persist_router_coordination_event(project_dir, resource, &event).map(|_| ())
}

/// Persist a lease renewal returned by the hard mutex API.
pub fn append_hard_renew_event(
    project_dir: &Path,
    resource: &str,
    lease: &MutexLease,
) -> Result<(), KanbusError> {
    let event = EventRecord::new(
        resource,
        EventType::CoordinationRenew,
        &lease.owner,
        json!({
            "owner": lease.owner,
            "claim_id": lease.claim_id,
            "revision": lease.revision,
            "lease_expires_at": format_time(lease.expires_at),
        }),
        format_time(coordination_now()),
    );
    persist_router_coordination_event(project_dir, resource, &event).map(|_| ())
}

fn persist_router_coordination_event(
    project_dir: &Path,
    resource: &str,
    event: &EventRecord,
) -> Result<EventRecord, KanbusError> {
    let mut event = event.clone();
    if event_kind(&event).is_some() {
        match event.payload.get("operation_sequence") {
            None => {
                let sequence = observed_operation_sequence(project_dir, resource)?
                    .checked_add(1)
                    .ok_or_else(|| {
                        KanbusError::IssueOperation(
                            "coordination operation sequence overflow".to_string(),
                        )
                    })?;
                event.payload["operation_sequence"] = json!(sequence);
            }
            Some(value) if value.as_u64().is_some_and(|sequence| sequence > 0) => {}
            Some(_) => {
                return Err(KanbusError::IssueOperation(
                    "coordination operation_sequence must be a positive integer".to_string(),
                ));
            }
        }
    }
    write_events_batch(
        &events_dir_for_project(project_dir),
        std::slice::from_ref(&event),
    )?;
    if resource.starts_with("router:") {
        let root = Command::new("git")
            .args(["rev-parse", "--show-toplevel"])
            .current_dir(project_dir)
            .output()
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        if root.status.success() {
            let root = String::from_utf8_lossy(&root.stdout).trim().to_string();
            crate::router::publish_shared_router_event(Path::new(&root), &event)?;
        }
    }
    Ok(event)
}

fn basic_output(provider: &str, resource: &str, state: &str) -> String {
    format!("provider: {provider}\nresource: {resource}\nstate: {state}\n")
}

fn published_result_output(provider: &str, resource: &str, revision: u64) -> String {
    format!("provider: {provider}\nresource: {resource}\nrevision: {revision}\nstate: published\n")
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
            let claim_event_result = Arc::new(Mutex::new(None));
            let provider = if mqtt_configured {
                let claim_event_result = Arc::clone(&claim_event_result);
                let claim_resource = resource.clone();
                let claim_owner = owner.clone();
                let stable_claim_id = claim_id.clone();
                let (_, published) = collect_coordination_gossip_window_with(
                    root,
                    &project_dir,
                    std::time::Duration::from_secs(contention_window_s),
                    project_configuration.overlay.ttl_s,
                    || {
                        let event = append_soft_claim_event(
                            &project_dir,
                            &claim_resource,
                            &claim_owner,
                            &stable_claim_id,
                            revision,
                            contention_window_s,
                            default_ttl_s,
                            coordination_now(),
                        );
                        let event = match event {
                            Ok(event) => event,
                            Err(error) => {
                                if let Ok(mut slot) = claim_event_result.lock() {
                                    *slot = Some(Err(error.to_string()));
                                }
                                return false;
                            }
                        };
                        if let Ok(mut slot) = claim_event_result.lock() {
                            *slot = Some(Ok(event.clone()));
                        } else {
                            return false;
                        }
                        publish_coordination_gossip(
                            root,
                            &project_dir,
                            "coordination.claim",
                            &event.event_id,
                            Some(&event.occurred_at),
                            CoordinationGossipFields {
                                resource: Some(claim_resource),
                                owner: Some(claim_owner),
                                claim_id: Some(stable_claim_id),
                                lease_ttl_s: Some(default_ttl_s),
                                expires_at: None,
                                operation_sequence: event
                                    .payload
                                    .get("operation_sequence")
                                    .and_then(Value::as_u64),
                            },
                        )
                    },
                );
                if published {
                    "mqtt"
                } else {
                    "git"
                }
            } else {
                "git"
            };
            match claim_event_result
                .lock()
                .map_err(|_| {
                    KanbusError::IssueOperation(
                        "coordination claim event result is unavailable".to_string(),
                    )
                })?
                .take()
            {
                Some(Ok(_)) => {}
                Some(Err(error)) => return Err(KanbusError::IssueOperation(error)),
                None => {
                    append_soft_claim_event(
                        &project_dir,
                        &resource,
                        &owner,
                        &claim_id,
                        revision,
                        contention_window_s,
                        default_ttl_s,
                        coordination_now(),
                    )?;
                }
            }
            let events = load_coordination_events(
                &project_dir,
                &resource,
                mqtt_configured,
                contention_window_s,
                project_configuration.overlay.ttl_s,
            )?;
            if mqtt_configured && resource.starts_with("router:issue:") {
                if let Err(error) = write_router_claim_observation(
                    &project_dir,
                    &resource,
                    &claim_id,
                    project_configuration.overlay.ttl_s,
                ) {
                    eprintln!("warning: router claim observation could not be recorded: {error}");
                }
            }
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
                json!({
                    "owner": owner,
                    "claim_id": claim_id,
                    "operation_sequence": observed_operation_sequence(&project_dir, &resource)?
                        .checked_add(1)
                        .ok_or_else(|| KanbusError::IssueOperation(
                            "coordination operation sequence overflow".to_string()
                        ))?,
                }),
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
                        operation_sequence: release_event
                            .payload
                            .get("operation_sequence")
                            .and_then(Value::as_u64),
                    },
                ) {
                "mqtt"
            } else {
                "git"
            };
            persist_router_coordination_event(&project_dir, &resource, &release_event)?;
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
        CoordinationOperation::PublishResult {
            resource,
            revision,
            artifact,
        } => {
            publish_coordination_result(&project_dir, &resource, revision, &artifact)?;
            Ok(published_result_output("git", &resource, revision))
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
    /// Publish an artifact reference for a logical task revision.
    PublishResult {
        /// Resource key for the logical task.
        resource: String,
        /// Positive logical revision to publish.
        revision: u64,
        /// Artifact reference produced by the worker.
        artifact: String,
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
        if !endpoint.is_empty() {
            match validate_http_endpoint(endpoint) {
                Ok(()) => {}
                Err(HttpEndpointError::Invalid) => errors.push(
                    "coordination.mutex_api.endpoint: must be an absolute http(s) URL".to_string(),
                ),
                Err(HttpEndpointError::Credentials) => errors.push(
                    "coordination.mutex_api.endpoint: must not include URL credentials".to_string(),
                ),
                Err(HttpEndpointError::Insecure) => errors.push(
                    "coordination.mutex_api.endpoint: must use HTTPS unless the host is loopback"
                        .to_string(),
                ),
            }
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

    #[test]
    fn router_claim_observation_snapshot_records_sorted_peer_claims() {
        let temp = tempfile::tempdir().expect("temporary project");
        let resource = "router:issue:kbs-observation";
        let now = format_time(Utc::now());
        for (message_id, event_id, claim_id) in [
            ("mqtt-own", "event-own", "claim-own"),
            ("mqtt-peer", "event-peer", "claim-peer"),
        ] {
            let mut envelope = gossip(
                message_id,
                "coordination.claim",
                event_id,
                &now,
                "worker",
                claim_id,
                Some(3600),
            );
            envelope.coordination.resource = Some(resource.to_string());
            envelope.coordination.expires_at = None;
            crate::overlay::write_coordination_overlay(temp.path(), &envelope, 3600)
                .expect("write MQTT claim overlay");
        }
        write_router_claim_observation(temp.path(), resource, "claim-own", 3600)
            .expect("write contention snapshot");

        let path = temp
            .path()
            .join(".overlay/coordination-observations")
            .join(sha256_hex(resource))
            .join(format!("{}.json", sha256_hex("claim-own")));
        let snapshot: Value =
            serde_json::from_slice(&fs::read(path).expect("read contention snapshot"))
                .expect("parse contention snapshot");
        assert_eq!(snapshot["resource"], resource);
        assert_eq!(snapshot["claim_id"], "claim-own");
        assert_eq!(snapshot["local_claim_id"], "claim-own");
        assert_eq!(
            snapshot["observed_claim_ids"],
            json!(["claim-own", "claim-peer"])
        );
        assert_eq!(snapshot["peer_claim_ids"], json!(["claim-peer"]));
        assert!(snapshot["observed_at"].as_str().is_some());
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
                operation_sequence: None,
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
        for invalid in ["0s", "00s", "01s", "0003m", "-1s", "1d", "1.5m", "s", "5"] {
            assert!(parse_duration_seconds(invalid).is_err(), "{invalid}");
        }
    }

    #[test]
    fn result_publication_reducer_uses_maximum_immutable_revision() {
        let first = record(
            "tts:voice-1",
            EventType::CoordinationResultPublished,
            "event-1",
            "2026-01-01T00:00:00Z",
            json!({"revision": 3, "artifact": "/tmp/render-r3.mp3"}),
        );
        let second = record(
            "tts:voice-1",
            EventType::CoordinationResultPublished,
            "event-2",
            "2026-01-01T00:01:00Z",
            json!({"revision": 5, "artifact": "/tmp/render-r5.mp3"}),
        );
        let invalid = record(
            "tts:voice-1",
            EventType::CoordinationResultPublished,
            "event-3",
            "2026-01-01T00:02:00Z",
            json!({"revision": 0, "artifact": "/tmp/invalid.mp3"}),
        );

        assert_eq!(
            reduce_published_revision(&[first, second, invalid]),
            Some(5)
        );
    }

    #[test]
    fn stale_result_publication_is_rejected_without_mutating_event_history() {
        let temp = tempfile::TempDir::new().expect("temp dir");
        let project_dir = temp.path().join("project");
        let first = EventRecord::new(
            "tts:voice-2",
            EventType::CoordinationResultPublished,
            "coordination",
            json!({"revision": 5, "artifact": "/tmp/render-r5.mp3"}),
            now_timestamp(),
        );
        let events_dir = events_dir_for_project(&project_dir);
        write_events_batch(&events_dir, &[first]).expect("write initial event");

        let error = publish_coordination_result(&project_dir, "tts:voice-2", 4, "/tmp/stale.mp3")
            .expect_err("older result must be rejected");

        assert_eq!(
            error.to_string(),
            "stale revision 4; published revision is 5"
        );
        assert_eq!(
            published_revision(&project_dir, "tts:voice-2").unwrap(),
            Some(5)
        );
        assert_eq!(fs::read_dir(events_dir).unwrap().count(), 1);
    }

    #[test]
    fn result_publication_accepts_newer_revision_and_records_immutable_event() {
        let temp = tempfile::TempDir::new().expect("temp dir");
        let project_dir = temp.path().join("project");
        let first = EventRecord::new(
            "tts:voice-3",
            EventType::CoordinationResultPublished,
            "coordination",
            json!({"revision": 2, "artifact": "/tmp/render-r2.mp3"}),
            now_timestamp(),
        );
        let events_dir = events_dir_for_project(&project_dir);
        write_events_batch(&events_dir, &[first]).expect("write initial event");

        publish_coordination_result(&project_dir, "tts:voice-3", 3, "/tmp/render-r3.mp3")
            .expect("publish newer revision");

        assert_eq!(
            published_revision(&project_dir, "tts:voice-3").unwrap(),
            Some(3)
        );
        assert_eq!(fs::read_dir(events_dir).unwrap().count(), 2);
    }

    #[test]
    fn identical_same_revision_publication_is_idempotent_and_different_artifact_is_rejected() {
        let temp = tempfile::TempDir::new().expect("temp dir");
        let project_dir = temp.path().join("project");
        let events_dir = events_dir_for_project(&project_dir);

        publish_coordination_result(&project_dir, "tts:voice-idempotent", 7, "/tmp/a.wav")
            .expect("first publication");
        publish_coordination_result(&project_dir, "tts:voice-idempotent", 7, "/tmp/a.wav")
            .expect("identical publication is idempotent");
        assert_eq!(fs::read_dir(&events_dir).unwrap().count(), 1);

        let error = publish_coordination_result(
            &project_dir,
            "tts:voice-idempotent",
            7,
            "/tmp/different.wav",
        )
        .expect_err("same revision cannot publish a different artifact");
        assert_eq!(
            error.to_string(),
            "revision 7 already published with a different artifact"
        );
        let path = fs::read_dir(&events_dir)
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        let event: EventRecord = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
        assert_eq!(event.payload["resource"], "tts:voice-idempotent");
        assert_eq!(event.payload["artifact"], "/tmp/a.wav");
        assert_ne!(event.actor_id, "coordination");
        assert_eq!(fs::read_dir(events_dir).unwrap().count(), 1);
    }

    #[test]
    fn publish_result_output_includes_provider_resource_revision_and_state() {
        assert_eq!(
            published_result_output("git", "tts:voice-1", 3),
            "provider: git\nresource: tts:voice-1\nrevision: 3\nstate: published\n"
        );
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
    fn concurrent_same_sequence_claims_keep_stable_arbitration() {
        let mut first = claim("claim-b", "worker-b", "z-event", "2026-01-01T00:00:00Z");
        first.payload["operation_sequence"] = json!(12);
        let mut second = claim("claim-a", "worker-a", "a-event", "2026-01-01T00:00:00Z");
        second.payload["operation_sequence"] = json!(12);
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 6).unwrap();

        for ordered in [[first.clone(), second.clone()], [second, first]] {
            let lease = reduce_coordination_events(&ordered, now);
            assert_eq!(lease.claim_id.as_deref(), Some("claim-a"));
            assert_eq!(lease.owner.as_deref(), Some("worker-a"));
        }
    }

    #[test]
    fn operation_sequence_replays_same_millisecond_claim_release_claim_causally() {
        let timestamp = "2026-01-01T00:00:00.000Z";
        let mut first = claim("claim-a", "worker-a", "z-claim-a", timestamp);
        first.payload["operation_sequence"] = json!(1);
        let release = record(
            "job:unit-test",
            EventType::CoordinationRelease,
            "a-release-a",
            timestamp,
            json!({"owner":"worker-a", "claim_id":"claim-a", "operation_sequence":2}),
        );
        let mut second = claim("claim-b", "worker-b", "m-claim-b", timestamp);
        second.payload["operation_sequence"] = json!(3);

        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 1).unwrap();
        let lease = reduce_coordination_events(&[second, release, first], now);

        assert_eq!(lease.owner.as_deref(), Some("worker-b"));
        assert_eq!(lease.claim_id.as_deref(), Some("claim-b"));
        assert_eq!(lease.operation_sequence, Some(3));
    }

    #[test]
    fn legacy_unsequenced_events_keep_timestamp_and_event_id_order() {
        let timestamp = "2026-01-01T00:00:00.000Z";
        let mut claim_event = claim("legacy-claim", "worker", "z-claim", timestamp);
        claim_event
            .payload
            .as_object_mut()
            .unwrap()
            .remove("operation_sequence");
        let release_event = record(
            "job:unit-test",
            EventType::CoordinationRelease,
            "a-release",
            timestamp,
            json!({"owner":"worker", "claim_id":"legacy-claim"}),
        );
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 1).unwrap();

        // The legacy release sorts before the claim by event ID, so it cannot
        // release a lease that has not yet been claimed.
        assert!(reduce_coordination_events(&[claim_event, release_event], now).is_active());
    }

    #[test]
    fn invalid_operation_sequences_are_ignored_and_not_used_for_allocation() {
        let temp = tempfile::TempDir::new().expect("temp dir");
        let project_dir = temp.path().join("project");
        let events_dir = events_dir_for_project(&project_dir);
        let mut valid = claim("valid", "worker-a", "event-valid", "2026-01-01T00:00:00Z");
        valid.payload["operation_sequence"] = json!(4);
        let invalid_values = [json!(0), json!(-2), json!(true), json!("5"), json!(1.5)];
        let invalid_events = invalid_values
            .into_iter()
            .enumerate()
            .map(|(index, value)| {
                let mut event = claim(
                    &format!("invalid-{index}"),
                    "worker-b",
                    &format!("event-invalid-{index}"),
                    "2026-01-01T00:00:00Z",
                );
                event.payload["operation_sequence"] = value;
                event
            })
            .collect::<Vec<_>>();
        let mut all_events = vec![valid.clone()];
        all_events.extend(invalid_events.clone());
        let now = Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 1).unwrap();
        let reduced = reduce_coordination_events(&all_events, now);
        assert_eq!(reduced.claim_id.as_deref(), Some("valid"));

        write_events_batch(&events_dir, &all_events).expect("write test events");
        assert_eq!(
            observed_operation_sequence(&project_dir, "job:unit-test").unwrap(),
            4
        );
        let next = append_event(
            &project_dir,
            "job:unit-test",
            "worker-c",
            EventType::CoordinationRelease,
            json!({"owner":"worker-c", "claim_id":"new"}),
        )
        .expect("append sequenced event");
        assert_eq!(next.payload["operation_sequence"], 5);
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
        let mut envelope = GossipEnvelope {
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
                operation_sequence: None,
            },
        };
        envelope.coordination.operation_sequence = Some(7);
        let invalid = GossipEnvelope {
            coordination: CoordinationGossipFields {
                operation_sequence: Some(0),
                ..envelope.coordination.clone()
            },
            ..envelope.clone()
        };
        assert!(coordination_gossip_event(invalid, 3).is_none());
        let event = coordination_gossip_event(envelope, 3).expect("valid claim message");
        assert_eq!(event.event_id, "event-1");
        assert_eq!(event.issue_id, "job:unit-test");
        assert_eq!(event_kind(&event), Some("claim"));
        assert_eq!(event.payload["contention_window_s"], 3);
        assert_eq!(event.payload["operation_sequence"], 7);
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
    fn mutex_api_endpoint_requires_tls_except_for_loopback_and_rejects_credentials() {
        let mut configuration = crate::config::default_project_configuration();
        configuration.coordination.mutex_api.endpoint =
            Some("http://mutex.example.test/api".to_string());
        assert_eq!(
            validate_coordination_configuration(&configuration),
            vec!["coordination.mutex_api.endpoint: must use HTTPS unless the host is loopback"]
        );

        for endpoint in ["http://localhost:8080/api", "http://127.0.0.1:8080/api"] {
            configuration.coordination.mutex_api.endpoint = Some(endpoint.to_string());
            assert!(validate_coordination_configuration(&configuration).is_empty());
        }

        configuration.coordination.mutex_api.endpoint =
            Some("https://user:secret@mutex.example.test".to_string());
        assert_eq!(
            validate_coordination_configuration(&configuration),
            vec!["coordination.mutex_api.endpoint: must not include URL credentials"]
        );
    }

    #[test]
    fn renewal_extension_targets_a_fixed_now_plus_ttl_horizon() {
        let now = parse_timestamp("2026-01-01T00:00:00.500Z").unwrap();
        let current = parse_timestamp("2026-01-01T00:04:00.500Z");
        assert_eq!(lease_renewal_extension_seconds(current, now, 300), 60);
        assert_eq!(
            lease_renewal_extension_seconds(parse_timestamp("2026-01-01T00:05:01Z"), now, 300),
            0
        );
        assert_eq!(lease_renewal_extension_seconds(None, now, 300), 0);
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
