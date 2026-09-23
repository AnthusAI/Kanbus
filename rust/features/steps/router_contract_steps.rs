//! Contract fixtures for deterministic Issue Router planning and execution.

use std::collections::BTreeMap;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex, OnceLock};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use chrono::{DateTime, TimeZone, Utc};
use cucumber::{gherkin::Step, given, then, when};
use kanbus::event_history::{now_timestamp, write_events_batch, EventRecord, EventType};
use kanbus::models::{DependencyLink, IssueData};
use serde_json::{json, Value};
use serde_yaml::{Mapping, Value as Yaml};

use crate::step_definitions::initialization_steps::{
    run_from_args_in_blocking_thread, KanbusWorld,
};

#[derive(Default)]
struct ForgeServer {
    stop: Arc<AtomicBool>,
    join: Option<JoinHandle<()>>,
}

struct FakeMqttServer {
    stop: Arc<AtomicBool>,
    subscribed: Arc<AtomicBool>,
    publish: mpsc::Sender<(String, Vec<u8>)>,
    join: Option<JoinHandle<()>>,
}

struct MqttSubscriber {
    client_id: u64,
    topic: String,
    stream: TcpStream,
}

fn mqtt_servers() -> &'static Mutex<BTreeMap<PathBuf, FakeMqttServer>> {
    static SERVERS: OnceLock<Mutex<BTreeMap<PathBuf, FakeMqttServer>>> = OnceLock::new();
    SERVERS.get_or_init(|| Mutex::new(BTreeMap::new()))
}

fn watch_threads() -> &'static Mutex<BTreeMap<PathBuf, JoinHandle<()>>> {
    static THREADS: OnceLock<Mutex<BTreeMap<PathBuf, JoinHandle<()>>>> = OnceLock::new();
    THREADS.get_or_init(|| Mutex::new(BTreeMap::new()))
}

fn watch_diagnostics() -> &'static Mutex<BTreeMap<PathBuf, String>> {
    static DIAGNOSTICS: OnceLock<Mutex<BTreeMap<PathBuf, String>>> = OnceLock::new();
    DIAGNOSTICS.get_or_init(|| Mutex::new(BTreeMap::new()))
}

fn active_fixture_children() -> &'static Mutex<BTreeMap<PathBuf, std::process::Child>> {
    static CHILDREN: OnceLock<Mutex<BTreeMap<PathBuf, std::process::Child>>> = OnceLock::new();
    CHILDREN.get_or_init(|| Mutex::new(BTreeMap::new()))
}

fn spawn_fixture_child(world: &mut KanbusWorld) -> u32 {
    let root_path = root(world).to_path_buf();
    let child = Command::new("sleep")
        .arg("60")
        .spawn()
        .expect("start disposable adapter child process");
    let pid = child.id();
    if let Some(mut previous) = active_fixture_children()
        .lock()
        .expect("lock fixture child processes")
        .insert(root_path, child)
    {
        let _ = previous.kill();
        let _ = previous.wait();
    }
    pid
}

fn cleanup_fixture_child(world: &mut KanbusWorld) {
    if let Some(mut child) = active_fixture_children()
        .lock()
        .expect("lock fixture child processes")
        .remove(root(world))
    {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn encode_mqtt_remaining_length(mut length: usize) -> Vec<u8> {
    let mut encoded = Vec::new();
    loop {
        let mut byte = (length % 128) as u8;
        length /= 128;
        if length > 0 {
            byte |= 0x80;
        }
        encoded.push(byte);
        if length == 0 {
            return encoded;
        }
    }
}

fn mqtt_publish_packet(topic: &str, payload: &[u8]) -> Vec<u8> {
    let topic = topic.as_bytes();
    let mut body = Vec::with_capacity(2 + topic.len() + payload.len());
    body.extend_from_slice(&(topic.len() as u16).to_be_bytes());
    body.extend_from_slice(topic);
    body.extend_from_slice(payload);
    let mut packet = vec![0x30];
    packet.extend(encode_mqtt_remaining_length(body.len()));
    packet.extend(body);
    packet
}

type MqttSubscriptions = Arc<Mutex<Vec<MqttSubscriber>>>;

fn deliver_mqtt_publish(subscriptions: &MqttSubscriptions, topic: &str, payload: &[u8]) {
    let packet = mqtt_publish_packet(topic, payload);
    let mut subscriptions = subscriptions.lock().expect("lock fake MQTT subscriptions");
    subscriptions.retain_mut(|subscriber| {
        subscriber.topic != topic || subscriber.stream.write_all(&packet).is_ok()
    });
}

fn handle_fake_mqtt_client(
    mut stream: TcpStream,
    stop: Arc<AtomicBool>,
    subscribed: Arc<AtomicBool>,
    subscriptions: MqttSubscriptions,
    client_id: u64,
) {
    let _ = stream.set_read_timeout(Some(Duration::from_millis(50)));
    while !stop.load(Ordering::Relaxed) {
        let packet = match read_mqtt_packet(&mut stream) {
            Ok(Some(packet)) => packet,
            Ok(None) => continue,
            Err(_) => break,
        };
        match packet.0 {
            1 => {
                let _ = stream.write_all(&[0x20, 0x02, 0x00, 0x00]);
            }
            3 if packet.1.len() >= 2 => {
                let topic_len = usize::from(u16::from_be_bytes([packet.1[0], packet.1[1]]));
                if packet.1.len() >= 2 + topic_len {
                    let topic = String::from_utf8_lossy(&packet.1[2..2 + topic_len]);
                    deliver_mqtt_publish(&subscriptions, &topic, &packet.1[2 + topic_len..]);
                }
            }
            8 if packet.1.len() >= 5 => {
                let packet_id = [packet.1[0], packet.1[1]];
                let topic_len = usize::from(u16::from_be_bytes([packet.1[2], packet.1[3]]));
                if packet.1.len() >= 5 + topic_len {
                    let topic = String::from_utf8_lossy(&packet.1[4..4 + topic_len]).to_string();
                    if let Ok(writer) = stream.try_clone() {
                        subscriptions
                            .lock()
                            .expect("lock fake MQTT subscriptions")
                            .push(MqttSubscriber {
                                client_id,
                                topic,
                                stream: writer,
                            });
                    }
                    subscribed.store(true, Ordering::Relaxed);
                    let ack = [0x90, 0x03, packet_id[0], packet_id[1], 0x00];
                    let _ = stream.write_all(&ack);
                }
            }
            12 => {
                let _ = stream.write_all(&[0xd0, 0x00]);
            }
            14 => break,
            _ => {}
        }
    }
    let has_subscribers = {
        let mut subscriptions = subscriptions.lock().expect("lock fake MQTT subscriptions");
        subscriptions.retain(|subscriber| subscriber.client_id != client_id);
        !subscriptions.is_empty()
    };
    subscribed.store(has_subscribers, Ordering::Relaxed);
}

fn read_mqtt_packet(stream: &mut std::net::TcpStream) -> std::io::Result<Option<(u8, Vec<u8>)>> {
    let mut first = [0_u8; 1];
    match stream.read(&mut first) {
        Ok(0) => return Err(std::io::Error::from(std::io::ErrorKind::UnexpectedEof)),
        Ok(_) => {}
        Err(error)
            if matches!(
                error.kind(),
                std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
            ) =>
        {
            return Ok(None);
        }
        Err(error) => return Err(error),
    }
    let mut remaining = 0_usize;
    let mut multiplier = 1_usize;
    loop {
        let mut byte = [0_u8; 1];
        stream.read_exact(&mut byte)?;
        remaining += usize::from(byte[0] & 0x7f) * multiplier;
        if byte[0] & 0x80 == 0 {
            break;
        }
        multiplier = multiplier.saturating_mul(128);
    }
    let mut body = vec![0_u8; remaining];
    stream.read_exact(&mut body)?;
    Ok(Some((first[0] >> 4, body)))
}

fn start_fake_mqtt(world: &mut KanbusWorld) -> String {
    let root_path = root(world).to_path_buf();
    if let Some(server) = mqtt_servers()
        .lock()
        .expect("lock fake MQTT map")
        .get(&root_path)
    {
        return server
            .join
            .as_ref()
            .map(|_| {
                let (_, config) = read_yaml(world);
                config["realtime"]["broker"]
                    .as_str()
                    .expect("fake MQTT broker URL")
                    .to_string()
            })
            .expect("fake MQTT server thread");
    }

    let listener = TcpListener::bind("127.0.0.1:0").expect("bind fake MQTT broker");
    listener
        .set_nonblocking(true)
        .expect("set fake MQTT listener nonblocking");
    let address = listener.local_addr().expect("fake MQTT address");
    let stop = Arc::new(AtomicBool::new(false));
    let subscribed = Arc::new(AtomicBool::new(false));
    let subscriptions = Arc::new(Mutex::new(Vec::<MqttSubscriber>::new()));
    let (publish_tx, publish_rx) = mpsc::channel::<(String, Vec<u8>)>();
    let stop_thread = Arc::clone(&stop);
    let subscribed_thread = Arc::clone(&subscribed);
    let subscriptions_thread = Arc::clone(&subscriptions);
    let join = thread::spawn(move || {
        let mut clients = Vec::new();
        let mut next_client_id = 0;
        while !stop_thread.load(Ordering::Relaxed) {
            while let Ok((stream, _)) = listener.accept() {
                let client_id = next_client_id;
                next_client_id += 1;
                let client_stop = Arc::clone(&stop_thread);
                let client_subscribed = Arc::clone(&subscribed_thread);
                let client_subscriptions = Arc::clone(&subscriptions_thread);
                clients.push(thread::spawn(move || {
                    handle_fake_mqtt_client(
                        stream,
                        client_stop,
                        client_subscribed,
                        client_subscriptions,
                        client_id,
                    )
                }));
            }
            while let Ok((topic, payload)) = publish_rx.try_recv() {
                deliver_mqtt_publish(&subscriptions_thread, &topic, &payload);
            }
            thread::sleep(Duration::from_millis(10));
        }
        for client in clients {
            let _ = client.join();
        }
        subscribed_thread.store(false, Ordering::Relaxed);
    });
    let url = format!("mqtt://{address}");
    set_path(
        world,
        &["realtime", "transport"],
        Yaml::String("mqtt".to_string()),
    );
    set_path(world, &["realtime", "broker"], Yaml::String(url.clone()));
    mqtt_servers().lock().expect("lock fake MQTT map").insert(
        root_path,
        FakeMqttServer {
            stop,
            subscribed,
            publish: publish_tx,
            join: Some(join),
        },
    );
    url
}

fn publish_peer_mqtt(world: &mut KanbusWorld, topic: &str, payload: Vec<u8>) {
    let root_path = root(world).to_path_buf();
    let servers = mqtt_servers().lock().expect("lock fake MQTT map");
    let server = servers.get(&root_path).expect("fake MQTT server started");
    let deadline = std::time::Instant::now() + Duration::from_secs(5);
    while !server.subscribed.load(Ordering::Relaxed) {
        assert!(
            std::time::Instant::now() < deadline,
            "router did not subscribe to the fake MQTT broker"
        );
        thread::sleep(Duration::from_millis(10));
    }
    server
        .publish
        .send((topic.to_string(), payload))
        .expect("publish peer coordination envelope");
}

fn stop_fake_mqtt(world: &mut KanbusWorld) {
    if let Some(mut server) = mqtt_servers()
        .lock()
        .expect("lock fake MQTT map")
        .remove(root(world))
    {
        server.stop.store(true, Ordering::Relaxed);
        if let Some(join) = server.join.take() {
            let _ = join.join();
        }
    }
}

/// Start router watch in the background so a Cucumber scenario can control it.
pub fn launch_watch(world: &mut KanbusWorld) {
    let root_path = root(world).to_path_buf();
    watch_diagnostics()
        .lock()
        .expect("lock router watch diagnostics")
        .remove(&root_path);
    world.stdout = None;
    world.stderr = None;
    world.last_command = Some("kanbus router run --watch".to_string());
    let mut overrides = world.environment_overrides.clone();
    overrides
        .entry("KANBUS_NO_DAEMON".to_string())
        .or_insert_with(|| "1".to_string());
    let diagnostic_root = root_path.clone();
    let join = thread::spawn(move || {
        let saved =
            crate::step_definitions::initialization_steps::apply_environment_overrides(&overrides);
        let result = run_from_args_in_blocking_thread(
            vec![
                "kanbus".to_string(),
                "router".to_string(),
                "run".to_string(),
                "--watch".to_string(),
            ],
            &root_path,
        );
        crate::step_definitions::initialization_steps::restore_environment(saved);
        let diagnostic = match result {
            Ok(output) => format!(
                "watch exited normally; stdout={:?}; stderr={:?}",
                output.stdout, output.stderr
            ),
            Err(error) => format!("watch exited with error: {error}"),
        };
        watch_diagnostics()
            .lock()
            .expect("lock router watch diagnostics")
            .insert(diagnostic_root, diagnostic);
    });
    let old = watch_threads()
        .lock()
        .expect("lock router watch threads")
        .insert(root(world).to_path_buf(), join);
    if let Some(old) = old {
        let _ = old.join();
    }
}

fn stop_watch(world: &mut KanbusWorld) {
    run_cli(world, "kanbus router stop");
    if let Some(join) = watch_threads()
        .lock()
        .expect("lock router watch threads")
        .remove(root(world))
    {
        let _ = join.join();
    }
    stop_fake_mqtt(world);
}

fn forge_servers() -> &'static Mutex<BTreeMap<PathBuf, ForgeServer>> {
    static SERVERS: OnceLock<Mutex<BTreeMap<PathBuf, ForgeServer>>> = OnceLock::new();
    SERVERS.get_or_init(|| Mutex::new(BTreeMap::new()))
}

fn root(world: &mut KanbusWorld) -> &Path {
    world
        .working_directory
        .as_deref()
        .expect("working directory")
}

fn project_dir(world: &mut KanbusWorld) -> PathBuf {
    kanbus::file_io::load_project_directory(root(world)).expect("project directory")
}

fn issue_path(world: &mut KanbusWorld, issue_id: &str) -> PathBuf {
    project_dir(world)
        .join("issues")
        .join(format!("{issue_id}.json"))
}

/// Ensure an active-claim contract fixture also has its corresponding issue record.
pub(crate) fn ensure_current_claim_issue(world: &mut KanbusWorld, issue_id: &str) {
    let path = issue_path(world, issue_id);
    if !path.exists() {
        seed_issue(
            world,
            issue_id,
            "in_progress",
            vec!["agent-class:implementation".to_string()],
            None,
            None,
            Utc::now(),
            Vec::new(),
        );
    }
}

fn read_yaml(world: &mut KanbusWorld) -> (PathBuf, Yaml) {
    let path = kanbus::file_io::get_configuration_path(root(world)).expect("configuration path");
    let value = serde_yaml::from_slice(&fs::read(&path).expect("read project configuration"))
        .expect("parse project configuration");
    (path, value)
}

fn write_yaml(world: &mut KanbusWorld, value: &Yaml) {
    let (path, _) = read_yaml(world);
    fs::write(
        path,
        serde_yaml::to_string(value).expect("serialize configuration"),
    )
    .expect("write configuration");
}

fn mapping(value: &mut Yaml) -> &mut Mapping {
    value.as_mapping_mut().expect("configuration mapping")
}

fn set_path(world: &mut KanbusWorld, parts: &[&str], value: Yaml) {
    let mut config = read_yaml(world).1;
    let mut current = mapping(&mut config);
    for part in &parts[..parts.len() - 1] {
        let key = Yaml::String((*part).to_string());
        if !current.contains_key(&key) {
            current.insert(key.clone(), Yaml::Mapping(Mapping::new()));
        }
        current = current
            .get_mut(&key)
            .and_then(Yaml::as_mapping_mut)
            .expect("configuration path mapping");
    }
    current.insert(Yaml::String(parts[parts.len() - 1].to_string()), value);
    write_yaml(world, &config);
}

fn set_router_path(world: &mut KanbusWorld, path: &[&str], value: Yaml) {
    let mut full_path = vec!["router"];
    full_path.extend_from_slice(path);
    set_path(world, &full_path, value);
}

fn utc(value: &str) -> DateTime<Utc> {
    DateTime::parse_from_rfc3339(value)
        .expect("RFC3339 fixture time")
        .with_timezone(&Utc)
}

fn seed_issue(
    world: &mut KanbusWorld,
    id: &str,
    status: &str,
    labels: Vec<String>,
    parent: Option<String>,
    assignee: Option<String>,
    created_at: DateTime<Utc>,
    dependencies: Vec<DependencyLink>,
) {
    let issue = IssueData {
        identifier: id.to_string(),
        title: format!("Router fixture {id}"),
        description: String::new(),
        issue_type: "task".to_string(),
        status: status.to_string(),
        priority: 2,
        assignee,
        creator: None,
        parent,
        labels,
        dependencies,
        comments: Vec::new(),
        created_at,
        updated_at: created_at,
        closed_at: None,
        agent: None,
        right_now_summary: None,
        right_now_updated_at: None,
        custom: BTreeMap::new(),
    };
    let path = issue_path(world, id);
    fs::create_dir_all(path.parent().expect("issues directory")).expect("create issues directory");
    fs::write(
        path,
        serde_json::to_vec_pretty(&issue).expect("serialize issue"),
    )
    .expect("write issue fixture");
}

fn load_issue(world: &mut KanbusWorld, id: &str) -> IssueData {
    serde_json::from_slice(&fs::read(issue_path(world, id)).expect("read issue fixture"))
        .expect("parse issue fixture")
}

fn effective_issue_status(world: &mut KanbusWorld, id: &str) -> String {
    let repository_root = root(world).to_path_buf();
    kanbus::router::effective_issue_router_status(&repository_root, id)
        .unwrap_or_else(|error| panic!("read effective router status for {id}: {error}"))
}

fn read_events(world: &mut KanbusWorld) -> Vec<EventRecord> {
    let events_dir = project_dir(world).join("events");
    if !events_dir.exists() {
        return Vec::new();
    }
    let mut files = fs::read_dir(events_dir)
        .expect("read events directory")
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some("json"))
        .collect::<Vec<_>>();
    files.sort();
    files
        .iter()
        .filter_map(|path| fs::read(path).ok())
        .filter_map(|bytes| serde_json::from_slice::<EventRecord>(&bytes).ok())
        .collect()
}

