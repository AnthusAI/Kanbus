use std::ffi::OsString;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use cucumber::{given, then, when};
use serde_json::Value;
use tempfile::TempDir;

use crate::step_definitions::command_steps::run_cli_command;
use crate::step_definitions::initialization_steps::KanbusWorld;

/// How the stub MQTT broker treats an accepted connection.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum StubBrokerMode {
    Answering,
    Silent,
}

/// A minimal MQTT 3.1.1 broker that records published events.
#[derive(Debug)]
struct StubMqttBroker {
    port: u16,
    connections: Arc<AtomicUsize>,
    published: Arc<Mutex<Vec<Value>>>,
    stopping: Arc<AtomicBool>,
}

impl StubMqttBroker {
    fn start(mode: StubBrokerMode) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind stub broker");
        listener.set_nonblocking(true).expect("nonblocking");
        let port = listener.local_addr().expect("address").port();
        let connections = Arc::new(AtomicUsize::new(0));
        let published = Arc::new(Mutex::new(Vec::new()));
        let stopping = Arc::new(AtomicBool::new(false));
        let accept_connections = Arc::clone(&connections);
        let accept_published = Arc::clone(&published);
        let accept_stopping = Arc::clone(&stopping);
        thread::spawn(move || {
            while !accept_stopping.load(Ordering::SeqCst) {
                match listener.accept() {
                    Ok((stream, _)) => {
                        accept_connections.fetch_add(1, Ordering::SeqCst);
                        let published = Arc::clone(&accept_published);
                        let stopping = Arc::clone(&accept_stopping);
                        thread::spawn(move || serve_connection(stream, mode, published, stopping));
                    }
                    Err(_) => thread::sleep(Duration::from_millis(10)),
                }
            }
        });
        Self {
            port,
            connections,
            published,
            stopping,
        }
    }

    fn url(&self) -> String {
        format!("mqtt://127.0.0.1:{}", self.port)
    }
}

impl Drop for StubMqttBroker {
    fn drop(&mut self) {
        self.stopping.store(true, Ordering::SeqCst);
    }
}

fn read_remaining_length(stream: &mut TcpStream) -> Option<usize> {
    let mut multiplier = 1usize;
    let mut value = 0usize;
    loop {
        let mut byte = [0u8; 1];
        stream.read_exact(&mut byte).ok()?;
        value += (byte[0] & 0x7f) as usize * multiplier;
        if byte[0] & 0x80 == 0 {
            return Some(value);
        }
        multiplier *= 128;
    }
}

fn serve_connection(
    mut stream: TcpStream,
    mode: StubBrokerMode,
    published: Arc<Mutex<Vec<Value>>>,
    stopping: Arc<AtomicBool>,
) {
    stream
        .set_read_timeout(Some(Duration::from_millis(100)))
        .expect("read timeout");
    if mode == StubBrokerMode::Silent {
        while !stopping.load(Ordering::SeqCst) {
            thread::sleep(Duration::from_millis(50));
        }
        return;
    }
    loop {
        if stopping.load(Ordering::SeqCst) {
            return;
        }
        let mut header = [0u8; 1];
        match stream.read_exact(&mut header) {
            Ok(()) => {}
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                ) =>
            {
                continue
            }
            Err(_) => return,
        }
        stream.set_read_timeout(None).expect("blocking reads");
        let Some(length) = read_remaining_length(&mut stream) else {
            return;
        };
        let mut body = vec![0u8; length];
        if stream.read_exact(&mut body).is_err() {
            return;
        }
        stream
            .set_read_timeout(Some(Duration::from_millis(100)))
            .expect("read timeout");
        match header[0] >> 4 {
            1 => {
                let _ = stream.write_all(&[0x20, 0x02, 0x00, 0x00]);
            }
            3 => {
                let topic_length = u16::from_be_bytes([body[0], body[1]]) as usize;
                let payload = &body[2 + topic_length..];
                if let Ok(event) = serde_json::from_slice::<Value>(payload) {
                    published.lock().expect("lock published").push(event);
                }
            }
            12 => {
                let _ = stream.write_all(&[0xd0, 0x00]);
            }
            14 => return,
            _ => {}
        }
    }
}

