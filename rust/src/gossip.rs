//! Realtime gossip transport and envelope helpers.

use chrono::Utc;
use rumqttc::{
    AsyncClient, Event, MqttOptions, Outgoing, Packet, QoS, SubscribeReasonCode, TlsConfiguration,
    Transport,
};
use serde::{Deserialize, Serialize};
#[cfg(unix)]
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
#[cfg(unix)]
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpStream, ToSocketAddrs};
#[cfg(unix)]
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};
use uuid::Uuid;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{get_configuration_path, resolve_labeled_projects};
use crate::models::{IssueData, OverlayConfig, ProjectConfiguration, RealtimeConfig};
use crate::overlay::{write_overlay_issue, write_tombstone, OverlayTombstone};

/// Realtime gossip envelope.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GossipEnvelope {
    pub id: String,
    pub ts: String,
    pub project: String,
    #[serde(rename = "type")]
    pub event_type: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub issue_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub event_id: Option<String>,
    pub producer_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub origin_cluster_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub issue: Option<IssueData>,
    #[serde(flatten)]
    pub coordination: CoordinationGossipFields,
}

/// Optional top-level fields used by coordination gossip envelopes.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CoordinationGossipFields {
    /// Resource identifier carried by CLAIM, LEASE, and RELEASE messages.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resource: Option<String>,
    /// Worker that issued the coordination message.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    /// Stable claim identifier associated with the message.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub claim_id: Option<String>,
    /// Lease TTL in seconds, present on CLAIM and LEASE messages.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lease_ttl_s: Option<u64>,
    /// Lease expiry timestamp, present on LEASE messages.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_at: Option<String>,
    /// Optional logical order for coordination event replay. Missing values are
    /// legacy sequence zero and remain accepted for existing envelopes.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub operation_sequence: Option<u64>,
}

#[derive(Debug, Clone)]
struct BrokerEndpoint {
    scheme: String,
    host: String,
    port: u16,
}

#[derive(Debug)]
pub struct BrokerStartup {
    pub endpoint: String,
    pub process: Child,
}

#[derive(Debug, Serialize, Deserialize)]
struct BrokerMetadata {
    kind: String,
    endpoint: String,
    pid: u32,
    started_by: String,
    started_at: String,
    log_path: String,
    conf_path: String,
    ttl_s: u64,
}

static PRODUCER_ID: OnceLock<String> = OnceLock::new();

fn producer_id() -> String {
    PRODUCER_ID
        .get_or_init(|| Uuid::new_v4().to_string())
        .clone()
}

#[derive(Debug)]
pub struct DedupeSet {
    ttl: Duration,
    entries: HashMap<String, Instant>,
}

impl DedupeSet {
    pub fn new(ttl: Duration) -> Self {
        Self {
            ttl,
            entries: HashMap::new(),
        }
    }

    pub fn seen(&mut self, key: &str) -> bool {
        let now = Instant::now();
        self.prune(now);
        if self.entries.contains_key(key) {
            return true;
        }
        self.entries.insert(key.to_string(), now);
        false
    }

    fn prune(&mut self, now: Instant) {
        let ttl = self.ttl;
        self.entries.retain(|_, ts| now.duration_since(*ts) <= ttl);
    }
}

/// Return true when a receiver should process the envelope under REALTIME rules.
pub fn should_accept_gossip(
    envelope: &GossipEnvelope,
    local_producer_id: &str,
    dedupe: &mut DedupeSet,
) -> bool {
    let duplicate = dedupe.seen(&envelope.id);
    !duplicate && envelope.producer_id != local_producer_id
}

#[cfg(test)]
mod dedupe_tests {
    use super::DedupeSet;
    use std::time::Duration;

    #[test]
    fn dedupe_set_tracks_seen_keys_and_prunes() {
        let mut set = DedupeSet::new(Duration::from_millis(5));
        assert!(!set.seen("alpha"));
        assert!(set.seen("alpha"), "second sighting should be true");
        std::thread::sleep(Duration::from_millis(6));
        assert!(
            !set.seen("alpha"),
            "entry should expire after ttl and be inserted again"
        );
    }
}

/// Publish a gossip envelope for an issue mutation.
pub fn publish_issue_mutation(
    root: &Path,
    project_dir: &Path,
    issue: &IssueData,
    event_id: Option<String>,
    event_type: &str,
) {
    let config_path = match get_configuration_path(root) {
        Ok(path) => path,
        Err(_) => return,
    };
    let configuration = match load_project_configuration(&config_path) {
        Ok(config) => config,
        Err(_) => return,
    };
    if configuration.realtime.broker == "off" {
        return;
    }
    let project_label = resolve_project_label(root, project_dir, &configuration);
    let Some(project_label) = project_label else {
        return;
    };
    let envelope = GossipEnvelope {
        id: Uuid::new_v4().to_string(),
        ts: now_iso(),
        project: project_label.clone(),
        event_type: event_type.to_string(),
        issue_id: Some(issue.identifier.clone()),
        event_id,
        producer_id: producer_id(),
        origin_cluster_id: None,
        issue: Some(issue.clone()),
        coordination: CoordinationGossipFields::default(),
    };
    let topic = project_topic(&configuration.realtime, &project_label);
    if let Err(error) = publish_envelope(root, &configuration, &topic, &envelope) {
        eprintln!("warning: realtime publish failed: {error}");
    }
}

/// Publish a gossip envelope for an issue deletion.
pub fn publish_issue_deleted(
    root: &Path,
    project_dir: &Path,
    issue_id: &str,
    event_id: Option<String>,
) {
    let config_path = match get_configuration_path(root) {
        Ok(path) => path,
        Err(_) => return,
    };
    let configuration = match load_project_configuration(&config_path) {
        Ok(config) => config,
        Err(_) => return,
    };
    if configuration.realtime.broker == "off" {
        return;
    }
    let project_label = resolve_project_label(root, project_dir, &configuration);
    let Some(project_label) = project_label else {
        return;
    };
    let envelope = GossipEnvelope {
        id: Uuid::new_v4().to_string(),
        ts: now_iso(),
        project: project_label.clone(),
        event_type: "issue.deleted".to_string(),
        issue_id: Some(issue_id.to_string()),
        event_id,
        producer_id: producer_id(),
        origin_cluster_id: None,
        issue: None,
        coordination: CoordinationGossipFields::default(),
    };
    let topic = project_topic(&configuration.realtime, &project_label);
    if let Err(error) = publish_envelope(root, &configuration, &topic, &envelope) {
        eprintln!("warning: realtime publish failed: {error}");
    }
}

/// Publish a coordination envelope through MQTT only.
///
/// Coordination gossip is an optional fast path. A missing or unreachable
/// broker returns `false` so the caller can continue with Git history.
pub fn publish_coordination_gossip(
    root: &Path,
    project_dir: &Path,
    event_type: &str,
    event_id: &str,
    message_ts: Option<&str>,
    fields: CoordinationGossipFields,
) -> bool {
    let Ok(config_path) = get_configuration_path(root) else {
        return false;
    };
    let Ok(configuration) = load_project_configuration(&config_path) else {
        return false;
    };
    if !coordination_mqtt_available(&configuration.realtime) {
        return false;
    }
    let Some(project_label) = resolve_project_label(root, project_dir, &configuration) else {
        return false;
    };
    let Ok(endpoint) = resolve_broker_endpoint(&configuration.realtime.broker) else {
        return false;
    };
    // MQTT coordination must never silently cross over to the local UDS bus.
    if !broker_is_reachable_for_realtime(&endpoint, &configuration.realtime) {
        return false;
    }

    let mut envelope =
        build_coordination_gossip_envelope(&project_label, event_type, event_id, fields);
    if let Some(message_ts) = message_ts {
        envelope.ts = message_ts.to_string();
    }
    if !coordination_gossip_envelope_is_valid(&envelope) {
        return false;
    }
    let topic = project_topic(&configuration.realtime, &project_label);
    if let Err(error) = publish_mqtt(&endpoint, &topic, &envelope, &configuration.realtime) {
        let effective_endpoint = effective_broker_endpoint(&endpoint, &configuration.realtime);
        eprintln!(
            "warning: coordination MQTT publish failed (type={event_type}, endpoint={}:{}, topic={topic}): {error}",
            effective_endpoint.host, effective_endpoint.port
        );
        return false;
    }
    let _ = crate::overlay::write_coordination_overlay(
        project_dir,
        &envelope,
        configuration.overlay.ttl_s,
    );
    true
}

/// Build a coordination gossip envelope using the common REALTIME fields.
pub fn build_coordination_gossip_envelope(
    project: &str,
    event_type: &str,
    event_id: &str,
    fields: CoordinationGossipFields,
) -> GossipEnvelope {
    GossipEnvelope {
        id: Uuid::new_v4().to_string(),
        ts: now_iso(),
        project: project.to_string(),
        event_type: event_type.to_string(),
        issue_id: None,
        event_id: Some(event_id.to_string()),
        producer_id: producer_id(),
        origin_cluster_id: None,
        issue: None,
        coordination: fields,
    }
}

/// Validate the per-type required fields for coordination gossip messages.
pub fn coordination_gossip_envelope_is_valid(envelope: &GossipEnvelope) -> bool {
    let fields = &envelope.coordination;
    if fields
        .operation_sequence
        .is_some_and(|sequence| sequence == 0)
    {
        return false;
    }
    let common_fields_present = envelope.event_id.as_ref().is_some_and(|id| !id.is_empty())
        && fields
            .resource
            .as_ref()
            .is_some_and(|value| !value.is_empty())
        && fields.owner.as_ref().is_some_and(|value| !value.is_empty())
        && fields
            .claim_id
            .as_ref()
            .is_some_and(|value| !value.is_empty());
    if !common_fields_present {
        return false;
    }
    match envelope.event_type.as_str() {
        "coordination.claim" => {
            fields.lease_ttl_s.is_some_and(|ttl| ttl > 0) && fields.expires_at.is_none()
        }
        "coordination.lease" => {
            fields.lease_ttl_s.is_some_and(|ttl| ttl > 0)
                && fields
                    .expires_at
                    .as_deref()
                    .and_then(parse_broker_timestamp)
                    .is_some()
        }
        "coordination.release" => fields.lease_ttl_s.is_none() && fields.expires_at.is_none(),
        _ => false,
    }
}

fn parse_broker_timestamp(value: &str) -> Option<chrono::DateTime<chrono::Utc>> {
    chrono::DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|timestamp| timestamp.with_timezone(&chrono::Utc))
}

/// Check whether the configured MQTT endpoint is reachable for coordination.
pub fn coordination_mqtt_available(realtime: &RealtimeConfig) -> bool {
    if realtime.broker == "off"
        || !matches!(realtime.transport.as_str(), "auto" | "mqtt")
        || (realtime.transport == "auto" && uds_socket_path(Some(realtime)).exists())
    {
        return false;
    }
    resolve_broker_endpoint(&realtime.broker)
        .is_ok_and(|endpoint| broker_is_reachable_for_realtime(&endpoint, realtime))
}

/// Listen for peer coordination envelopes for a bounded contention window and
/// persist valid messages into the project's coordination overlay.
///
/// This is intentionally a short-lived subscriber used by claim reconciliation,
/// not a replacement for the long-running gossip watcher. MQTT remains an
/// optional fast path: connection/subscription failures yield zero messages and
/// the caller continues with durable Git history.
pub fn collect_coordination_gossip_window(
    root: &Path,
    project_dir: &Path,
    budget: Duration,
    overlay_ttl_s: u64,
) -> usize {
    collect_coordination_gossip_window_with(root, project_dir, budget, overlay_ttl_s, || false).0
}

