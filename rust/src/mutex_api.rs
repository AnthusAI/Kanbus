//! HTTP client for the optional hard coordination mutex API.

use std::time::Duration;

use chrono::{DateTime, Utc};
use reqwest::blocking::Client;
use reqwest::StatusCode;
use serde::Deserialize;
use serde_json::{json, Value};

use crate::models::MutexApiConfiguration;

/// Request timeout used for the optional mutex API.
pub const REQUEST_TIMEOUT: Duration = Duration::from_secs(3);

/// An active hard lease returned by the mutex API.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MutexLease {
    /// Resource key protected by this lease.
    pub resource: String,
    /// Owner that acquired the lease.
    pub owner: String,
    /// Stable claim identifier.
    pub claim_id: String,
    /// Logical revision assigned by the router.
    pub revision: u64,
    /// Unix time at which the API created the lease.
    pub claimed_at: DateTime<Utc>,
    /// Unix time at which the API lease expires.
    pub expires_at: DateTime<Utc>,
}

/// Failure calling the mutex API, separated into fallback-safe unavailability
/// and a request the API explicitly rejected.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MutexApiError {
    /// The endpoint is not configured, unreachable, timed out, or returned 5xx.
    Unavailable(String),
    /// The API returned a non-success status other than an availability error.
    Rejected { status: u16, message: String },
}

impl std::fmt::Display for MutexApiError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Unavailable(message) => formatter.write_str(message),
            Self::Rejected { message, .. } => formatter.write_str(message),
        }
    }
}

impl std::error::Error for MutexApiError {}

/// Return whether the configured endpoint and token form a usable HTTP URL.
pub fn is_configured(configuration: &MutexApiConfiguration) -> bool {
    let endpoint = configuration.endpoint.as_deref().unwrap_or_default().trim();
    let token = configuration
        .bearer_token
        .as_deref()
        .unwrap_or_default()
        .trim();
    if endpoint.is_empty() || token.is_empty() {
        return false;
    }
    reqwest::Url::parse(endpoint)
        .is_ok_and(|url| matches!(url.scheme(), "http" | "https") && url.host_str().is_some())
}

/// Acquire a lease, returning contention and validation errors without fallback.
pub fn acquire(
    configuration: &MutexApiConfiguration,
    resource: &str,
    owner: &str,
    claim_id: &str,
    revision: u64,
    ttl_seconds: u64,
) -> Result<MutexLease, MutexApiError> {
    validate_positive_integer(revision, "revision")?;
    validate_positive_integer(ttl_seconds, "ttl_seconds")?;
    let response = request(
        configuration,
        "POST",
        resource,
        Some(json!({
            "owner": owner,
            "claim_id": claim_id,
            "revision": revision,
            "ttl_seconds": ttl_seconds,
        })),
    )?;
    if response.status == StatusCode::CONFLICT {
        return Err(rejected(response, "lease already held"));
    }
    if response.status != StatusCode::CREATED {
        let status = response.status;
        return Err(rejected(
            response,
            &format!("mutex api acquire failed with status {status}"),
        ));
    }
    parse_lease(response, resource)
}

/// Extend a matching live lease.
pub fn renew(
    configuration: &MutexApiConfiguration,
    resource: &str,
    owner: &str,
    claim_id: &str,
    extend_seconds: u64,
) -> Result<MutexLease, MutexApiError> {
    validate_positive_integer(extend_seconds, "extend_seconds")?;
    let response = request(
        configuration,
        "PUT",
        resource,
        Some(json!({
            "owner": owner,
            "claim_id": claim_id,
            "extend_seconds": extend_seconds,
        })),
    )?;
    if response.status == StatusCode::FORBIDDEN || response.status == StatusCode::NOT_FOUND {
        let fallback = if response.status == StatusCode::FORBIDDEN {
            "lease owner mismatch"
        } else {
            "no live lease"
        };
        return Err(rejected(response, fallback));
    }
    if response.status != StatusCode::OK {
        let status = response.status;
        return Err(rejected(
            response,
            &format!("mutex api renew failed with status {status}"),
        ));
    }
    parse_lease(response, resource)
}