fn append_event(world: &mut KanbusWorld, event: EventRecord) {
    write_events_batch(&project_dir(world).join("events"), &[event])
        .expect("write router fixture event");
}

fn router_event(world: &mut KanbusWorld, issue: &str, kind: EventType, payload: Value, at: &str) {
    append_event(
        world,
        EventRecord::new(
            issue,
            kind,
            "router-contract-fixture",
            payload,
            at.to_string(),
        ),
    );
}

fn seed_pending(world: &mut KanbusWorld, id: &str, label: &str) {
    let minute = 10
        + fs::read_dir(project_dir(world).join("issues"))
            .expect("read issue fixtures")
            .filter_map(Result::ok)
            .filter(|entry| {
                entry.path().extension().and_then(|value| value.to_str()) == Some("json")
            })
            .count() as u32;
    seed_issue(
        world,
        id,
        "open",
        label.split_whitespace().map(str::to_string).collect(),
        None,
        None,
        Utc.with_ymd_and_hms(2026, 9, 17, minute.min(59), 0, 0)
            .unwrap(),
        Vec::new(),
    );
}

fn run_cli(world: &mut KanbusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse router command");
    let cwd = root(world).to_path_buf();
    let overrides = world.environment_overrides.clone();
    let saved =
        crate::step_definitions::initialization_steps::apply_environment_overrides(&overrides);
    let result = run_from_args_in_blocking_thread(args, &cwd);
    crate::step_definitions::initialization_steps::restore_environment(saved);
    match result {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(output.stderr);
        }
        Err(error) => {
            let (exit_code, stdout, stderr) = match error {
                kanbus::error::KanbusError::CommandFailure { exit_code, message } => {
                    (exit_code, String::new(), format!("{message}\n"))
                }
                kanbus::error::KanbusError::CommandFailureWithOutput {
                    exit_code,
                    stdout,
                    stderr,
                } => (exit_code, stdout, format!("{stderr}\n")),
                other => (1, String::new(), other.to_string()),
            };
            world.exit_code = Some(exit_code);
            world.stdout = Some(stdout);
            world.stderr = Some(stderr);
        }
    }
    world.last_command = Some(command.to_string());
}

fn parse_plan(world: &mut KanbusWorld) -> Value {
    serde_json::from_str(world.stdout.as_deref().expect("router plan output"))
        .expect("router JSON plan")
}

fn deferred_reason<'a>(plan: &'a Value, issue_id: &str) -> Option<&'a str> {
    plan["deferred"]
        .as_array()?
        .iter()
        .find(|item| item["issue_id"] == issue_id)?["reason"]
        .as_str()
}

fn plan_order(world: &mut KanbusWorld) -> Vec<String> {
    parse_plan(world)["eligible"]
        .as_array()
        .expect("eligible plan")
        .iter()
        .map(|entry| entry["issue_id"].as_str().unwrap().to_string())
        .collect()
}

