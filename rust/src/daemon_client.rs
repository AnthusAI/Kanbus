//! Daemon client utilities for index access.

use std::collections::{BTreeMap, HashSet};
use std::env;
#[cfg(unix)]
use std::io::{BufRead, BufReader, Write};
#[cfg(unix)]
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
#[cfg(unix)]
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
static TEST_DAEMON_RESTART_RECORDED: OnceLock<Mutex<bool>> = OnceLock::new();
static DAEMON_UNAVAILABLE_ROOTS: OnceLock<Mutex<HashSet<PathBuf>>> = OnceLock::new();

/// Maximum time to wait for a just-started daemon socket to become connectable.
const DAEMON_SOCKET_WAIT: Duration = Duration::from_millis(400);
/// Delay between socket-connect attempts while waiting for a starting daemon.
const DAEMON_SOCKET_POLL_INTERVAL: Duration = Duration::from_millis(25);

fn mark_daemon_unavailable(root: &Path) {
    let cell = DAEMON_UNAVAILABLE_ROOTS.get_or_init(|| Mutex::new(HashSet::new()));
    if let Ok(mut guard) = cell.lock() {
        guard.insert(root.to_path_buf());
    }
}

fn is_daemon_unavailable(root: &Path) -> bool {
    let cell = DAEMON_UNAVAILABLE_ROOTS.get_or_init(|| Mutex::new(HashSet::new()));
    cell.lock()
        .map(|guard| guard.contains(&root.to_path_buf()))
        .unwrap_or(false)
}

/// Clear the per-root "daemon unavailable" sticky marks (test helper).
pub fn reset_daemon_unavailable_roots_for_testing() {
    let cell = DAEMON_UNAVAILABLE_ROOTS.get_or_init(|| Mutex::new(HashSet::new()));
    if let Ok(mut guard) = cell.lock() {
        guard.clear();
    }
}

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

/// Error message returned when a stale daemon rejects the current config schema.
pub const DAEMON_CONFIG_SCHEMA_ERROR_MESSAGE: &str = "unknown configuration fields";

/// Return whether a daemon error indicates stale config schema parsing.
///
/// # Arguments
/// * `message` - Daemon error message text.
///
/// # Returns
/// `true` when the message is a config schema rejection.
pub fn is_daemon_config_schema_error(message: &str) -> bool {
    message == DAEMON_CONFIG_SCHEMA_ERROR_MESSAGE
}

/// Return whether `restart_daemon` ran during the current test scenario.
pub fn was_daemon_restarted_for_testing() -> bool {
    let cell = TEST_DAEMON_RESTART_RECORDED.get_or_init(|| Mutex::new(false));
    *cell.lock().expect("lock daemon restart recorder")
}

/// Clear the `restart_daemon` test recorder.
pub fn reset_daemon_restart_recorded_for_testing() {
    let cell = TEST_DAEMON_RESTART_RECORDED.get_or_init(|| Mutex::new(false));
    *cell.lock().expect("lock daemon restart recorder") = false;
}

