//! Notification publisher for sending real-time events to the console server via Unix domain socket.

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::notification_events::NotificationEvent;
use reqwest::blocking::Client;
use sha2::{Digest, Sha256};
#[cfg(unix)]
use std::io::Write;
#[cfg(unix)]
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};

/// Get the Unix domain socket path for the current project.
///
/// The socket path is derived from the project root directory to ensure
/// each project has its own isolated notification channel.
fn get_socket_path(root: &Path) -> PathBuf {
    let canonical = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let mut hasher = Sha256::new();
    hasher.update(canonical.to_string_lossy().as_bytes());
    let hash = format!("{:x}", hasher.finalize());
    let socket_name = format!("kanbus-{}.sock", &hash[..12]);

    std::env::temp_dir().join(socket_name)
}

/// Publish a notification event to the console server via Unix domain socket.
///
/// This function sends the event to the console server's Unix socket.
/// The socket path is derived from the project root directory to ensure
/// each project has its own isolated notification channel.
///
/// Errors are logged but not propagated - notification failures should
/// not block CRUD operations.
pub fn publish_notification(root: &Path, event: NotificationEvent) -> Result<(), KanbusError> {
    let socket_path = get_socket_path(root);
    let result = send_notification_sync(&socket_path, &event);

    if let Err(e) = result {
        if let Err(http_error) = send_notification_http(root, &event) {
            eprintln!(
                "Warning: Failed to send notification (socket: {}, http: {})",
                e, http_error
            );
        }
    }

    Ok(())
}

/// Synchronously send notification via Unix domain socket.
#[cfg(unix)]
fn send_notification_sync(
    socket_path: &Path,
    event: &NotificationEvent,
) -> Result<(), KanbusError> {
    // Try to connect to the Unix socket
    let mut stream = UnixStream::connect(socket_path).map_err(|e| {
        KanbusError::IssueOperation(format!(
            "Console server not reachable (socket: {}): {}",
            socket_path.display(),
            e
        ))
    })?;

    // Serialize event to JSON and send as newline-delimited message
    let json_body = serde_json::to_string(event)
        .map_err(|e| KanbusError::IssueOperation(format!("Failed to serialize event: {}", e)))?;

    stream
        .write_all(json_body.as_bytes())
        .map_err(|e| KanbusError::IssueOperation(format!("Failed to write to socket: {}", e)))?;

    stream
        .write_all(b"\n")
        .map_err(|e| KanbusError::IssueOperation(format!("Failed to write newline: {}", e)))?;

    Ok(())
}

#[cfg(not(unix))]
fn send_notification_sync(
    _socket_path: &Path,
    _event: &NotificationEvent,
) -> Result<(), KanbusError> {
    Err(KanbusError::IssueOperation(
        "Unix sockets are not supported".to_string(),
    ))
}

fn send_notification_http(root: &Path, event: &NotificationEvent) -> Result<(), KanbusError> {
    let port = resolve_console_port(root);
    let url = format!("http://127.0.0.1:{port}/api/notifications");
    let body = serde_json::to_vec(event)
        .map_err(|e| KanbusError::IssueOperation(format!("Failed to serialize event: {}", e)))?;
    if let Ok(handle) = tokio::runtime::Handle::try_current() {
        let url = url.clone();
        let body = body.clone();
        handle.spawn(async move {
            let client = reqwest::Client::new();
            let _ = client
                .post(url)
                .header("Content-Type", "application/json")
                .body(body)
                .send()
                .await;
        });
        return Ok(());
    }

    let client = Client::new();
    client
        .post(url)
        .header("Content-Type", "application/json")
        .body(body)
        .send()
        .map_err(|e| {
            KanbusError::IssueOperation(format!("Failed to send HTTP notification: {}", e))
        })?;
    Ok(())
}

fn resolve_console_port(root: &Path) -> u16 {
    if let Ok(config_path) = get_configuration_path(root) {
        if let Ok(config) = load_project_configuration(&config_path) {
            if let Some(port) = config.console_port {
                return port;
            }
        }
    }
    5174
}