fn add_policy_rejecting_unassigned(world: &mut KanbusWorld) {
    let path = project_dir(world).join("policies/router-dispatch.policy");
    fs::create_dir_all(path.parent().unwrap()).expect("create policies");
    fs::write(
        path,
        "Feature: Routed issues need an assignee\n  Scenario: Require assignee\n    Then the issue must have field \"assignee\"\n",
    )
    .expect("write router policy fixture");
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn ensure_git_commit(world: &mut KanbusWorld) {
    let output = Command::new("git")
        .args(["rev-parse", "--verify", "HEAD"])
        .current_dir(root(world))
        .output()
        .expect("inspect fixture Git HEAD");
    if output.status.success() {
        return;
    }
    let add = Command::new("git")
        .args(["add", "-A"])
        .current_dir(root(world))
        .status()
        .expect("stage project fixture");
    assert!(add.success(), "stage initialized Kanbus fixture");
    let commit = Command::new("git")
        .args([
            "-c",
            "user.name=Router contract fixture",
            "-c",
            "user.email=router-contract@localhost",
            "commit",
            "--allow-empty",
            "-m",
            "router contract fixture base",
        ])
        .current_dir(root(world))
        .status()
        .expect("commit fixture base");
    assert!(commit.success(), "commit initialized Kanbus fixture");
}

fn start_fake_forge(world: &mut KanbusWorld) -> String {
    let root_path = root(world).to_path_buf();
    let mut servers = forge_servers().lock().expect("lock fake forge map");
    if let Some(server) = servers.get(&root_path) {
        let _ = server;
    } else {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind fake forge API");
        listener
            .set_nonblocking(true)
            .expect("set mock forge nonblocking");
        let address = listener.local_addr().unwrap();
        let stop = Arc::new(AtomicBool::new(false));
        let stop_thread = Arc::clone(&stop);
        let request_log = root_path.join(".git/router-contract-forge-requests.jsonl");
        let join = thread::spawn(move || {
            while !stop_thread.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((mut stream, _)) => {
                        let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
                        let mut request = Vec::new();
                        let mut buffer = [0_u8; 4096];
                        loop {
                            match stream.read(&mut buffer) {
                                Ok(0) => break,
                                Ok(read) => {
                                    request.extend_from_slice(&buffer[..read]);
                                    if let Some(header_end) =
                                        request.windows(4).position(|w| w == b"\r\n\r\n")
                                    {
                                        let headers =
                                            String::from_utf8_lossy(&request[..header_end]);
                                        let content_length = headers
                                            .lines()
                                            .find_map(|line| {
                                                let (name, value) = line.split_once(':')?;
                                                name.eq_ignore_ascii_case("content-length")
                                                    .then(|| value.trim().parse::<usize>().ok())
                                                    .flatten()
                                            })
                                            .unwrap_or_default();
                                        if request.len() >= header_end + 4 + content_length {
                                            break;
                                        }
                                    }
                                }
                                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                                    break;
                                }
                                Err(_) => break,
                            }
                        }
                        let raw = String::from_utf8_lossy(&request).to_string();
                        let split = raw.find("\r\n\r\n").unwrap_or(raw.len());
                        let header = &raw[..split];
                        let body = raw.get(split.saturating_add(4)..).unwrap_or("");
                        let first = header.lines().next().unwrap_or("");
                        let method = first.split_whitespace().next().unwrap_or("");
                        let path = first.split_whitespace().nth(1).unwrap_or("");
                        if let Ok(mut log) = fs::OpenOptions::new()
                            .create(true)
                            .append(true)
                            .open(&request_log)
                        {
                            let _ = writeln!(
                                log,
                                "{}",
                                json!({"method":method,"path":path,"body":body})
                            );
                        }
                        let payload = if method == "POST" {
                            let branch = serde_json::from_str::<Value>(body)
                                .ok()
                                .and_then(|value| {
                                    value
                                        .get("head")
                                        .and_then(Value::as_str)
                                        .map(str::to_string)
                                })
                                .unwrap_or_else(|| "codex/router/unknown/r1".to_string());
                            json!({"number":73,"html_url":"https://github.invalid/anthusai/kanbus/pull/73","head":{"sha":"router-fixture-head","ref":branch}}).to_string()
                        } else {
                            "[]".to_string()
                        };
                        let response = format!(
                            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                            payload.len(),
                            payload
                        );
                        let _ = stream.write_all(response.as_bytes());
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(10));
                    }
                    Err(_) => break,
                }
            }
        });
        servers.insert(
            root_path.clone(),
            ForgeServer {
                stop,
                join: Some(join),
            },
        );
        let url = format!("http://{address}");
        set_router_path(world, &["forge", "api_url"], Yaml::String(url.clone()));
        world.environment_overrides.insert(
            "GITHUB_TOKEN".to_string(),
            "router-fixture-token".to_string(),
        );
        return url;
    }
    let (_, config) = read_yaml(world);
    config
        .get("router")
        .and_then(|router| router.get("forge"))
        .and_then(|forge| forge.get("api_url"))
        .and_then(Yaml::as_str)
        .expect("fake forge API URL")
        .to_string()
}

fn stop_fake_forge(world: &mut KanbusWorld) {
    if let Some(mut server) = forge_servers()
        .lock()
        .expect("lock fake forge map")
        .remove(root(world))
    {
        server.stop.store(true, Ordering::Relaxed);
        if let Some(join) = server.join.take() {
            let _ = join.join();
        }
    }
}

/// A finished agent leaves a change in its worktree; the router rejects a
/// `completed` result that changed nothing.
pub(crate) const AGENT_WORK_LINE: &str = "printf 'work' > agent-work.txt\n";

fn argv_log_path(world: &mut KanbusWorld) -> PathBuf {
    root(world).join(".git/router-contract-adapter-argv.txt")
}

pub(crate) fn configure_fake_adapter(world: &mut KanbusWorld, result: &str) {
    ensure_git_commit(world);
    let request_log = root(world).join(".git/router-contract-adapter-request.txt");
    let stdout_capture = root(world).join(".git/router-contract-adapter-stdout.txt");
    let script = root(world).join(".git/router-contract-adapter.sh");
    let argv_log = argv_log_path(world);
    let body = format!(
        "#!/bin/sh\n{AGENT_WORK_LINE}printf '%s\\n' \"$@\" > {}\nprintf '%s' \"$5\" > {}\nprintf '%s\\n' {} > {}\ncat {}\n",
        shell_quote(&argv_log.display().to_string()),
        shell_quote(&request_log.display().to_string()),
        shell_quote(result),
        shell_quote(&stdout_capture.display().to_string()),
        shell_quote(&stdout_capture.display().to_string())
    );
    fs::write(&script, body).expect("write fake Codex adapter");
    let mut permissions = fs::metadata(&script).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&script, permissions).expect("make adapter executable");
    set_router_path(
        world,
        &["providers", "codex-default", "command"],
        Yaml::String(script.display().to_string()),
    );
    world.environment_overrides.insert(
        "KANBUS_ROUTER_FIXTURE_REQUEST".to_string(),
        request_log.display().to_string(),
    );
    let _ = start_fake_forge(world);
}

const BLOCKING_ADAPTER_STARTED: &str = "KANBUS_TEST_ROUTER_BLOCKING_ADAPTER_STARTED";
const BLOCKING_ADAPTER_RELEASE: &str = "KANBUS_TEST_ROUTER_BLOCKING_ADAPTER_RELEASE";
const STOPPED_WATCH_SECOND_PACKAGE: &str = "kbs-222";

fn configure_blocking_fake_adapter(world: &mut KanbusWorld, result: &str) {
    configure_fake_adapter(world, result);
    let request_log = root(world).join(".git/router-contract-adapter-request.txt");
    let stdout_capture = root(world).join(".git/router-contract-adapter-stdout.txt");
    let started = root(world).join(".git/router-contract-adapter-started");
    let release = root(world).join(".git/router-contract-adapter-release");
    let script = root(world).join(".git/router-contract-adapter.sh");
    let body = format!(
        "#!/bin/sh\n{AGENT_WORK_LINE}printf '%s' \"$5\" > {}\ntouch {}\nwhile [ ! -e {} ]; do sleep 0.02; done\nprintf '%s\\n' {} > {}\ncat {}\n",
        shell_quote(&request_log.display().to_string()),
        shell_quote(&started.display().to_string()),
        shell_quote(&release.display().to_string()),
        shell_quote(result),
        shell_quote(&stdout_capture.display().to_string()),
        shell_quote(&stdout_capture.display().to_string())
    );
    fs::write(&script, body).expect("write blocking fake Codex adapter");
    let mut permissions = fs::metadata(&script).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&script, permissions).expect("make blocking adapter executable");
    world.environment_overrides.insert(
        BLOCKING_ADAPTER_STARTED.to_string(),
        started.display().to_string(),
    );
    world.environment_overrides.insert(
        BLOCKING_ADAPTER_RELEASE.to_string(),
        release.display().to_string(),
    );
}

fn wait_for_blocking_adapter(world: &mut KanbusWorld, issue_id: &str) -> String {
    let started = PathBuf::from(
        world
            .environment_overrides
            .get(BLOCKING_ADAPTER_STARTED)
            .expect("blocking adapter start marker"),
    );
    let deadline = std::time::Instant::now() + Duration::from_secs(15);
    loop {
        let state = local_router_state(world);
        let active_pid = state["active_child_pid"].as_u64();
        if started.exists()
            && state["active_issue_id"] == issue_id
            && active_pid.is_some_and(process_is_running)
        {
            return state["scheduler_claim_id"]
                .as_str()
                .expect("production scheduler claim id")
                .to_string();
        }
        if std::time::Instant::now() >= deadline {
            release_blocking_adapter(world);
            let diagnostic = read_events(world)
                .into_iter()
                .rev()
                .take(8)
                .map(|event| (event.issue_id, event.payload))
                .collect::<Vec<_>>();
            panic!(
                "router did not start the blocking adapter for {issue_id}; state={state}; recent events={diagnostic:?}"
            );
        }
        thread::sleep(Duration::from_millis(20));
    }
}

fn release_blocking_adapter(world: &mut KanbusWorld) {
    let release = world
        .environment_overrides
        .get(BLOCKING_ADAPTER_RELEASE)
        .expect("blocking adapter release marker");
    fs::write(release, "finish adapter call\n").expect("release blocked adapter call");
}

fn wait_for_watch_shutdown(world: &mut KanbusWorld) {
    let deadline = std::time::Instant::now() + Duration::from_secs(15);
    loop {
        let state = local_router_state(world);
        if state["watch_pid"].is_null() {
            break;
        }
        if std::time::Instant::now() >= deadline {
            panic!("router did not shut down after stop; local state={state}");
        }
        thread::sleep(Duration::from_millis(20));
    }
    if let Some(join) = watch_threads()
        .lock()
        .expect("lock router watch threads")
        .remove(root(world))
    {
        join.join().expect("join stopped router watch");
    }
    stop_fake_forge(world);
}

fn start_blocked_watch(world: &mut KanbusWorld, issue_id: &str) -> String {
    seed_pending(world, issue_id, "agent-provider:codex-default");
    seed_pending(
        world,
        STOPPED_WATCH_SECOND_PACKAGE,
        "agent-provider:codex-default",
    );
    set_router_path(world, &["watch_interval"], Yaml::String("1s".to_string()));
    set_path(
        world,
        &["coordination", "contention_window"],
        Yaml::String("1s".to_string()),
    );
    let result = json!({
        "schema_version":1,
        "outcome":"completed",
        "summary":"completed current adapter call",
        "issue_updates":[],
        "checkpoint":null,
        "artifacts":[]
    })
    .to_string();
    configure_blocking_fake_adapter(world, &result);
    launch_watch(world);
    wait_for_blocking_adapter(world, issue_id)
}

fn local_router_state_path(world: &mut KanbusWorld) -> PathBuf {
    let output = Command::new("git")
        .args(["rev-parse", "--git-path", "kanbus/router-state.json"])
        .current_dir(root(world))
        .output()
        .expect("resolve local router-state path");
    assert!(output.status.success(), "resolve router-state path");
    let path = PathBuf::from(String::from_utf8_lossy(&output.stdout).trim());
    if path.is_absolute() {
        path
    } else {
        root(world).join(path)
    }
}

fn set_local_router_state(world: &mut KanbusWorld, value: Value) {
    let path = local_router_state_path(world);
    fs::create_dir_all(path.parent().unwrap()).expect("create local router state directory");
    fs::write(
        path,
        serde_json::to_vec_pretty(&value).expect("serialize local router state"),
    )
    .expect("write local router state");
}

fn local_router_state(world: &mut KanbusWorld) -> Value {
    fs::read(local_router_state_path(world))
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        .unwrap_or_else(|| json!({}))
}

fn seed_claim(world: &mut KanbusWorld, issue_id: &str, claim_id: &str, revision: u64) {
    let resource = format!("router:issue:{issue_id}");
    let now = now_timestamp();
    let expiry = (Utc::now() + chrono::Duration::minutes(20)).to_rfc3339();
    router_event(
        world,
        &resource,
        EventType::CoordinationClaim,
        json!({"owner":"router-contract-fixture","claim_id":claim_id,"revision":revision,"lease_expires_at":expiry,"contention_window_s":0,"ttl_s":1200}),
        &now,
    );
    router_event(
        world,
        &format!("router:{issue_id}"),
        EventType::RouterAttempt,
        json!({"action":"started","attempt":1,"claim_id":claim_id,"revision":revision,"provider_profile":"codex-default"}),
        &now,
    );
}

fn seed_request_checkpoint(
    world: &mut KanbusWorld,
    issue_id: &str,
    reference: &str,
    revision: u64,
) {
    let now = now_timestamp();
    router_event(
        world,
        &format!("router:{issue_id}"),
        EventType::RouterAttempt,
        json!({"action":"checkpoint_accepted","attempt":1,"claim_id":"previous-claim","revision":revision,"checkpoint_ref":reference,"checkpoint_revision":revision}),
        &now,
    );
    router_event(
        world,
        &format!("router:package:{issue_id}:checkpoint"),
        EventType::CoordinationResultPublished,
        json!({"resource":format!("router:package:{issue_id}:checkpoint"),"revision":revision,"artifact":reference}),
        &now,
    );
}

