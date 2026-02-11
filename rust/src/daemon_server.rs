//! Daemon server for just-in-time index access.

use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;

use serde_json::Value;

use crate::cache::{collect_issue_file_mtimes, load_cache_if_valid, write_cache};
use crate::daemon_paths::{get_daemon_socket_path, get_index_cache_path};
use crate::daemon_protocol::{
    validate_protocol_compatibility, ErrorEnvelope, RequestEnvelope, ResponseEnvelope,
    PROTOCOL_VERSION,
};
use crate::error::TaskulusError;
use crate::file_io::load_project_directory;
use crate::index::build_index_from_directory;
use crate::models::IssueData;

/// Run the daemon server for a repository root.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `TaskulusError` if the daemon fails to bind or serve requests.
pub fn run_daemon(root: &Path) -> Result<(), TaskulusError> {
    let socket_path = get_daemon_socket_path(root)?;
    let socket_dir = socket_path
        .parent()
        .ok_or_else(|| TaskulusError::Io("invalid socket path".to_string()))?;
    std::fs::create_dir_all(socket_dir).map_err(|error| TaskulusError::Io(error.to_string()))?;
    if socket_path.exists() {
        std::fs::remove_file(&socket_path).map_err(|error| TaskulusError::Io(error.to_string()))?;
    }

    let listener =
        UnixListener::bind(&socket_path).map_err(|error| TaskulusError::Io(error.to_string()))?;
    for stream in listener.incoming() {
        let stream = stream.map_err(|error| TaskulusError::Io(error.to_string()))?;
        handle_stream(root, stream)?;
    }
    Ok(())
}

fn handle_stream(root: &Path, stream: UnixStream) -> Result<(), TaskulusError> {
    let mut reader = BufReader::new(
        stream
            .try_clone()
            .map_err(|error| TaskulusError::Io(format!("failed to clone stream: {error}")))?,
    );
    let mut line = String::new();
    if reader
        .read_line(&mut line)
        .map_err(|error| TaskulusError::Io(format!("failed to read from stream: {error}")))?
        == 0
    {
        return Ok(());
    }
    let mut stream = stream;
    let response = match serde_json::from_str::<RequestEnvelope>(&line) {
        Ok(request) => handle_request(root, request),
        Err(error) => ResponseEnvelope {
            protocol_version: PROTOCOL_VERSION.to_string(),
            request_id: "unknown".to_string(),
            status: "error".to_string(),
            result: None,
            error: Some(ErrorEnvelope {
                code: "invalid_request".to_string(),
                message: error.to_string(),
                details: BTreeMap::new(),
            }),
        },
    };
    let payload =
        serde_json::to_string(&response).map_err(|error| TaskulusError::Io(error.to_string()))?;
    stream
        .write_all(payload.as_bytes())
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    stream
        .write_all(b"\n")
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    Ok(())
}

fn handle_request(root: &Path, request: RequestEnvelope) -> ResponseEnvelope {
    if let Err(error) = validate_protocol_compatibility(&request.protocol_version, PROTOCOL_VERSION)
    {
        let code = if error.to_string() == "protocol version unsupported" {
            "protocol_version_unsupported"
        } else {
            "protocol_version_mismatch"
        };
        return ResponseEnvelope {
            protocol_version: PROTOCOL_VERSION.to_string(),
            request_id: request.request_id,
            status: "error".to_string(),
            result: None,
            error: Some(ErrorEnvelope {
                code: code.to_string(),
                message: error.to_string(),
                details: BTreeMap::new(),
            }),
        };
    }

    if request.action == "ping" {
        let mut result = BTreeMap::new();
        result.insert("status".to_string(), Value::String("ok".to_string()));
        return ResponseEnvelope {
            protocol_version: PROTOCOL_VERSION.to_string(),
            request_id: request.request_id,
            status: "ok".to_string(),
            result: Some(result),
            error: None,
        };
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
                return ResponseEnvelope {
                    protocol_version: PROTOCOL_VERSION.to_string(),
                    request_id: request.request_id,
                    status: "ok".to_string(),
                    result: Some(result),
                    error: None,
                };
            }
            Err(error) => {
                return ResponseEnvelope {
                    protocol_version: PROTOCOL_VERSION.to_string(),
                    request_id: request.request_id,
                    status: "error".to_string(),
                    result: None,
                    error: Some(ErrorEnvelope {
                        code: "internal_error".to_string(),
                        message: error.to_string(),
                        details: BTreeMap::new(),
                    }),
                };
            }
        }
    }

    ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: request.request_id,
        status: "error".to_string(),
        result: None,
        error: Some(ErrorEnvelope {
            code: "unknown_action".to_string(),
            message: "unknown action".to_string(),
            details: {
                let mut details = BTreeMap::new();
                details.insert("action".to_string(), Value::String(request.action));
                details
            },
        }),
    }
}

fn load_index(root: &Path) -> Result<Vec<IssueData>, TaskulusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    let cache_path = get_index_cache_path(root)?;
    if let Some(index) = load_cache_if_valid(&cache_path, &issues_dir)? {
        return Ok(index.by_id.values().cloned().collect());
    }
    let index = build_index_from_directory(&issues_dir)?;
    let mtimes = collect_issue_file_mtimes(&issues_dir)?;
    write_cache(&index, &cache_path, &mtimes)?;
    Ok(index.by_id.values().cloned().collect())
}
