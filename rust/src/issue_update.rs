//! Issue update workflow.

use chrono::Utc;
use std::fs;
use std::path::Path;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_files::{read_issue_from_file, write_issue_to_file};
use crate::issue_lookup::load_issue_from_project;
use crate::models::IssueData;
use crate::workflows::{
    apply_transition_side_effects, validate_status_transition, validate_status_value,
};

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
/// Returns `KanbusError` if the update fails.
#[allow(clippy::too_many_arguments)]
pub fn update_issue(
    root: &Path,
    identifier: &str,
    title: Option<&str>,
    description: Option<&str>,
    status: Option<&str>,
    assignee: Option<&str>,
    claim: bool,
    validate: bool,
) -> Result<IssueData, KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let config_path = get_configuration_path(lookup.project_dir.as_path())?;
    let configuration = load_project_configuration(&config_path)?;

    let mut updated_issue = lookup.issue.clone();
    let current_time = Utc::now();

    let mut resolved_status = if claim { Some("in_progress") } else { status };

    let mut updated_title: Option<String> = None;
    if let Some(new_title) = title {
        let normalized_title = new_title.trim();
        if normalized_title.to_lowercase() != updated_issue.title.trim().to_lowercase() {
            if let Some(duplicate_identifier) = find_duplicate_title(
                &lookup.project_dir.join("issues"),
                normalized_title,
                &updated_issue.identifier,
            )? {
                return Err(KanbusError::IssueOperation(format!(
                    "duplicate title: \"{}\" already exists as {}",
                    normalized_title, duplicate_identifier
                )));
            }
            updated_title = Some(normalized_title.to_string());
        }
    }

    let mut updated_description: Option<String> = None;
    if let Some(new_description) = description {
        let normalized_description = new_description.trim();
        if normalized_description != updated_issue.description {
            updated_description = Some(normalized_description.to_string());
        }
    }

    let mut updated_assignee: Option<String> = None;
    if let Some(new_assignee) = assignee {
        if updated_issue.assignee.as_deref() != Some(new_assignee) {
            updated_assignee = Some(new_assignee.to_string());
        }
    }

    if resolved_status.is_some() && resolved_status == Some(updated_issue.status.as_str()) {
        resolved_status = None;
    }

    if resolved_status.is_none()
        && updated_title.is_none()
        && updated_description.is_none()
        && updated_assignee.is_none()
    {
        return Err(KanbusError::IssueOperation(
            "no updates requested".to_string(),
        ));
    }

    if let Some(new_status) = resolved_status {
        if validate {
            validate_status_value(&configuration, &updated_issue.issue_type, new_status)?;
            validate_status_transition(
                &configuration,
                &updated_issue.issue_type,
                &updated_issue.status,
                new_status,
            )?;
        }
        updated_issue = apply_transition_side_effects(&updated_issue, new_status, current_time);
        updated_issue.status = new_status.to_string();
    }

    if let Some(new_title) = updated_title {
        updated_issue.title = new_title;
    }
    if let Some(new_description) = updated_description {
        updated_issue.description = new_description;
    }
    if let Some(new_assignee) = updated_assignee {
        updated_issue.assignee = Some(new_assignee);
    }
    updated_issue.updated_at = current_time;

    write_issue_to_file(&updated_issue, &lookup.issue_path)?;

    // Publish real-time notification
    use crate::notification_events::NotificationEvent;
    use crate::notification_publisher::publish_notification;
    let mut fields_changed = Vec::new();
    if status.is_some() {
        fields_changed.push("status".to_string());
    }
    if title.is_some() {
        fields_changed.push("title".to_string());
    }
    if description.is_some() {
        fields_changed.push("description".to_string());
    }
    if assignee.is_some() || claim {
        fields_changed.push("assignee".to_string());
    }
    let _ = publish_notification(root, NotificationEvent::IssueUpdated {
        issue_id: updated_issue.identifier.clone(),
        fields_changed,
        issue_data: updated_issue.clone(),
    });

    Ok(updated_issue)
}

fn find_duplicate_title(
    issues_dir: &Path,
    title: &str,
    current_identifier: &str,
) -> Result<Option<String>, KanbusError> {
    let normalized_title = title.trim().to_lowercase();
    for entry in fs::read_dir(issues_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        if path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .map(|stem| stem == current_identifier)
            .unwrap_or(false)
        {
            continue;
        }
        let issue = match read_issue_from_file(&path) {
            Ok(issue) => issue,
            Err(_) => continue,
        };
        if issue.title.trim().to_lowercase() == normalized_title {
            return Ok(Some(issue.identifier));
        }
    }
    Ok(None)
}