fn rows<'a>(step: &'a Step) -> (&'a [String], &'a [Vec<String>]) {
    let table = step.table.as_ref().expect("step table");
    (&table.rows[0], &table.rows[1..])
}

fn cell<'a>(headers: &[String], row: &'a [String], name: &str) -> &'a str {
    let index = headers
        .iter()
        .position(|header| header == name)
        .expect("table column");
    row[index].trim()
}

fn optional_cell<'a>(headers: &[String], row: &'a [String], name: &str) -> &'a str {
    headers
        .iter()
        .position(|header| header == name)
        .and_then(|index| row.get(index))
        .map_or("", |value| value.trim())
}

#[given("the issue hierarchy and labels are:")]
fn given_issue_hierarchy(world: &mut KanbusWorld, step: &Step) {
    let (headers, data) = rows(step);
    let date = Utc.with_ymd_and_hms(2026, 9, 17, 10, 0, 0).unwrap();
    for row in data {
        let labels = cell(headers, row, "labels")
            .split_whitespace()
            .map(str::to_string)
            .collect();
        let parent = match cell(headers, row, "parent") {
            "" => None,
            value => Some(value.to_string()),
        };
        seed_issue(
            world,
            cell(headers, row, "issue_id"),
            cell(headers, row, "status"),
            labels,
            parent,
            None,
            date,
            Vec::new(),
        );
    }
}

#[given(
    regex = r#"^class "(?P<class>[^\"]+)" is configured with provider profiles "(?P<profiles>[^\"]*)"$"#
)]
fn given_class_profiles(world: &mut KanbusWorld, class: String, profiles: String) {
    let profiles = profiles
        .split(',')
        .map(|item| Yaml::String(item.trim().to_string()))
        .collect();
    set_router_path(
        world,
        &["classes", &class, "providers"],
        Yaml::Sequence(profiles),
    );
    set_router_path(
        world,
        &["providers", "codex-backup", "adapter"],
        Yaml::String("codex".to_string()),
    );
}

#[given(regex = r#"^provider profile "(?P<profile>[^\"]+)" has reached its WIP limit$"#)]
fn given_provider_wip_limit(world: &mut KanbusWorld, profile: String) {
    set_router_path(
        world,
        &["limits", "provider_wip", &profile],
        Yaml::Number(1.into()),
    );
    seed_issue(
        world,
        "kbs-wip-provider",
        "in_progress",
        vec![format!("agent-provider:{profile}")],
        None,
        None,
        Utc.with_ymd_and_hms(2026, 9, 16, 10, 0, 0).unwrap(),
        Vec::new(),
    );
}

#[given("router candidates are:")]
fn given_router_candidates(world: &mut KanbusWorld, step: &Step) {
    let (headers, data) = rows(step);
    for row in data {
        let id = cell(headers, row, "issue_id");
        let state = cell(headers, row, "state");
        let pending = utc(cell(headers, row, "pending_since"));
        let created = utc(cell(headers, row, "created_at"));
        let status = if state == "recoverable_active" {
            "in_progress"
        } else {
            "open"
        };
        seed_issue(
            world,
            id,
            status,
            vec!["agent-class:implementation".to_string()],
            None,
            None,
            created,
            Vec::new(),
        );
        if state == "requested_changes" {
            router_event(
                world,
                &format!("router:{id}"),
                EventType::RouterForge,
                json!({"action":"requested_changes"}),
                &now_timestamp(),
            );
        } else if state == "pending" && pending != created {
            router_event(
                world,
                id,
                EventType::StateTransition,
                json!({"from_status":"in_progress","to_status":"open"}),
                &pending.to_rfc3339(),
            );
        }
    }
}

#[given(regex = r#"^project WIP limit is (?P<limit>\d+)$"#)]
fn given_project_wip_limit(world: &mut KanbusWorld, limit: String) {
    set_router_path(
        world,
        &["limits", "project_wip"],
        Yaml::Number(limit.parse::<i64>().unwrap().into()),
    );
}

#[given("project issues in router WIP statuses are:")]
fn given_project_wip_issues(world: &mut KanbusWorld, step: &Step) {
    let (headers, data) = rows(step);
    for row in data {
        let id = cell(headers, row, "issue_id");
        let status = cell(headers, row, "status");
        let assignee = match cell(headers, row, "assignee") {
            "" => None,
            value => Some(value.to_string()),
        };
        seed_issue(
            world,
            id,
            status,
            Vec::new(),
            None,
            assignee,
            Utc.with_ymd_and_hms(2026, 9, 16, 10, 0, 0).unwrap(),
            Vec::new(),
        );
        let issue_type = optional_cell(headers, row, "type");
        let labels = optional_cell(headers, row, "labels");
        if !issue_type.is_empty() || !labels.is_empty() {
            let mut issue = load_issue(world, id);
            if !issue_type.is_empty() {
                issue.issue_type = issue_type.to_string();
            }
            if !labels.is_empty() {
                issue.labels = labels
                    .split(',')
                    .map(str::trim)
                    .filter(|label| !label.is_empty())
                    .map(str::to_string)
                    .collect();
            }
            write_issue_fixture(world, &issue);
        }
    }
}

#[given(regex = r#"^only the "(?P<limit>[^\"]+)" WIP limit is reached$"#)]
fn given_only_wip_limit(world: &mut KanbusWorld, limit: String) {
    for field in ["project_wip", "review_wip"] {
        set_router_path(world, &["limits", field], Yaml::Number(20.into()));
    }
    match limit.as_str() {
        "project" => {
            set_router_path(world, &["limits", "review_wip"], Yaml::Number(1.into()));
            set_router_path(world, &["limits", "project_wip"], Yaml::Number(1.into()));
            seed_issue(
                world,
                "kbs-wip-human",
                "in_progress",
                vec!["agent-provider:codex-default".into()],
                None,
                Some("human@example.com".into()),
                Utc.with_ymd_and_hms(2026, 9, 16, 10, 0, 0).unwrap(),
                Vec::new(),
            );
        }
        "review" => {
            set_router_path(world, &["limits", "review_wip"], Yaml::Number(1.into()));
            seed_issue(
                world,
                "kbs-wip-review",
                "review",
                vec!["agent-provider:codex-default".into()],
                None,
                None,
                Utc.with_ymd_and_hms(2026, 9, 16, 10, 0, 0).unwrap(),
                Vec::new(),
            );
            router_event(
                world,
                "router:kbs-wip-review",
                EventType::RouterConversation,
                json!({"lifecycle": "review"}),
                &now_timestamp(),
            );
        }
        "class" => {
            set_router_path(
                world,
                &["limits", "class_wip", "implementation"],
                Yaml::Number(1.into()),
            );
            seed_issue(
                world,
                "kbs-wip-class",
                "in_progress",
                vec!["agent-class:implementation".into()],
                None,
                None,
                Utc.with_ymd_and_hms(2026, 9, 16, 10, 0, 0).unwrap(),
                Vec::new(),
            );
        }
        "provider" => {
            set_router_path(
                world,
                &["limits", "provider_wip", "codex-default"],
                Yaml::Number(1.into()),
            );
            seed_issue(
                world,
                "kbs-wip-provider",
                "in_progress",
                vec!["agent-provider:codex-default".into()],
                None,
                None,
                Utc.with_ymd_and_hms(2026, 9, 16, 10, 0, 0).unwrap(),
                Vec::new(),
            );
        }
        _ => panic!("unknown WIP limit {limit}"),
    }
}

#[given(
    "a pending package is paused, held, invalidly routed, dependency blocked, policy rejected, in retry backoff, and over every WIP limit"
)]
fn given_all_deferrals(world: &mut KanbusWorld) {
    seed_pending(world, "kbs-170", "agent-provider:codex-default");
    set_router_path(world, &["limits", "project_wip"], Yaml::Number(1.into()));
    set_router_path(world, &["limits", "review_wip"], Yaml::Number(1.into()));
    set_router_path(
        world,
        &["limits", "class_wip", "implementation"],
        Yaml::Number(1.into()),
    );
    set_router_path(
        world,
        &["limits", "provider_wip", "codex-default"],
        Yaml::Number(1.into()),
    );
    router_event(
        world,
        "router:global",
        EventType::RouterControl,
        json!({"action":"pause"}),
        &now_timestamp(),
    );
    router_event(
        world,
        "router:global",
        EventType::RouterControl,
        json!({"action":"hold","route":"provider-profile:codex-default"}),
        &now_timestamp(),
    );
    add_policy_rejecting_unassigned(world);
    router_event(
        world,
        "router:kbs-170",
        EventType::RouterAttempt,
        json!({"action":"retryable_failure","attempt":1,"next_attempt":2,"retry_at":"2099-01-01T00:00:00Z"}),
        &now_timestamp(),
    );
}

#[given(regex = r#"^issue "(?P<issue>[^\"]+)" has an unresolved blocking dependency$"#)]
fn given_blocking_dependency(world: &mut KanbusWorld, issue: String) {
    let mut value = load_issue(world, &issue);
    value.dependencies.push(DependencyLink {
        target: "kbs-dependency-open".into(),
        dependency_type: "blocked-by".into(),
    });
    fs::write(
        issue_path(world, &issue),
        serde_json::to_vec_pretty(&value).unwrap(),
    )
    .unwrap();
    seed_issue(
        world,
        "kbs-dependency-open",
        "open",
        Vec::new(),
        None,
        None,
        Utc.with_ymd_and_hms(2026, 9, 17, 9, 0, 0).unwrap(),
        Vec::new(),
    );
}

#[given(regex = r#"^project policy rejects issue "(?P<issue>[^\"]+)" for router dispatch$"#)]
fn given_policy_rejects(world: &mut KanbusWorld, _issue: String) {
    add_policy_rejecting_unassigned(world);
}

#[given(
    regex = r#"^one eligible package "(?P<issue>[^\"]+)" routed to class "(?P<class>[^\"]+)" using provider profile "(?P<profile>[^\"]+)"$"#
)]
fn given_one_eligible(world: &mut KanbusWorld, issue: String, class: String, profile: String) {
    set_router_path(
        world,
        &["classes", &class, "providers"],
        Yaml::Sequence(vec![Yaml::String(profile)]),
    );
    seed_pending(world, &issue, &format!("agent-class:{class}"));
}

#[then(regex = r#"^eligible package order should be "(?P<order>[^\"]*)"$"#)]
fn then_plan_order(world: &mut KanbusWorld, order: String) {
    assert_eq!(
        plan_order(world),
        order
            .split(',')
            .map(|item| item.trim().to_string())
            .collect::<Vec<_>>()
    );
}

#[then(regex = r#"^its deferred reason should be "(?P<reason>[^\"]+)"$"#)]
fn then_any_deferred_reason(world: &mut KanbusWorld, reason: String) {
    assert_eq!(
        deferred_reason(&parse_plan(world), "kbs-170"),
        Some(reason.as_str())
    );
}

#[then("deferred reasons should use this precedence:")]
fn then_deferred_precedence(world: &mut KanbusWorld, step: &Step) {
    let _ = world;
    let (headers, data) = rows(step);
    let actual = data
        .iter()
        .map(|row| {
            (
                cell(headers, row, "precedence").parse::<usize>().unwrap(),
                cell(headers, row, "reason").to_string(),
            )
        })
        .collect::<Vec<_>>();
    let expected = [
        "paused",
        "held",
        "invalid_route",
        "dependency_blocked",
        "policy_rejected",
        "retry_backoff",
        "project_wip_limit",
        "review_wip_limit",
        "class_wip_limit",
        "provider_wip_limit",
    ]
    .iter()
    .enumerate()
    .map(|(i, value)| (i + 1, value.to_string()))
    .collect::<Vec<_>>();
    assert_eq!(actual, expected);
}

