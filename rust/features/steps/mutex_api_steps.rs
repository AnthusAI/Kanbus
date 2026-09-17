use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use chrono::DateTime;
use cucumber::{given, then, when};
use serde_json::{json, Value};

use kanbus::coordination::parse_duration_seconds;
use kanbus::file_io::get_configuration_path;

use crate::step_definitions::initialization_steps::{
    run_from_args_in_blocking_thread, KanbusWorld,
};

const TEST_BEARER_TOKEN: &str = "mutex-api-test-token";

/// Small in-process HTTP fixture used by the Mutex API Gherkin scenarios.
#[derive(Debug)]
pub struct MutexApiFixture {
    pub endpoint: String,
    pub leases: Arc<Mutex<HashMap<String, Value>>>,
    pub last_response: Arc<Mutex<Option<(u16, Vec<u8>)>>>,
    shutdown: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

impl MutexApiFixture {
    fn start() -> std::io::Result<Self> {
        let listener = TcpListener::bind("127.0.0.1:0")?;
        let address = listener.local_addr()?;
        listener.set_nonblocking(true)?;
        let leases = Arc::new(Mutex::new(HashMap::new()));
        let last_response = Arc::new(Mutex::new(None));
        let shutdown = Arc::new(AtomicBool::new(false));
        let thread_shutdown = Arc::clone(&shutdown);
        let thread_leases = Arc::clone(&leases);
        let thread_response = Arc::clone(&last_response);
        let thread = thread::spawn(move || {
            while !thread_shutdown.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((stream, _)) => handle_request(stream, &thread_leases, &thread_response),
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(5));
                    }
                    Err(_) => break,
                }
            }
        });
        Ok(Self {
            endpoint: format!("http://{address}"),
            leases,
            last_response,
            shutdown,
            thread: Some(thread),
        })
    }
}

impl Drop for MutexApiFixture {
    fn drop(&mut self) {
        self.shutdown.store(true, Ordering::Relaxed);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

fn now_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn decode_path_segment(value: &str) -> Option<String> {
    let bytes = value.as_bytes();
    let mut decoded = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' {
            let high = *bytes.get(index + 1)?;
            let low = *bytes.get(index + 2)?;
            let digit = |byte: u8| -> Option<u8> {
                match byte {
                    b'0'..=b'9' => Some(byte - b'0'),
                    b'a'..=b'f' => Some(byte - b'a' + 10),
                    b'A'..=b'F' => Some(byte - b'A' + 10),
                    _ => None,
                }
            };
            decoded.push(digit(high)? * 16 + digit(low)?);
            index += 3;
        } else {
            decoded.push(bytes[index]);
            index += 1;
        }
    }
    String::from_utf8(decoded).ok()
}

fn handle_request(
    mut stream: TcpStream,
    leases: &Arc<Mutex<HashMap<String, Value>>>,
    last_response: &Arc<Mutex<Option<(u16, Vec<u8>)>>>,
) {
    let Ok(reader_stream) = stream.try_clone() else {
        return;
    };
    let mut reader = BufReader::new(reader_stream);
    let mut request_line = String::new();
    if reader.read_line(&mut request_line).is_err() || request_line.is_empty() {
        return;
    }
    let mut content_length = 0usize;
    let mut authorization = String::new();
    loop {
        let mut line = String::new();
        if reader.read_line(&mut line).is_err() || line == "\r\n" || line.is_empty() {
            break;
        }
        if let Some((name, value)) = line.split_once(':') {
            if name.eq_ignore_ascii_case("content-length") {
                content_length = value.trim().parse().unwrap_or(0);
            } else if name.eq_ignore_ascii_case("authorization") {
                authorization = value.trim().to_string();
            }
        }
    }
    let mut body = vec![0; content_length];
    if reader.read_exact(&mut body).is_err() {
        return;
    }
    let parts: Vec<&str> = request_line.split_whitespace().collect();
    if parts.len() < 2 {
        return;
    }
    let method = parts[0];
    let path = parts[1];
    let route = "/api/coordination/leases/";
    let response = if authorization != format!("Bearer {TEST_BEARER_TOKEN}") {
        (401, json!({"message": "unauthorized"}).to_string())
    } else if let Some(resource) = path.strip_prefix(route).and_then(decode_path_segment) {
        let request_body = serde_json::from_slice::<Value>(&body).unwrap_or(Value::Null);
        fixture_operation(method, &resource, &request_body, leases)
    } else {
        (404, json!({"message": "no live lease"}).to_string())
    };
    let (status, response_body) = response;
    let status_text = match status {
        200 => "OK",
        201 => "Created",
        204 => "No Content",
        401 => "Unauthorized",
        403 => "Forbidden",
        404 => "Not Found",
        409 => "Conflict",
        _ => "Bad Request",
    };
    let response_bytes = response_body.into_bytes();
    if let Ok(mut last) = last_response.lock() {
        *last = Some((status, response_bytes.clone()));
    }
    let content_type = if status == 204 {
        ""
    } else {
        "Content-Type: application/json\r\n"
    };
    let _ = write!(
        stream,
        "HTTP/1.1 {status} {status_text}\r\n{content_type}Content-Length: {}\r\nConnection: close\r\n\r\n",
        response_bytes.len()
    );
    let _ = stream.write_all(&response_bytes);
}

