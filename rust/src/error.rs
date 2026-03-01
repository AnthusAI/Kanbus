//! Error types for Kanbus.

use std::fmt::{self, Display, Formatter};

/// Additional optional detail for policy violations.
#[derive(Debug, Default)]
pub struct PolicyViolationDetails {
    /// Explanations attached by follow-up explain steps.
    pub explanations: Vec<String>,
    /// Guidance lines attached to this violation.
    pub guidance: Vec<String>,
}

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
    /// Policy violation occurred.
    PolicyViolation {
        /// Path to the policy file.
        policy_file: Box<str>,
        /// Scenario name that failed.
        scenario: Box<str>,
        /// The specific step that failed.
        failed_step: Box<str>,
        /// Human-readable explanation.
        message: Box<str>,
        /// Issue ID being evaluated.
        issue_id: Box<str>,
        /// Optional expanded detail for rendering.
        details: Box<PolicyViolationDetails>,
    },
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
            KanbusError::PolicyViolation {
                policy_file,
                scenario,
                failed_step,
                message,
                issue_id,
                details,
            } => {
                write!(
                    formatter,
                    "policy violation in {policy_file} for issue {issue_id}\n  Scenario: {scenario}\n  Failed: {failed_step}\n  {message}"
                )?;
                for explanation in &details.explanations {
                    write!(formatter, "\n  Explanation: {explanation}")?;
                }
                if !details.guidance.is_empty() {
                    write!(formatter, "\n  Guidance:")?;
                    for line in &details.guidance {
                        write!(formatter, "\n    {line}")?;
                    }
                }
                Ok(())
            }
        }
    }
}

impl std::error::Error for KanbusError {}
