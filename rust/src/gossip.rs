//! Realtime gossip transport and envelope helpers.

use chrono::Utc;
use rumqttc::{AsyncClient, Event, MqttOptions, Packet, QoS, Transport};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};
use uuid::Uuid;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{get_configuration_path, resolve_labeled_projects};
use crate::models::{IssueData, ProjectConfiguration, RealtimeConfig};
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
    };
    let topic = project_topic(&configuration.realtime, &project_label);
    if let Err(error) = publish_envelope(root, &configuration, &topic, &envelope) {
        eprintln!(
            "warning: realtime publish failed for {}: {}",
            issue.identifier, error
        );
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
    };
    let topic = project_topic(&configuration.realtime, &project_label);
    if let Err(error) = publish_envelope(root, &configuration, &topic, &envelope) {
        eprintln!("warning: realtime publish failed for {issue_id}: {error}");
    }
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
        if envelope.producer_id == local_producer {
            return;
        }
        if let Ok(mut guard) = dedupe.lock() {
            if guard.seen(&envelope.id) {
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

        if overlay_config.enabled {
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

        if let Some(callback) = on_envelope_handler.as_ref() {
            callback(envelope);
        }
    });

    let mut use_uds =
        transport == "uds" || (transport == "auto" && uds_socket_path(Some(realtime)).exists());
    if options.autostart_local_uds && !use_uds && (transport == "uds" || transport == "auto") {
        ensure_local_uds_broker(realtime)?;
        use_uds = true;
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
    if !broker_is_reachable(&endpoint) {
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
            print_mosquitto_missing();
            return Ok(());
        };
        endpoint = parse_broker_url(&startup.endpoint)?;
        broker_process = Some(startup.process);
    }

    run_mqtt_subscription(&endpoint, &topics, handler)?;
    if let Some(mut process) = broker_process {
        if !keepalive {
            let _ = process.kill();
        }
    }
    Ok(())
}

fn ensure_local_uds_broker(realtime: &RealtimeConfig) -> Result<(), KanbusError> {
    let socket_path = uds_socket_path(Some(realtime));
    if socket_path.exists() {
        return Ok(());
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

/// Run a UDS gossip broker.
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

#[derive(Clone)]
struct Subscriber {
    topic: String,
    stream: Arc<Mutex<UnixStream>>,
}

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

fn publish_envelope(
    _root: &Path,
    configuration: &ProjectConfiguration,
    topic: &str,
    envelope: &GossipEnvelope,
) -> Result<(), KanbusError> {
    let transport = configuration.realtime.transport.as_str();
    let broker = configuration.realtime.broker.as_str();
    let autostart = configuration.realtime.autostart;
    let keepalive = configuration.realtime.keepalive;
    if transport == "uds"
        || (transport == "auto" && uds_socket_path(Some(&configuration.realtime)).exists())
    {
        let _ = publish_uds(topic, envelope, &configuration.realtime);
        return Ok(());
    }
    if broker == "off" {
        return Ok(());
    }
    let mut endpoint = resolve_broker_endpoint(broker)?;
    let mut broker_process: Option<Child> = None;
    if !broker_is_reachable(&endpoint) {
        if broker == "auto" {
            endpoint = parse_broker_url("mqtt://127.0.0.1:1883")?;
        }
        if !autostart {
            return Ok(());
        }
        let startup = ensure_mosquitto(&endpoint)?;
        let Some(startup) = startup else {
            print_mosquitto_missing();
            return Ok(());
        };
        endpoint = parse_broker_url(&startup.endpoint)?;
        broker_process = Some(startup.process);
    }
    publish_mqtt(&endpoint, topic, envelope)?;
    if let Some(mut process) = broker_process {
        if !keepalive {
            let _ = process.kill();
        }
    }
    Ok(())
}

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

fn publish_mqtt(
    endpoint: &BrokerEndpoint,
    topic: &str,
    envelope: &GossipEnvelope,
) -> Result<(), KanbusError> {
    let payload =
        serde_json::to_vec(envelope).map_err(|error| KanbusError::Io(error.to_string()))?;
    let options = mqtt_options(endpoint);
    let (client, mut eventloop) = AsyncClient::new(options, 10);
    let runtime =
        tokio::runtime::Runtime::new().map_err(|error| KanbusError::Io(error.to_string()))?;
    runtime.block_on(async move {
        client
            .publish(topic, QoS::AtMostOnce, false, payload)
            .await
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        for _ in 0..5 {
            let _ = eventloop
                .poll()
                .await
                .map_err(|error| KanbusError::Io(error.to_string()))?;
        }
        Ok(())
    })
}

fn run_mqtt_subscription(
    endpoint: &BrokerEndpoint,
    topics: &[String],
    handler: Arc<dyn Fn(GossipEnvelope) + Send + Sync>,
) -> Result<(), KanbusError> {
    let options = mqtt_options(endpoint);
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
        loop {
            match eventloop.poll().await {
                Ok(Event::Incoming(Packet::Publish(publish))) => {
                    if let Ok(envelope) = serde_json::from_slice::<GossipEnvelope>(&publish.payload)
                    {
                        handler(envelope);
                    }
                }
                Ok(_) => {}
                Err(error) => return Err(KanbusError::Io(error.to_string())),
            }
        }
    })
}

fn mqtt_options(endpoint: &BrokerEndpoint) -> MqttOptions {
    let mut options = MqttOptions::new(producer_id(), endpoint.host.clone(), endpoint.port);
    options.set_keep_alive(Duration::from_secs(30));
    if endpoint.scheme == "mqtts" {
        options.set_transport(Transport::tls_with_default_config());
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

fn print_mosquitto_missing() {
    eprintln!(
        "Mosquitto not found. Install with: brew install mosquitto (macOS) or apt install mosquitto (Debian/Ubuntu)."
    );
}