fn fixture_operation(
    method: &str,
    resource: &str,
    request: &Value,
    leases: &Arc<Mutex<HashMap<String, Value>>>,
) -> (u16, String) {
    let mut leases = leases.lock().expect("mutex API fixture lease lock");
    let now = now_seconds();
    match method {
        "POST" => {
            if leases
                .get(resource)
                .and_then(|lease| lease.get("expires_at"))
                .and_then(Value::as_u64)
                .is_some_and(|expires_at| expires_at > now)
            {
                return (409, json!({"message": "lease already held"}).to_string());
            }
            let Some(owner) = request.get("owner").and_then(Value::as_str) else {
                return (400, json!({"message": "owner required"}).to_string());
            };
            let Some(claim_id) = request.get("claim_id").and_then(Value::as_str) else {
                return (400, json!({"message": "claim id required"}).to_string());
            };
            let Some(revision) = request.get("revision").and_then(Value::as_u64) else {
                return (
                    400,
                    json!({"message": "revision must be a positive integer"}).to_string(),
                );
            };
            let Some(ttl_seconds) = request.get("ttl_seconds").and_then(Value::as_u64) else {
                return (
                    400,
                    json!({"message": "ttl_seconds must be a positive integer"}).to_string(),
                );
            };
            let lease = json!({
                "resource": resource,
                "owner": owner,
                "claim_id": claim_id,
                "revision": revision,
                "claimed_at": now,
                "expires_at": now.saturating_add(ttl_seconds),
            });
            leases.insert(resource.to_string(), lease.clone());
            (201, lease.to_string())
        }
        "PUT" => {
            let Some(lease) = leases.get_mut(resource) else {
                return (404, json!({"message": "no live lease"}).to_string());
            };
            if lease["expires_at"]
                .as_u64()
                .is_none_or(|expiry| expiry <= now)
            {
                leases.remove(resource);
                return (404, json!({"message": "no live lease"}).to_string());
            }
            if lease["owner"] != request["owner"] || lease["claim_id"] != request["claim_id"] {
                return (403, json!({"message": "lease owner mismatch"}).to_string());
            }
            let Some(extend_seconds) = request.get("extend_seconds").and_then(Value::as_u64) else {
                return (
                    400,
                    json!({"message": "extend_seconds must be a positive integer"}).to_string(),
                );
            };
            let old_expiry = lease["expires_at"].as_u64().expect("lease expiry");
            lease["expires_at"] = json!(old_expiry.saturating_add(extend_seconds));
            (200, lease.to_string())
        }
        "DELETE" => {
            let Some(lease) = leases.get(resource) else {
                return (404, json!({"message": "no live lease"}).to_string());
            };
            if lease["expires_at"]
                .as_u64()
                .is_none_or(|expiry| expiry <= now)
            {
                leases.remove(resource);
                return (404, json!({"message": "no live lease"}).to_string());
            }
            if lease["owner"] != request["owner"] || lease["claim_id"] != request["claim_id"] {
                return (403, json!({"message": "lease owner mismatch"}).to_string());
            }
            leases.remove(resource);
            (204, String::new())
        }
        "GET" => {
            let Some(lease) = leases.get(resource) else {
                return (404, json!({"message": "no live lease"}).to_string());
            };
            if lease["expires_at"]
                .as_u64()
                .is_none_or(|expiry| expiry <= now)
            {
                leases.remove(resource);
                return (404, json!({"message": "no live lease"}).to_string());
            }
            (200, lease.to_string())
        }
        _ => (405, json!({"message": "method not allowed"}).to_string()),
    }
}

