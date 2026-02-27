//! Policy evaluation context.

use crate::models::{IssueData, ProjectConfiguration};

/// Type of operation triggering policy evaluation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyOperation {
    /// Issue is being created.
    Create,
    /// Issue is being updated.
    Update,
    /// Issue is being closed.
    Close,
    /// Issue is being deleted.
    Delete,
}

/// Status transition details.
#[derive(Debug, Clone)]
pub struct StatusTransition {
    /// Status before the transition.
    pub from: String,
    /// Status after the transition.
    pub to: String,
}

/// Context provided to policy evaluation steps.
///
/// Contains all information needed to evaluate policies against
/// a proposed issue state change.
#[derive(Debug, Clone)]
pub struct PolicyContext {
    /// Current issue state on disk.
    pub current_issue: Option<IssueData>,
    /// Proposed issue state after applying updates.
    pub proposed_issue: IssueData,
    /// Status transition details if status is changing.
    pub transition: Option<StatusTransition>,
    /// Type of operation triggering evaluation.
    pub operation: PolicyOperation,
    /// Project configuration.
    pub project_configuration: ProjectConfiguration,
    /// All issues in the project for aggregate checks.
    pub all_issues: Vec<IssueData>,
}

impl PolicyContext {
    /// Get the issue being evaluated (proposed state).
    pub fn issue(&self) -> &IssueData {
        &self.proposed_issue
    }

    /// Check if this is a status transition.
    pub fn is_transition(&self) -> bool {
        self.transition.is_some()
    }

    /// Check if transitioning to a specific status.
    pub fn is_transitioning_to(&self, status: &str) -> bool {
        self.transition
            .as_ref()
            .map(|t| t.to == status)
            .unwrap_or(false)
    }

    /// Check if transitioning from a specific status.
    pub fn is_transitioning_from(&self, status: &str) -> bool {
        self.transition
            .as_ref()
            .map(|t| t.from == status)
            .unwrap_or(false)
    }

    /// Get child issues of the proposed issue.
    pub fn child_issues(&self) -> Vec<&IssueData> {
        let parent_id = &self.proposed_issue.identifier;
        self.all_issues
            .iter()
            .filter(|issue| issue.parent.as_ref() == Some(parent_id))
            .collect()
    }

    /// Get parent issue of the proposed issue.
    pub fn parent_issue(&self) -> Option<&IssueData> {
        let parent_id = self.proposed_issue.parent.as_ref()?;
        self.all_issues
            .iter()
            .find(|issue| &issue.identifier == parent_id)
    }
}
