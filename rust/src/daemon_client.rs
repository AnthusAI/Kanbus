//! Daemon client utilities for index access.

use std::collections::BTreeMap;
use std::env;
use std::io::{BufRead, BufReader, Write};
#[cfg(unix)]
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

use serde_json::Value;
use uuid::Uuid;

use crate::daemon_paths::get_daemon_socket_path;
use crate::daemon_protocol::{ErrorEnvelope, RequestEnvelope, ResponseEnvelope, PROTOCOL_VERSION};
use crate::error::KanbusError;

/// Test-only response override for daemon client requests.
#[derive(Clone, Debug)]
pub enum TestDaemonResponse {
    /// Simulate an empty daemon response.
    Empty,
    /// Simulate a daemon connection error.
    IoError,
    /// Return a fixed response envelope.
    Envelope(ResponseEnvelope),
}

static TEST_DAEMON_RESPONSES: OnceLock<Mutex<Vec<TestDaemonResponse>>> = OnceLock::new();
static TEST_DAEMON_SPAWN_DISABLED: OnceLock<Mutex<bool>> = OnceLock::new();

/// Set the test response for the next daemon request.
///
/// Passing `None` clears any pending override.
pub fn set_test_daemon_response(response: Option<TestDaemonResponse>) {
    let cell = TEST_DAEMON_RESPONSES.get_or_init(|| Mutex::new(Vec::new()));
    let mut guard = cell.lock().expect("lock test response");
    guard.clear();
    if let Some(item) = response {
        guard.push(item);
    }
}

/// Set a sequence of test responses for daemon requests.
pub fn set_test_daemon_responses(responses: Vec<TestDaemonResponse>) {
    let cell = TEST_DAEMON_RESPONSES.get_or_init(|| Mutex::new(Vec::new()));
    let mut guard = cell.lock().expect("lock test responses");
    *guard = responses;
}

/// Return whether a test daemon response override is set.
pub fn has_test_daemon_response() -> bool {
    let cell = TEST_DAEMON_RESPONSES.get_or_init(|| Mutex::new(Vec::new()));
    let guard = cell.lock().expect("lock test response");
    !guard.is_empty()
}

/// Disable daemon spawning for tests when set to true.
pub fn set_test_daemon_spawn_disabled(disabled: bool) {
    let cell = TEST_DAEMON_SPAWN_DISABLED.get_or_init(|| Mutex::new(false));
    let mut guard = cell.lock().expect("lock test spawn flag");
    *guard = disabled;
}

fn take_test_daemon_response() -> Option<TestDaemonResponse> {
    let cell = TEST_DAEMON_RESPONSES.get_or_init(|| Mutex::new(Vec::new()));
    let mut guard = cell.lock().expect("lock test response");
    if guard.is_empty() {
        None
    } else {
        Some(guard.remove(0))
    }
}

fn is_test_spawn_disabled() -> bool {
    let cell = TEST_DAEMON_SPAWN_DISABLED.get_or_init(|| Mutex::new(false));
    let guard = cell.lock().expect("lock test spawn flag");
    *guard
}

/// Return whether daemon mode is enabled.
pub fn is_daemon_enabled() -> bool {
    let value = env::var("KANBUS_NO_DAEMON")
        .unwrap_or_default()
        .to_lowercase();
    !matches!(value.as_str(), "1" | "true" | "yes")
}

/// Request index list from the daemon, spawning it if needed.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if daemon request fails.
pub fn request_index_list(root: &Path) -> Result<Vec<Value>, KanbusError> {
    if !is_daemon_enabled() {
        return Err(KanbusError::IssueOperation("daemon disabled".to_string()));
    }
    let socket_path = get_daemon_socket_path(root)?;
    let request = RequestEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: format!("req-{}", Uuid::new_v4().simple()),
        action: "index.list".to_string(),
        payload: BTreeMap::new(),
    };
    if !socket_path.exists() {
        spawn_daemon(root)?;
    }
    let response = request_with_recovery(&socket_path, &request, root)?;
    if response.status != "ok" {
        let error = response.error.unwrap_or(ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        });
        return Err(KanbusError::IssueOperation(error.message));
    }
    let result = response.result.unwrap_or_default();
    match result.get("issues") {
        Some(Value::Array(values)) => Ok(values.clone()),
        _ => Ok(Vec::new()),
    }
}