fn root(world: &KanbusWorld) -> &Path {
    world
        .working_directory
        .as_deref()
        .expect("working directory not set")
}

fn configure_mutex_api(world: &mut KanbusWorld, endpoint: &str) {
    let path = get_configuration_path(root(world)).expect("configuration path");
    let contents = std::fs::read_to_string(&path).expect("read project config");
    let mut config: serde_yaml::Value = serde_yaml::from_str(&contents).expect("parse config");
    let root = config.as_mapping_mut().expect("config mapping");
    let coordination_key = serde_yaml::Value::String("coordination".to_string());
    if !root.contains_key(&coordination_key) {
        root.insert(
            coordination_key.clone(),
            serde_yaml::Value::Mapping(serde_yaml::Mapping::new()),
        );
    }
    let coordination = root
        .get_mut(&coordination_key)
        .and_then(serde_yaml::Value::as_mapping_mut)
        .expect("coordination config mapping");
    coordination.insert(
        serde_yaml::Value::String("providers".to_string()),
        serde_yaml::Value::Sequence(
            ["mutex_api", "mqtt", "git"]
                .into_iter()
                .map(|provider| serde_yaml::Value::String(provider.to_string()))
                .collect(),
        ),
    );
    let mutex_key = serde_yaml::Value::String("mutex_api".to_string());
    let mut mutex_config = serde_yaml::Mapping::new();
    mutex_config.insert(
        serde_yaml::Value::String("endpoint".to_string()),
        serde_yaml::Value::String(endpoint.to_string()),
    );
    mutex_config.insert(
        serde_yaml::Value::String("bearer_token".to_string()),
        serde_yaml::Value::String(TEST_BEARER_TOKEN.to_string()),
    );
    coordination.insert(mutex_key, serde_yaml::Value::Mapping(mutex_config));
    std::fs::write(
        path,
        serde_yaml::to_string(&config).expect("serialize config"),
    )
    .expect("write config");
}

fn set_default_ttl(world: &KanbusWorld, ttl: &str) {
    let path = get_configuration_path(root(world)).expect("configuration path");
    let contents = std::fs::read_to_string(&path).expect("read project config");
    let mut config: serde_yaml::Value = serde_yaml::from_str(&contents).expect("parse config");
    config["coordination"]["default_lease_ttl"] = serde_yaml::Value::String(ttl.to_string());
    std::fs::write(
        path,
        serde_yaml::to_string(&config).expect("serialize config"),
    )
    .expect("write config");
}

fn fixture(world: &KanbusWorld) -> &MutexApiFixture {
    world
        .mutex_api_fixture
        .as_ref()
        .expect("mutex API test server not started")
}

fn run_cli(world: &mut KanbusWorld, args: Vec<String>) {
    let cwd = root(world).to_path_buf();
    std::env::set_var("KANBUS_NO_DAEMON", "1");
    match run_from_args_in_blocking_thread(args, &cwd) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(output.stderr);
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

fn store_live_lease(
    world: &KanbusWorld,
    resource: &str,
    owner: &str,
    claim_id: &str,
    revision: u64,
    expires_at: u64,
) {
    let now = now_seconds();
    fixture(world).leases.lock().expect("leases lock").insert(
        resource.to_string(),
        json!({
            "resource": resource,
            "owner": owner,
            "claim_id": claim_id,
            "revision": revision,
            "claimed_at": now,
            "expires_at": expires_at,
        }),
    );
}

#[given(expr = "coordination mutex API endpoint is {string}")]
fn given_mutex_api_endpoint(world: &mut KanbusWorld, _configured_endpoint: String) {
    let fixture = MutexApiFixture::start().expect("start mutex API fixture");
    if world.mutex_api_original_env.is_none() {
        world.mutex_api_original_env = Some((
            std::env::var_os("KANBUS_COORDINATION_MUTEX_API_ENDPOINT"),
            std::env::var_os("KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN"),
        ));
    }
    std::env::set_var("KANBUS_COORDINATION_MUTEX_API_ENDPOINT", &fixture.endpoint);
    std::env::set_var(
        "KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN",
        TEST_BEARER_TOKEN,
    );
    configure_mutex_api(world, &fixture.endpoint);
    world.mutex_api_fixture = Some(fixture);
}

#[given(expr = "mutex API live lease storage is empty")]
fn given_empty_mutex_api_storage(world: &mut KanbusWorld) {
    fixture(world).leases.lock().expect("leases lock").clear();
}

#[given(
    expr = "mutex API live lease for {string} is held by owner {string} with claim id {string}"
)]
fn given_mutex_api_held_lease(
    world: &mut KanbusWorld,
    resource: String,
    owner: String,
    claim_id: String,
) {
    let expiry = now_seconds().saturating_add(300);
    store_live_lease(world, &resource, &owner, &claim_id, 1, expiry);
}