/// Variant of [`collect_coordination_gossip_window`] that invokes a local
/// publish callback only after the broker confirms the subscription. This
/// closes the publish-before-subscribe race for claim contention.
pub fn collect_coordination_gossip_window_with<F>(
    root: &Path,
    project_dir: &Path,
    budget: Duration,
    overlay_ttl_s: u64,
    on_subscribed: F,
) -> (usize, bool)
where
    F: FnOnce() -> bool + Send,
{
    if budget.is_zero() {
        return (0, false);
    }
    let Ok(config_path) = get_configuration_path(root) else {
        return (0, false);
    };
    let Ok(configuration) = load_project_configuration(&config_path) else {
        return (0, false);
    };
    if configuration.realtime.broker == "off"
        || !matches!(configuration.realtime.transport.as_str(), "auto" | "mqtt")
        || (configuration.realtime.transport == "auto"
            && uds_socket_path(Some(&configuration.realtime)).exists())
    {
        return (0, false);
    }
    let Some(project_label) = resolve_project_label(root, project_dir, &configuration) else {
        return (0, false);
    };
    let Ok(endpoint) = resolve_broker_endpoint(&configuration.realtime.broker) else {
        return (0, false);
    };
    let topic = project_topic(&configuration.realtime, &project_label);
    let options = mqtt_options(&endpoint, &configuration.realtime);
    let (client, mut eventloop) = AsyncClient::new(options, 16);
    let mut network_options = eventloop.network_options();
    network_options.set_connection_timeout(15);
    eventloop.set_network_options(network_options);
    let (callback_request_tx, callback_request_rx) = mpsc::channel();
    let (received, published) = std::thread::scope(|scope| {
        let worker = scope.spawn(move || {
            let Ok(runtime) = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
            else {
                return Vec::new();
            };
            runtime.block_on(async move {
                if let Err(error) = client.subscribe(topic.clone(), QoS::AtMostOnce).await {
                    eprintln!("warning: coordination MQTT subscribe enqueue failed (topic={topic}): {error}");
                    return Vec::new();
                }
                let setup_deadline = Instant::now() + Duration::from_secs(16);
                let mut contention_deadline = None;
                let mut envelopes = Vec::new();
                let mut publish_requested = false;
                loop {
                    let deadline = contention_deadline.unwrap_or(setup_deadline);
                    if Instant::now() >= deadline {
                        if contention_deadline.is_none() {
                            eprintln!("warning: coordination MQTT subscription timed out before claim publish (topic={topic})");
                        }
                        break;
                    }
                    let remaining = deadline.saturating_duration_since(Instant::now());
                    match tokio::time::timeout(remaining, eventloop.poll()).await {
                        Ok(Ok(Event::Incoming(Packet::SubAck(suback)))) => {
                            if !subscription_ack_granted(&suback) {
                                eprintln!("warning: coordination MQTT subscription was denied by broker (topic={topic})");
                                break;
                            }
                            if !publish_requested {
                                let (response_tx, response_rx) = mpsc::sync_channel(1);
                                publish_requested = callback_request_tx.send(response_tx).is_ok();
                                if publish_requested {
                                    let callback_published = response_rx.recv().unwrap_or(false);
                                    if !callback_published {
                                        break;
                                    }
                                    contention_deadline = Some(Instant::now() + budget);
                                }
                            }
                        }
                        Ok(Ok(Event::Incoming(Packet::Publish(publish)))) => {
                            if let Ok(envelope) =
                                serde_json::from_slice::<GossipEnvelope>(&publish.payload)
                            {
                                if envelope.project == project_label
                                    && coordination_gossip_envelope_is_valid(&envelope)
                                {
                                    envelopes.push(envelope);
                                }
                            }
                        }
                        Ok(Ok(_)) => {}
                        Ok(Err(error)) => {
                            eprintln!("warning: coordination MQTT subscription failed (topic={topic}): {error}");
                            break;
                        }
                        Err(_) => {
                            if contention_deadline.is_none() {
                                eprintln!("warning: coordination MQTT subscription timed out before claim publish (topic={topic})");
                            }
                            break;
                        }
                    }
                }
                envelopes
            })
        });
        let published = if let Ok(response_tx) = callback_request_rx.recv() {
            let published = std::thread::scope(|callback_scope| {
                callback_scope.spawn(on_subscribed).join().unwrap_or(false)
            });
            let _ = response_tx.send(published);
            published
        } else {
            false
        };
        (worker.join().unwrap_or_default(), published)
    });

    let mut accepted = 0;
    for envelope in received {
        if crate::overlay::write_coordination_overlay(project_dir, &envelope, overlay_ttl_s).is_ok()
        {
            accepted += 1;
        }
    }
    (accepted, published)
}

/// Wait for one valid peer coordination message, persisting it to the local
/// coordination overlay before returning. Connection, subscription, and
/// timeout failures are an optional-fast-path miss; durable Git reconciliation
/// remains the caller's fallback.
pub fn wait_for_coordination_gossip_notification(
    root: &Path,
    project_dir: &Path,
    budget: Duration,
    overlay_ttl_s: u64,
) -> bool {
    if budget.is_zero() {
        return false;
    }
    let Ok(config_path) = get_configuration_path(root) else {
        return false;
    };
    let Ok(configuration) = load_project_configuration(&config_path) else {
        return false;
    };
    let realtime = configuration.realtime.clone();
    if realtime.broker == "off"
        || !matches!(realtime.transport.as_str(), "auto" | "mqtt")
        || (realtime.transport == "auto" && uds_socket_path(Some(&realtime)).exists())
    {
        return false;
    }
    let Some(project_label) = resolve_project_label(root, project_dir, &configuration) else {
        return false;
    };
    let Ok(endpoint) = resolve_broker_endpoint(&realtime.broker) else {
        return false;
    };
    let topic = project_topic(&realtime, &project_label);
    let options = mqtt_options(&endpoint, &realtime);
    let ttl = overlay_ttl_s;
    let project_directory = project_dir.to_path_buf();
    std::thread::spawn(move || {
        let Ok(runtime) = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
        else {
            return false;
        };
        runtime.block_on(async move {
            let (client, mut eventloop) = AsyncClient::new(options, 16);
            if client.subscribe(topic, QoS::AtMostOnce).await.is_err() {
                return false;
            }
            let deadline = Instant::now() + budget;
            let mut subscribed = false;
            while Instant::now() < deadline {
                let remaining = deadline.saturating_duration_since(Instant::now());
                match tokio::time::timeout(remaining, eventloop.poll()).await {
                    Ok(Ok(Event::Incoming(Packet::SubAck(suback)))) => {
                        if !subscription_ack_granted(&suback) {
                            return false;
                        }
                        subscribed = true;
                    }
                    Ok(Ok(Event::Incoming(Packet::Publish(publish)))) => {
                        if !subscribed {
                            continue;
                        }
                        let Ok(envelope) =
                            serde_json::from_slice::<GossipEnvelope>(&publish.payload)
                        else {
                            continue;
                        };
                        if envelope.project != project_label
                            || envelope.producer_id == producer_id()
                            || !coordination_gossip_envelope_is_valid(&envelope)
                        {
                            continue;
                        }
                        return crate::overlay::write_coordination_overlay(
                            &project_directory,
                            &envelope,
                            ttl,
                        )
                        .is_ok();
                    }
                    Ok(Ok(_)) => {}
                    Ok(Err(_)) | Err(_) => return false,
                }
            }
            false
        })
    })
    .join()
    .unwrap_or(false)
}

/// Subscribe to gossip notifications and update overlays.
pub fn run_gossip_watch(
    root: &Path,
    project_filter: Option<String>,
    transport_override: Option<String>,
    broker_override: Option<String>,
    autostart_override: Option<bool>,
    keepalive_override: Option<bool>,
    print_envelopes: bool,
) -> Result<(), KanbusError> {
    run_gossip_consumer(
        root,
        GossipConsumerOptions {
            project_filter,
            transport_override,
            broker_override,
            autostart_override,
            keepalive_override,
            print_envelopes,
            on_envelope: None,
            autostart_local_uds: false,
            broker_off_is_error: true,
        },
    )
}

/// Subscribe to gossip notifications for console bridging.
///
/// This consumer path applies overlay updates and forwards accepted envelopes to
/// the provided callback so the console can broadcast immediate SSE updates.
pub fn run_gossip_bridge(
    root: &Path,
    on_envelope: Arc<dyn Fn(GossipEnvelope) + Send + Sync>,
) -> Result<(), KanbusError> {
    run_gossip_consumer(
        root,
        GossipConsumerOptions {
            project_filter: None,
            transport_override: None,
            broker_override: None,
            autostart_override: None,
            keepalive_override: None,
            print_envelopes: false,
            on_envelope: Some(on_envelope),
            autostart_local_uds: true,
            broker_off_is_error: false,
        },
    )
}

struct GossipConsumerOptions {
    project_filter: Option<String>,
    transport_override: Option<String>,
    broker_override: Option<String>,
    autostart_override: Option<bool>,
    keepalive_override: Option<bool>,
    print_envelopes: bool,
    on_envelope: Option<Arc<dyn Fn(GossipEnvelope) + Send + Sync>>,
    autostart_local_uds: bool,
    broker_off_is_error: bool,
}

/// Persist an accepted gossip envelope in the appropriate local cache.
///
/// Coordination records are intentionally independent of the optional issue
/// overlay: workers must see speculative lease candidates even when a project
/// disables cached issue mutations.
fn persist_gossip_overlay(
    project_dir: &Path,
    envelope: &GossipEnvelope,
    overlay_config: &OverlayConfig,
) {
    if matches!(
        envelope.event_type.as_str(),
        "coordination.claim" | "coordination.lease" | "coordination.release"
    ) {
        let _ =
            crate::overlay::write_coordination_overlay(project_dir, envelope, overlay_config.ttl_s);
    } else if overlay_config.enabled {
        if envelope.event_type == "issue.mutated" {
            if let Some(issue) = envelope.issue.as_ref() {
                let _ = write_overlay_issue(
                    project_dir,
                    issue,
                    &envelope.ts,
                    envelope.event_id.clone(),
                );
            }
        } else if envelope.event_type == "issue.deleted" {
            if let Some(issue_id) = envelope.issue_id.clone() {
                let tombstone = OverlayTombstone {
                    op: "delete".to_string(),
                    project: envelope.project.clone(),
                    id: issue_id,
                    event_id: envelope.event_id.clone(),
                    ts: envelope.ts.clone(),
                    ttl_s: overlay_config.ttl_s,
                };
                let _ = write_tombstone(project_dir, &tombstone);
            }
        }
    }
}

