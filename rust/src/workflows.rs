//! Workflow validation and transition side effects.

use chrono::{DateTime, Utc};
use std::collections::BTreeMap;

use crate::error::KanbusError;
use crate::models::{IssueData, ProjectConfiguration};

/// Return the workflow definition for a specific issue type.
///
/// # Arguments
/// * `configuration` - Project configuration containing workflow definitions.
/// * `issue_type` - Issue type to lookup.
///
/// # Returns
/// Workflow definition for the issue type.
///
/// # Errors
/// Returns `KanbusError::Configuration` if the default workflow is missing.
pub fn get_workflow_for_issue_type<'a>(
    configuration: &'a ProjectConfiguration,
    issue_type: &str,
) -> Result<&'a BTreeMap<String, Vec<String>>, KanbusError> {
    if let Some(workflow) = configuration.workflows.get(issue_type) {
        return Ok(workflow);
    }
    configuration
        .workflows
        .get("default")
        .ok_or_else(|| KanbusError::Configuration("default workflow not defined".to_string()))
}

/// Validate that a status transition is permitted by the workflow.
///
/// Looks up the workflow for the given issue type in the project
/// configuration (falling back to the default workflow if no
/// type-specific workflow exists), then verifies that the new status
/// appears in the list of allowed transitions from the current status.
///
/// # Arguments
/// * `configuration` - Project configuration containing workflow definitions.
/// * `issue_type` - Issue type being transitioned.
/// * `current_status` - Issue's current status.
/// * `new_status` - Desired new status.
///
/// # Errors
/// Returns `KanbusError::InvalidTransition` if the transition is not permitted.
pub fn validate_status_transition(
    configuration: &ProjectConfiguration,
    issue_type: &str,
    current_status: &str,
    new_status: &str,
) -> Result<(), KanbusError> {
    let workflow = get_workflow_for_issue_type(configuration, issue_type)?;
    let allowed_transitions = workflow
        .get(current_status)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if !allowed_transitions
        .iter()
        .any(|status| status == new_status)
    {
        return Err(KanbusError::InvalidTransition(format!(
            "invalid transition from '{current_status}' to '{new_status}' for type '{issue_type}'"
        )));
    }
    Ok(())
}

/// Apply workflow side effects based on a status transition.
///
/// # Arguments
/// * `issue` - Issue being updated.
/// * `new_status` - New status being applied.
/// * `current_utc_time` - Current UTC timestamp.
///
/// # Returns
/// Updated issue data with side effects applied.
pub fn apply_transition_side_effects(
    issue: &IssueData,
    new_status: &str,
    current_utc_time: DateTime<Utc>,
) -> IssueData {
    let mut updated_issue = issue.clone();
    if new_status == "closed" {
        updated_issue.closed_at = Some(current_utc_time);
    } else if issue.status == "closed" && new_status != "closed" {
        updated_issue.closed_at = None;
    }
    updated_issue
}
