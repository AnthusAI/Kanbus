//! Workflow validation and transition side effects.

use chrono::{DateTime, Utc};
use std::collections::{BTreeMap, BTreeSet};

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

/// Return every status key reachable in a workflow definition.
pub fn collect_workflow_statuses(workflow: &BTreeMap<String, Vec<String>>) -> BTreeSet<String> {
    let mut statuses: BTreeSet<String> = workflow.keys().cloned().collect();
    for transitions in workflow.values() {
        statuses.extend(transitions.iter().cloned());
    }
    statuses
}

fn preferred_alternative_issue_type(
    configuration: &ProjectConfiguration,
    status: &str,
    current_type: &str,
) -> Option<String> {
    let alternative_types = find_issue_types_allowing_status(configuration, status)
        .into_iter()
        .filter(|candidate_type| candidate_type != current_type)
        .collect::<Vec<_>>();
    if alternative_types
        .iter()
        .any(|candidate| candidate == "task")
    {
        return Some("task".to_string());
    }
    alternative_types.first().cloned()
}

/// Return issue types whose workflow includes the given status.
pub fn find_issue_types_allowing_status(
    configuration: &ProjectConfiguration,
    status: &str,
) -> Vec<String> {
    let mut matching_types = Vec::new();
    for candidate_type in configuration
        .hierarchy
        .iter()
        .chain(configuration.types.iter())
    {
        if let Ok(workflow) = get_workflow_for_issue_type(configuration, candidate_type) {
            if collect_workflow_statuses(workflow).contains(status) {
                matching_types.push(candidate_type.clone());
            }
        }
    }
    matching_types
}

/// Build an actionable error for a type and status workflow mismatch.
pub fn format_status_not_allowed_for_type_error(
    configuration: &ProjectConfiguration,
    issue_type: &str,
    status: &str,
    issue_identifier: Option<&str>,
) -> Result<String, KanbusError> {
    let workflow = get_workflow_for_issue_type(configuration, issue_type)?;
    let allowed_statuses: Vec<String> = collect_workflow_statuses(workflow).into_iter().collect();
    let allowed_text = allowed_statuses.join(", ");
    let prefix = issue_identifier
        .map(|identifier| format!("{identifier}: "))
        .unwrap_or_default();
    let message = format!(
        "{prefix}status '{status}' is not allowed for type '{issue_type}' (allowed: {allowed_text})"
    );

    let mut remediation_parts = Vec::new();
    if issue_identifier.is_some() {
        if let Some(first_allowed_status) = allowed_statuses.first() {
            remediation_parts.push(format!(
                "kbs update {} --status {}",
                issue_identifier.expect("checked above"),
                first_allowed_status
            ));
        }
    }

    let alternative_type = preferred_alternative_issue_type(configuration, status, issue_type);

    if let Some(identifier) = issue_identifier {
        if let Some(alternative_type) = alternative_type {
            remediation_parts.push(format!("kbs move {identifier} {alternative_type}"));
        }
    } else if let Some(alternative_type) = alternative_type {
        remediation_parts.push(format!("use --type {alternative_type}"));
    }

    if remediation_parts.is_empty() {
        Ok(message)
    } else {
        Ok(format!(
            "{}. Remediation: {}",
            message,
            remediation_parts.join(" OR ")
        ))
    }
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

/// Validate that a status value exists and is allowed for the issue type workflow.
///
/// # Errors
/// Returns `KanbusError::InvalidTransition` if the status is unknown or not allowed.
pub fn validate_status_value(
    configuration: &ProjectConfiguration,
    issue_type: &str,
    status: &str,
    issue_identifier: Option<&str>,
) -> Result<(), KanbusError> {
    if std::env::var("KANBUS_TEST_INVALID_STATUS").is_ok() {
        return Err(KanbusError::InvalidTransition("unknown status".to_string()));
    }
    let valid_statuses: BTreeSet<&str> = configuration
        .statuses
        .iter()
        .map(|entry| entry.key.as_str())
        .collect();
    if !valid_statuses.contains(status) {
        return Err(KanbusError::InvalidTransition("unknown status".to_string()));
    }

    let workflow = get_workflow_for_issue_type(configuration, issue_type)?;
    if !collect_workflow_statuses(workflow).contains(status) {
        return Err(KanbusError::InvalidTransition(
            format_status_not_allowed_for_type_error(
                configuration,
                issue_type,
                status,
                issue_identifier,
            )?,
        ));
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