fn run_gossip_consumer(root: &Path, options: GossipConsumerOptions) -> Result<(), KanbusError> {
    let configuration = load_project_configuration(&get_configuration_path(root)?)?;
    let realtime = &configuration.realtime;
    let transport = options
        .transport_override
        .unwrap_or_else(|| realtime.transport.clone());
    let broker = options
        .broker_override
        .unwrap_or_else(|| realtime.broker.clone());
    let autostart = options.autostart_override.unwrap_or(realtime.autostart);
    let keepalive = options.keepalive_override.unwrap_or(realtime.keepalive);

    let mut labeled = resolve_labeled_projects(root)?;
    if let Some(filter) = options.project_filter.as_deref() {
        labeled.retain(|project| project.label == filter);
        if labeled.is_empty() {
            return Err(KanbusError::IssueOperation(format!(
                "unknown project label: {filter}"
            )));
        }
    }
    let mut project_map = HashMap::new();
    for project in &labeled {
        project_map.insert(project.label.clone(), project.project_dir.clone());
    }
    let topics: Vec<String> = labeled
        .iter()
        .map(|project| project_topic(realtime, &project.label))
        .collect();

    let dedupe = Arc::new(Mutex::new(DedupeSet::new(Duration::from_secs(3600))));
    let local_producer = producer_id();
    let overlay_config = configuration.overlay.clone();
    let on_envelope_handler = options.on_envelope.clone();
    let handler = Arc::new(move |envelope: GossipEnvelope| {
        if envelope.event_type.starts_with("coordination.")
            && !coordination_gossip_envelope_is_valid(&envelope)
        {
            return;
        }
        if let Ok(mut guard) = dedupe.lock() {
            if !should_accept_gossip(&envelope, &local_producer, &mut guard) {
                return;
            }
        }
        let project_dir = match project_map.get(&envelope.project) {
            Some(path) => path,
            None => return,
        };
        if options.print_envelopes {
            if let Ok(line) = serde_json::to_string(&envelope) {
                println!("{line}");
            }
        }

        persist_gossip_overlay(project_dir, &envelope, &overlay_config);

        if let Some(callback) = on_envelope_handler.as_ref() {
            callback(envelope);
        }
    });

    let socket_path = uds_socket_path(Some(realtime));
    let mut use_uds =
        cfg!(unix) && (transport == "uds" || (transport == "auto" && socket_path.exists()));
    if cfg!(unix) && options.autostart_local_uds && (transport == "uds" || transport == "auto") {
        ensure_local_uds_broker(realtime)?;
        use_uds = true;
    }

    let dual_transport_local_fallback =
        cfg!(unix) && options.autostart_local_uds && transport == "mqtt";
    if dual_transport_local_fallback {
        ensure_local_uds_broker(realtime)?;
        let topics_for_mqtt = topics.clone();
        let handler_for_mqtt = Arc::clone(&handler);
        let realtime_for_mqtt = realtime.clone();
        let broker_for_mqtt = broker.clone();
        let autostart_for_mqtt = autostart;
        let keepalive_for_mqtt = keepalive;
        thread::spawn(move || {
            run_mqtt_subscription_resilient(
                &broker_for_mqtt,
                &realtime_for_mqtt,
                &topics_for_mqtt,
                handler_for_mqtt,
                autostart_for_mqtt,
                keepalive_for_mqtt,
            );
        });
        run_uds_subscription(realtime, &topics, handler)?;
        return Ok(());
    }

    if use_uds {
        run_uds_subscription(realtime, &topics, handler)?;
        return Ok(());
    }

    if broker == "off" {
        if !options.broker_off_is_error {
            return Ok(());
        }
        return Err(KanbusError::IssueOperation(
            "realtime broker is disabled".to_string(),
        ));
    }

    let mut endpoint = resolve_broker_endpoint(&broker)?;
    let mut broker_process: Option<Child> = None;
    if !broker_is_reachable_for_realtime(&endpoint, realtime) {
        if broker == "auto" {
            endpoint = parse_broker_url("mqtt://127.0.0.1:1883")?;
        }
        if !autostart {
            return Err(KanbusError::IssueOperation(
                "broker not reachable and autostart disabled".to_string(),
            ));
        }
        let startup = ensure_mosquitto(&endpoint)?;
        let Some(startup) = startup else {
            maybe_warn_mosquitto_missing();
            return Ok(());
        };
        endpoint = parse_broker_url(&startup.endpoint)?;
        broker_process = Some(startup.process);
    }

    run_mqtt_subscription(&endpoint, &topics, handler, realtime)?;
    if let Some(mut process) = broker_process {
        if !keepalive {
            let _ = process.kill();
        }
    }
    Ok(())
}

fn run_mqtt_subscription_resilient(
    broker: &str,
    realtime: &RealtimeConfig,
    topics: &[String],
    handler: Arc<dyn Fn(GossipEnvelope) + Send + Sync>,
    autostart: bool,
    keepalive: bool,
) {
    loop {
        let mut endpoint = match resolve_broker_endpoint(broker) {
            Ok(endpoint) => endpoint,
            Err(error) => {
                eprintln!("warning: realtime mqtt endpoint resolve failed: {error}");
                thread::sleep(Duration::from_secs(2));
                continue;
            }
        };
        let mut broker_process: Option<Child> = None;
        if !broker_is_reachable_for_realtime(&endpoint, realtime) {
            if broker == "auto" {
                match parse_broker_url("mqtt://127.0.0.1:1883") {
                    Ok(parsed) => endpoint = parsed,
                    Err(error) => {
                        eprintln!("warning: realtime mqtt auto broker parse failed: {error}");
                        thread::sleep(Duration::from_secs(2));
                        continue;
                    }
                }
            }
            if !autostart {
                thread::sleep(Duration::from_secs(2));
                continue;
            }
            match ensure_mosquitto(&endpoint) {
                Ok(Some(startup)) => {
                    match parse_broker_url(&startup.endpoint) {
                        Ok(parsed) => endpoint = parsed,
                        Err(error) => {
                            eprintln!(
                                "warning: realtime mqtt startup endpoint parse failed: {error}"
                            );
                            thread::sleep(Duration::from_secs(2));
                            continue;
                        }
                    }
                    broker_process = Some(startup.process);
                }
                Ok(None) => {
                    maybe_warn_mosquitto_missing();
                    thread::sleep(Duration::from_secs(2));
                    continue;
                }
                Err(error) => {
                    eprintln!("warning: realtime mqtt autostart failed: {error}");
                    thread::sleep(Duration::from_secs(2));
                    continue;
                }
            }
        }

        if let Err(error) = run_mqtt_subscription(&endpoint, topics, Arc::clone(&handler), realtime)
        {
            eprintln!("warning: realtime mqtt subscription dropped: {error}");
        }
        if let Some(mut process) = broker_process {
            if !keepalive {
                let _ = process.kill();
            }
        }
        thread::sleep(Duration::from_secs(2));
    }
}

#[cfg(unix)]
fn ensure_local_uds_broker(realtime: &RealtimeConfig) -> Result<(), KanbusError> {
    let socket_path = uds_socket_path(Some(realtime));
    if socket_path.exists() {
        match UnixStream::connect(&socket_path) {
            Ok(_) => return Ok(()),
            Err(_) => {
                fs::remove_file(&socket_path)
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
            }
        }
    }

    let broker_socket = socket_path.clone();
    thread::spawn(move || {
        if let Err(error) = run_uds_broker(&broker_socket) {
            eprintln!(
                "warning: failed to run local UDS broker at {}: {}",
                broker_socket.display(),
                error
            );
        }
    });

    for _ in 0..20 {
        if socket_path.exists() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(50));
    }

    Err(KanbusError::IssueOperation(format!(
        "failed to start local UDS broker at {}",
        socket_path.display()
    )))
}

#[cfg(not(unix))]
fn ensure_local_uds_broker(_realtime: &RealtimeConfig) -> Result<(), KanbusError> {
    Ok(())
}

/// Run a UDS gossip broker.
#[cfg(unix)]
pub fn run_gossip_broker(root: &Path, socket_override: Option<PathBuf>) -> Result<(), KanbusError> {
    let socket_path = match socket_override {
        Some(path) => path,
        None => {
            let configuration = load_project_configuration(&get_configuration_path(root)?)?;
            uds_socket_path(Some(&configuration.realtime))
        }
    };
    run_uds_broker(&socket_path)
}

#[cfg(not(unix))]
pub fn run_gossip_broker(
    _root: &Path,
    _socket_override: Option<PathBuf>,
) -> Result<(), KanbusError> {
    Err(KanbusError::IssueOperation(
        "unix domain socket gossip broker is not supported on this platform".to_string(),
    ))
}