/// Release a matching live lease.
pub fn release(
    configuration: &MutexApiConfiguration,
    resource: &str,
    owner: &str,
    claim_id: &str,
) -> Result<(), MutexApiError> {
    let response = request(
        configuration,
        "DELETE",
        resource,
        Some(json!({"owner": owner, "claim_id": claim_id})),
    )?;
    if response.status == StatusCode::FORBIDDEN || response.status == StatusCode::NOT_FOUND {
        let fallback = if response.status == StatusCode::FORBIDDEN {
            "lease owner mismatch"
        } else {
            "no live lease"
        };
        return Err(rejected(response, fallback));
    }
    if response.status != StatusCode::NO_CONTENT {
        let status = response.status;
        return Err(rejected(
            response,
            &format!("mutex api release failed with status {status}"),
        ));
    }
    Ok(())
}

/// Return the active lease, or `None` when no live lease exists.
pub fn inspect(
    configuration: &MutexApiConfiguration,
    resource: &str,
) -> Result<Option<MutexLease>, MutexApiError> {
    let response = request(configuration, "GET", resource, None)?;
    if response.status == StatusCode::NOT_FOUND {
        return Ok(None);
    }
    if response.status != StatusCode::OK {
        let status = response.status;
        return Err(rejected(
            response,
            &format!("mutex api inspect failed with status {status}"),
        ));
    }
    let lease = parse_lease(response, resource)?;
    // DynamoDB's TTL deletion is asynchronous, so a direct API mapping may
    // still return an expired record.  The lease timestamp is server-issued;
    // do not present that stale record as active to the coordinator.
    if lease.expires_at <= Utc::now() {
        Ok(None)
    } else {
        Ok(Some(lease))
    }
}

fn request(
    configuration: &MutexApiConfiguration,
    method: &str,
    resource: &str,
    body: Option<Value>,
) -> Result<RawResponse, MutexApiError> {
    if !is_configured(configuration) {
        return Err(MutexApiError::Unavailable(
            "mutex api is not configured".to_string(),
        ));
    }
    let endpoint = configuration
        .endpoint
        .as_deref()
        .expect("validated endpoint")
        .trim()
        .trim_end_matches('/');
    let url = format!(
        "{endpoint}/api/coordination/leases/{}",
        encode_path_segment(resource)
    );
    let client = Client::builder()
        .timeout(REQUEST_TIMEOUT)
        .build()
        .map_err(|_| unavailable())?;
    let mut request = client
        .request(method.parse().expect("static HTTP method"), url)
        .header(reqwest::header::ACCEPT, "application/json")
        .bearer_auth(
            configuration
                .bearer_token
                .as_deref()
                .expect("validated bearer token")
                .trim(),
        );
    if let Some(body) = body {
        request = request.json(&body);
    }
    let response = request.send().map_err(|_| unavailable())?;
    let status = response.status();
    let body = response.bytes().map_err(|_| unavailable())?.to_vec();
    let response = RawResponse { status, body };
    if response.status.is_server_error() {
        return Err(MutexApiError::Unavailable(response_message(
            &response,
            "mutex api unavailable",
        )));
    }
    Ok(response)
}

fn encode_path_segment(value: &str) -> String {
    let mut encoded = String::with_capacity(value.len());
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~') {
            encoded.push(byte as char);
        } else {
            use std::fmt::Write as _;
            write!(&mut encoded, "%{byte:02X}").expect("write to string");
        }
    }
    encoded
}

#[derive(Debug)]
struct RawResponse {
    status: StatusCode,
    body: Vec<u8>,
}

fn rejected(response: RawResponse, fallback: &str) -> MutexApiError {
    MutexApiError::Rejected {
        status: response.status.as_u16(),
        message: response_message(&response, fallback),
    }
}

