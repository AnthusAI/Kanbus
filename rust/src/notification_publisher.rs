//! Notification publisher for sending real-time events to the console server via Unix domain socket.

use crate::error::KanbusError;
use crate::notification_events::NotificationEvent;
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

    // Debug: write to file
    use std::io::Write;
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open("/tmp/kanbus-cli-debug.log")
    {
        let _ = writeln!(
            f,
            "CLI: Sending notification to socket: {}",
            socket_path.display()
        );
    }

    let result = send_notification_sync(&socket_path, &event);

    if let Err(e) = result {
        // Log error but don't fail - notification is best-effort
        if let Ok(mut f) = std::fs::OpenOptions::new()
            .append(true)
            .open("/tmp/kanbus-cli-debug.log")
        {
            let _ = writeln!(f, "CLI: Failed: {}", e);
        }
        eprintln!("Warning: Failed to send notification: {}", e);
    } else if let Ok(mut f) = std::fs::OpenOptions::new()
        .append(true)
        .open("/tmp/kanbus-cli-debug.log")
    {
        let _ = writeln!(f, "CLI: Notification sent successfully");
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
    Ok(())
}