#[cfg(unix)]
fn run_uds_broker(socket_path: &Path) -> Result<(), KanbusError> {
    if socket_path.exists() {
        let _ = fs::remove_file(socket_path);
    }
    if let Some(parent) = socket_path.parent() {
        fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    let listener =
        UnixListener::bind(socket_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let subscribers: Arc<Mutex<Vec<Subscriber>>> = Arc::new(Mutex::new(Vec::new()));
    for stream in listener.incoming() {
        let stream = match stream {
            Ok(stream) => stream,
            Err(_) => continue,
        };
        let subscribers = Arc::clone(&subscribers);
        thread::spawn(move || handle_uds_connection(stream, subscribers));
    }
    Ok(())
}

#[cfg(unix)]
#[derive(Clone)]
struct Subscriber {
    topic: String,
    stream: Arc<Mutex<UnixStream>>,
}

#[cfg(unix)]
fn handle_uds_connection(stream: UnixStream, subscribers: Arc<Mutex<Vec<Subscriber>>>) {
    let Ok(read_stream) = stream.try_clone() else {
        return;
    };
    let reader = BufReader::new(read_stream);
    for line in reader.lines().map_while(Result::ok) {
        if line.trim().is_empty() {
            continue;
        }
        let payload: Value = match serde_json::from_str(&line) {
            Ok(value) => value,
            Err(_) => continue,
        };
        let op = payload.get("op").and_then(|v| v.as_str()).unwrap_or("");
        if op == "sub" {
            if let Some(topic) = payload.get("topic").and_then(|v| v.as_str()) {
                let Ok(write_stream) = stream.try_clone() else {
                    continue;
                };
                let subscriber = Subscriber {
                    topic: topic.to_string(),
                    stream: Arc::new(Mutex::new(write_stream)),
                };
                if let Ok(mut guard) = subscribers.lock() {
                    guard.push(subscriber);
                }
            }
        } else if op == "pub" {
            broadcast_payload(&payload, &subscribers);
        }
    }
}

#[cfg(unix)]
fn broadcast_payload(payload: &Value, subscribers: &Arc<Mutex<Vec<Subscriber>>>) {
    let Some(topic) = payload.get("topic").and_then(|v| v.as_str()) else {
        return;
    };
    let message = serde_json::json!({"topic": topic, "msg": payload.get("msg")});
    let payload_line = match serde_json::to_string(&message) {
        Ok(text) => text + "\n",
        Err(_) => return,
    };

    let current = match subscribers.lock() {
        Ok(guard) => guard.clone(),
        Err(_) => return,
    };
    let mut remaining = Vec::new();
    for subscriber in current {
        if subscriber.topic != topic {
            remaining.push(subscriber);
            continue;
        }
        let mut ok = false;
        if let Ok(mut stream) = subscriber.stream.lock() {
            if stream.write_all(payload_line.as_bytes()).is_ok() {
                ok = true;
            }
        }
        if ok {
            remaining.push(subscriber);
        }
    }
    if let Ok(mut guard) = subscribers.lock() {
        *guard = remaining;
    }
}

#[cfg(unix)]
fn run_uds_subscription(
    realtime: &RealtimeConfig,
    topics: &[String],
    handler: Arc<dyn Fn(GossipEnvelope) + Send + Sync>,
) -> Result<(), KanbusError> {
    let socket_path = uds_socket_path(Some(realtime));
    let mut stream =
        UnixStream::connect(&socket_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    for topic in topics {
        let payload = serde_json::json!({"op": "sub", "topic": topic});
        let line = serde_json::to_string(&payload)
            .map_err(|error| KanbusError::Io(error.to_string()))?
            + "\n";
        stream
            .write_all(line.as_bytes())
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    let reader = BufReader::new(stream);
    for line in reader.lines().map_while(Result::ok) {
        if line.trim().is_empty() {
            continue;
        }
        let payload: Value = match serde_json::from_str(&line) {
            Ok(value) => value,
            Err(_) => continue,
        };
        let Some(msg) = payload.get("msg") else {
            continue;
        };
        let envelope: GossipEnvelope = match serde_json::from_value(msg.clone()) {
            Ok(env) => env,
            Err(_) => continue,
        };
        handler(envelope);
    }
    Ok(())
}

#[cfg(not(unix))]
fn run_uds_subscription(
    _realtime: &RealtimeConfig,
    _topics: &[String],
    _handler: Arc<dyn Fn(GossipEnvelope) + Send + Sync>,
) -> Result<(), KanbusError> {
    Err(KanbusError::IssueOperation(
        "unix domain socket realtime is not supported on this platform".to_string(),
    ))
}

fn publish_envelope(
    _root: &Path,
    configuration: &ProjectConfiguration,
    topic: &str,
    envelope: &GossipEnvelope,
) -> Result<(), KanbusError> {
    publish_with_transport(
        topic,
        envelope,
        &configuration.realtime,
        &configuration.realtime.transport,
        &configuration.realtime.broker,
        configuration.realtime.autostart,
        configuration.realtime.keepalive,
    )
}

fn publish_with_transport(
    topic: &str,
    envelope: &GossipEnvelope,
    realtime: &RealtimeConfig,
    transport: &str,
    broker: &str,
    autostart: bool,
    keepalive: bool,
) -> Result<(), KanbusError> {
    if cfg!(unix)
        && (transport == "uds" || (transport == "auto" && uds_socket_path(Some(realtime)).exists()))
    {
        let _ = publish_uds(topic, envelope, realtime);
        return Ok(());
    }
    if broker == "off" {
        if cfg!(unix) {
            let _ = publish_uds_if_available(topic, envelope, realtime);
        }
        return Ok(());
    }
    let mut endpoint = resolve_broker_endpoint(broker)?;
    let mut broker_process: Option<Child> = None;
    if !broker_is_reachable_for_realtime(&endpoint, realtime) {
        if broker == "auto" {
            endpoint = parse_broker_url("mqtt://127.0.0.1:1883")?;
        }
        if !autostart {
            if cfg!(unix) {
                let _ = publish_uds_if_available(topic, envelope, realtime);
            }
            return Ok(());
        }
        let startup = ensure_mosquitto(&endpoint)?;
        if startup.is_none() {
            return Ok(());
        }
        let startup = startup.expect("startup checked above");
        endpoint = parse_broker_url(&startup.endpoint)?;
        broker_process = Some(startup.process);
    }
    if let Err(error) = publish_mqtt(&endpoint, topic, envelope, realtime) {
        if cfg!(unix) && publish_uds_if_available(topic, envelope, realtime) {
            return Ok(());
        }
        return Err(error);
    }
    if let Some(mut process) = broker_process {
        if !keepalive {
            let _ = process.kill();
        }
    }
    Ok(())
}

#[cfg(unix)]
fn publish_uds_if_available(
    topic: &str,
    envelope: &GossipEnvelope,
    realtime: &RealtimeConfig,
) -> bool {
    let socket_path = uds_socket_path(Some(realtime));
    if !socket_path.exists() {
        return false;
    }
    publish_uds(topic, envelope, realtime).is_ok()
}

#[cfg(unix)]
fn publish_uds(
    topic: &str,
    envelope: &GossipEnvelope,
    realtime: &RealtimeConfig,
) -> Result<(), KanbusError> {
    let socket_path = uds_socket_path(Some(realtime));
    let mut stream =
        UnixStream::connect(socket_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let payload = serde_json::json!({"op": "pub", "topic": topic, "msg": envelope});
    let line =
        serde_json::to_string(&payload).map_err(|error| KanbusError::Io(error.to_string()))? + "\n";
    stream
        .write_all(line.as_bytes())
        .map_err(|error| KanbusError::Io(error.to_string()))
}

#[cfg(not(unix))]
fn publish_uds_if_available(
    _topic: &str,
    _envelope: &GossipEnvelope,
    _realtime: &RealtimeConfig,
) -> bool {
    false
}

#[cfg(not(unix))]
fn publish_uds(
    _topic: &str,
    _envelope: &GossipEnvelope,
    _realtime: &RealtimeConfig,
) -> Result<(), KanbusError> {
    Ok(())
}

fn publish_mqtt(
    endpoint: &BrokerEndpoint,
    topic: &str,
    envelope: &GossipEnvelope,
    realtime: &RealtimeConfig,
) -> Result<(), KanbusError> {
    let payload =
        serde_json::to_vec(envelope).map_err(|error| KanbusError::Io(error.to_string()))?;
    let options = mqtt_options(endpoint, realtime);
    let (client, mut eventloop) = AsyncClient::new(options, 10);
    let mut network_options = eventloop.network_options();
    // Match the 15s connection window used by the Python Paho client. AWS IoT
    // custom-authorizer setup can take longer than the crate's 5s default.
    network_options.set_connection_timeout(15);
    eventloop.set_network_options(network_options);
    let runtime =
        tokio::runtime::Runtime::new().map_err(|error| KanbusError::Io(error.to_string()))?;
    runtime.block_on(async move {
        // `EventLoop::poll` owns the in-progress TCP/TLS handshake. Do not put
        // short per-poll timeouts around it: dropping poll cancels that handshake
        // and can prevent custom-authorizer brokers from ever reaching CONNACK.
        let connect_result = tokio::time::timeout(Duration::from_secs(16), async {
            loop {
                match eventloop.poll().await {
                    Ok(Event::Incoming(Packet::ConnAck(_))) => return Ok(()),
                    Ok(_) => {}
                    Err(error) => {
                        return Err(KanbusError::Io(format!("mqtt connect failed: {error}")))
                    }
                }
            }
        })
        .await;
        match connect_result {
            Ok(result) => result?,
            Err(_) => return Err(KanbusError::Io("mqtt connect timeout".to_string())),
        }

        client
            .publish(topic, QoS::AtMostOnce, false, payload)
            .await
            .map_err(|error| KanbusError::Io(error.to_string()))?;

        // Keep driving the event loop briefly after queueing publish so the outgoing
        // packet has a chance to flush without indefinite blocking.
        let publish_result = tokio::time::timeout(Duration::from_secs(2), async {
            loop {
                match eventloop.poll().await {
                    Ok(Event::Outgoing(Outgoing::Publish(_))) => {
                        // QoS 0 has no broker acknowledgement. rumqttc emits this
                        // only after its network write has completed; cross-runtime
                        // watcher validation remains the end-to-end receipt check.
                        break;
                    }
                    Ok(_) => {}
                    Err(error) => {
                        return Err(KanbusError::Io(format!("mqtt publish failed: {error}")))
                    }
                }
            }
            Ok(())
        })
        .await;
        match publish_result {
            Ok(result) => result?,
            Err(_) => return Err(KanbusError::Io("mqtt publish flush timeout".to_string())),
        }
        Ok(())
    })
}

fn run_mqtt_subscription(
    endpoint: &BrokerEndpoint,
    topics: &[String],
    handler: Arc<dyn Fn(GossipEnvelope) + Send + Sync>,
    realtime: &RealtimeConfig,
) -> Result<(), KanbusError> {
    let options = mqtt_options(endpoint, realtime);
    let (client, mut eventloop) = AsyncClient::new(options, 10);
    let runtime =
        tokio::runtime::Runtime::new().map_err(|error| KanbusError::Io(error.to_string()))?;
    runtime.block_on(async move {
        for topic in topics {
            client
                .subscribe(topic, QoS::AtMostOnce)
                .await
                .map_err(|error| KanbusError::Io(error.to_string()))?;
        }
        let mut acknowledged_subscriptions = usize::from(topics.is_empty());
        loop {
            match eventloop.poll().await {
                Ok(Event::Incoming(Packet::SubAck(suback))) => {
                    if !subscription_ack_granted(&suback) {
                        return Err(KanbusError::Io(
                            "mqtt subscription was denied by the broker".to_string(),
                        ));
                    }
                    acknowledged_subscriptions += 1;
                }
                Ok(Event::Incoming(Packet::Publish(publish))) => {
                    if acknowledged_subscriptions >= topics.len() {
                        if let Ok(envelope) =
                            serde_json::from_slice::<GossipEnvelope>(&publish.payload)
                        {
                            handler(envelope);
                        }
                    }
                }
                Ok(_) => {}
                Err(error) => return Err(KanbusError::Io(error.to_string())),
            }
        }
    })
}

fn subscription_ack_granted(suback: &rumqttc::SubAck) -> bool {
    !suback.return_codes.is_empty()
        && suback
            .return_codes
            .iter()
            .all(|code| matches!(code, SubscribeReasonCode::Success(_)))
}

fn mqtt_options(endpoint: &BrokerEndpoint, realtime: &RealtimeConfig) -> MqttOptions {
    let endpoint = effective_broker_endpoint(endpoint, realtime);
    let has_custom_authorizer = has_custom_authorizer(realtime);
    // The stable envelope producer ID identifies this process's messages, not
    // the broker connection. Claims keep a subscriber open while a separate
    // publisher connection is created; reusing one MQTT client ID would cause
    // brokers to evict that subscriber as a duplicate connection.
    let mut options = MqttOptions::new(
        Uuid::new_v4().to_string(),
        endpoint.host.clone(),
        endpoint.port,
    );
    options.set_keep_alive(Duration::from_secs(30));
    if endpoint.scheme == "mqtts" {
        if has_custom_authorizer {
            let transport = match TlsConfiguration::default() {
                TlsConfiguration::Rustls(config) => {
                    let mut config = (*config).clone();
                    config.alpn_protocols = vec![b"mqtt".to_vec()];
                    Transport::tls_with_config(TlsConfiguration::Rustls(Arc::new(config)))
                }
                _ => Transport::tls_with_default_config(),
            };
            options.set_transport(transport);
        } else {
            options.set_transport(Transport::tls_with_default_config());
        }
    }
    if let (Some(authorizer), Some(api_token)) = (
        realtime.mqtt_custom_authorizer_name.as_ref(),
        realtime.mqtt_api_token.as_ref(),
    ) {
        let username = format!("?x-amz-customauthorizer-name={authorizer}");
        options.set_credentials(username, api_token.clone());
    }
    options
}

fn resolve_broker_endpoint(broker: &str) -> Result<BrokerEndpoint, KanbusError> {
    if broker == "auto" {
        if let Some(metadata) = load_broker_metadata() {
            if let Ok(endpoint) = parse_broker_url(&metadata.endpoint) {
                return Ok(endpoint);
            }
        }
        return parse_broker_url("mqtt://127.0.0.1:1883");
    }
    parse_broker_url(broker)
}

fn has_custom_authorizer(realtime: &RealtimeConfig) -> bool {
    realtime.mqtt_custom_authorizer_name.is_some() && realtime.mqtt_api_token.is_some()
}

fn effective_broker_endpoint(
    endpoint: &BrokerEndpoint,
    realtime: &RealtimeConfig,
) -> BrokerEndpoint {
    let custom_authorizer_uses_websocket_port =
        endpoint.scheme == "mqtts" && has_custom_authorizer(realtime) && endpoint.port == 8883;
    BrokerEndpoint {
        scheme: endpoint.scheme.clone(),
        host: endpoint.host.clone(),
        port: if custom_authorizer_uses_websocket_port {
            443
        } else {
            endpoint.port
        },
    }
}

fn broker_is_reachable_for_realtime(endpoint: &BrokerEndpoint, realtime: &RealtimeConfig) -> bool {
    broker_is_reachable(&effective_broker_endpoint(endpoint, realtime))
}

fn broker_is_reachable(endpoint: &BrokerEndpoint) -> bool {
    let addr = (endpoint.host.as_str(), endpoint.port)
        .to_socket_addrs()
        .ok()
        .and_then(|mut addrs| addrs.next());
    let Some(addr) = addr else {
        return false;
    };
    TcpStream::connect_timeout(&addr, Duration::from_secs(1)).is_ok()
}

fn ensure_mosquitto(endpoint: &BrokerEndpoint) -> Result<Option<BrokerStartup>, KanbusError> {
    if std::env::var("KANBUS_TEST_MOSQUITTO_UNAVAILABLE")
        .ok()
        .as_deref()
        == Some("1")
    {
        return Ok(None);
    }
    if endpoint.scheme != "mqtt" {
        return Ok(None);
    }
    if endpoint.host != "127.0.0.1" && endpoint.host != "localhost" {
        return Ok(None);
    }
    if !mosquitto_available() {
        return Ok(None);
    }
    let run_dir = broker_run_dir();
    fs::create_dir_all(&run_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let mut port = if endpoint.port == 0 {
        1883
    } else {
        endpoint.port
    };
    port = find_free_port(port)?;
    let conf_path = run_dir.join("mosquitto.conf");
    let log_path = run_dir.join("mosquitto.log");
    let conf_contents = format!(
        "listener {port} 127.0.0.1\nallow_anonymous true\nlog_dest file {}\npersistence false\n",
        log_path.display()
    );
    fs::write(&conf_path, conf_contents).map_err(|error| KanbusError::Io(error.to_string()))?;
    let process = Command::new("mosquitto")
        .arg("-c")
        .arg(&conf_path)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let metadata = BrokerMetadata {
        kind: "mosquitto".to_string(),
        endpoint: format!("mqtt://127.0.0.1:{port}"),
        pid: process.id(),
        started_by: "kbs".to_string(),
        started_at: now_iso(),
        log_path: log_path.display().to_string(),
        conf_path: conf_path.display().to_string(),
        ttl_s: 86_400,
    };
    write_broker_metadata(&metadata)?;
    Ok(Some(BrokerStartup {
        endpoint: metadata.endpoint.clone(),
        process,
    }))
}

/// Autostart Mosquitto using the provided broker URL (primarily for tests).
pub fn autostart_mosquitto(endpoint_url: &str) -> Result<Option<BrokerStartup>, KanbusError> {
    let endpoint = parse_broker_url(endpoint_url)?;
    ensure_mosquitto(&endpoint)
}

fn mosquitto_available() -> bool {
    if let Some(path) = std::env::var_os("PATH") {
        for entry in std::env::split_paths(&path) {
            let candidate = entry.join("mosquitto");
            if candidate.exists() {
                return true;
            }
        }
    }
    false
}

fn find_free_port(start_port: u16) -> Result<u16, KanbusError> {
    let mut port = start_port;
    loop {
        match std::net::TcpListener::bind(("127.0.0.1", port)) {
            Ok(_) => return Ok(port),
            Err(_) => {
                port = port.saturating_add(1);
            }
        }
    }
}

fn broker_run_dir() -> PathBuf {
    home_dir().join(".kanbus").join("run")
}

fn load_broker_metadata() -> Option<BrokerMetadata> {
    let path = broker_run_dir().join("broker.json");
    if !path.exists() {
        return None;
    }
    let contents = fs::read_to_string(path).ok()?;
    serde_json::from_str(&contents).ok()
}

fn write_broker_metadata(metadata: &BrokerMetadata) -> Result<(), KanbusError> {
    let run_dir = broker_run_dir();
    fs::create_dir_all(&run_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let path = run_dir.join("broker.json");
    let payload = serde_json::to_string_pretty(metadata)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::write(path, payload).map_err(|error| KanbusError::Io(error.to_string()))
}

fn now_iso() -> String {
    Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true)
}

fn uds_socket_path(realtime: Option<&RealtimeConfig>) -> PathBuf {
    if let Some(config) = realtime {
        if let Some(path) = &config.uds_socket_path {
            return PathBuf::from(path);
        }
    }
    if let Ok(runtime_dir) = std::env::var("XDG_RUNTIME_DIR") {
        return PathBuf::from(runtime_dir).join("kanbus").join("bus.sock");
    }
    home_dir().join(".kanbus").join("run").join("bus.sock")
}

fn home_dir() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}

fn project_topic(realtime: &RealtimeConfig, label: &str) -> String {
    realtime.topics.project_events.replace("{project}", label)
}

fn resolve_project_label(
    root: &Path,
    project_dir: &Path,
    configuration: &ProjectConfiguration,
) -> Option<String> {
    let labeled = resolve_labeled_projects(root).ok()?;
    for project in labeled {
        if project.project_dir == project_dir {
            return Some(project.label);
        }
    }
    Some(configuration.project_key.clone())
}

fn parse_broker_url(url: &str) -> Result<BrokerEndpoint, KanbusError> {
    let Some((scheme, rest)) = url.split_once("://") else {
        return Err(KanbusError::IssueOperation(format!(
            "invalid broker url: {url}"
        )));
    };
    let host_port = rest.split('/').next().unwrap_or(rest);
    let (host, port) = if let Some((host, port_text)) = host_port.split_once(':') {
        let port = port_text
            .parse::<u16>()
            .map_err(|_| KanbusError::IssueOperation(format!("invalid broker url: {url}")))?;
        (host.to_string(), port)
    } else {
        (host_port.to_string(), 1883)
    };
    Ok(BrokerEndpoint {
        scheme: scheme.to_string(),
        host,
        port,
    })
}

static MOSQUITTO_MISSING_WARNED: AtomicBool = AtomicBool::new(false);
static MOSQUITTO_MISSING_WARNING_COUNT: AtomicUsize = AtomicUsize::new(0);

fn mosquitto_warnings_enabled() -> bool {
    std::env::var("KANBUS_REALTIME_WARN_MOSQUITTO")
        .ok()
        .as_deref()
        != Some("0")
}

/// Emit a single Mosquitto install hint per process for explicit realtime commands.
fn maybe_warn_mosquitto_missing() {
    if !mosquitto_warnings_enabled() {
        return;
    }
    if MOSQUITTO_MISSING_WARNED.swap(true, Ordering::SeqCst) {
        return;
    }
    MOSQUITTO_MISSING_WARNING_COUNT.fetch_add(1, Ordering::SeqCst);
    eprintln!(
        "Mosquitto not found; local MQTT realtime is optional. Install mosquitto for gossip watch (see docs/REALTIME.md). macOS: brew install mosquitto. Debian/Ubuntu: apt install mosquitto."
    );
}

/// Reset the once-per-session Mosquitto warning gate.
pub fn reset_mosquitto_missing_warning() {
    MOSQUITTO_MISSING_WARNED.store(false, Ordering::SeqCst);
    MOSQUITTO_MISSING_WARNING_COUNT.store(0, Ordering::SeqCst);
}

/// Return how many Mosquitto install hints were emitted in this process.
pub fn mosquitto_missing_warning_count() -> usize {
    MOSQUITTO_MISSING_WARNING_COUNT.load(Ordering::SeqCst)
}

/// Publish a gossip envelope for behavior-spec MQTT publish checks.
pub fn attempt_mqtt_publish_without_broker(
    configuration: &ProjectConfiguration,
    topic: &str,
    envelope: &GossipEnvelope,
) -> Result<(), KanbusError> {
    publish_with_transport(
        topic,
        envelope,
        &configuration.realtime,
        "mqtt",
        &configuration.realtime.broker,
        configuration.realtime.autostart,
        configuration.realtime.keepalive,
    )
}

/// Emit the Mosquitto install hint gate used by realtime MQTT commands.
pub fn attempt_mosquitto_missing_warning() {
    maybe_warn_mosquitto_missing();
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;
    use crate::models::RealtimeTopics;
    use crate::models::VirtualProjectConfig;
    use once_cell::sync::Lazy;
    #[cfg(unix)]
    use std::os::unix::net::{UnixListener, UnixStream};
    use std::path::PathBuf;
    use std::sync::{mpsc, Mutex};
    use tempfile::TempDir;

    fn env_lock() -> std::sync::MutexGuard<'static, ()> {
        static ENV_LOCK: Lazy<Mutex<()>> = Lazy::new(|| Mutex::new(()));
        ENV_LOCK.lock().expect("env lock")
    }

    fn accept_mock_connection_with_deadline(
        listener: &std::net::TcpListener,
        timeout: Duration,
    ) -> std::io::Result<(std::net::TcpStream, std::net::SocketAddr)> {
        let deadline = Instant::now() + timeout;
        loop {
            match listener.accept() {
                Ok((stream, address)) => {
                    stream.set_nonblocking(false)?;
                    return Ok((stream, address));
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    if Instant::now() >= deadline {
                        return Err(std::io::Error::new(
                            std::io::ErrorKind::TimedOut,
                            "timed out waiting for mock MQTT connection",
                        ));
                    }
                    thread::sleep(Duration::from_millis(10));
                }
                Err(error) => return Err(error),
            }
        }
    }

    #[test]
    fn mock_mqtt_accept_is_bounded_when_setup_never_connects() {
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).expect("bind listener");
        listener
            .set_nonblocking(true)
            .expect("enable nonblocking accept");
        let started = Instant::now();
        let error = accept_mock_connection_with_deadline(&listener, Duration::from_millis(40))
            .expect_err("missing mock client must time out");
        assert_eq!(error.kind(), std::io::ErrorKind::TimedOut);
        assert!(started.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn mqtt_subscription_readiness_requires_every_suback_code_to_grant_access() {
        assert!(subscription_ack_granted(&rumqttc::SubAck::new(
            1,
            vec![SubscribeReasonCode::Success(QoS::AtMostOnce)],
        )));
        assert!(!subscription_ack_granted(&rumqttc::SubAck::new(
            1,
            vec![SubscribeReasonCode::Failure],
        )));
        assert!(!subscription_ack_granted(&rumqttc::SubAck::new(
            1,
            Vec::new()
        )));
        assert!(!subscription_ack_granted(&rumqttc::SubAck::new(
            1,
            vec![
                SubscribeReasonCode::Success(QoS::AtMostOnce),
                SubscribeReasonCode::Failure,
            ],
        )));
    }

    fn sample_realtime(socket_path: Option<String>) -> RealtimeConfig {
        RealtimeConfig {
            transport: "mqtt".to_string(),
            broker: "mqtts://example.invalid:443".to_string(),
            autostart: false,
            keepalive: false,
            uds_socket_path: socket_path,
            mqtt_custom_authorizer_name: None,
            mqtt_api_token: None,
            topics: RealtimeTopics::default(),
        }
    }

    fn sample_envelope() -> GossipEnvelope {
        GossipEnvelope {
            id: Uuid::new_v4().to_string(),
            ts: now_iso(),
            project: "test".to_string(),
            event_type: "issue.mutated".to_string(),
            issue_id: Some("test-1".to_string()),
            event_id: Some(Uuid::new_v4().to_string()),
            producer_id: Uuid::new_v4().to_string(),
            origin_cluster_id: None,
            issue: None,
            coordination: CoordinationGossipFields::default(),
        }
    }

    #[test]
    fn coordination_envelopes_use_top_level_realtime_fields_and_receiver_rules() {
        let first = build_coordination_gossip_envelope(
            "KAN",
            "coordination.claim",
            "claim-event-1",
            CoordinationGossipFields {
                resource: Some("job:fast-1".to_string()),
                owner: Some("worker-a".to_string()),
                claim_id: Some("claim-a".to_string()),
                lease_ttl_s: Some(300),
                expires_at: None,
                operation_sequence: None,
            },
        );
        let second = build_coordination_gossip_envelope(
            "KAN",
            "coordination.release",
            "release-event-1",
            CoordinationGossipFields {
                resource: Some("job:fast-1".to_string()),
                owner: Some("worker-a".to_string()),
                claim_id: Some("claim-a".to_string()),
                lease_ttl_s: None,
                expires_at: None,
                operation_sequence: None,
            },
        );
        let serialized = serde_json::to_value(&first).expect("serialize claim envelope");
        for field in [
            "id",
            "ts",
            "project",
            "type",
            "event_id",
            "producer_id",
            "resource",
            "owner",
            "claim_id",
            "lease_ttl_s",
        ] {
            assert!(serialized.get(field).is_some(), "missing top-level {field}");
        }
        assert_eq!(serialized["type"], "coordination.claim");
        assert_eq!(serialized["event_id"], "claim-event-1");
        assert_eq!(serialized["resource"], "job:fast-1");
        assert!(serialized.get("coordination").is_none());
        assert_eq!(first.producer_id, second.producer_id);
        assert_ne!(first.id, second.id);

        let mut dedupe = DedupeSet::new(Duration::from_secs(3600));
        assert!(!should_accept_gossip(
            &first,
            &first.producer_id,
            &mut dedupe
        ));
        let mut receiver_dedupe = DedupeSet::new(Duration::from_secs(3600));
        assert!(should_accept_gossip(
            &first,
            "another-producer",
            &mut receiver_dedupe
        ));
        assert!(!should_accept_gossip(
            &first,
            "another-producer",
            &mut receiver_dedupe
        ));
    }

    #[test]
    fn coordination_gossip_is_stored_when_issue_overlay_is_disabled() {
        let temp = TempDir::new().expect("temp dir");
        let envelope = build_coordination_gossip_envelope(
            "KAN",
            "coordination.claim",
            "claim-event-1",
            CoordinationGossipFields {
                resource: Some("job:fast-1".to_string()),
                owner: Some("worker-a".to_string()),
                claim_id: Some("claim-a".to_string()),
                lease_ttl_s: Some(300),
                expires_at: None,
                operation_sequence: None,
            },
        );

        persist_gossip_overlay(
            temp.path(),
            &envelope,
            &OverlayConfig {
                enabled: false,
                ttl_s: 77,
            },
        );

        let stored = crate::overlay::load_coordination_overlay(temp.path(), "job:fast-1", 77)
            .expect("load coordination overlay");
        assert_eq!(stored.len(), 1);
        assert_eq!(stored[0].id, envelope.id);
    }

    fn write_test_config(root: &Path, broker: &str, transport: &str) {
        let mut configuration = default_project_configuration();
        configuration.realtime.broker = broker.to_string();
        configuration.realtime.transport = transport.to_string();
        let yaml = serde_yaml::to_string(&configuration).expect("serialize config");
        std::fs::write(root.join(".kanbus.yml"), yaml).expect("write config");
    }

    #[test]
    fn test_gossip_server_and_broadcast() {
        let temp = tempfile::TempDir::new().unwrap();
        let root = temp.path();

        let dummy_issue: IssueData = serde_json::from_value(serde_json::json!({
            "id": "kanbus-test01",
            "title": "Test Issue",
            "description": "Test Description",
            "type": "task",
            "status": "open",
            "priority": 1,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "labels": [],
            "dependencies": [],
            "custom": {},
            "comments": []
        }))
        .unwrap();

        let root_clone = root.to_path_buf();
        std::thread::spawn(move || {
            let _ = run_gossip_broker(&root_clone, None);
        });

        std::thread::sleep(std::time::Duration::from_millis(150));

        publish_issue_mutation(root, root, &dummy_issue, None, "ui.reload");

        publish_issue_deleted(root, root, "id", None);

        #[cfg(unix)]
        {
            let socket_path = root.join(".kanbus").join("gossip.sock");
            if let Ok(mut stream) = std::os::unix::net::UnixStream::connect(&socket_path) {
                use std::io::Write;
                let _ = stream.write_all(b"invalid json\n");
                let _ = stream.flush();
            }
        }

        std::thread::sleep(std::time::Duration::from_millis(50));
    }

    #[test]
    fn publish_uds_if_available_returns_false_without_socket() {
        let realtime = sample_realtime(Some("/tmp/kanbus-nonexistent.sock".to_string()));
        let envelope = sample_envelope();
        assert!(!publish_uds_if_available(
            "projects/test/events",
            &envelope,
            &realtime
        ));
    }

    #[cfg(unix)]
    #[test]
    fn publish_uds_if_available_returns_true_with_running_broker() {
        let tmp = TempDir::new().expect("temp dir");
        let socket_path = tmp.path().join("bus.sock");
        let realtime = sample_realtime(Some(socket_path.display().to_string()));
        let broker_socket = socket_path.clone();
        thread::spawn(move || {
            let _ = run_uds_broker(&broker_socket);
        });
        for _ in 0..40 {
            if socket_path.exists() {
                break;
            }
            thread::sleep(Duration::from_millis(25));
        }
        let envelope = sample_envelope();
        assert!(publish_uds_if_available(
            "projects/test/events",
            &envelope,
            &realtime
        ));
    }

    #[cfg(unix)]
    #[test]
    fn publish_with_mqtt_unreachable_falls_back_to_uds_delivery() {
        let tmp = TempDir::new().expect("temp dir");
        let socket_path = tmp.path().join("bus.sock");
        let topic = "projects/test/events".to_string();
        let realtime = sample_realtime(Some(socket_path.display().to_string()));
        let broker_socket = socket_path.clone();
        thread::spawn(move || {
            let _ = run_uds_broker(&broker_socket);
        });
        for _ in 0..40 {
            if socket_path.exists() {
                break;
            }
            thread::sleep(Duration::from_millis(25));
        }

        let (tx, rx) = mpsc::channel::<String>();
        let sub_socket = socket_path.clone();
        let sub_topic = topic.clone();
        thread::spawn(move || {
            let mut stream = UnixStream::connect(&sub_socket).expect("connect uds");
            let sub = serde_json::json!({"op":"sub","topic": sub_topic});
            let line = serde_json::to_string(&sub).expect("serialize sub") + "\n";
            stream.write_all(line.as_bytes()).expect("subscribe write");
            let mut reader = BufReader::new(stream);
            let mut inbound = String::new();
            if reader.read_line(&mut inbound).is_ok() {
                let _ = tx.send(inbound);
            }
        });
        thread::sleep(Duration::from_millis(50));

        let envelope = sample_envelope();
        let result = publish_with_transport(
            &topic,
            &envelope,
            &realtime,
            "mqtt",
            "mqtts://203.0.113.1:443",
            false,
            false,
        );
        assert!(result.is_ok(), "publish_with_transport should not fail");
        let inbound = rx
            .recv_timeout(Duration::from_secs(2))
            .expect("expected UDS-delivered message");
        let parsed: Value = serde_json::from_str(inbound.trim()).expect("parse inbound payload");
        assert_eq!(
            parsed.get("topic").and_then(|v| v.as_str()),
            Some("projects/test/events")
        );
        assert_eq!(
            parsed
                .get("msg")
                .and_then(|v| v.get("type"))
                .and_then(|v| v.as_str()),
            Some("issue.mutated")
        );
    }

    #[test]
    fn parse_broker_url_supports_default_and_explicit_ports() {
        let default_endpoint = parse_broker_url("mqtt://broker.example").expect("endpoint");
        assert_eq!(default_endpoint.host, "broker.example");
        assert_eq!(default_endpoint.port, 1883);

        let explicit_endpoint = parse_broker_url("mqtts://broker.example:8883").expect("endpoint");
        assert_eq!(explicit_endpoint.host, "broker.example");
        assert_eq!(explicit_endpoint.port, 8883);
    }

    #[test]
    fn uds_socket_path_prefers_env_runtime_dir() {
        let _guard = env_lock();
        let prior_runtime = std::env::var("XDG_RUNTIME_DIR").ok();
        std::env::set_var("XDG_RUNTIME_DIR", "/tmp/kanbus-runtime");
        let path = uds_socket_path(None);
        if let Some(value) = prior_runtime {
            std::env::set_var("XDG_RUNTIME_DIR", value);
        } else {
            std::env::remove_var("XDG_RUNTIME_DIR");
        }
        assert_eq!(path, PathBuf::from("/tmp/kanbus-runtime/kanbus/bus.sock"));
    }

    #[test]
    fn resolve_broker_endpoint_auto_defaults_when_no_metadata() {
        let _guard = env_lock();
        let tmp = TempDir::new().expect("temp dir");
        let prior_home = std::env::var("HOME").ok();
        std::env::set_var("HOME", tmp.path());
        let endpoint = resolve_broker_endpoint("auto").expect("endpoint");
        assert_eq!(endpoint.host, "127.0.0.1");
        assert_eq!(endpoint.port, 1883);
        assert_eq!(endpoint.scheme, "mqtt");
        if let Some(value) = prior_home {
            std::env::set_var("HOME", value);
        } else {
            std::env::remove_var("HOME");
        }
    }

    #[test]
    fn parse_broker_url_rejects_invalid_urls() {
        assert!(parse_broker_url("not-a-url").is_err());
        assert!(parse_broker_url("mqtt://host:not-a-port").is_err());
    }

    #[test]
    fn resolve_broker_endpoint_auto_prefers_metadata_endpoint() {
        let _guard = env_lock();
        let tmp = TempDir::new().expect("temp dir");
        let prior_home = std::env::var("HOME").ok();
        std::env::set_var("HOME", tmp.path());
        let run_dir = tmp.path().join(".kanbus").join("run");
        std::fs::create_dir_all(&run_dir).expect("create run dir");
        std::fs::write(
            run_dir.join("broker.json"),
            serde_json::json!({
                "kind": "mosquitto",
                "endpoint": "mqtt://127.0.0.1:2883",
                "pid": 1234,
                "started_by": "kbs",
                "started_at": "2026-01-01T00:00:00.000Z",
                "log_path": "/tmp/mosquitto.log",
                "conf_path": "/tmp/mosquitto.conf",
                "ttl_s": 86400
            })
            .to_string(),
        )
        .expect("write metadata");

        let endpoint = resolve_broker_endpoint("auto").expect("endpoint");
        assert_eq!(endpoint.host, "127.0.0.1");
        assert_eq!(endpoint.port, 2883);
        if let Some(value) = prior_home {
            std::env::set_var("HOME", value);
        } else {
            std::env::remove_var("HOME");
        }
    }

    #[test]
    fn ensure_mosquitto_returns_none_for_non_local_or_non_mqtt() {
        let remote_mqtt = BrokerEndpoint {
            scheme: "mqtt".to_string(),
            host: "broker.example".to_string(),
            port: 1883,
        };
        let tls_local = BrokerEndpoint {
            scheme: "mqtts".to_string(),
            host: "127.0.0.1".to_string(),
            port: 8883,
        };

        assert!(ensure_mosquitto(&remote_mqtt)
            .expect("ensure result")
            .is_none());
        assert!(ensure_mosquitto(&tls_local)
            .expect("ensure result")
            .is_none());
    }

    #[test]
    fn parse_broker_url_rejects_empty_and_unknown_scheme() {
        assert!(parse_broker_url("").is_err());
        assert!(parse_broker_url("http://example.com").is_ok());
    }

    #[test]
    fn broker_is_reachable_detects_active_listener() {
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).expect("listener");
        let port = listener.local_addr().expect("addr").port();
        let endpoint = BrokerEndpoint {
            scheme: "mqtt".to_string(),
            host: "127.0.0.1".to_string(),
            port,
        };
        assert!(broker_is_reachable(&endpoint));
        drop(listener);
    }

    #[test]
    fn publish_mqtt_preserves_slow_connack_and_flushes_qos0_publish() {
        use std::io::{Read, Write};

        fn read_mqtt_packet(stream: &mut std::net::TcpStream) -> (u8, Vec<u8>) {
            let mut header = [0_u8; 1];
            stream.read_exact(&mut header).expect("read MQTT header");
            let mut multiplier = 1_usize;
            let mut remaining_length = 0_usize;
            loop {
                let mut byte = [0_u8; 1];
                stream
                    .read_exact(&mut byte)
                    .expect("read MQTT remaining length");
                remaining_length += usize::from(byte[0] & 0x7f) * multiplier;
                if byte[0] & 0x80 == 0 {
                    break;
                }
                multiplier *= 128;
                assert!(multiplier <= 128_usize.pow(4), "invalid MQTT length");
            }
            let mut body = vec![0_u8; remaining_length];
            stream.read_exact(&mut body).expect("read MQTT packet body");
            (header[0], body)
        }

        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).expect("listener");
        let port = listener.local_addr().expect("listener address").port();
        let (tx, rx) = mpsc::channel();
        let broker = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept MQTT connection");
            let (connect_header, _) = read_mqtt_packet(&mut stream);
            assert_eq!(connect_header >> 4, 1, "expected MQTT CONNECT");

            // Exceed the old 250ms per-poll timeout. Cancelling rumqttc's first
            // poll here dropped the in-flight connection and restarted CONNECT.
            thread::sleep(Duration::from_millis(400));
            stream
                .write_all(&[0x20, 0x02, 0x00, 0x00])
                .expect("write MQTT CONNACK");

            let (publish_header, body) = read_mqtt_packet(&mut stream);
            let topic_length = usize::from(u16::from_be_bytes([body[0], body[1]]));
            let topic_end = 2 + topic_length;
            let topic = String::from_utf8(body[2..topic_end].to_vec()).expect("topic UTF-8");
            let payload = body[topic_end..].to_vec();
            tx.send((publish_header, topic, payload))
                .expect("send observed publish");
        });

        let endpoint = BrokerEndpoint {
            scheme: "mqtt".to_string(),
            host: "127.0.0.1".to_string(),
            port,
        };
        let realtime = sample_realtime(None);
        let envelope = sample_envelope();
        publish_mqtt(&endpoint, "projects/test/events", &envelope, &realtime)
            .expect("MQTT publish should complete after delayed CONNACK");

        let (publish_header, topic, payload) = rx
            .recv_timeout(Duration::from_secs(1))
            .expect("broker should receive publish");
        assert_eq!(publish_header >> 4, 3, "expected MQTT PUBLISH");
        assert_eq!((publish_header >> 1) & 0x03, 0, "publish must remain QoS 0");
        assert_eq!(topic, "projects/test/events");
        let payload: serde_json::Value = serde_json::from_slice(&payload).expect("JSON payload");
        assert_eq!(payload["type"], "issue.mutated");
        broker.join().expect("mock broker thread");
    }

    #[test]
    fn bounded_coordination_mqtt_subscriber_persists_peer_claim_overlay() {
        use std::io::{Read, Write};
        use std::net::TcpListener;

        fn read_packet_after_header(stream: &mut std::net::TcpStream, header: u8) -> (u8, Vec<u8>) {
            let mut multiplier = 1_usize;
            let mut remaining = 0_usize;
            loop {
                let mut byte = [0_u8; 1];
                stream.read_exact(&mut byte).expect("read MQTT length");
                remaining += usize::from(byte[0] & 0x7f) * multiplier;
                if byte[0] & 0x80 == 0 {
                    break;
                }
                multiplier *= 128;
            }
            let mut body = vec![0_u8; remaining];
            stream.read_exact(&mut body).expect("read MQTT body");
            (header, body)
        }

        fn read_packet(stream: &mut std::net::TcpStream) -> (u8, Vec<u8>) {
            let mut header = [0_u8; 1];
            stream.read_exact(&mut header).expect("read MQTT header");
            read_packet_after_header(stream, header[0])
        }

        fn publish_packet(topic: &str, payload: &[u8]) -> Vec<u8> {
            let topic = topic.as_bytes();
            let mut body = Vec::new();
            body.extend_from_slice(&(topic.len() as u16).to_be_bytes());
            body.extend_from_slice(topic);
            body.extend_from_slice(payload);
            let mut packet = vec![0x30];
            let mut remaining = body.len();
            loop {
                let mut encoded = (remaining % 128) as u8;
                remaining /= 128;
                if remaining > 0 {
                    encoded |= 0x80;
                }
                packet.push(encoded);
                if remaining == 0 {
                    break;
                }
            }
            packet.extend(body);
            packet
        }

        let temp = TempDir::new().expect("temporary project");
        let root = temp.path();
        let listener = TcpListener::bind(("127.0.0.1", 0)).expect("bind broker");
        listener
            .set_nonblocking(true)
            .expect("make mock broker accept nonblocking");
        let port = listener.local_addr().expect("broker address").port();
        write_test_config(root, &format!("mqtt://127.0.0.1:{port}"), "mqtt");
        let (published_tx, published_rx) = mpsc::channel();
        let broker = thread::spawn(move || {
            let (mut subscriber, _) =
                accept_mock_connection_with_deadline(&listener, Duration::from_secs(3))
                    .expect("accept subscriber within deadline");
            subscriber
                .set_read_timeout(Some(Duration::from_secs(3)))
                .expect("bound subscriber reads");
            subscriber
                .set_write_timeout(Some(Duration::from_secs(3)))
                .expect("bound subscriber writes");
            let (connect, _) = read_packet(&mut subscriber);
            assert_eq!(connect >> 4, 1, "expected MQTT CONNECT");
            // Simulate slow TLS/custom-authorizer CONNACK and SUBACK phases.
            thread::sleep(Duration::from_millis(600));
            subscriber
                .write_all(&[0x20, 0x02, 0x00, 0x00])
                .expect("send CONNACK");
            let (subscribe, body) = read_packet(&mut subscriber);
            assert_eq!(subscribe >> 4, 8, "expected MQTT SUBSCRIBE");
            let packet_id = [body[0], body[1]];
            // The contention window starts after successful MQTT setup and
            // local publication, not while waiting on a slow custom-authorizer
            // handshake or the broker's SUBACK.
            thread::sleep(Duration::from_millis(600));
            subscriber
                .write_all(&[0x90, 0x03, packet_id[0], packet_id[1], 0x00])
                .expect("send SUBACK");
            let publisher_deadline = Instant::now() + Duration::from_secs(3);
            let (mut publisher, first_header) = loop {
                let timeout = publisher_deadline.saturating_duration_since(Instant::now());
                let (mut stream, _) = accept_mock_connection_with_deadline(&listener, timeout)
                    .expect("accept publisher connection within overall deadline");
                stream
                    .set_read_timeout(Some(Duration::from_secs(3)))
                    .expect("set publisher read timeout");
                stream
                    .set_write_timeout(Some(Duration::from_secs(3)))
                    .expect("set publisher write timeout");
                let mut header = [0_u8; 1];
                match stream.read(&mut header) {
                    Ok(0) => continue, // TCP-only reachability probe
                    Ok(1) if header[0] >> 4 == 1 => break (stream, header[0]),
                    other => panic!("unexpected publisher connection: {other:?}"),
                }
            };
            let (connect, _) = read_packet_after_header(&mut publisher, first_header);
            assert_eq!(connect >> 4, 1, "expected MQTT CONNECT");
            publisher
                .write_all(&[0x20, 0x02, 0x00, 0x00])
                .expect("send publisher CONNACK");
            let (publish, body) = read_packet(&mut publisher);
            assert_eq!(publish >> 4, 3, "expected MQTT PUBLISH");
            let topic_length = usize::from(u16::from_be_bytes([body[0], body[1]]));
            let topic_end = 2 + topic_length;
            let topic = String::from_utf8(body[2..topic_end].to_vec()).expect("topic");
            let payload = body[topic_end..].to_vec();
            published_tx
                .send(
                    serde_json::from_slice::<serde_json::Value>(&payload).expect("claim envelope"),
                )
                .expect("send captured claim envelope");
            subscriber
                .write_all(&publish_packet(&topic, &payload))
                .expect("relay peer claim to subscribed router");
        });

        let project_dir = root.join("project");
        let before_setup = Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
        let (received, published) = collect_coordination_gossip_window_with(
            root,
            &project_dir,
            Duration::from_millis(500),
            300,
            || {
                let claim_event = crate::coordination::append_soft_claim_event(
                    &project_dir,
                    "router:issue:kbs-peer",
                    "peer-worker",
                    "peer-claim",
                    1,
                    1,
                    300,
                    Utc::now(),
                )
                .expect("persist local claim after SUBACK readiness");
                publish_coordination_gossip(
                    root,
                    &project_dir,
                    "coordination.claim",
                    &claim_event.event_id,
                    Some(&claim_event.occurred_at),
                    CoordinationGossipFields {
                        resource: Some("router:issue:kbs-peer".to_string()),
                        owner: Some("peer-worker".to_string()),
                        claim_id: Some("peer-claim".to_string()),
                        lease_ttl_s: Some(300),
                        expires_at: None,
                        operation_sequence: claim_event
                            .payload
                            .get("operation_sequence")
                            .and_then(serde_json::Value::as_u64),
                    },
                )
            },
        );
        broker.join().expect("broker thread");
        assert!(published, "local claim publishes only after subscription");
        assert_eq!(received, 1);
        let published_envelope = published_rx
            .recv_timeout(Duration::from_secs(1))
            .expect("capture the local MQTT claim publication");
        let event_path =
            std::fs::read_dir(crate::event_history::events_dir_for_project(&project_dir))
                .expect("read durable claim event")
                .next()
                .expect("one claim event")
                .expect("event path")
                .path();
        let durable_claim: crate::event_history::EventRecord =
            serde_json::from_slice(&std::fs::read(event_path).expect("read durable claim"))
                .expect("parse durable claim");
        assert_eq!(durable_claim.event_id, published_envelope["event_id"]);
        assert_eq!(durable_claim.occurred_at, published_envelope["ts"]);
        assert_eq!(
            durable_claim.payload["operation_sequence"],
            published_envelope["operation_sequence"]
        );
        assert!(
            published_envelope["ts"]
                .as_str()
                .expect("publication timestamp")
                > before_setup.as_str(),
            "claim time must be allocated after delayed MQTT setup"
        );
        let overlay =
            crate::overlay::load_coordination_overlay(&project_dir, "router:issue:kbs-peer", 300)
                .expect("load peer coordination overlay");
        assert_eq!(overlay.len(), 1);
        assert_eq!(
            overlay[0].event_id.as_deref(),
            published_envelope["event_id"].as_str()
        );
    }

    #[test]
    fn denied_coordination_mqtt_subscription_falls_back_without_publishing() {
        use std::io::{Read, Write};
        use std::sync::atomic::{AtomicBool, Ordering};

        fn read_packet(stream: &mut std::net::TcpStream) -> (u8, Vec<u8>) {
            let mut header = [0_u8; 1];
            stream.read_exact(&mut header).expect("read MQTT header");
            let mut multiplier = 1_usize;
            let mut remaining = 0_usize;
            loop {
                let mut byte = [0_u8; 1];
                stream.read_exact(&mut byte).expect("read MQTT length");
                remaining += usize::from(byte[0] & 0x7f) * multiplier;
                if byte[0] & 0x80 == 0 {
                    break;
                }
                multiplier *= 128;
            }
            let mut body = vec![0_u8; remaining];
            stream.read_exact(&mut body).expect("read MQTT body");
            (header[0], body)
        }

        let temp = TempDir::new().expect("temporary project");
        let root = temp.path();
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).expect("bind broker");
        listener
            .set_nonblocking(true)
            .expect("make denied-subscription accept nonblocking");
        let port = listener.local_addr().expect("broker address").port();
        write_test_config(root, &format!("mqtt://127.0.0.1:{port}"), "mqtt");
        let (broker_finished_tx, broker_finished_rx) = mpsc::channel();
        let broker = thread::spawn(move || {
            let (mut subscriber, _) =
                accept_mock_connection_with_deadline(&listener, Duration::from_secs(3))
                    .expect("accept subscriber within deadline");
            subscriber
                .set_read_timeout(Some(Duration::from_secs(3)))
                .expect("bound denied-subscriber reads");
            subscriber
                .set_write_timeout(Some(Duration::from_secs(3)))
                .expect("bound denied-subscriber writes");
            let (connect, _) = read_packet(&mut subscriber);
            assert_eq!(connect >> 4, 1, "expected MQTT CONNECT");
            subscriber
                .write_all(&[0x20, 0x02, 0x00, 0x00])
                .expect("send CONNACK");
            let (subscribe, body) = read_packet(&mut subscriber);
            assert_eq!(subscribe >> 4, 8, "expected MQTT SUBSCRIBE");
            subscriber
                .write_all(&[0x90, 0x03, body[0], body[1], 0x80])
                .expect("deny MQTT subscription");
            broker_finished_tx
                .send(())
                .expect("signal denied broker completion");
        });

        let publish_called = Arc::new(AtomicBool::new(false));
        let callback_flag = Arc::clone(&publish_called);
        let started = Instant::now();
        let (received, published) = collect_coordination_gossip_window_with(
            root,
            &root.join("project"),
            Duration::from_secs(2),
            300,
            move || {
                callback_flag.store(true, Ordering::SeqCst);
                true
            },
        );

        broker_finished_rx
            .recv_timeout(Duration::from_secs(3))
            .expect("denied subscription broker should finish promptly");
        broker.join().expect("broker thread");
        assert!(started.elapsed() < Duration::from_secs(5));
        assert_eq!(received, 0);
        assert!(!published, "denied subscription must select Git fallback");
        assert!(!publish_called.load(Ordering::SeqCst));
    }

    #[test]
    fn find_free_port_returns_bindable_port() {
        let port = find_free_port(1883).expect("free port");
        let listener = std::net::TcpListener::bind(("127.0.0.1", port)).expect("bind");
        drop(listener);
    }

    #[test]
    fn mqtt_options_uses_tls_443_and_credentials_for_custom_authorizer() {
        let mut realtime = sample_realtime(None);
        realtime.mqtt_custom_authorizer_name = Some("authz".to_string());
        realtime.mqtt_api_token = Some("token-123".to_string());
        let endpoint = BrokerEndpoint {
            scheme: "mqtts".to_string(),
            host: "example.com".to_string(),
            port: 8883,
        };

        let options = mqtt_options(&endpoint, &realtime);
        assert_eq!(options.broker_address(), ("example.com".to_string(), 443));
        assert_eq!(effective_broker_endpoint(&endpoint, &realtime).port, 443);
        assert_eq!(
            options
                .credentials()
                .map(|(username, _)| username.to_string()),
            Some("?x-amz-customauthorizer-name=authz".to_string())
        );
    }

    #[test]
    fn mqtt_connections_use_unique_client_ids_separate_from_stable_producer_id() {
        let endpoint = BrokerEndpoint {
            scheme: "mqtts".to_string(),
            host: "example.com".to_string(),
            port: 8883,
        };
        let realtime = sample_realtime(None);
        let stable_producer_id = producer_id();
        let first = mqtt_options(&endpoint, &realtime);
        let second = mqtt_options(&endpoint, &realtime);

        assert_ne!(first.client_id(), second.client_id());
        assert_ne!(first.client_id(), stable_producer_id);
        assert_eq!(producer_id(), stable_producer_id);
    }

    #[test]
    fn mqtt_options_keeps_port_without_custom_authorizer() {
        let realtime = sample_realtime(None);
        let endpoint = BrokerEndpoint {
            scheme: "mqtts".to_string(),
            host: "example.com".to_string(),
            port: 8883,
        };

        let options = mqtt_options(&endpoint, &realtime);
        assert_eq!(options.broker_address(), ("example.com".to_string(), 8883));
        assert!(options.credentials().is_none());
    }

    #[test]
    fn effective_reachability_endpoint_maps_only_custom_auth_mqtts_8883_to_443() {
        let mut realtime = sample_realtime(None);
        realtime.mqtt_custom_authorizer_name = Some("authz".to_string());
        realtime.mqtt_api_token = Some("token-123".to_string());
        let endpoint = BrokerEndpoint {
            scheme: "mqtts".to_string(),
            host: "broker.example".to_string(),
            port: 8883,
        };

        let effective = effective_broker_endpoint(&endpoint, &realtime);

        assert_eq!(effective.host, endpoint.host);
        assert_eq!(effective.scheme, endpoint.scheme);
        assert_eq!(effective.port, 443);

        let mut cases = Vec::new();
        let mut missing_token = realtime.clone();
        missing_token.mqtt_api_token = None;
        cases.push((endpoint.clone(), missing_token, 8883));
        let mut missing_authorizer = realtime.clone();
        missing_authorizer.mqtt_custom_authorizer_name = None;
        cases.push((endpoint.clone(), missing_authorizer, 8883));
        let mut plain_mqtt = endpoint.clone();
        plain_mqtt.scheme = "mqtt".to_string();
        cases.push((plain_mqtt, realtime.clone(), 8883));
        let mut other_port = endpoint.clone();
        other_port.port = 8884;
        cases.push((other_port, realtime, 8884));

        for (endpoint, realtime, expected_port) in cases {
            assert_eq!(
                effective_broker_endpoint(&endpoint, &realtime).port,
                expected_port
            );
        }
    }

    #[test]
    fn broker_metadata_round_trip_and_invalid_payload_handling() {
        let _guard = env_lock();
        let tmp = TempDir::new().expect("temp dir");
        let prior_home = std::env::var("HOME").ok();
        std::env::set_var("HOME", tmp.path());
        let metadata = BrokerMetadata {
            kind: "mosquitto".to_string(),
            endpoint: "mqtt://127.0.0.1:1999".to_string(),
            pid: 42,
            started_by: "kbs".to_string(),
            started_at: "2026-03-09T00:00:00.000Z".to_string(),
            log_path: "/tmp/mosquitto.log".to_string(),
            conf_path: "/tmp/mosquitto.conf".to_string(),
            ttl_s: 86_400,
        };

        write_broker_metadata(&metadata).expect("write metadata");
        let parsed = load_broker_metadata().expect("load metadata");
        assert_eq!(parsed.endpoint, "mqtt://127.0.0.1:1999");

        let run_dir = broker_run_dir();
        std::fs::write(run_dir.join("broker.json"), "{").expect("write invalid metadata");
        assert!(load_broker_metadata().is_none());
        if let Some(value) = prior_home {
            std::env::set_var("HOME", value);
        } else {
            std::env::remove_var("HOME");
        }
    }

    #[test]
    fn dedupe_set_prunes_expired_entries() {
        let mut set = DedupeSet::new(Duration::from_millis(5));
        assert!(!set.seen("a"));
        assert!(set.seen("a"));
        thread::sleep(Duration::from_millis(6));
        assert!(!set.seen("a"), "entry should expire after ttl");
    }

    #[test]
    fn uds_socket_path_uses_override_when_provided() {
        let realtime = sample_realtime(Some("/tmp/custom.sock".to_string()));
        let custom = uds_socket_path(Some(&realtime));
        assert_eq!(custom, PathBuf::from("/tmp/custom.sock"));
    }

    #[test]
    fn local_uds_broker_preserves_a_live_socket() {
        let temp = TempDir::new().expect("temp dir");
        let socket_path = temp.path().join("bus.sock");
        let _listener = UnixListener::bind(&socket_path).expect("bind live broker");
        let realtime = sample_realtime(Some(socket_path.display().to_string()));

        ensure_local_uds_broker(&realtime).expect("preserve live broker");
        assert!(socket_path.exists());
    }

    #[test]
    fn local_uds_broker_recovers_a_stale_socket() {
        let temp = TempDir::new().expect("temp dir");
        let socket_path = temp.path().join("bus.sock");
        std::fs::write(&socket_path, b"stale").expect("write stale socket");
        let realtime = sample_realtime(Some(socket_path.display().to_string()));

        ensure_local_uds_broker(&realtime).expect("recover stale broker");
        assert!(UnixStream::connect(&socket_path).is_ok());
    }

    #[test]
    fn project_topic_replaces_project_template() {
        let realtime = sample_realtime(None);
        assert_eq!(
            project_topic(&realtime, "dev"),
            "projects/dev/events".to_string()
        );
    }

    #[test]
    fn resolve_project_label_returns_matching_label_and_fallback() {
        let tmp = TempDir::new().expect("temp dir");
        let root = tmp.path();
        let projects_dir = root.join("projects");
        let alpha_dir = projects_dir.join("alpha");
        std::fs::create_dir_all(&alpha_dir).expect("create project dir");
        let mut configuration = default_project_configuration();
        configuration.project_directory = "projects/primary".to_string();
        configuration.project_key = "fallback".to_string();
        configuration.virtual_projects.insert(
            "alpha".to_string(),
            VirtualProjectConfig {
                path: "projects/alpha".to_string(),
                display_name: None,
            },
        );
        let yaml = serde_yaml::to_string(&configuration).expect("serialize config");
        std::fs::write(root.join(".kanbus.yml"), yaml).expect("write config");
        let configuration =
            load_project_configuration(&root.join(".kanbus.yml")).expect("load project config");

        assert_eq!(
            resolve_project_label(root, &alpha_dir, &configuration),
            Some("alpha".to_string())
        );
        assert_eq!(
            resolve_project_label(root, &root.join("projects").join("missing"), &configuration),
            Some("fallback".to_string())
        );
    }

    #[cfg(unix)]
    #[test]
    fn run_uds_subscription_ignores_invalid_payloads_before_valid_envelope() {
        let tmp = TempDir::new().expect("temp dir");
        let socket_path = tmp.path().join("bus.sock");
        let realtime = sample_realtime(Some(socket_path.display().to_string()));
        let broker_socket = socket_path.clone();
        thread::spawn(move || {
            let _ = run_uds_broker(&broker_socket);
        });
        for _ in 0..40 {
            if socket_path.exists() {
                break;
            }
            thread::sleep(Duration::from_millis(25));
        }

        let topic = "kanbus/test/events".to_string();
        let envelope = sample_envelope();
        let received_id = envelope.id.clone();
        let realtime_for_sub = realtime.clone();
        let topic_for_sub = topic.clone();
        let (tx, rx) = mpsc::channel::<String>();
        thread::spawn(move || {
            let handler = Arc::new(move |env: GossipEnvelope| {
                let _ = tx.send(env.id);
            });
            let _ = run_uds_subscription(&realtime_for_sub, &[topic_for_sub], handler);
        });
        thread::sleep(Duration::from_millis(100));

        let mut publisher = UnixStream::connect(&socket_path).expect("connect publisher");
        for payload in [
            "{\"op\":\"pub\",\"topic\":\"kanbus/test/events\",\"msg\":not-json}\n".to_string(),
            "{\"op\":\"pub\",\"topic\":\"kanbus/test/events\"}\n".to_string(),
            format!(
                "{}\n",
                serde_json::json!({"op":"pub","topic":"kanbus/test/events","msg": envelope})
            ),
        ] {
            publisher
                .write_all(payload.as_bytes())
                .expect("publish payload");
        }

        let observed = rx
            .recv_timeout(Duration::from_secs(2))
            .expect("expected valid envelope delivery");
        assert_eq!(observed, received_id);
    }

    #[test]
    fn run_gossip_consumer_rejects_unknown_project_label() {
        let temp = TempDir::new().expect("temp dir");
        write_test_config(temp.path(), "off", "mqtt");
        let result = run_gossip_consumer(
            temp.path(),
            GossipConsumerOptions {
                project_filter: Some("missing".to_string()),
                transport_override: None,
                broker_override: None,
                autostart_override: None,
                keepalive_override: None,
                print_envelopes: false,
                on_envelope: None,
                autostart_local_uds: false,
                broker_off_is_error: true,
            },
        );
        assert!(result.is_err());
        assert!(result
            .expect_err("expected error")
            .to_string()
            .contains("unknown project label"));
    }

    #[test]
    fn run_gossip_consumer_broker_off_respects_error_policy() {
        let temp = TempDir::new().expect("temp dir");
        write_test_config(temp.path(), "off", "mqtt");

        let ok_result = run_gossip_consumer(
            temp.path(),
            GossipConsumerOptions {
                project_filter: None,
                transport_override: None,
                broker_override: None,
                autostart_override: None,
                keepalive_override: None,
                print_envelopes: false,
                on_envelope: None,
                autostart_local_uds: false,
                broker_off_is_error: false,
            },
        );
        assert!(ok_result.is_ok());

        let error_result = run_gossip_consumer(
            temp.path(),
            GossipConsumerOptions {
                project_filter: None,
                transport_override: None,
                broker_override: None,
                autostart_override: None,
                keepalive_override: None,
                print_envelopes: false,
                on_envelope: None,
                autostart_local_uds: false,
                broker_off_is_error: true,
            },
        );
        assert!(error_result.is_err());
        assert!(error_result
            .expect_err("expected error")
            .to_string()
            .contains("realtime broker is disabled"));
    }

    #[test]
    fn publish_issue_mutation_early_returns_when_broker_off() {
        let temp = TempDir::new().expect("temp dir");
        write_test_config(temp.path(), "off", "mqtt");
        let issue = IssueData {
            identifier: "test-1".to_string(),
            title: "Test".to_string(),
            description: "".to_string(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: vec![],
            dependencies: vec![],
            comments: vec![],
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: Default::default(),
        };
        // Should return early and not panic or error.
        publish_issue_mutation(
            temp.path(),
            &temp.path().join("projects/test"),
            &issue,
            None,
            "issue.mutated",
        );
    }

    #[test]
    fn publish_issue_deleted_early_returns_when_broker_off() {
        let temp = TempDir::new().expect("temp dir");
        write_test_config(temp.path(), "off", "mqtt");
        // Should return early and not panic or error.
        publish_issue_deleted(
            temp.path(),
            &temp.path().join("projects/test"),
            "test-1",
            None,
        );
    }

    #[test]
    fn run_gossip_watch_returns_error_when_broker_off_and_no_override() {
        let temp = TempDir::new().expect("temp dir");
        write_test_config(temp.path(), "off", "mqtt");
        let result = run_gossip_watch(temp.path(), None, None, None, None, None, false);
        assert!(result.is_err());
        assert!(result
            .expect_err("error")
            .to_string()
            .contains("realtime broker is disabled"));
    }

    #[test]
    fn maybe_warn_mosquitto_missing_prints_once_per_session() {
        let _guard = env_lock();
        reset_mosquitto_missing_warning();
        attempt_mosquitto_missing_warning();
        attempt_mosquitto_missing_warning();
        assert_eq!(mosquitto_missing_warning_count(), 1);
    }

    #[test]
    fn maybe_warn_mosquitto_missing_respects_disable_env() {
        let _guard = env_lock();
        reset_mosquitto_missing_warning();
        let prior = std::env::var("KANBUS_REALTIME_WARN_MOSQUITTO").ok();
        std::env::set_var("KANBUS_REALTIME_WARN_MOSQUITTO", "0");
        attempt_mosquitto_missing_warning();
        assert_eq!(mosquitto_missing_warning_count(), 0);
        if let Some(value) = prior {
            std::env::set_var("KANBUS_REALTIME_WARN_MOSQUITTO", value);
        } else {
            std::env::remove_var("KANBUS_REALTIME_WARN_MOSQUITTO");
        }
    }
}
