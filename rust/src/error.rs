//! Error types for Kanbus.

use std::fmt::{self, Display, Formatter};

/// Errors returned by Kanbus operations.
#[derive(Debug)]
pub enum KanbusError {
    /// Initialization failed due to user-facing validation.
    Initialization(String),
    /// An unexpected IO error occurred.
    Io(String),
    /// Issue ID generation failed.
    IdGenerationFailed(String),
    /// Configuration loading or validation failed.
    Configuration(String),
    /// Workflow transition validation failed.
    InvalidTransition(String),
    /// Hierarchy validation failed.
    InvalidHierarchy(String),
    /// Issue operation failed.
    IssueOperation(String),
    /// Protocol validation failed.
    ProtocolError(String),
}

impl Display for KanbusError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        match self {
            KanbusError::Initialization(message) => write!(formatter, "{message}"),
            KanbusError::Io(message) => write!(formatter, "{message}"),
            KanbusError::IdGenerationFailed(message) => write!(formatter, "{message}"),
            KanbusError::Configuration(message) => write!(formatter, "{message}"),
            KanbusError::InvalidTransition(message) => write!(formatter, "{message}"),
            KanbusError::InvalidHierarchy(message) => write!(formatter, "{message}"),
            KanbusError::IssueOperation(message) => write!(formatter, "{message}"),
            KanbusError::ProtocolError(message) => write!(formatter, "{message}"),
        }
    }
}

impl std::error::Error for KanbusError {}