fn response_message(response: &RawResponse, fallback: &str) -> String {
    let Ok(Value::Object(payload)) = serde_json::from_slice::<Value>(&response.body) else {
        return fallback.to_string();
    };
    ["message", "error", "detail"]
        .into_iter()
        .find_map(|key| payload.get(key).and_then(Value::as_str))
        .filter(|message| !message.is_empty())
        .unwrap_or(fallback)
        .to_string()
}

#[derive(Debug, Deserialize)]
struct LeaseResponse {
    resource: String,
    owner: String,
    claim_id: String,
    revision: u64,
    claimed_at: Value,
    expires_at: Value,
}

fn parse_lease(
    response: RawResponse,
    requested_resource: &str,
) -> Result<MutexLease, MutexApiError> {
    let parsed = (|| {
        let payload: LeaseResponse = serde_json::from_slice(&response.body).ok()?;
        if payload.resource.is_empty()
            || payload.resource != requested_resource
            || payload.revision == 0
        {
            return None;
        }
        Some(MutexLease {
            resource: payload.resource,
            owner: payload.owner,
            claim_id: payload.claim_id,
            revision: payload.revision,
            claimed_at: parse_unix_timestamp(&payload.claimed_at)?,
            expires_at: parse_unix_timestamp(&payload.expires_at)?,
        })
    })();
    parsed.ok_or_else(|| MutexApiError::Rejected {
        status: response.status.as_u16(),
        message: "mutex api returned an invalid lease response".to_string(),
    })
}

fn parse_unix_timestamp(value: &Value) -> Option<DateTime<Utc>> {
    let timestamp = value.as_f64()?;
    if !timestamp.is_finite() {
        return None;
    }
    let seconds = timestamp.floor();
    if seconds < i64::MIN as f64 || seconds > i64::MAX as f64 {
        return None;
    }
    let whole_seconds = seconds as i64;
    let nanos = ((timestamp - seconds) * 1_000_000_000.0) as u32;
    DateTime::from_timestamp(whole_seconds, nanos)
}

fn validate_positive_integer(value: u64, field: &str) -> Result<(), MutexApiError> {
    if value == 0 {
        Err(MutexApiError::Rejected {
            status: 0,
            message: format!("{field} must be a positive integer"),
        })
    } else {
        Ok(())
    }
}

