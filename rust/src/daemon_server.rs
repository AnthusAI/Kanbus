//! Daemon server for just-in-time index access.

use std::collections::BTreeMap;
#[cfg(unix)]
use std::io::{BufRead, BufReader, Write};
#[cfg(unix)]
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;

use serde_json::Value;

#[cfg(unix)]
use crate::daemon_paths::get_daemon_socket_path;
use crate::daemon_protocol::{
    validate_protocol_compatibility, ErrorEnvelope, RequestEnvelope, ResponseEnvelope,
    PROTOCOL_VERSION,
};
use crate::error::KanbusError;
use crate::file_io::load_project_directory;
use crate::issue_files::ensure_all_issue_files_loaded;
use crate::models::IssueData;
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use virtuus::table::{StorageMode, ValidationMode};
use virtuus::Table;

/// Run the daemon server for a repository root.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if the daemon fails to bind or serve requests.
#[cfg(unix)]
pub fn run_daemon(root: &Path) -> Result<(), KanbusError> {
    let socket_path = get_daemon_socket_path(root)?;
    let socket_dir = socket_path
        .parent()
        .ok_or_else(|| KanbusError::Io("invalid socket path".to_string()))?;
    std::fs::create_dir_all(socket_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    if socket_path.exists() {
        std::fs::remove_file(&socket_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    }

    let listener =
        UnixListener::bind(&socket_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    warm_cache(root)?;
    let mut virtuus_service = virtuus::service::Service::new();
    for stream in listener.incoming() {
        let stream = stream.map_err(|error| KanbusError::Io(error.to_string()))?;
        if handle_stream(root, &mut virtuus_service, stream)? {
            break;
        }
    }
    Ok(())
}

#[cfg(not(unix))]
pub fn run_daemon(_root: &Path) -> Result<(), KanbusError> {
    Err(KanbusError::IssueOperation(
        "daemon not supported on this platform".to_string(),
    ))
}

fn warm_cache(root: &Path) -> Result<(), KanbusError> {
    let _ = load_index(root)?;
    Ok(())
}

#[cfg(unix)]
fn handle_stream(
    root: &Path,
    virtuus_service: &mut virtuus::service::Service,
    stream: UnixStream,
) -> Result<bool, KanbusError> {
    let mut reader = BufReader::new(
        stream
            .try_clone()
            .map_err(|error| KanbusError::Io(format!("failed to clone stream: {error}")))?,
    );
    let mut line = String::new();
    if reader
        .read_line(&mut line)
        .map_err(|error| KanbusError::Io(format!("failed to read from stream: {error}")))?
        == 0
    {
        return Ok(false);
    }
    let mut stream = stream;
    let generic_request: Value = match serde_json::from_str(&line) {
        Ok(request) => request,
        Err(error) => {
            let response = ResponseEnvelope {
                protocol_version: PROTOCOL_VERSION.to_string(),
                request_id: "unknown".to_string(),
                status: "error".to_string(),
                result: None,
                error: Some(ErrorEnvelope {
                    code: "internal_error".to_string(),
                    message: error.to_string(),
                    details: BTreeMap::new(),
                }),
            };
            let payload = serde_json::to_string(&response)
                .map_err(|serialization_error| KanbusError::Io(serialization_error.to_string()))?;
            stream
                .write_all(payload.as_bytes())
                .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
            stream
                .write_all(b"\n")
                .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
            return Ok(false);
        }
    };
    if generic_request.get("protocol_version").is_none() {
        let should_shutdown =
            generic_request.get("action").and_then(Value::as_str) == Some("shutdown");
        let response = virtuus_service.dispatch(generic_request);
        let payload =
            serde_json::to_string(&response).map_err(|error| KanbusError::Io(error.to_string()))?;
        stream
            .write_all(payload.as_bytes())
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        stream
            .write_all(b"\n")
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        return Ok(should_shutdown);
    }
    let (response, should_shutdown) = match serde_json::from_str::<RequestEnvelope>(&line) {
        Ok(request) => handle_request(root, request),
        Err(error) => (
            ResponseEnvelope {
                protocol_version: PROTOCOL_VERSION.to_string(),
                request_id: "unknown".to_string(),
                status: "error".to_string(),
                result: None,
                error: Some(ErrorEnvelope {
                    code: "internal_error".to_string(),
                    message: error.to_string(),
                    details: BTreeMap::new(),
                }),
            },
            false,
        ),
    };
    let payload =
        serde_json::to_string(&response).map_err(|error| KanbusError::Io(error.to_string()))?;
    stream
        .write_all(payload.as_bytes())
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    stream
        .write_all(b"\n")
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(should_shutdown)
}

fn handle_request(root: &Path, request: RequestEnvelope) -> (ResponseEnvelope, bool) {
    if let Err(error) = validate_protocol_compatibility(&request.protocol_version, PROTOCOL_VERSION)
    {
        let code = if error.to_string() == "protocol version unsupported" {
            "protocol_version_unsupported"
        } else {
            "protocol_version_mismatch"
        };
        return (
            ResponseEnvelope {
                protocol_version: PROTOCOL_VERSION.to_string(),
                request_id: request.request_id,
                status: "error".to_string(),
                result: None,
                error: Some(ErrorEnvelope {
                    code: code.to_string(),
                    message: error.to_string(),
                    details: BTreeMap::new(),
                }),
            },
            false,
        );
    }

    if request.action == "ping" {
        let mut result = BTreeMap::new();
        result.insert("status".to_string(), Value::String("ok".to_string()));
        return (
            ResponseEnvelope {
                protocol_version: PROTOCOL_VERSION.to_string(),
                request_id: request.request_id,
                status: "ok".to_string(),
                result: Some(result),
                error: None,
            },
            false,
        );
    }

    if request.action == "shutdown" {
        let mut result = BTreeMap::new();
        result.insert("status".to_string(), Value::String("stopping".to_string()));
        return (
            ResponseEnvelope {
                protocol_version: PROTOCOL_VERSION.to_string(),
                request_id: request.request_id,
                status: "ok".to_string(),
                result: Some(result),
                error: None,
            },
            true,
        );
    }

    if request.action == "index.list" {
        match load_index(root) {
            Ok(issues) => {
                let mut result = BTreeMap::new();
                let values: Vec<Value> = issues
                    .into_iter()
                    .map(|issue| serde_json::to_value(issue).unwrap_or(Value::Null))
                    .collect();
                result.insert("issues".to_string(), Value::Array(values));
                return (
                    ResponseEnvelope {
                        protocol_version: PROTOCOL_VERSION.to_string(),
                        request_id: request.request_id,
                        status: "ok".to_string(),
                        result: Some(result),
                        error: None,
                    },
                    false,
                );
            }
            Err(error) => {
                return (
                    ResponseEnvelope {
                        protocol_version: PROTOCOL_VERSION.to_string(),
                        request_id: request.request_id,
                        status: "error".to_string(),
                        result: None,
                        error: Some(ErrorEnvelope {
                            code: "internal_error".to_string(),
                            message: error.to_string(),
                            details: BTreeMap::new(),
                        }),
                    },
                    false,
                );
            }
        }
    }

    let mut details = BTreeMap::new();
    details.insert("action".to_string(), Value::String(request.action));
    (
        ResponseEnvelope {
            protocol_version: PROTOCOL_VERSION.to_string(),
            request_id: request.request_id,
            status: "error".to_string(),
            result: None,
            error: Some(ErrorEnvelope {
                code: "unknown_action".to_string(),
                message: "unknown action".to_string(),
                details,
            }),
        },
        false,
    )
}

/// Handle a daemon request without opening a socket.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `request` - Request envelope to handle.
///
/// # Returns
/// Response envelope for the request.
pub fn handle_request_for_testing(root: &Path, request: RequestEnvelope) -> ResponseEnvelope {
    handle_request(root, request).0
}

fn load_index(root: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    static TABLES: OnceLock<Mutex<HashMap<std::path::PathBuf, Table>>> = OnceLock::new();
    let tables = TABLES.get_or_init(|| Mutex::new(HashMap::new()));
    let mut tables = tables
        .lock()
        .map_err(|_| KanbusError::Io("Virtuus table registry lock poisoned".to_string()))?;
    let table = tables.entry(issues_dir.clone()).or_insert_with(|| {
        let mut table = Table::new(
            "issues",
            Some("id"),
            None,
            None,
            Some(issues_dir.clone()),
            ValidationMode::Warn,
        )
        .expect("valid Virtuus issue table");
        table.set_storage_mode(StorageMode::Memory);
        table.set_pretty_json(true);
        table.set_check_interval(2);
        table.add_gsi("by_status", "status", None);
        table.add_gsi("by_type", "type", None);
        table.add_gsi("by_parent", "parent", None);
        table.add_gsi("by_label", "labels[*]", None);
        table.add_gsi(
            "blocked_by",
            "dependencies[dependency_type=blocked-by].target",
            None,
        );
        table.load_from_dir(None);
        table
    });
    let records = table.scan();
    ensure_all_issue_files_loaded(&issues_dir, &records)?;
    records
        .into_iter()
        .map(|record| {
            serde_json::from_value(record).map_err(|error| KanbusError::Io(error.to_string()))
        })
        .collect()
}
