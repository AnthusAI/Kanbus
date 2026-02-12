//! Issue update workflow.

use chrono::Utc;
use std::path::Path;

use crate::config_loader::load_project_configuration;
use crate::error::TaskulusError;
use crate::issue_files::write_issue_to_file;
use crate::issue_lookup::load_issue_from_project;
use crate::models::IssueData;
use crate::workflows::{apply_transition_side_effects, validate_status_transition};

/// Update an issue and persist it to disk.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
/// * `title` - Updated title if provided.
/// * `description` - Updated description if provided.
/// * `status` - Updated status if provided.
/// * `assignee` - Updated assignee if provided.
/// * `claim` - Whether to claim the issue.
///
/// # Errors
/// Returns `TaskulusError` if the update fails.
pub fn update_issue(
    root: &Path,
    identifier: &str,
    title: Option<&str>,
    description: Option<&str>,
    status: Option<&str>,
    assignee: Option<&str>,
    claim: bool,
) -> Result<IssueData, TaskulusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let configuration = load_project_configuration(&lookup.project_dir.join("config.yaml"))?;

    let mut updated_issue = lookup.issue.clone();
    let current_time = Utc::now();

    let resolved_status = if claim { Some("in_progress") } else { status };

    if let Some(new_status) = resolved_status {
        validate_status_transition(
            &configuration,
            &updated_issue.issue_type,
            &updated_issue.status,
            new_status,
        )?;
        updated_issue = apply_transition_side_effects(&updated_issue, new_status, current_time);
        updated_issue.status = new_status.to_string();
    }

    if let Some(new_title) = title {
        updated_issue.title = new_title.to_string();
    }
    if let Some(new_description) = description {
        updated_issue.description = new_description.to_string();
    }
    if let Some(new_assignee) = assignee {
        updated_issue.assignee = Some(new_assignee.to_string());
    }
    updated_issue.updated_at = current_time;

    write_issue_to_file(&updated_issue, &lookup.issue_path)?;
    Ok(updated_issue)
}