#[given("there are no eligible router packages")]
fn given_no_packages(_world: &mut KanbusWorld) {}

#[given(regex = r#"^pending routed packages are ordered "(?P<ids>[^\"]+)"$"#)]
fn given_pending_packages(world: &mut KanbusWorld, ids: String) {
    for (ordinal, id) in ids.split(',').map(str::trim).enumerate() {
        let minute = 10 + ordinal as u32;
        let at = Utc.with_ymd_and_hms(2026, 9, 17, minute, 0, 0).unwrap();
        seed_issue(
            world,
            id,
            "open",
            vec!["agent-provider:codex-default".to_string()],
            None,
            None,
            at,
            Vec::new(),
        );
    }
}

#[given(
    regex = r#"^provider profile "(?P<profile>[^\"]+)" runs fake adapter outcome "(?P<outcome>[^\"]+)"$"#
)]
fn given_fake_adapter_outcome(world: &mut KanbusWorld, profile: String, outcome: String) {
    let result=json!({"schema_version":1,"outcome":outcome,"summary":"fixture result","issue_updates":[],"checkpoint":null,"artifacts":[]}).to_string();
    configure_fake_adapter(world, &result);
    let (_, mut config) = read_yaml(world);
    let provider = config
        .get_mut("router")
        .and_then(|router| router.get_mut("providers"))
        .and_then(Yaml::as_mapping_mut)
        .unwrap();
    let entry = provider
        .get_mut(Yaml::String(profile))
        .and_then(Yaml::as_mapping_mut)
        .unwrap();
    entry.insert(
        Yaml::String("command".into()),
        Yaml::String(
            root(world)
                .join(".git/router-contract-adapter.sh")
                .display()
                .to_string(),
        ),
    );
    write_yaml(world, &config);
}

#[given(regex = r#"^the Codex adapter returns this result:$"#)]
fn given_adapter_result(world: &mut KanbusWorld, step: &Step) {
    let mut result: Value = serde_json::from_str(step.docstring().expect("adapter result JSON"))
        .expect("valid adapter result fixture");
    let package_id = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_PACKAGE")
        .cloned();
    if let (Some(package_id), Some(checkpoint)) = (
        package_id,
        result.get_mut("checkpoint").and_then(Value::as_object_mut),
    ) {
        let current_revision = read_events(world)
            .iter()
            .filter(|event| event.issue_id == format!("router:{package_id}"))
            .filter_map(|event| event.payload.get("revision").and_then(Value::as_u64))
            .max()
            .unwrap_or_default();
        checkpoint.insert(
            "revision".to_string(),
            json!(current_revision.saturating_add(1).max(1)),
        );
    }
    configure_fake_adapter(
        world,
        &serde_json::to_string(&result).expect("serialize adjusted adapter result"),
    );
}

#[given(regex = r#"^the Codex adapter returns result outcome "(?P<outcome>[^\"]+)"$"#)]
fn given_adapter_outcome(world: &mut KanbusWorld, outcome: String) {
    let result=json!({"schema_version":1,"outcome":outcome,"summary":"fixture result","issue_updates":[],"checkpoint":null,"artifacts":[]}).to_string();
    configure_fake_adapter(world, &result);
}

fn insert_adapter_script_lines(world: &mut KanbusWorld, lines: &str) {
    let script = root(world).join(".git/router-contract-adapter.sh");
    let body = fs::read_to_string(&script).expect("read fake adapter script");
    let (shebang, rest) = body.split_once('\n').expect("script has a shebang");
    fs::write(&script, format!("{shebang}\n{lines}{rest}")).expect("rewrite fake adapter");
}

#[given(
    regex = r#"^the Codex adapter (?P<mode>edits|edits and commits) Kanbus project state in its worktree$"#
)]
fn given_adapter_edits_project_state(world: &mut KanbusWorld, mode: String) {
    let mut lines = String::from(
        "mkdir -p project/issues\nprintf '{\"edited\":true}' > project/issues/agent-edit.json\n",
    );
    if mode == "edits and commits" {
        lines.push_str(
            "git add -A -- project\ngit -c user.name=agent -c user.email=agent@example.invalid commit --no-verify -qm 'agent board commit'\n",
        );
    }
    insert_adapter_script_lines(world, &lines);
}

#[given("the Codex adapter refreshes the project cache in its worktree")]
fn given_adapter_refreshes_cache(world: &mut KanbusWorld) {
    insert_adapter_script_lines(
        world,
        "mkdir -p project/.cache\nprintf '{}' > project/.cache/index.json\n",
    );
}

#[given("the Codex adapter makes no changes in its worktree")]
fn given_adapter_makes_no_changes(world: &mut KanbusWorld) {
    let script = root(world).join(".git/router-contract-adapter.sh");
    let body = fs::read_to_string(&script).expect("read fake adapter script");
    fs::write(&script, body.replace(AGENT_WORK_LINE, "")).expect("rewrite fake adapter");
}

fn ensure_routed_issue(world: &mut KanbusWorld, id: &str, status: &str) {
    if !issue_path(world, id).exists() {
        seed_issue(
            world,
            id,
            status,
            vec!["agent-provider:codex-default".to_string()],
            None,
            None,
            Utc.with_ymd_and_hms(2026, 9, 17, 10, 0, 0).unwrap(),
            Vec::new(),
        );
    }
}

fn write_issue_fixture(world: &mut KanbusWorld, issue: &IssueData) {
    let path = issue_path(world, &issue.identifier);
    fs::write(
        path,
        serde_json::to_vec_pretty(issue).expect("serialize issue"),
    )
    .expect("write issue fixture");
}

#[given(
    regex = r#"^package "(?P<issue>[^"]+)" asked a question in session "(?P<session>[^"]+)" on branch "(?P<branch>[^"]+)"$"#
)]
fn given_package_asked_a_question(
    world: &mut KanbusWorld,
    issue: String,
    session: String,
    branch: String,
) {
    ensure_git_commit(world);
    ensure_routed_issue(world, &issue, "blocked");
    thread::sleep(Duration::from_millis(50));
    router_event(
        world,
        &format!("router:{issue}"),
        EventType::RouterConversation,
        json!({
            "action":"awaiting_reply", "provider":"codex", "lifecycle":"blocked",
            "claim_id":"claim-old", "revision":1, "session_id":session,
            "worktree":"/nonexistent/old-worktree", "branch":branch,
        }),
        &now_timestamp(),
    );
    thread::sleep(Duration::from_millis(50));
}

#[given(regex = r#"^a human replied "(?P<reply>[^"]+)" to package "(?P<issue>[^"]+)"$"#)]
fn given_human_replied(world: &mut KanbusWorld, reply: String, issue: String) {
    ensure_routed_issue(world, &issue, "blocked");
    thread::sleep(Duration::from_millis(50));
    let mut record = load_issue(world, &issue);
    record.comments.push(kanbus::models::IssueComment {
        id: None,
        author: "home".to_string(),
        text: Some(reply),
        created_at: Utc::now(),
        comment_type: "default".to_string(),
        data: BTreeMap::new(),
        agent: None,
    });
    write_issue_fixture(world, &record);
    thread::sleep(Duration::from_millis(50));
}

#[given(regex = r#"^package "(?P<issue>[^"]+)" is ready again$"#)]
fn given_package_ready_again(world: &mut KanbusWorld, issue: String) {
    ensure_routed_issue(world, &issue, "blocked");
    let mut record = load_issue(world, &issue);
    record.status = "open".to_string();
    // A human's status change is newer than the router's last lifecycle event.
    record.updated_at = Utc::now();
    write_issue_fixture(world, &record);
}

#[given(regex = r#"^package "(?P<issue>[^"]+)" is ready and has never been run$"#)]
fn given_package_ready_never_run(world: &mut KanbusWorld, issue: String) {
    ensure_routed_issue(world, &issue, "open");
}

fn adapter_argv(world: &mut KanbusWorld) -> Option<Vec<String>> {
    fs::read_to_string(argv_log_path(world))
        .ok()
        .map(|text| text.lines().map(str::to_string).collect())
}

#[then(
    regex = r#"^the adapter should resume session "(?P<session>[^"]+)" with a prompt containing "(?P<text>[^"]+)"$"#
)]
fn then_adapter_resumed_session(world: &mut KanbusWorld, session: String, text: String) {
    let argv = adapter_argv(world).expect("the adapter was never invoked");
    assert_eq!(argv.get(1).map(String::as_str), Some("resume"), "{argv:?}");
    assert!(argv.contains(&session), "{argv:?}");
    let prompt = fs::read_to_string(root(world).join(".git/router-contract-adapter-request.txt"))
        .unwrap_or_default();
    assert!(prompt.contains(&text), "prompt was: {prompt}");
}

#[then(regex = r#"^no new agent session should have been started for package "(?P<issue>[^"]+)"$"#)]
fn then_no_new_session(world: &mut KanbusWorld, _issue: String) {
    let argv = adapter_argv(world).expect("the adapter was never invoked");
    assert_eq!(argv.get(1).map(String::as_str), Some("resume"), "{argv:?}");
}

#[then(regex = r#"^the adapter should start a fresh session for package "(?P<issue>[^"]+)"$"#)]
fn then_fresh_session(world: &mut KanbusWorld, _issue: String) {
    let argv = adapter_argv(world).expect("the adapter was never invoked");
    assert_ne!(argv.get(1).map(String::as_str), Some("resume"), "{argv:?}");
}

#[then(regex = r#"^the run should use branch "(?P<branch>[^"]+)"$"#)]
fn then_run_used_branch(world: &mut KanbusWorld, branch: String) {
    let started = read_events(world)
        .into_iter()
        .filter(|event| event.issue_id == "router:kbs-401")
        .filter(|event| matches!(&event.event_type, EventType::RouterConversation))
        .filter(|event| event.payload.get("action").and_then(Value::as_str) == Some("started"))
        .filter(|event| event.payload.get("claim_id").and_then(Value::as_str) != Some("claim-old"))
        .max_by(|left, right| left.occurred_at.cmp(&right.occurred_at));
    let actual = started
        .as_ref()
        .and_then(|event| event.payload.get("branch"))
        .and_then(Value::as_str);
    assert_eq!(actual, Some(branch.as_str()), "{started:?}");
}

#[given("a fake forge is available for the router")]
fn given_fake_forge_available(world: &mut KanbusWorld) {
    let _ = start_fake_forge(world);
}

#[given("the Codex adapter writes malformed JSON to standard output")]
fn given_adapter_malformed(world: &mut KanbusWorld) {
    configure_fake_adapter(world, "not-json");
}

#[given(
    regex = r#"^the Codex adapter returns issue update "(?P<issue>[^\"]+)" to status "(?P<status>[^\"]+)"$"#
)]
fn given_adapter_issue_update(world: &mut KanbusWorld, issue: String, status: String) {
    let result=json!({"schema_version":1,"outcome":"completed","summary":"fixture result","issue_updates":[{"issue_id":issue,"status":status}],"checkpoint":null,"artifacts":[]}).to_string();
    configure_fake_adapter(world, &result);
    seed_pending(world, "kbs-999", "agent-provider:codex-default");
}

#[given(regex = r#"^package "(?P<issue>[^\"]+)" contains issues "(?P<issues>[^\"]+)"$"#)]
fn given_router_package_members(world: &mut KanbusWorld, issue: String, issues: String) {
    crate::step_definitions::revision_publication_steps::seed_router_package_members(
        world, &issue, &issues,
    );
    for member in issues
        .split(',')
        .map(str::trim)
        .filter(|member| *member != issue)
    {
        let mut child = load_issue(world, &issue);
        child.identifier = member.to_string();
        child.title = format!("Router fixture {member}");
        child.parent = Some(issue.clone());
        child.status = "open".to_string();
        fs::write(
            project_dir(world)
                .join("issues")
                .join(format!("{member}.json")),
            serde_json::to_vec_pretty(&child).expect("serialize router package child"),
        )
        .expect("write router package child with canonical id");
    }
}