#[given(
    expr = "mutex API live lease for {string} is held by owner {string} with claim id {string} expiring at {string}"
)]
fn given_mutex_api_held_lease_expiry(
    world: &mut KanbusWorld,
    resource: String,
    owner: String,
    claim_id: String,
    expiry: String,
) {
    let expires_at = DateTime::parse_from_rfc3339(&expiry)
        .expect("valid expiry timestamp")
        .timestamp() as u64;
    store_live_lease(world, &resource, &owner, &claim_id, 1, expires_at);
}

#[given(expr = "mutex API live lease for {string} expired by TTL garbage collection")]
fn given_expired_mutex_api_lease(world: &mut KanbusWorld, resource: String) {
    fixture(world)
        .leases
        .lock()
        .expect("leases lock")
        .remove(&resource);
}

#[when(
    expr = "mutex API client acquires resource {string} for owner {string} with claim id {string} revision {int} lease TTL {string}"
)]
fn when_mutex_api_acquire(
    world: &mut KanbusWorld,
    resource: String,
    owner: String,
    claim_id: String,
    revision: i64,
    ttl: String,
) {
    set_default_ttl(world, &ttl);
    run_cli(
        world,
        vec![
            "kanbus".into(),
            "coordination".into(),
            "claim".into(),
            "--resource".into(),
            resource,
            "--owner".into(),
            owner,
            "--claim-id".into(),
            claim_id,
            "--revision".into(),
            revision.to_string(),
        ],
    );
}

#[when(
    expr = "mutex API client renews resource {string} for owner {string} with claim id {string} extending {string}"
)]
fn when_mutex_api_renew(
    world: &mut KanbusWorld,
    resource: String,
    owner: String,
    claim_id: String,
    extend: String,
) {
    let extend_seconds = parse_duration_seconds(&extend).expect("valid extension duration");
    let extend = format!("{extend_seconds}s");
    run_cli(
        world,
        vec![
            "kanbus".into(),
            "coordination".into(),
            "renew".into(),
            "--resource".into(),
            resource,
            "--owner".into(),
            owner,
            "--claim-id".into(),
            claim_id,
            "--extend".into(),
            extend,
        ],
    );
}

#[when(
    expr = "mutex API client releases resource {string} for owner {string} with claim id {string}"
)]
fn when_mutex_api_release(
    world: &mut KanbusWorld,
    resource: String,
    owner: String,
    claim_id: String,
) {
    run_cli(
        world,
        vec![
            "kanbus".into(),
            "coordination".into(),
            "release".into(),
            "--resource".into(),
            resource,
            "--owner".into(),
            owner,
            "--claim-id".into(),
            claim_id,
        ],
    );
}

#[when(expr = "mutex API client inspects resource {string}")]
fn when_mutex_api_inspect(world: &mut KanbusWorld, resource: String) {
    run_cli(
        world,
        vec![
            "kanbus".into(),
            "coordination".into(),
            "inspect".into(),
            "--resource".into(),
            resource,
        ],
    );
}

#[then(expr = "mutex API {word} response status should be {int}")]
fn then_mutex_api_status(world: &mut KanbusWorld, _operation: String, expected: i64) {
    let status = fixture(world)
        .last_response
        .lock()
        .expect("last response lock")
        .as_ref()
        .map(|(status, _)| *status);
    assert_eq!(status, Some(expected as u16));
}

