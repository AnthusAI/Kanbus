//! Notification publisher for sending real-time events to the console server via Unix domain socket.

use crate::error::KanbusError;
use crate::notification_events::NotificationEvent;
use sha2::{Digest, Sha256};
use std::io::Write;
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
        // Log error but don't fail - notification is best-effort
        eprintln!("Warning: Failed to send notification: {}", e);
    }

    Ok(())
}

/// Synchronously send notification via Unix domain socket.
fn send_notification_sync(socket_path: &Path, event: &NotificationEvent) -> Result<(), KanbusError> {
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

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_publish_notification_does_not_block() {
        // This should complete immediately even if server is unreachable
        let temp_dir = tempdir().unwrap();
        let event = NotificationEvent::IssueFocused {
            issue_id: "test-123".to_string(),
            user: None,
        };

        let result = publish_notification(temp_dir.path(), event);
        assert!(result.is_ok());
    }

    #[test]
    fn test_socket_path_is_deterministic() {
        let temp_dir = tempdir().unwrap();
        let path1 = get_socket_path(temp_dir.path());
        let path2 = get_socket_path(temp_dir.path());
        assert_eq!(path1, path2);
    }

    #[test]
    fn test_socket_path_differs_by_project() {
        let temp_dir1 = tempdir().unwrap();
        let temp_dir2 = tempdir().unwrap();
        let path1 = get_socket_path(temp_dir1.path());
        let path2 = get_socket_path(temp_dir2.path());
        assert_ne!(path1, path2);
    }
}