/// Restart the daemon after a stale process rejects the current config schema.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` when socket cleanup fails.
pub fn restart_daemon(root: &Path) -> Result<(), KanbusError> {
    {
        let cell = TEST_DAEMON_RESTART_RECORDED.get_or_init(|| Mutex::new(false));
        *cell.lock().expect("lock daemon restart recorder") = true;
    }
    if !has_test_daemon_response() {
        let _ = request_shutdown(root);
    }
    let socket_path = get_daemon_socket_path(root)?;
    if socket_path.exists() {
        std::fs::remove_file(&socket_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    spawn_daemon(root)?;
    std::thread::sleep(Duration::from_millis(50));
    Ok(())
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
    ensure_daemon_socket_best_effort(root, &socket_path)?;
    let response = request_with_recovery(&socket_path, &request, root)?;
    if response.status != "ok" {
        let error = response.error.unwrap_or(ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        });
        if is_daemon_config_schema_error(&error.message) {
            restart_daemon(root)?;
            let retry_response = request_with_recovery(&socket_path, &request, root)?;
            if retry_response.status != "ok" {
                let retry_error = retry_response.error.unwrap_or(ErrorEnvelope {
                    code: "internal_error".to_string(),
                    message: "daemon error".to_string(),
                    details: BTreeMap::new(),
                });
                return Err(KanbusError::IssueOperation(retry_error.message));
            }
            let result = retry_response.result.unwrap_or_default();
            return match result.get("issues") {
                Some(Value::Array(values)) => Ok(values.clone()),
                _ => Ok(Vec::new()),
            };
        }
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

/// Best-effort just-in-time daemon start: spawn once, wait briefly for the
/// socket, and mark the root unavailable when the daemon cannot be reached.
///
/// The daemon is an accelerator only: callers fall back to direct storage
/// access whenever this returns `Err`.
fn ensure_daemon_socket_best_effort(root: &Path, socket_path: &Path) -> Result<(), KanbusError> {
    if socket_path.exists() {
        return Ok(());
    }
    if has_test_daemon_response() {
        // Mocked daemon scenarios drive responses through send_request; skip
        // spawning so the override is consumed as-is.
        return Ok(());
    }
    if is_daemon_unavailable(root) {
        log::debug!("daemon previously unavailable; using direct storage access");
        return Err(KanbusError::Io(format!(
            "daemon socket unavailable: {}",
            socket_path.display()
        )));
    }
    if let Err(error) = spawn_daemon(root) {
        mark_daemon_unavailable(root);
        log::debug!("daemon spawn failed; using direct storage access");
        return Err(KanbusError::Io(format!("daemon spawn failed: {error}")));
    }
    let deadline = std::time::Instant::now() + DAEMON_SOCKET_WAIT;
    loop {
        if socket_path.exists() && is_socket_connectable(socket_path) {
            return Ok(());
        }
        if std::time::Instant::now() >= deadline {
            mark_daemon_unavailable(root);
            log::debug!("daemon socket did not become ready; using direct storage access");
            return Err(KanbusError::Io(format!(
                "daemon socket did not become ready: {}",
                socket_path.display()
            )));
        }
        std::thread::sleep(DAEMON_SOCKET_POLL_INTERVAL);
    }
}

#[cfg(unix)]
fn is_socket_connectable(socket_path: &Path) -> bool {
    UnixStream::connect(socket_path).is_ok()
}

#[cfg(not(unix))]
fn is_socket_connectable(_socket_path: &Path) -> bool {
    false
}

/// Send a generic Virtuus service request through Kanbus's resident daemon.
///
/// The daemon is a just-in-time accelerator: it is started best-effort and is
/// never required for correctness. Callers fall back to direct synchronous
/// storage access whenever this returns `Err`.
pub fn request_virtuus(root: &Path, request: &Value) -> Result<Value, KanbusError> {
    if !is_daemon_enabled() {
        return Err(KanbusError::IssueOperation("daemon disabled".to_string()));
    }
    let socket_path = get_daemon_socket_path(root)?;
    if is_daemon_unavailable(root) {
        log::debug!("daemon previously unavailable; using direct storage access");
        return Err(KanbusError::Io(format!(
            "daemon socket unavailable: {}",
            socket_path.display()
        )));
    }
    if !socket_path.exists() {
        ensure_daemon_socket_best_effort(root, &socket_path)?;
    }
    match send_virtuus_request(&socket_path, request) {
        Ok(response) => {
            if response.get("ok").and_then(Value::as_bool) == Some(true) {
                return Ok(response.get("result").cloned().unwrap_or(Value::Null));
            }
            log::debug!(
                "Virtuus daemon request failed: {}; falling back to direct storage access",
                response
                    .get("error")
                    .and_then(Value::as_str)
                    .unwrap_or("Virtuus daemon error")
            );
            Err(KanbusError::IssueOperation(
                response
                    .get("error")
                    .and_then(Value::as_str)
                    .unwrap_or("Virtuus daemon error")
                    .to_string(),
            ))
        }
        Err(error) => {
            log::debug!(
                "Virtuus daemon request failed: {}; falling back to direct storage access",
                error
            );
            Err(KanbusError::Io(format!(
                "Virtuus daemon request failed: {error}"
            )))
        }
    }
}

#[cfg(unix)]
fn send_virtuus_request(socket_path: &Path, request: &Value) -> Result<Value, String> {
    let mut stream = UnixStream::connect(socket_path).map_err(|error| error.to_string())?;
    let payload = serde_json::to_string(request).map_err(|error| error.to_string())?;
    stream
        .write_all(payload.as_bytes())
        .map_err(|error| error.to_string())?;
    stream.write_all(b"\n").map_err(|error| error.to_string())?;
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader
        .read_line(&mut line)
        .map_err(|error| error.to_string())?;
    if line.trim().is_empty() {
        return Err("empty daemon response".to_string());
    }
    serde_json::from_str(&line).map_err(|error| error.to_string())
}

#[cfg(not(unix))]
fn send_virtuus_request(_socket_path: &Path, _request: &Value) -> Result<Value, String> {
    Err("daemon not supported on this platform".to_string())
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
            for _ in 0..10 {
                match send_request(socket_path, request) {
                    Ok(response) => return Ok(response),
                    Err(err) => {
                        if !matches!(err, KanbusError::Io(_)) {
                            return Err(err);
                        }
                        std::thread::sleep(Duration::from_millis(50));
                    }
                }
            }
            Err(KanbusError::Io(format!(
                "daemon connection failed after retries: {}. Set KANBUS_NO_DAEMON=1 to bypass the daemon.",
                socket_path.display()
            )))
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
    let mut stream = UnixStream::connect(socket_path).map_err(|error| {
        KanbusError::Io(format!(
            "daemon connect failed: {}: {}",
            socket_path.display(),
            error
        ))
    })?;
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
    // Resolve to a canonical, existing directory before handing it to the
    // respawned process. `root` is passed as a single argv entry (never
    // through a shell, so shell metacharacters are inert), but canonicalize
    // still gives a hard guarantee that we only ever pass on a real
    // filesystem path this process already found, not an arbitrary string.
    let canonical_root = root.canonicalize().map_err(|error| {
        KanbusError::Io(format!(
            "cannot resolve daemon root {}: {error}",
            root.display()
        ))
    })?;
    if !canonical_root.is_dir() {
        return Err(KanbusError::Io(format!(
            "daemon root is not a directory: {}",
            canonical_root.display()
        )));
    }
    Command::new(std::env::current_exe().map_err(|error| KanbusError::Io(error.to_string()))?)
        .arg("daemon")
        .arg("--root")
        .arg(&canonical_root)
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