/// State shared by the CLI realtime default scenarios.
#[derive(Debug, Default)]
pub struct RealtimeCliState {
    stub_broker: Option<StubMqttBroker>,
    closed_port: Option<u16>,
    launch_recorder_directory: Option<TempDir>,
    launch_marker: Option<PathBuf>,
    original_environment: Vec<(String, Option<OsString>)>,
    broker_discovery_path: Option<PathBuf>,
    last_command_elapsed: Option<Duration>,
}

impl RealtimeCliState {
    fn remember_environment(&mut self, name: &str) {
        if !self
            .original_environment
            .iter()
            .any(|(recorded, _)| recorded == name)
        {
            self.original_environment
                .push((name.to_string(), std::env::var_os(name)));
        }
    }
}

impl Drop for RealtimeCliState {
    fn drop(&mut self) {
        for (name, original) in self.original_environment.drain(..).rev() {
            match original {
                Some(value) => std::env::set_var(&name, value),
                None => std::env::remove_var(&name),
            }
        }
        if let Some(path) = self.broker_discovery_path.take() {
            let _ = fs::remove_file(path);
        }
    }
}

fn set_scenario_environment(world: &mut KanbusWorld, name: &str, value: &str) {
    world.realtime_cli.remember_environment(name);
    std::env::set_var(name, value);
}

fn closed_local_port() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
    listener.local_addr().expect("address").port()
}

fn write_broker_discovery(world: &mut KanbusWorld, endpoint: &str) {
    let home = PathBuf::from(std::env::var_os("HOME").expect("HOME"));
    let run_directory = home.join(".kanbus").join("run");
    fs::create_dir_all(&run_directory).expect("run directory");
    let path = run_directory.join("broker.json");
    let record = serde_json::json!({
        "kind": "mosquitto",
        "endpoint": endpoint,
        "pid": 1,
        "started_by": "kbs",
        "started_at": "2026-01-01T00:00:00.000Z",
        "log_path": "/dev/null",
        "conf_path": "/dev/null",
        "ttl_s": 86400,
    });
    fs::write(&path, record.to_string()).expect("write broker discovery");
    world.realtime_cli.broker_discovery_path = Some(path);
}

fn stub_broker(world: &KanbusWorld) -> &StubMqttBroker {
    world
        .realtime_cli
        .stub_broker
        .as_ref()
        .expect("stub MQTT broker not started")
}

#[given("a stub MQTT broker on a free port")]
fn given_stub_broker(world: &mut KanbusWorld) {
    world.realtime_cli.stub_broker = Some(StubMqttBroker::start(StubBrokerMode::Answering));
}

#[given("an MQTT broker on a free port that accepts connections and never answers")]
fn given_silent_broker(world: &mut KanbusWorld) {
    world.realtime_cli.stub_broker = Some(StubMqttBroker::start(StubBrokerMode::Silent));
}

#[given("broker discovery points at the stub MQTT broker")]
fn given_discovery_points_at_stub(world: &mut KanbusWorld) {
    let endpoint = stub_broker(world).url();
    write_broker_discovery(world, &endpoint);
}

#[given("broker discovery points at a closed port")]
fn given_discovery_points_at_closed_port(world: &mut KanbusWorld) {
    let port = closed_local_port();
    world.realtime_cli.closed_port = Some(port);
    write_broker_discovery(world, &format!("mqtt://127.0.0.1:{port}"));
}

#[given("the realtime broker is the stub MQTT broker")]
fn given_realtime_broker_is_stub(world: &mut KanbusWorld) {
    let endpoint = stub_broker(world).url();
    set_scenario_environment(world, "KANBUS_REALTIME_BROKER", &endpoint);
}