#[given(
    regex = r#"^package "(?P<issue>[^\"]+)" has accepted checkpoint "(?P<reference>[^\"]+)" at revision (?P<revision>\d+)$"#
)]
fn given_accepted_checkpoint(
    world: &mut KanbusWorld,
    issue: String,
    reference: String,
    revision: String,
) {
    seed_request_checkpoint(world, &issue, &reference, revision.parse().unwrap());
}

#[when(regex = r#"^the Codex adapter starts claim "(?P<claim>[^\"]+)"$"#)]
fn when_start_adapter_claim(world: &mut KanbusWorld, _claim: String) {
    let result = json!({
        "schema_version":1,
        "outcome":"retryable_failure",
        "summary":"fixture adapter request capture",
        "issue_updates":[],
        "checkpoint":null,
        "artifacts":[]
    })
    .to_string();
    configure_fake_adapter(world, &result);
    let package = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_PACKAGE")
        .expect("current package claim fixture")
        .clone();
    let checkpoint_revision = read_events(world)
        .iter()
        .filter(|event| {
            event.issue_id == format!("router:{package}")
                && matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload["action"] == "checkpoint_accepted"
        })
        .filter_map(|event| event.payload["checkpoint_revision"].as_u64())
        .max()
        .expect("accepted checkpoint fixture");
    let issues_dir = project_dir(world).join("issues");
    let mut package_issue_ids = fs::read_dir(issues_dir)
        .expect("read package issue fixtures")
        .filter_map(Result::ok)
        .filter_map(|entry| fs::read(entry.path()).ok())
        .filter_map(|bytes| serde_json::from_slice::<IssueData>(&bytes).ok())
        .filter(|issue| issue.identifier == package || issue.parent.as_deref() == Some(&package))
        .map(|issue| issue.identifier)
        .collect::<Vec<_>>();
    package_issue_ids.sort();
    let root_path = root(world).to_path_buf();
    let fixture_temp = world
        .temp_dir
        .as_ref()
        .expect("scenario temporary directory")
        .path()
        .join("router-worktree-temp");
    fs::create_dir_all(&fixture_temp).expect("create isolated router worktree temp directory");
    let previous_tmpdir = std::env::var_os("TMPDIR");
    std::env::set_var("TMPDIR", &fixture_temp);
    let result = kanbus::router::execute_issue_router_adapter_for_claim(
        &root_path,
        &package,
        &package_issue_ids,
        "codex-default",
        &_claim,
        checkpoint_revision + 1,
    );
    if let Some(previous_tmpdir) = previous_tmpdir {
        std::env::set_var("TMPDIR", previous_tmpdir);
    } else {
        std::env::remove_var("TMPDIR");
    }
    result.unwrap_or_else(|error| panic!("direct Codex adapter invocation failed: {error}"));
}

#[when("the router publishes the completed result")]
fn when_publish_completed_result(world: &mut KanbusWorld) {
    run_cli(world, "kanbus router run --once");
}

#[then(regex = r#"^the adapter should run only package "(?P<issue>[^\"]+)"$"#)]
fn then_adapter_package(world: &mut KanbusWorld, issue: String) {
    let events = read_events(world);
    let started = events
        .iter()
        .find(|event| {
            event.issue_id == format!("router:{issue}")
                && matches!(&event.event_type, EventType::RouterAttempt)
                && event.payload["action"] == "started"
        })
        .expect("started router attempt");
    assert_eq!(
        started.payload["package_issue_ids"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(Value::as_str)
            .collect::<Vec<_>>(),
        vec![issue.as_str()]
    );
}

#[then("no adapter should have run")]
fn then_no_adapter(world: &mut KanbusWorld) {
    assert!(!read_events(world).iter().any(|event| matches!(
        &event.event_type,
        EventType::RouterAttempt
    ) && event.payload["action"] == "started"));
}

#[then("the router should publish the checkpoint and artifact references")]
fn then_publications_exist(world: &mut KanbusWorld) {
    let events = read_events(world);
    assert!(
        events.iter().any(|event| matches!(
            &event.event_type,
            EventType::CoordinationResultPublished
        ) && event.issue_id.ends_with(":checkpoint")),
        "checkpoint publication event missing"
    );
    assert!(
        events.iter().any(|event| matches!(
            &event.event_type,
            EventType::CoordinationResultPublished
        ) && event.issue_id.contains(":artifact:")),
        "artifact publication event missing"
    );
}

#[then(regex = r#"^the router should create a pull request for package "(?P<issue>[^\"]+)"$"#)]
fn then_created_pull_request(world: &mut KanbusWorld, issue: String) {
    assert!(read_events(world)
        .iter()
        .any(|event| event.issue_id == format!("router:{issue}")
            && matches!(&event.event_type, EventType::RouterForge)
            && event.payload["action"] == "opened"));
    stop_fake_forge(world);
}

#[then("the command should stay running until stopped")]
fn then_watch_still_running(world: &mut KanbusWorld) {
    // A Git-backed startup claim waits through its configured contention window.
    let deadline = std::time::Instant::now() + Duration::from_secs(15);
    loop {
        if local_router_state(world)["watch_pid"]
            .as_u64()
            .is_some_and(process_is_running)
        {
            return;
        }
        if std::time::Instant::now() >= deadline {
            let path = root(world).to_path_buf();
            let state = local_router_state(world);
            let diagnostic = watch_diagnostics()
                .lock()
                .expect("lock router watch diagnostics")
                .get(&path)
                .cloned()
                .unwrap_or_else(|| "watch runner has not returned".to_string());
            panic!("router watch did not start; local state={state}; {diagnostic}");
        }
        thread::sleep(Duration::from_millis(20));
    }
}

#[then("the router should reconcile the issue board immediately")]
fn then_watch_reconciled_immediately(world: &mut KanbusWorld) {
    wait_for_forge_poll_count(world, 1);
}

fn process_is_running(pid: u64) -> bool {
    pid <= u32::MAX as u64
        && Command::new("kill")
            .args(["-0", &pid.to_string()])
            .status()
            .is_ok_and(|status| status.success())
}

#[given(regex = r#"^router watch interval is (?P<seconds>\d+) seconds$"#)]
fn given_watch_interval(world: &mut KanbusWorld, seconds: String) {
    set_router_path(
        world,
        &["watch_interval"],
        Yaml::String(format!("{seconds}s")),
    );
    set_path(
        world,
        &["coordination", "providers"],
        Yaml::Sequence(vec![
            Yaml::String("mqtt".to_string()),
            Yaml::String("git".to_string()),
        ]),
    );
    set_path(
        world,
        &["coordination", "contention_window"],
        Yaml::String("1s".to_string()),
    );
    let _ = start_fake_forge(world);
    let _ = start_fake_mqtt(world);
}

#[given("the router scheduler is stopped")]
fn given_scheduler_stopped(world: &mut KanbusWorld) {
    set_local_router_state(world, json!({"stop_requested":false}));
}

#[given(regex = r#"^the router is watching with interval (?P<seconds>\d+) seconds$"#)]
fn given_router_watching(world: &mut KanbusWorld, seconds: String) {
    given_watch_interval(world, seconds);
    world
        .environment_overrides
        .insert("GITHUB_TOKEN".into(), "router-fixture-token".into());
    let _ = start_fake_forge(world);
}

#[given("the MQTT broker becomes unreachable")]
fn given_mqtt_unreachable(world: &mut KanbusWorld) {
    world.mosquitto_unavailable = true;
    set_path(
        world,
        &["realtime", "transport"],
        Yaml::String("mqtt".to_string()),
    );
    set_path(
        world,
        &["realtime", "broker"],
        Yaml::String("mqtt://127.0.0.1:1".to_string()),
    );
}

#[when("the router enters its next watch cycle")]
fn when_next_watch_cycle(world: &mut KanbusWorld) {
    launch_watch(world);
}

#[then(
    regex = r#"^the router should poll GitHub pull request state every (?P<seconds>\d+) seconds$"#
)]
fn then_watch_poll_interval(world: &mut KanbusWorld, seconds: String) {
    let (_, config) = read_yaml(world);
    assert_eq!(
        config["router"]["watch_interval"].as_str(),
        Some(format!("{seconds}s").as_str())
    );
    wait_for_forge_poll_count(world, 1);
}

#[then("MQTT router notifications should trigger reconciliation before the next poll")]
fn then_mqtt_wakeup(world: &mut KanbusWorld) {
    let initial_polls = wait_for_forge_poll_count(world, 1);
    let (_, config) = read_yaml(world);
    let project = config["project_key"]
        .as_str()
        .expect("configured project key");
    let topic = config["realtime"]["topics"]["project_events"]
        .as_str()
        .expect("project event MQTT topic")
        .replace("{project}", project);
    let envelope = json!({
        "id":"peer-msg-1",
        "ts":"2026-09-17T10:00:00.000Z",
        "project":project,
        "type":"coordination.claim",
        "event_id":"peer-event-1",
        "producer_id":"peer-test",
        "resource":"router:issue:kbs-watch-peer",
        "owner":"peer-worker",
        "claim_id":"peer-claim-1",
        "lease_ttl_s":300
    });
    publish_peer_mqtt(world, &topic, serde_json::to_vec(&envelope).unwrap());
    let deadline = std::time::Instant::now() + Duration::from_secs(8);
    while std::time::Instant::now() < deadline {
        if forge_poll_count(world) > initial_polls {
            stop_watch(world);
            stop_fake_forge(world);
            return;
        }
        thread::sleep(Duration::from_millis(20));
    }
    stop_watch(world);
    stop_fake_forge(world);
    panic!("MQTT notification did not trigger GitHub reconciliation before the 30-second poll");
}

fn forge_poll_count(world: &mut KanbusWorld) -> usize {
    fs::read_to_string(root(world).join(".git/router-contract-forge-requests.jsonl"))
        .unwrap_or_default()
        .lines()
        .filter(|line| {
            serde_json::from_str::<Value>(line).is_ok_and(|request| {
                request["method"] == "GET"
                    && request["path"]
                        .as_str()
                        .is_some_and(|path| path.contains("/pulls?state=all"))
            })
        })
        .count()
}

fn wait_for_forge_poll_count(world: &mut KanbusWorld, expected: usize) -> usize {
    let deadline = std::time::Instant::now() + Duration::from_secs(5);
    while std::time::Instant::now() < deadline {
        let count = forge_poll_count(world);
        if count >= expected {
            return count;
        }
        thread::sleep(Duration::from_millis(20));
    }
    panic!("router did not make {expected} GitHub pull-request poll(s)");
}

#[then("the router should continue by polling Git history every 30 seconds")]
fn then_watch_git_fallback(world: &mut KanbusWorld) {
    let (_, config) = read_yaml(world);
    assert_eq!(config["router"]["watch_interval"].as_str(), Some("30s"));
    wait_for_forge_poll_count(world, 1);
    assert!(local_router_state(world)["watch_pid"]
        .as_u64()
        .is_some_and(process_is_running));
    assert!(read_events(world).iter().all(|event| !matches!(
        &event.event_type,
        EventType::RouterResult
    ) && event.payload["outcome"] != "completed"));
    stop_watch(world);
    stop_fake_forge(world);
}

#[then("no package should be marked complete solely because MQTT is unavailable")]
fn then_no_mqtt_completion(world: &mut KanbusWorld) {
    assert!(!read_events(world)
        .iter()
        .any(|event| matches!(&event.event_type, EventType::RouterResult)
            && event.payload["outcome"] == "completed"));
    stop_fake_forge(world);
}

