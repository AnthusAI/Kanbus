//! IPC protocol models and version checks.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::error::KanbusError;

/// Current protocol version supported by the daemon.
pub const PROTOCOL_VERSION: &str = "1.0";

/// Client request envelope for daemon IPC.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RequestEnvelope {
    /// Protocol version string.
    pub protocol_version: String,
    /// Client request identifier.
    pub request_id: String,
    /// Requested action name.
    pub action: String,
    /// Action payload data.
    pub payload: BTreeMap<String, serde_json::Value>,
}

/// Structured error payload for daemon responses.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorEnvelope {
    /// Machine-readable error code.
    pub code: String,
    /// Human-readable error summary.
    pub message: String,
    /// Structured error details.
    pub details: BTreeMap<String, serde_json::Value>,
}

/// Daemon response envelope for IPC.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResponseEnvelope {
    /// Protocol version string.
    pub protocol_version: String,
    /// Echo of the client request ID.
    pub request_id: String,
    /// Status string ("ok" or "error").
    pub status: String,
    /// Result payload when successful.
    pub result: Option<BTreeMap<String, serde_json::Value>>,
    /// Error payload when failed.
    pub error: Option<ErrorEnvelope>,
}

/// Validate protocol version compatibility.
///
/// # Arguments
/// * `client_version` - Client protocol version string.
/// * `daemon_version` - Daemon protocol version string.
///
/// # Errors
/// Returns `KanbusError::ProtocolError` if versions are incompatible.
pub fn validate_protocol_compatibility(
    client_version: &str,
    daemon_version: &str,
) -> Result<(), KanbusError> {
    let (client_major, client_minor) = parse_version(client_version)?;
    let (daemon_major, daemon_minor) = parse_version(daemon_version)?;
    if client_major != daemon_major {
        return Err(KanbusError::ProtocolError(
            "protocol version mismatch".to_string(),
        ));
    }
    if client_minor > daemon_minor {
        return Err(KanbusError::ProtocolError(
            "protocol version unsupported".to_string(),
        ));
    }
    Ok(())
}

fn parse_version(version: &str) -> Result<(u32, u32), KanbusError> {
    let mut parts = version.split('.');
    let major = parts
        .next()
        .ok_or_else(|| KanbusError::ProtocolError("invalid protocol version".to_string()))?;
    let minor = parts
        .next()
        .ok_or_else(|| KanbusError::ProtocolError("invalid protocol version".to_string()))?;
    if parts.next().is_some() {
        return Err(KanbusError::ProtocolError(
            "invalid protocol version".to_string(),
        ));
    }
    let major: u32 = major
        .parse()
        .map_err(|_| KanbusError::ProtocolError("invalid protocol version".to_string()))?;
    let minor: u32 = minor
        .parse()
        .map_err(|_| KanbusError::ProtocolError("invalid protocol version".to_string()))?;
    Ok((major, minor))
}