fn unavailable() -> MutexApiError {
    MutexApiError::Unavailable("mutex api unavailable".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;
    use crate::coordination::{run_coordination, CoordinationOperation};
    use std::io::{BufRead, Read, Write};
    use std::net::TcpListener;
    use std::thread;
    use tempfile::TempDir;

    fn mock_server(
        status: u16,
        response_body: &'static str,
    ) -> (String, thread::JoinHandle<String>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock server");
        let address = listener.local_addr().expect("local address");
        let handle = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept request");
            let mut request = [0; 8192];
            let size = stream.read(&mut request).expect("read request");
            let request_text = String::from_utf8_lossy(&request[..size]).to_string();
            let reason = match status {
                200 => "OK",
                201 => "Created",
                204 => "No Content",
                403 => "Forbidden",
                404 => "Not Found",
                409 => "Conflict",
                503 => "Service Unavailable",
                _ => "Bad Request",
            };
            write!(
                stream,
                "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{response_body}",
                response_body.len()
            )
            .expect("write response");
            request_text
        });
        (format!("http://{address}"), handle)
    }

    fn scripted_mock_server(
        responses: Vec<(u16, String)>,
        before_response: impl Fn(usize, &str) + Send + 'static,
    ) -> (String, thread::JoinHandle<Vec<String>>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock server");
        let address = listener.local_addr().expect("local address");
        let handle = thread::spawn(move || {
            let mut requests = Vec::with_capacity(responses.len());
            for (index, (status, response_body)) in responses.into_iter().enumerate() {
                let (mut stream, _) = listener.accept().expect("accept request");
                let mut reader = std::io::BufReader::new(stream.try_clone().expect("clone stream"));
                let mut request_text = String::new();
                let mut line = String::new();
                reader.read_line(&mut line).expect("read request line");
                request_text.push_str(&line);
                let mut content_length = 0usize;
                loop {
                    line.clear();
                    reader.read_line(&mut line).expect("read header");
                    if line == "\r\n" || line.is_empty() {
                        break;
                    }
                    if let Some((name, value)) = line.split_once(':') {
                        if name.eq_ignore_ascii_case("content-length") {
                            content_length = value.trim().parse().unwrap_or(0);
                        }
                    }
                    request_text.push_str(&line);
                }
                let mut body = vec![0; content_length];
                reader.read_exact(&mut body).expect("read request body");
                request_text.push_str(&String::from_utf8_lossy(&body));
                before_response(index, &request_text);
                requests.push(request_text);
                let reason = match status {
                    200 => "OK",
                    201 => "Created",
                    204 => "No Content",
                    403 => "Forbidden",
                    404 => "Not Found",
                    409 => "Conflict",
                    503 => "Service Unavailable",
                    _ => "Bad Request",
                };
                write!(
                    stream,
                    "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{response_body}",
                    response_body.len()
                )
                .expect("write response");
            }
            requests
        });
        (format!("http://{address}"), handle)
    }

    fn env_lock() -> std::sync::MutexGuard<'static, ()> {
        static ENV_LOCK: std::sync::OnceLock<std::sync::Mutex<()>> = std::sync::OnceLock::new();
        // Recover from poisoning so one flaky test panicking while holding
        // this lock doesn't cascade into every later test that locks it.
        ENV_LOCK
            .get_or_init(|| std::sync::Mutex::new(()))
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// RAII guard that forces `KANBUS_REALTIME_BROKER=off` in the process
    /// environment for the duration of a test, restoring the prior value on
    /// drop (including on panic).
    ///
    /// `conflict_is_not_downgraded_and_unavailability_falls_back_to_git`
    /// drives `mutex_api::acquire` into `Unavailable` and then expects
    /// `run_coordination` to also find MQTT unavailable, so it falls all the
    /// way through to the `git` provider. That assumption does not hold on a
    /// machine running a live Mosquitto broker on the default
    /// `127.0.0.1:1883` (the REALTIME guide documents running exactly that
    /// broker): `config_loader::load_project_configuration` loads a real
    /// `~/.kanbus.env`, which can set `KANBUS_REALTIME_BROKER` to that
    /// broker's address, letting the MQTT publish succeed and turning the
    /// expected `provider: git` into `provider: mqtt`. Forcing the env var
    /// here (rather than only writing `broker: off` into the test's own
    /// config file) closes that gap, since `load_dotenv` only sets a key
    /// that is not already present in the process environment. Mirrors
    /// `gossip::tests::IsolatedHomeGuard::force_realtime_broker` and the
    /// Python fix in
    /// `python/tests/test_coordination_mutex_api.py::test_mutex_api_unavailability_falls_back_to_git_without_aws_credentials`
    /// (`monkeypatch.setenv("KANBUS_REALTIME_BROKER", "off")`).
    struct DisabledBrokerGuard {
        prior_broker: Option<String>,
    }

    impl DisabledBrokerGuard {
        fn new() -> Self {
            let prior_broker = std::env::var("KANBUS_REALTIME_BROKER").ok();
            std::env::set_var("KANBUS_REALTIME_BROKER", "off");
            Self { prior_broker }
        }
    }

    impl Drop for DisabledBrokerGuard {
        fn drop(&mut self) {
            match self.prior_broker.take() {
                Some(value) => std::env::set_var("KANBUS_REALTIME_BROKER", value),
                None => std::env::remove_var("KANBUS_REALTIME_BROKER"),
            }
        }
    }

    fn configured_project(endpoint: &str) -> TempDir {
        let temp = tempfile::tempdir().expect("temporary project");
        std::fs::create_dir_all(temp.path().join("project/events")).expect("project events");
        let mut configuration = default_project_configuration();
        configuration.coordination.providers = vec![
            "mutex_api".to_string(),
            "mqtt".to_string(),
            "git".to_string(),
        ];
        configuration.coordination.mutex_api = MutexApiConfiguration {
            endpoint: Some(endpoint.to_string()),
            bearer_token: Some("test-token".to_string()),
        };
        let contents = serde_yaml::to_string(&configuration).expect("serialize configuration");
        std::fs::write(temp.path().join(".kanbus.yml"), contents)
            .expect("write project configuration");
        temp
    }

    fn configuration(endpoint: String) -> MutexApiConfiguration {
        MutexApiConfiguration {
            endpoint: Some(endpoint),
            bearer_token: Some("test-token".to_string()),
        }
    }

    const LEASE: &str = r#"{"resource":"job:api","owner":"worker-a","claim_id":"claim-1","revision":7,"claimed_at":1700000000,"expires_at":4000000000}"#;

    #[test]
    fn acquire_uses_bearer_route_and_logical_revision() {
        let (endpoint, server) = mock_server(
            201,
            r#"{"resource":"job:api/1","owner":"worker-a","claim_id":"claim-1","revision":7,"claimed_at":1700000000,"expires_at":1700000300}"#,
        );
        let lease = acquire(
            &configuration(endpoint),
            "job:api/1",
            "worker-a",
            "claim-1",
            7,
            300,
        )
        .expect("acquired lease");
        let request = server.join().expect("request captured");
        assert!(request.starts_with("POST /api/coordination/leases/job%3Aapi%2F1 HTTP/1.1"));
        assert!(request
            .to_ascii_lowercase()
            .contains("authorization: bearer test-token"));
        assert!(request.contains("\"revision\":7"));
        assert_eq!(lease.revision, 7);
        assert_eq!(lease.owner, "worker-a");
    }

    #[test]
    fn conflict_and_owner_mismatch_preserve_api_diagnostics() {
        let (endpoint, server) = mock_server(409, r#"{"message":"lease already held"}"#);
        let error = acquire(&configuration(endpoint), "job", "worker", "claim", 1, 30)
            .expect_err("conflict");
        server.join().expect("request captured");
        assert_eq!(error.to_string(), "lease already held");

        let (endpoint, server) = mock_server(403, r#"{"message":"lease owner mismatch"}"#);
        let error = renew(&configuration(endpoint), "job", "worker", "claim", 30)
            .expect_err("mismatched owner");
        server.join().expect("request captured");
        assert_eq!(error.to_string(), "lease owner mismatch");
    }

    #[test]
    fn missing_expired_lease_and_unavailable_are_distinct() {
        let (endpoint, server) = mock_server(404, r#"{"message":"no live lease"}"#);
        assert!(inspect(&configuration(endpoint), "job")
            .expect("inspect missing lease")
            .is_none());
        server.join().expect("request captured");

        let (endpoint, server) = mock_server(503, r#"{"message":"maintenance"}"#);
        let error = inspect(&configuration(endpoint), "job").expect_err("unavailable");
        server.join().expect("request captured");
        assert_eq!(error, MutexApiError::Unavailable("maintenance".to_string()));
    }

    #[test]
    fn inspect_treats_a_stale_success_response_as_eligible() {
        let (endpoint, server) = mock_server(
            200,
            r#"{"resource":"job:expired","owner":"worker-a","claim_id":"claim-1","revision":1,"claimed_at":1700000000,"expires_at":1700000300}"#,
        );
        assert!(inspect(&configuration(endpoint), "job:expired")
            .expect("inspect expired lease")
            .is_none());
        server.join().expect("request captured");
    }

    #[test]
    fn renew_inspect_and_release_follow_the_http_contract() {
        let renewed_body = r#"{"resource":"job:api","owner":"worker-a","claim_id":"claim-1","revision":7,"claimed_at":1700000000,"expires_at":1700000420}"#;
        let (endpoint, server) = mock_server(200, renewed_body);
        let lease = renew(
            &configuration(endpoint),
            "job:api",
            "worker-a",
            "claim-1",
            120,
        )
        .expect("renew lease");
        let request = server.join().expect("request captured");
        assert!(request.starts_with("PUT /api/coordination/leases/job%3Aapi HTTP/1.1"));
        assert!(request.contains("\"extend_seconds\":120"));
        assert_eq!(lease.expires_at.timestamp(), 1_700_000_420);

        let (endpoint, server) = mock_server(200, LEASE);
        let lease = inspect(&configuration(endpoint), "job:api")
            .expect("inspect lease")
            .expect("active lease");
        let request = server.join().expect("request captured");
        assert!(request.starts_with("GET /api/coordination/leases/job%3Aapi HTTP/1.1"));
        assert_eq!(lease.claim_id, "claim-1");

        let (endpoint, server) = mock_server(204, "");
        release(&configuration(endpoint), "job:api", "worker-a", "claim-1").expect("release lease");
        let request = server.join().expect("request captured");
        assert!(request.starts_with("DELETE /api/coordination/leases/job%3Aapi HTTP/1.1"));
    }

    #[test]
    fn invalid_success_response_and_nonpositive_inputs_are_rejected() {
        let (endpoint, server) = mock_server(201, r#"{"owner":"worker","claim_id":"claim"}"#);
        assert_eq!(
            acquire(&configuration(endpoint), "job", "worker", "claim", 1, 30)
                .expect_err("invalid response")
                .to_string(),
            "mutex api returned an invalid lease response"
        );
        server.join().expect("request captured");
        let (endpoint, server) = mock_server(
            201,
            r#"{"resource":"different-resource","owner":"worker","claim_id":"claim","revision":1,"claimed_at":1700000000,"expires_at":1700000030}"#,
        );
        assert_eq!(
            acquire(&configuration(endpoint), "job", "worker", "claim", 1, 30)
                .expect_err("mismatched resource response")
                .to_string(),
            "mutex api returned an invalid lease response"
        );
        server.join().expect("request captured");
        assert_eq!(
            acquire(
                &MutexApiConfiguration::default(),
                "job",
                "worker",
                "claim",
                0,
                30
            )
            .expect_err("invalid revision")
            .to_string(),
            "revision must be a positive integer"
        );
    }

    #[test]
    fn hard_claim_audits_after_acquire_and_preserves_router_revision() {
        let event_dir = std::sync::Arc::new(std::sync::Mutex::new(std::path::PathBuf::new()));
        let callback_event_dir = std::sync::Arc::clone(&event_dir);
        let observed_event_exists = std::sync::Arc::new(std::sync::Mutex::new(None));
        let callback_observed = std::sync::Arc::clone(&observed_event_exists);
        let lease = r#"{"resource":"job:hard","owner":"worker-a","claim_id":"claim-hard","revision":7,"claimed_at":1700000000,"expires_at":1700000300}"#.to_string();
        let (endpoint, server) =
            scripted_mock_server(vec![(201, lease)], move |index, _request| {
                if index == 0 {
                    let path = callback_event_dir.lock().expect("event path lock").clone();
                    let has_events =
                        std::fs::read_dir(path).is_ok_and(|mut entries| entries.next().is_some());
                    *callback_observed.lock().expect("observation lock") = Some(has_events);
                }
            });
        let temp = configured_project(&endpoint);
        *event_dir.lock().expect("event path lock") = temp.path().join("project/events");

        let output = crate::cli::run_from_args_with_output(
            [
                "kanbus",
                "coordination",
                "claim",
                "--resource",
                "job:hard",
                "--owner",
                "worker-a",
                "--claim-id",
                "claim-hard",
                "--revision",
                "7",
            ],
            temp.path(),
        )
        .expect("CLI hard claim");
        let requests = server.join().expect("mock server requests");
        assert_eq!(requests.len(), 1);
        assert!(requests[0].starts_with("POST /api/coordination/leases/job%3Ahard"));
        assert!(requests[0].contains("\"revision\":7"));
        assert_eq!(
            *observed_event_exists.lock().expect("observation lock"),
            Some(false)
        );
        assert!(output.stdout.contains("provider: mutex_api"));
        assert!(output.stdout.contains("state: active hard mutex"));
        assert!(output.stdout.contains("revision: 7"));
        assert!(output
            .stdout
            .contains("claimed_at: 2023-11-14T22:13:20.000Z"));
        let output_fields = [
            "provider: mutex_api",
            "resource: job:hard",
            "state: active hard mutex",
            "owner: worker-a",
            "claim_id: claim-hard",
            "revision: 7",
            "claimed_at: 2023-11-14T22:13:20.000Z",
            "expires_at: 2023-11-14T22:18:20.000Z",
        ];
        let mut preceding_offset = 0;
        for field in output_fields {
            let offset = output.stdout[preceding_offset..]
                .find(field)
                .expect("ordered hard mutex output field");
            preceding_offset += offset + field.len();
        }
        let event_path = std::fs::read_dir(temp.path().join("project/events"))
            .expect("event directory")
            .next()
            .expect("audit event")
            .expect("audit path")
            .path();
        let event: Value =
            serde_json::from_slice(&std::fs::read(event_path).expect("read audit event"))
                .expect("parse audit event");
        assert_eq!(event["event_type"], "coordination.claim");
        assert_eq!(event["payload"]["revision"], 7);
    }

    #[test]
    #[serial_test::serial]
    fn conflict_is_not_downgraded_and_unavailability_falls_back_to_git() {
        let _env_guard = env_lock();
        let _broker_guard = DisabledBrokerGuard::new();
        let (endpoint, server) = mock_server(409, r#"{"message":"lease already held"}"#);
        let temp = configured_project(&endpoint);
        let result = crate::cli::run_from_args_with_output(
            [
                "kanbus",
                "coordination",
                "claim",
                "--resource",
                "job:held",
                "--owner",
                "worker-b",
                "--claim-id",
                "claim-new",
            ],
            temp.path(),
        );
        assert!(result
            .expect_err("lease conflict")
            .to_string()
            .contains("lease already held"));
        server.join().expect("mock server request");
        assert_eq!(
            std::fs::read_dir(temp.path().join("project/events"))
                .expect("event directory")
                .count(),
            0
        );

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind closed endpoint");
        let address = listener.local_addr().expect("closed address");
        drop(listener);
        let fallback = configured_project(&format!("http://{address}"));
        let output = run_coordination(
            fallback.path(),
            CoordinationOperation::Claim {
                resource: "job:fallback".to_string(),
                owner: "worker".to_string(),
                claim_id: "claim-fallback".to_string(),
                revision: 1,
            },
        )
        .expect("Git fallback");
        assert!(output.contains("provider: git"));
        assert_eq!(
            std::fs::read_dir(fallback.path().join("project/events"))
                .expect("event directory")
                .count(),
            1
        );
    }

    #[test]
    fn failed_audit_attempts_remote_release_and_returns_matching_diagnostic() {
        let lease = r#"{"resource":"job:rollback","owner":"worker","claim_id":"claim-rollback","revision":1,"claimed_at":1700000000,"expires_at":1700000300}"#.to_string();
        let (endpoint, server) = scripted_mock_server(
            vec![(201, lease), (204, String::new())],
            |_index, _request| {},
        );
        let temp = tempfile::tempdir().expect("temporary project");
        std::fs::create_dir_all(temp.path().join("project")).expect("project directory");
        std::fs::write(
            temp.path().join("project/events"),
            "blocks directory creation",
        )
        .expect("event path file");
        let mut project_configuration = default_project_configuration();
        project_configuration.coordination.providers = vec![
            "mutex_api".to_string(),
            "mqtt".to_string(),
            "git".to_string(),
        ];
        project_configuration.coordination.mutex_api = MutexApiConfiguration {
            endpoint: Some(endpoint),
            bearer_token: Some("test-token".to_string()),
        };
        std::fs::write(
            temp.path().join(".kanbus.yml"),
            serde_yaml::to_string(&project_configuration).expect("serialize config"),
        )
        .expect("write config");

        let error = crate::cli::run_from_args_with_output(
            [
                "kanbus",
                "coordination",
                "claim",
                "--resource",
                "job:rollback",
                "--owner",
                "worker",
                "--claim-id",
                "claim-rollback",
            ],
            temp.path(),
        )
        .expect_err("audit append failure");
        assert!(error
            .to_string()
            .contains("durable Git claim could not be recorded:"));
        let requests = server.join().expect("mock server requests");
        assert_eq!(requests.len(), 2);
        assert!(requests[0].starts_with("POST "));
        assert!(requests[1].starts_with("DELETE "));
    }

    #[test]
    fn hard_renew_inspect_and_release_record_audit_history() {
        let lease = r#"{"resource":"job:hard-flow","owner":"worker","claim_id":"claim-flow","revision":3,"claimed_at":1700000000,"expires_at":4000000000}"#.to_string();
        let renewed = r#"{"resource":"job:hard-flow","owner":"worker","claim_id":"claim-flow","revision":3,"claimed_at":1700000000,"expires_at":4000000120}"#.to_string();
        let (endpoint, server) = scripted_mock_server(
            vec![
                (201, lease),
                (200, renewed.clone()),
                (200, renewed),
                (204, String::new()),
            ],
            |_index, _request| {},
        );
        let temp = configured_project(&endpoint);
        let claim = run_coordination(
            temp.path(),
            CoordinationOperation::Claim {
                resource: "job:hard-flow".to_string(),
                owner: "worker".to_string(),
                claim_id: "claim-flow".to_string(),
                revision: 3,
            },
        )
        .expect("hard claim");
        assert!(claim.contains("state: active hard mutex"));
        let renewed = run_coordination(
            temp.path(),
            CoordinationOperation::Renew {
                resource: "job:hard-flow".to_string(),
                owner: "worker".to_string(),
                claim_id: "claim-flow".to_string(),
                extend: Some("120s".to_string()),
            },
        )
        .expect("hard renewal");
        assert!(renewed.contains("provider: mutex_api"));
        assert!(renewed.contains("state: active hard mutex"));
        let inspected = run_coordination(
            temp.path(),
            CoordinationOperation::Inspect {
                resource: "job:hard-flow".to_string(),
            },
        )
        .expect("hard inspection");
        assert!(inspected.contains("claim_id: claim-flow"));
        assert!(run_coordination(
            temp.path(),
            CoordinationOperation::Release {
                resource: "job:hard-flow".to_string(),
                owner: "worker".to_string(),
                claim_id: "claim-flow".to_string(),
            },
        )
        .expect("hard release")
        .contains("state: released"));

        let requests = server.join().expect("mock server requests");
        assert_eq!(requests.len(), 4);
        assert!(requests[0].starts_with("POST "));
        assert!(requests[1].starts_with("PUT "));
        assert!(requests[2].starts_with("GET "));
        assert!(requests[3].starts_with("DELETE "));
        let mut event_types = std::fs::read_dir(temp.path().join("project/events"))
            .expect("event directory")
            .map(|entry| {
                let record: Value = serde_json::from_slice(
                    &std::fs::read(entry.expect("event path").path()).expect("read event"),
                )
                .expect("parse event");
                record["event_type"]
                    .as_str()
                    .expect("event type")
                    .to_string()
            })
            .collect::<Vec<_>>();
        event_types.sort();
        assert_eq!(
            event_types,
            vec![
                "coordination.claim",
                "coordination.release",
                "coordination.renew",
            ]
        );
    }
}