#[given("the Mutex API endpoint is configured but unreachable")]
fn given_mutex_endpoint_unreachable(world: &mut KanbusWorld) {
    let _ = start_fake_forge(world);
    set_path(
        world,
        &["coordination", "mutex_api", "endpoint"],
        Yaml::String("http://127.0.0.1:1".into()),
    );
    world.environment_overrides.insert(
        "KANBUS_COORDINATION_MUTEX_API_ENDPOINT".into(),
        "http://127.0.0.1:1".into(),
    );
    world.environment_overrides.insert(
        "KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN".into(),
        "router-fixture-token".into(),
    );
}

#[given(regex = r#"^pending package "(?P<issue>[^\"]+)" is eligible$"#)]
fn given_eligible_package(world: &mut KanbusWorld, issue: String) {
    seed_pending(world, &issue, "agent-provider:codex-default");
}

#[given("the router scheduler is running")]
fn given_scheduler_running(world: &mut KanbusWorld) {
    let has_routed_candidate = fs::read_dir(project_dir(world).join("issues"))
        .expect("read issue directory")
        .filter_map(Result::ok)
        .filter_map(|entry| fs::read(entry.path()).ok())
        .filter_map(|bytes| serde_json::from_slice::<IssueData>(&bytes).ok())
        .any(|issue| {
            matches!(issue.status.as_str(), "open" | "in_progress")
                && issue.labels.iter().any(|label| {
                    label.starts_with("agent-class:") || label.starts_with("agent-provider:")
                })
        });
    if !has_routed_candidate {
        seed_pending(
            world,
            "kbs-scheduler-pending",
            "agent-provider:codex-default",
        );
    }
    set_local_router_state(
        world,
        json!({"watch_pid":std::process::id(),"stop_requested":false}),
    );
}

#[given("the router is paused")]
fn given_router_paused(world: &mut KanbusWorld) {
    router_event(
        world,
        "router:global",
        EventType::RouterControl,
        json!({"action":"pause"}),
        &now_timestamp(),
    );
}

#[given(regex = r#"^provider profile "(?P<profile>[^\"]+)" is held$"#)]
fn given_profile_held(world: &mut KanbusWorld, profile: String) {
    router_event(
        world,
        "router:global",
        EventType::RouterControl,
        json!({"action":"hold","route":format!("provider-profile:{profile}")}),
        &now_timestamp(),
    );
}

#[given("provider profile \"codex-default\" and class \"implementation\" are held")]
fn given_two_holds(world: &mut KanbusWorld) {
    given_profile_held(world, "codex-default".into());
    router_event(
        world,
        "router:global",
        EventType::RouterControl,
        json!({"action":"hold","route":"class:implementation"}),
        &now_timestamp(),
    );
}

#[given("one router package is active")]
fn given_active_package(world: &mut KanbusWorld) {
    seed_issue(
        world,
        "kbs-active",
        "in_progress",
        vec!["agent-class:implementation".into()],
        None,
        None,
        Utc.with_ymd_and_hms(2026, 9, 16, 10, 0, 0).unwrap(),
        Vec::new(),
    );
    set_local_router_state(
        world,
        json!({"watch_pid":std::process::id(),"active_issue_id":"kbs-active","active_claim_id":"claim-active","active_child_pid":null}),
    );
}

#[then("the router scheduler should remain paused after restart")]
fn then_pause_persisted(world: &mut KanbusWorld) {
    run_cli(world, "kanbus router plan --json");
    assert_eq!(parse_plan(world)["paused"], true);
}

#[then(
    regex = r#"^packages pinned to provider profile "(?P<profile>[^\"]+)" should be deferred with reason "(?P<reason>[^\"]+)"$"#
)]
fn then_profile_held_defer(world: &mut KanbusWorld, profile: String, reason: String) {
    seed_pending(
        world,
        "kbs-held-provider",
        &format!("agent-provider:{profile}"),
    );
    run_cli(world, "kanbus router plan --json");
    assert_eq!(
        deferred_reason(&parse_plan(world), "kbs-held-provider"),
        Some(reason.as_str())
    );
}

#[then(
    regex = r#"^class-routed packages for "(?P<class>[^\"]+)" should be deferred with reason "(?P<reason>[^\"]+)"$"#
)]
fn then_class_held_defer(world: &mut KanbusWorld, class: String, reason: String) {
    seed_pending(world, "kbs-held-class", &format!("agent-class:{class}"));
    run_cli(world, "kanbus router plan --json");
    assert_eq!(
        deferred_reason(&parse_plan(world), "kbs-held-class"),
        Some(reason.as_str())
    );
}

#[then("the router should not be paused")]
fn then_not_paused(world: &mut KanbusWorld) {
    run_cli(world, "kanbus router plan --json");
    assert_eq!(parse_plan(world)["paused"], false);
}

#[then(regex = r#"^provider profile "(?P<profile>[^\"]+)" should remain held$"#)]
fn then_remains_held(world: &mut KanbusWorld, profile: String) {
    assert!(read_events(world).iter().any(|event| matches!(
        &event.event_type,
        EventType::RouterControl
    ) && event.payload["action"] == "hold"
        && event.payload["route"] == format!("provider-profile:{profile}")));
}

#[then(regex = r#"^stdout should equal:$"#)]
fn then_stdout_docstring(world: &mut KanbusWorld, step: &Step) {
    let expected = step.docstring().expect("stdout docstring").trim();
    let expected = format!("{expected}\n");
    assert_eq!(world.stdout.as_deref().unwrap_or(""), expected);
}

#[then(
    regex = r#"^stdout should equal the following JSON value with 2-space indentation and a trailing newline:$"#
)]
fn then_json_docstring(world: &mut KanbusWorld, step: &Step) {
    let expected = step.docstring().expect("JSON output docstring").trim();
    let actual = world.stdout.as_deref().unwrap_or("");
    let actual_json: Value = serde_json::from_str(actual).expect("stdout JSON");
    let expected_json: Value = serde_json::from_str(expected).expect("expected JSON docstring");
    assert_eq!(actual_json, expected_json);
    assert!(actual.ends_with('\n'), "JSON output must end in a newline");
    assert_two_space_json_indentation(actual);
}

fn assert_two_space_json_indentation(json_text: &str) {
    let mut depth = 0_usize;
    let mut in_string = false;
    let mut escaped = false;
    for (line_number, line) in json_text.lines().enumerate() {
        let leading_spaces = line
            .chars()
            .take_while(|character| *character == ' ')
            .count();
        let first = line.trim_start_matches(' ').chars().next();
        let expected_depth = if matches!(first, Some('}' | ']')) {
            depth.saturating_sub(1)
        } else {
            depth
        };
        assert_eq!(
            leading_spaces,
            expected_depth * 2,
            "JSON line {} must be indented two spaces per nesting level: {line:?}",
            line_number + 1
        );

        for character in line.chars() {
            if in_string {
                if escaped {
                    escaped = false;
                } else if character == '\\' {
                    escaped = true;
                } else if character == '"' {
                    in_string = false;
                }
                continue;
            }
            match character {
                '"' => in_string = true,
                '{' | '[' => depth += 1,
                '}' | ']' => {
                    depth = depth
                        .checked_sub(1)
                        .expect("balanced JSON container indentation");
                }
                _ => {}
            }
        }
    }
    assert_eq!(depth, 0, "JSON containers should be balanced");
}

#[then(regex = r#"^package "(?P<issue>[^\"]+)" should be in status "(?P<status>[^\"]+)"$"#)]
fn then_package_in_status(world: &mut KanbusWorld, issue: String, status: String) {
    assert_eq!(effective_issue_status(world, &issue), status);
}

#[given(
    regex = r#"^active package "(?P<issue>[^\"]+)" has claim "(?P<claim>[^\"]+)" and accepted checkpoint "(?P<checkpoint>[^\"]+)"$"#
)]
fn given_active_claim_checkpoint(
    world: &mut KanbusWorld,
    issue: String,
    claim: String,
    checkpoint: String,
) {
    seed_issue(
        world,
        &issue,
        "in_progress",
        vec!["agent-provider:codex-default".into()],
        None,
        None,
        Utc.with_ymd_and_hms(2026, 9, 17, 9, 0, 0).unwrap(),
        Vec::new(),
    );
    seed_claim(world, &issue, &claim, 1);
    seed_request_checkpoint(world, &issue, &checkpoint, 1);
    set_local_router_state(
        world,
        json!({"active_issue_id":issue,"active_claim_id":claim,"active_child_pid":null}),
    );
}

#[given(
    regex = r#"^provider profile "(?P<profile>[^\"]+)" is running package "(?P<issue>[^\"]+)"$"#
)]
fn given_profile_running_package(world: &mut KanbusWorld, _profile: String, issue: String) {
    let mut state = local_router_state(world);
    state["active_issue_id"] = json!(issue);
    state["active_claim_id"] = json!("claim-210");
    state["active_child_pid"] = json!(spawn_fixture_child(world));
    set_local_router_state(world, state);
}

#[then(
    regex = r#"^the adapter should receive a cancellation request for claim "(?P<claim>[^\"]+)"$"#
)]
fn then_cancel_request(world: &mut KanbusWorld, claim: String) {
    assert!(read_events(world).iter().any(|event| matches!(
        &event.event_type,
        EventType::RouterControl
    ) && event.payload["action"] == "cancel"
        && event.issue_id == "router:kbs-210"));
    assert_eq!(local_router_state(world)["active_claim_id"], Value::Null);
    assert!(!claim.is_empty());
    cleanup_fixture_child(world);
}

#[then(regex = r#"^checkpoint "(?P<checkpoint>[^\"]+)" should remain accepted$"#)]
fn then_checkpoint_accepted(world: &mut KanbusWorld, checkpoint: String) {
    assert!(read_events(world).iter().any(|event| matches!(
        &event.event_type,
        EventType::RouterAttempt
    ) && event.payload["checkpoint_ref"]
        == checkpoint));
}

#[given(regex = r#"^the router scheduler is running package "(?P<issue>[^\"]+)"$"#)]
fn given_running_package(world: &mut KanbusWorld, issue: String) {
    let _scheduler_claim_id = start_blocked_watch(world, &issue);
}

#[then("package \"kbs-220\" should be allowed to finish its current adapter call")]
fn then_current_adapter_kept_running(world: &mut KanbusWorld) {
    let state = local_router_state(world);
    let active = state["stop_requested"].as_bool().unwrap_or(false)
        && state["active_issue_id"] == "kbs-220"
        && state["active_child_pid"]
            .as_u64()
            .is_some_and(process_is_running);
    release_blocking_adapter(world);
    wait_for_watch_shutdown(world);
    assert!(
        active,
        "adapter was not active when stop was requested: {state}"
    );
}

#[then("the router scheduler should stop before starting another package")]
fn then_stopped_scheduler(world: &mut KanbusWorld) {
    assert!(local_router_state(world)["watch_pid"].is_null());
    assert!(read_events(world).iter().any(|event| {
        event.issue_id == "router:kbs-220"
            && matches!(&event.event_type, EventType::RouterResult)
            && event.payload["outcome"] == "completed"
    }));
    assert_eq!(effective_issue_status(world, "kbs-220"), "review");
    assert!(!read_events(world).iter().any(|event| {
        event.issue_id == format!("router:{STOPPED_WATCH_SECOND_PACKAGE}")
            && matches!(&event.event_type, EventType::RouterAttempt)
            && event.payload["action"] == "started"
    }));
}

#[then("the router scheduler holds claim \"scheduler-1\" and runs package \"kbs-221\"")]
fn then_scheduler_holds_claim(world: &mut KanbusWorld) {
    assert_eq!(world.exit_code, Some(0));
}

