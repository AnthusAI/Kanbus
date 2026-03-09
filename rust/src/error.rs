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
                    "policy violation in {policy_file} for issue {issue_id}\n  Rule: {scenario}\n  Failed: {failed_step}\n  {message}"
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn display_for_simple_variants_returns_message() {
        let variants = vec![
            KanbusError::Initialization("init".to_string()),
            KanbusError::Io("io".to_string()),
            KanbusError::IdGenerationFailed("id".to_string()),
            KanbusError::Configuration("cfg".to_string()),
            KanbusError::InvalidTransition("transition".to_string()),
            KanbusError::InvalidHierarchy("hierarchy".to_string()),
            KanbusError::IssueOperation("issue".to_string()),
            KanbusError::ProtocolError("protocol".to_string()),
        ];
        let rendered: Vec<String> = variants.into_iter().map(|e| e.to_string()).collect();
        assert_eq!(
            rendered,
            vec!["init", "io", "id", "cfg", "transition", "hierarchy", "issue", "protocol"]
        );
    }

    #[test]
    fn display_for_policy_violation_includes_details_and_guidance() {
        let error = KanbusError::PolicyViolation {
            policy_file: "rules.policy".into(),
            scenario: "Scenario name".into(),
            failed_step: "Then step".into(),
            message: "step failed".into(),
            issue_id: "kanbus-1".into(),
            details: Box::new(PolicyViolationDetails {
                explanations: vec!["why one".to_string(), "why two".to_string()],
                guidance: vec!["do this".to_string()],
            }),
        };
        let text = error.to_string();
        assert!(text.contains("policy violation in rules.policy for issue kanbus-1"));
        assert!(text.contains("Rule: Scenario name"));
        assert!(text.contains("Failed: Then step"));
        assert!(text.contains("step failed"));
        assert!(text.contains("Explanation: why one"));
        assert!(text.contains("Explanation: why two"));
        assert!(text.contains("Guidance:"));
        assert!(text.contains("do this"));
    }
}