#[then(expr = "mutex API live lease for {string} should include owner {string}")]
fn then_mutex_api_owner(world: &mut KanbusWorld, resource: String, owner: String) {
    assert_eq!(
        fixture(world)
            .leases
            .lock()
            .expect("leases lock")
            .get(&resource)
            .and_then(|lease| lease.get("owner"))
            .and_then(Value::as_str),
        Some(owner.as_str())
    );
}

#[then(expr = "mutex API live lease for {string} should include claim id {string}")]
fn then_mutex_api_claim_id(world: &mut KanbusWorld, resource: String, claim_id: String) {
    assert_eq!(
        fixture(world)
            .leases
            .lock()
            .expect("leases lock")
            .get(&resource)
            .and_then(|lease| lease.get("claim_id"))
            .and_then(Value::as_str),
        Some(claim_id.as_str())
    );
}

#[then(expr = "mutex API live lease for {string} should include revision {int}")]
fn then_mutex_api_revision(world: &mut KanbusWorld, resource: String, revision: i64) {
    assert_eq!(
        fixture(world)
            .leases
            .lock()
            .expect("leases lock")
            .get(&resource)
            .and_then(|lease| lease.get("revision"))
            .and_then(Value::as_i64),
        Some(revision)
    );
}

#[then(expr = "mutex API live lease for {string} should include claimed_at timestamp")]
fn then_mutex_api_claimed_at(world: &mut KanbusWorld, resource: String) {
    assert!(fixture(world)
        .leases
        .lock()
        .expect("leases lock")
        .get(&resource)
        .and_then(|lease| lease.get("claimed_at"))
        .and_then(Value::as_u64)
        .is_some());
}

#[then(expr = "mutex API live lease for {string} should include expires_at timestamp")]
fn then_mutex_api_expires_at(world: &mut KanbusWorld, resource: String) {
    assert!(fixture(world)
        .leases
        .lock()
        .expect("leases lock")
        .get(&resource)
        .and_then(|lease| lease.get("expires_at"))
        .and_then(Value::as_u64)
        .is_some());
}

#[then(expr = "mutex API error message should contain {string}")]
fn then_mutex_api_error(world: &mut KanbusWorld, expected: String) {
    assert!(
        world
            .stderr
            .as_deref()
            .unwrap_or_default()
            .contains(&expected),
        "error should contain {expected:?}; got {:?}",
        world.stderr
    );
}

#[then(expr = "mutex API live lease for {string} should expire after {string}")]
fn then_mutex_api_expiry_after(world: &mut KanbusWorld, resource: String, timestamp: String) {
    let expected = DateTime::parse_from_rfc3339(&timestamp)
        .expect("expected expiry timestamp")
        .timestamp();
    let actual = fixture(world)
        .leases
        .lock()
        .expect("leases lock")
        .get(&resource)
        .and_then(|lease| lease.get("expires_at"))
        .and_then(Value::as_i64)
        .expect("live lease expiry");
    assert!(
        actual > expected,
        "{actual} should be later than {expected}"
    );
}

#[then(expr = "mutex API live lease for {string} should not exist")]
fn then_mutex_api_lease_missing(world: &mut KanbusWorld, resource: String) {
    assert!(!fixture(world)
        .leases
        .lock()
        .expect("leases lock")
        .contains_key(&resource));
}

#[then(expr = "mutex API inspect body should contain claim id {string}")]
fn then_mutex_api_inspect_claim_id(world: &mut KanbusWorld, claim_id: String) {
    let response = fixture(world)
        .last_response
        .lock()
        .expect("last response lock")
        .clone()
        .expect("last API response");
    let body = String::from_utf8_lossy(&response.1);
    assert!(body.contains(&claim_id), "inspect body was {body:?}");
}

#[then(expr = "mutex API inspect body should contain {string}")]
fn then_mutex_api_inspect_body(world: &mut KanbusWorld, expected: String) {
    let response = fixture(world)
        .last_response
        .lock()
        .expect("last response lock")
        .clone()
        .expect("last API response");
    let body = String::from_utf8_lossy(&response.1);
    assert!(body.contains(&expected), "inspect body was {body:?}");
}

#[then(expr = "mutex API storage for resource {string} should contain no historical claim records")]
fn then_mutex_api_storage_has_no_history(world: &mut KanbusWorld, resource: String) {
    let leases = fixture(world).leases.lock().expect("leases lock");
    if let Some(lease) = leases.get(&resource) {
        assert!(lease.get("history").is_none());
    }
}
