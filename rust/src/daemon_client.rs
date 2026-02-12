//! Daemon client utilities for index access.

use std::collections::BTreeMap;
use std::env;
use std::io::{BufRead, BufReader, Write};
#[cfg(unix)]
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::process::{Command, Stdio};

use serde_json::Value;
use uuid::Uuid;

use crate::daemon_paths::get_daemon_socket_path;
use crate::daemon_protocol::{ErrorEnvelope, RequestEnvelope, ResponseEnvelope, PROTOCOL_VERSION};
use crate::error::TaskulusError;

/// Return whether daemon mode is enabled.
pub fn is_daemon_enabled() -> bool {
    let value = env::var("TASKULUS_NO_DAEMON")
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
/// Returns `TaskulusError` if daemon request fails.
pub fn request_index_list(root: &Path) -> Result<Vec<Value>, TaskulusError> {
    if !is_daemon_enabled() {
        return Err(TaskulusError::IssueOperation("daemon disabled".to_string()));
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
        return Err(TaskulusError::IssueOperation(error.message));
    }
    let result = response.result.unwrap_or_default();
    match result.get("issues") {
        Some(Value::Array(values)) => Ok(values.clone()),
        _ => Ok(Vec::new()),
    }
}

/// Request daemon status.
pub fn request_status(root: &Path) -> Result<BTreeMap<String, Value>, TaskulusError> {
    if !is_daemon_enabled() {
        return Err(TaskulusError::IssueOperation("daemon disabled".to_string()));
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
        return Err(TaskulusError::IssueOperation(error.message));
    }
    Ok(response.result.unwrap_or_default())
}

/// Request daemon shutdown.
pub fn request_shutdown(root: &Path) -> Result<BTreeMap<String, Value>, TaskulusError> {
    if !is_daemon_enabled() {
        return Err(TaskulusError::IssueOperation("daemon disabled".to_string()));
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
        return Err(TaskulusError::IssueOperation(error.message));
    }
    Ok(response.result.unwrap_or_default())
}

fn request_with_recovery(
    socket_path: &Path,
    request: &RequestEnvelope,
    root: &Path,
) -> Result<ResponseEnvelope, TaskulusError> {
    match send_request(socket_path, request) {
        Ok(response) => Ok(response),
        Err(error) => {
            if !matches!(error, TaskulusError::Io(_)) {
                return Err(error);
            }
            if socket_path.exists() {
                std::fs::remove_file(socket_path)
                    .map_err(|error| TaskulusError::Io(error.to_string()))?;
            }
            spawn_daemon(root)?;
            send_request(socket_path, request)
        }
    }
}

#[cfg(unix)]
fn send_request(
    socket_path: &Path,
    request: &RequestEnvelope,
) -> Result<ResponseEnvelope, TaskulusError> {
    let mut stream =
        UnixStream::connect(socket_path).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let payload =
        serde_json::to_string(request).map_err(|error| TaskulusError::Io(error.to_string()))?;
    stream
        .write_all(payload.as_bytes())
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    stream
        .write_all(b"\n")
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader
        .read_line(&mut line)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    if line.trim().is_empty() {
        return Err(TaskulusError::IssueOperation(
            "empty daemon response".to_string(),
        ));
    }
    serde_json::from_str(&line).map_err(|error| TaskulusError::Io(error.to_string()))
}

#[cfg(not(unix))]
fn send_request(
    _socket_path: &Path,
    _request: &RequestEnvelope,
) -> Result<ResponseEnvelope, TaskulusError> {
    Err(TaskulusError::IssueOperation(
        "daemon not supported on this platform".to_string(),
    ))
}

#[cfg(unix)]
fn spawn_daemon(root: &Path) -> Result<(), TaskulusError> {
    Command::new(std::env::current_exe().map_err(|error| TaskulusError::Io(error.to_string()))?)
        .arg("daemon")
        .arg("--root")
        .arg(root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    Ok(())
}

#[cfg(not(unix))]
fn spawn_daemon(_root: &Path) -> Result<(), TaskulusError> {
    Err(TaskulusError::IssueOperation(
        "daemon not supported on this platform".to_string(),
    ))
}
