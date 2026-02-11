//! Error types for Taskulus.

use std::fmt::{self, Display, Formatter};

/// Errors returned by Taskulus operations.
#[derive(Debug)]
pub enum TaskulusError {
    /// Initialization failed due to user-facing validation.
    Initialization(String),
    /// An unexpected IO error occurred.
    Io(String),
    /// Issue ID generation failed.
    IdGenerationFailed(String),
}

impl Display for TaskulusError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        match self {
            TaskulusError::Initialization(message) => write!(formatter, "{message}"),
            TaskulusError::Io(message) => write!(formatter, "{message}"),
            TaskulusError::IdGenerationFailed(message) => write!(formatter, "{message}"),
        }
    }
}

impl std::error::Error for TaskulusError {}