#[given("the realtime broker is a closed port")]
fn given_realtime_broker_is_closed_port(world: &mut KanbusWorld) {
    let port = closed_local_port();
    world.realtime_cli.closed_port = Some(port);
    set_scenario_environment(
        world,
        "KANBUS_REALTIME_BROKER",
        &format!("mqtt://127.0.0.1:{port}"),
    );
}

#[given("realtime autostart is requested")]
fn given_autostart_requested(world: &mut KanbusWorld) {
    set_scenario_environment(world, "KANBUS_REALTIME_AUTOSTART", "true");
}

#[given("a mosquitto executable that records its launches")]
fn given_launch_recorder(world: &mut KanbusWorld) {
    let directory = TempDir::new().expect("launch recorder directory");
    let marker = directory.path().join("launched");
    let script = directory.path().join("mosquitto");
    fs::write(
        &script,
        format!(
            "#!/bin/sh\necho launched >> \"{}\"\nsleep 1\n",
            marker.display()
        ),
    )
    .expect("write recorder");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&script, fs::Permissions::from_mode(0o755)).expect("chmod");
    }
    let existing_path = std::env::var_os("PATH").unwrap_or_default();
    let mut entries = vec![directory.path().to_path_buf()];
    entries.extend(std::env::split_paths(&existing_path));
    let joined = std::env::join_paths(entries).expect("join PATH");
    world.realtime_cli.remember_environment("PATH");
    std::env::set_var("PATH", joined);
    world
        .realtime_cli
        .remember_environment("KANBUS_TEST_MOSQUITTO_UNAVAILABLE");
    std::env::remove_var("KANBUS_TEST_MOSQUITTO_UNAVAILABLE");
    world.realtime_cli.launch_marker = Some(marker);
    world.realtime_cli.launch_recorder_directory = Some(directory);
}

#[when(expr = "I run {string} and time it")]
fn when_run_and_time(world: &mut KanbusWorld, command: String) {
    let started = Instant::now();
    run_cli_command(world, &command);
    world.realtime_cli.last_command_elapsed = Some(started.elapsed());
}

#[then(expr = "the command should have finished within {int} seconds")]
fn then_finished_within(world: &mut KanbusWorld, seconds: u64) {
    let elapsed = world
        .realtime_cli
        .last_command_elapsed
        .expect("command was not timed");
    assert!(
        elapsed <= Duration::from_secs(seconds),
        "command took {elapsed:?}, limit {seconds}s"
    );
}

#[then("the stub MQTT broker should have received no connections")]
fn then_stub_no_connections(world: &mut KanbusWorld) {
    thread::sleep(Duration::from_millis(300));
    let connections = stub_broker(world).connections.load(Ordering::SeqCst);
    assert_eq!(
        connections, 0,
        "stub broker received {connections} connections"
    );
}

#[then(
    expr = "the stub MQTT broker should receive an {string} event for the issue titled {string}"
)]
fn then_stub_received_event(world: &mut KanbusWorld, event_type: String, title: String) {
    let published = Arc::clone(&stub_broker(world).published);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let found = published
            .lock()
            .expect("lock published")
            .iter()
            .any(|event| {
                event["type"].as_str() == Some(event_type.as_str())
                    && event["issue"]["title"].as_str() == Some(title.as_str())
            });
        if found {
            return;
        }
        if Instant::now() >= deadline {
            panic!(
                "stub broker did not receive {event_type} for {title}: {:?}",
                published.lock().expect("lock published")
            );
        }
        thread::sleep(Duration::from_millis(25));
    }
}

#[then("no mosquitto launch should have been recorded")]
fn then_no_launch(world: &mut KanbusWorld) {
    thread::sleep(Duration::from_millis(300));
    let marker = world
        .realtime_cli
        .launch_marker
        .as_ref()
        .expect("launch recorder not installed");
    assert!(!marker.exists(), "mosquitto was launched");
}