#[given(
    regex = r#"^the router scheduler holds claim "(?P<claim>[^\"]+)" and runs package "(?P<issue>[^\"]+)"$"#
)]
fn given_scheduler_claim_running(world: &mut KanbusWorld, claim: String, issue: String) {
    let scheduler_claim_id = start_blocked_watch(world, &issue);
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_SCHEDULER_CLAIM_LABEL".to_string(),
        claim,
    );
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_SCHEDULER_CLAIM_ID".to_string(),
        scheduler_claim_id,
    );
}

#[when(regex = r#"^package "(?P<issue>[^\"]+)" finishes its current adapter call$"#)]
fn when_scheduler_package_finishes(world: &mut KanbusWorld, _issue: String) {
    release_blocking_adapter(world);
    wait_for_watch_shutdown(world);
}

#[then(regex = r#"^the router scheduler should release claim "(?P<claim>[^\"]+)"$"#)]
fn then_scheduler_claim_released(world: &mut KanbusWorld, claim: String) {
    assert_eq!(
        world
            .environment_overrides
            .get("KANBUS_TEST_ROUTER_SCHEDULER_CLAIM_LABEL")
            .map(String::as_str),
        Some(claim.as_str())
    );
    let actual_claim_id = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_SCHEDULER_CLAIM_ID")
        .expect("actual production scheduler claim id")
        .clone();
    let events = read_events(world);
    assert!(
        events.iter().any(|event| {
            event.issue_id == "router:scheduler"
                && matches!(&event.event_type, EventType::CoordinationClaim)
                && event.payload["claim_id"].as_str() == Some(actual_claim_id.as_str())
        }),
        "production scheduler claim was not recorded: {events:?}"
    );
    assert!(
        events.iter().any(|event| {
            event.issue_id == "router:scheduler"
                && matches!(&event.event_type, EventType::CoordinationRelease)
                && event.payload["claim_id"].as_str() == Some(actual_claim_id.as_str())
        }),
        "production shutdown did not release {actual_claim_id}: {events:?}"
    );
    let output = run_from_args_in_blocking_thread(
        vec![
            "kanbus".into(),
            "coordination".into(),
            "inspect".into(),
            "--resource".into(),
            "router:scheduler".into(),
        ],
        root(world),
    )
    .expect("inspect scheduler lease");
    assert!(
        output.stdout.contains("eligible") || output.stdout.contains("no active"),
        "scheduler lease still active: {}",
        output.stdout
    );
}

#[then("the scheduler should not start another package")]
fn then_no_next_scheduler_package(world: &mut KanbusWorld) {
    assert!(local_router_state(world)["watch_pid"].is_null());
    assert!(!read_events(world).iter().any(|event| {
        event.issue_id == format!("router:{STOPPED_WATCH_SECOND_PACKAGE}")
            && matches!(&event.event_type, EventType::RouterAttempt)
            && event.payload["action"] == "started"
    }));
}

#[then("Kanbus history should contain router control events in command order:")]
fn then_control_history_order(world: &mut KanbusWorld, step: &Step) {
    let (headers, data) = rows(step);
    let actual = read_events(world)
        .into_iter()
        .filter(|event| matches!(&event.event_type, EventType::RouterControl))
        .collect::<Vec<_>>();
    let mut index = 0;
    for row in data {
        let wanted = match cell(headers, row, "event") {
            "router_paused" => "pause",
            "route_held" => "hold",
            other => panic!("unsupported control fixture {other}"),
        };
        let event = actual[index..]
            .iter()
            .find(|event| event.payload["action"] == wanted)
            .expect("control event in requested order");
        if cell(headers, row, "target").is_empty() {
            assert_eq!(event.issue_id, "router:global");
        } else {
            assert_eq!(event.payload["route"], cell(headers, row, "target"));
        }
        index += actual[index..]
            .iter()
            .position(|candidate| candidate.event_id == event.event_id)
            .unwrap()
            + 1;
    }
}

#[given(
    regex = r#"^package "(?P<issue>[^\"]+)" completes at logical revision (?P<revision>\d+) on branch "(?P<branch>[^\"]+)"$"#
)]
fn given_package_completes(
    world: &mut KanbusWorld,
    issue: String,
    revision: String,
    branch: String,
) {
    let revision = revision.parse::<u64>().unwrap();
    seed_pending(world, &issue, "agent-provider:codex-default");
    if issue == "kbs-501" {
        let mut package = load_issue(world, &issue);
        package.title = "Implement router planning".to_string();
        fs::write(
            issue_path(world, &issue),
            serde_json::to_vec_pretty(&package).expect("serialize GitHub title fixture"),
        )
        .expect("write GitHub title fixture");
    }
    for prior in 1..revision {
        seed_request_checkpoint(
            world,
            &issue,
            &format!("refs/kanbus/router/checkpoints/{issue}"),
            prior,
        );
    }
    let output=json!({"schema_version":1,"outcome":"completed","summary":"Implement router planning","issue_updates":[],"checkpoint":{"ref":format!("refs/kanbus/router/checkpoints/{issue}"),"revision":revision},"artifacts":[]}).to_string();
    configure_fake_adapter(world, &output);
    let desired = branch;
    world
        .environment_overrides
        .insert("KANBUS_ROUTER_EXPECTED_BRANCH".into(), desired);
}

#[then(regex = r#"^the adapter request should include only issues "(?P<issues>[^\"]+)"$"#)]
fn then_adapter_package_request(world: &mut KanbusWorld, issues: String) {
    let prompt = match read_adapter_prompt(world) {
        Ok(prompt) => prompt,
        Err(error) => {
            let exit_code = world.exit_code;
            let stdout = world.stdout.clone().unwrap_or_default();
            let stderr = world.stderr.clone().unwrap_or_default();
            let recent_events = read_events(world)
                .into_iter()
                .rev()
                .take(8)
                .map(|event| (event.issue_id, event.payload))
                .collect::<Vec<_>>();
            panic!(
                "adapter request capture failed ({error}); exit={exit_code:?}, stdout={stdout:?}, stderr={stderr:?}, recent events={recent_events:?}"
            );
        }
    };
    let package_ids = prompt
        .split_once("Only update issue IDs in this package: ")
        .and_then(|(_, rest)| rest.split_once(". Current claim ").map(|(ids, _)| ids))
        .expect("adapter prompt has bounded-package section")
        .split(", ")
        .map(str::to_string)
        .collect::<Vec<_>>();
    let mut expected_ids = issues
        .split(',')
        .map(str::trim)
        .map(str::to_string)
        .collect::<Vec<_>>();
    expected_ids.sort();
    assert_eq!(
        package_ids, expected_ids,
        "adapter package membership: {prompt}"
    );
}

fn read_adapter_prompt(world: &mut KanbusWorld) -> std::io::Result<String> {
    fs::read_to_string(root(world).join(".git/router-contract-adapter-request.txt"))
}

#[then(
    regex = r#"^the adapter request should include checkpoint "(?P<reference>[^\"]+)" at revision (?P<revision>\d+)$"#
)]
fn then_adapter_checkpoint_request(world: &mut KanbusWorld, reference: String, revision: String) {
    let prompt = read_adapter_prompt(world).expect("adapter request capture");
    let checkpoint = prompt
        .split_once("Latest accepted checkpoint: ")
        .and_then(|(_, rest)| {
            rest.split_once(". Return one JSON object ")
                .map(|(value, _)| value)
        })
        .expect("adapter prompt has checkpoint section");
    let actual: Value =
        serde_json::from_str(checkpoint).expect("checkpoint JSON in adapter prompt");
    assert_eq!(
        actual,
        json!({"ref":reference,"revision":revision.parse::<u64>().unwrap()}),
        "adapter checkpoint: {prompt}"
    );
}

#[then(
    regex = r#"^the adapter request should include claim "(?P<claim>[^\"]+)" at logical revision (?P<revision>\d+)$"#
)]
fn then_adapter_claim_request(world: &mut KanbusWorld, claim: String, revision: String) {
    let prompt = read_adapter_prompt(world).expect("adapter request capture");
    let (actual_claim, actual_revision) = prompt
        .split_once("Current claim ")
        .and_then(|(_, rest)| rest.split_once(" has logical revision "))
        .expect("adapter prompt has claim section");
    let actual_revision = actual_revision
        .split_once(". Latest accepted checkpoint: ")
        .map(|(value, _)| value)
        .expect("adapter prompt has revision delimiter");
    assert_eq!(actual_claim, claim, "adapter claim: {prompt}");
    assert_eq!(actual_revision, revision, "adapter revision: {prompt}");
}

#[then(regex = r#"^package "(?P<issue>[^\"]+)" should receive a retry time$"#)]
fn then_retry_time(world: &mut KanbusWorld, issue: String) {
    assert!(read_events(world)
        .iter()
        .any(|event| event.issue_id == format!("router:{issue}")
            && matches!(&event.event_type, EventType::RouterAttempt)
            && event.payload["retry_at"].as_str().is_some()));
    stop_fake_forge(world);
}

pub(crate) fn capture_issue_statuses(world: &mut KanbusWorld) {
    let snapshot = fs::read_dir(project_dir(world).join("issues"))
        .expect("read issue directory")
        .filter_map(Result::ok)
        .filter_map(|entry| fs::read(entry.path()).ok())
        .filter_map(|bytes| serde_json::from_slice::<IssueData>(&bytes).ok())
        .map(|issue| (issue.identifier, issue.status))
        .collect::<BTreeMap<_, _>>();
    world.environment_overrides.insert(
        "KANBUS_TEST_ROUTER_STATUS_SNAPSHOT".to_string(),
        serde_json::to_string(&snapshot).expect("serialize issue status snapshot"),
    );
}

#[then("no issue status should change")]
fn then_no_status_change(world: &mut KanbusWorld) {
    let expected: BTreeMap<String, String> = world
        .environment_overrides
        .get("KANBUS_TEST_ROUTER_STATUS_SNAPSHOT")
        .and_then(|snapshot| serde_json::from_str(snapshot).ok())
        .expect("issue statuses captured before router execution");
    let actual = fs::read_dir(project_dir(world).join("issues"))
        .expect("read issue directory")
        .filter_map(Result::ok)
        .filter_map(|entry| fs::read(entry.path()).ok())
        .filter_map(|bytes| serde_json::from_slice::<IssueData>(&bytes).ok())
        .map(|issue| (issue.identifier, issue.status))
        .collect::<BTreeMap<_, _>>();
    assert_eq!(actual, expected);
}

#[then("the router should open a pull request with title \"[kbs-501] Implement router planning\"")]
fn then_forge_title(world: &mut KanbusWorld) {
    assert_forge_body(world, |body| {
        body["title"] == "[kbs-501] Implement router planning"
    });
}

#[then(regex = r#"^the pull request should use head branch "(?P<branch>[^\"]+)"$"#)]
fn then_forge_head(world: &mut KanbusWorld, branch: String) {
    assert_forge_body(world, |body| body["head"] == branch);
}

#[then(regex = r#"^the pull request should use base branch "(?P<branch>[^\"]+)"$"#)]
fn then_forge_base(world: &mut KanbusWorld, branch: String) {
    assert_forge_body(world, |body| body["base"] == branch);
}

#[then(regex = r#"^the pull request body should include "(?P<text>[^\"]+)"$"#)]
fn then_forge_body(world: &mut KanbusWorld, text: String) {
    assert_forge_body(world, |body| {
        body["body"]
            .as_str()
            .is_some_and(|body| body.contains(&text))
    });
    stop_fake_forge(world);
}

fn assert_forge_body(world: &mut KanbusWorld, predicate: impl FnOnce(Value) -> bool) {
    let path = root(world).join(".git/router-contract-forge-requests.jsonl");
    let lines = fs::read_to_string(path).expect("forge request log");
    let body = lines
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .find(|item| item["method"] == "POST")
        .expect("pull-request POST")["body"]
        .as_str()
        .map(|body| serde_json::from_str::<Value>(body).expect("parse PR request body"))
        .expect("request body JSON");
    assert!(predicate(body));
}