/// Request daemon status.
pub fn request_status(root: &Path) -> Result<BTreeMap<String, Value>, KanbusError> {
    if !is_daemon_enabled() {
        return Err(KanbusError::IssueOperation("daemon disabled".to_string()));
    }
    let socket_path = get_daemon_socket_path(root)?;
    let request = RequestEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: format!("req-{}", Uuid::new_v4().simple()),
        action: "ping".to_string(),
        payload: BTreeMap::new(),
    };
    let response = request_with_recovery(&socket_path, &request, root)?;
    if response.status != "ok" {
        let error = response.error.unwrap_or(ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        });
        return Err(KanbusError::IssueOperation(error.message));
    }
    Ok(response.result.unwrap_or_default())
}

/// Request daemon shutdown.
pub fn request_shutdown(root: &Path) -> Result<BTreeMap<String, Value>, KanbusError> {
    if !is_daemon_enabled() {
        return Err(KanbusError::IssueOperation("daemon disabled".to_string()));
    }
    let socket_path = get_daemon_socket_path(root)?;
    let request = RequestEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: format!("req-{}", Uuid::new_v4().simple()),
        action: "shutdown".to_string(),
        payload: BTreeMap::new(),
    };
    let response = request_with_recovery(&socket_path, &request, root)?;
    if response.status != "ok" {
        let error = response.error.unwrap_or(ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        });
        return Err(KanbusError::IssueOperation(error.message));
    }
    Ok(response.result.unwrap_or_default())
}

fn request_with_recovery(
    socket_path: &Path,
    request: &RequestEnvelope,
    root: &Path,
) -> Result<ResponseEnvelope, KanbusError> {
    match send_request(socket_path, request) {
        Ok(response) => Ok(response),
        Err(error) => {
            if !matches!(error, KanbusError::Io(_)) {
                return Err(error);
            }
            if socket_path.exists() {
                std::fs::remove_file(socket_path)
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
            }
            spawn_daemon(root)?;
            let mut last_error = error;
            for _ in 0..10 {
                match send_request(socket_path, request) {
                    Ok(response) => return Ok(response),
                    Err(err) => {
                        if !matches!(err, KanbusError::Io(_)) {
                            return Err(err);
                        }
                        last_error = err;
                        std::thread::sleep(Duration::from_millis(50));
                    }
                }
            }
            Err(last_error)
        }
    }
}

#[cfg(unix)]
fn send_request(
    socket_path: &Path,
    request: &RequestEnvelope,
) -> Result<ResponseEnvelope, KanbusError> {
    if let Some(response) = take_test_daemon_response() {
        return match response {
            TestDaemonResponse::Empty => Err(KanbusError::IssueOperation(
                "empty daemon response".to_string(),
            )),
            TestDaemonResponse::IoError => {
                Err(KanbusError::Io("daemon connection failed".to_string()))
            }
            TestDaemonResponse::Envelope(envelope) => Ok(envelope),
        };
    }
    let mut stream =
        UnixStream::connect(socket_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let payload =
        serde_json::to_string(request).map_err(|error| KanbusError::Io(error.to_string()))?;
    stream
        .write_all(payload.as_bytes())
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    stream
        .write_all(b"\n")
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader
        .read_line(&mut line)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if line.trim().is_empty() {
        return Err(KanbusError::IssueOperation(
            "empty daemon response".to_string(),
        ));
    }
    serde_json::from_str(&line).map_err(|error| KanbusError::Io(error.to_string()))
}

#[cfg(not(unix))]
fn send_request(
    _socket_path: &Path,
    _request: &RequestEnvelope,
) -> Result<ResponseEnvelope, KanbusError> {
    Err(KanbusError::IssueOperation(
        "daemon not supported on this platform".to_string(),
    ))
}

#[cfg(unix)]
fn spawn_daemon(root: &Path) -> Result<(), KanbusError> {
    if is_test_spawn_disabled() {
        return Ok(());
    }
    Command::new(std::env::current_exe().map_err(|error| KanbusError::Io(error.to_string()))?)
        .arg("daemon")
        .arg("--root")
        .arg(root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(())
}

#[cfg(not(unix))]
fn spawn_daemon(_root: &Path) -> Result<(), KanbusError> {
    Err(KanbusError::IssueOperation(
        "daemon not supported on this platform".to_string(),
    ))
}
