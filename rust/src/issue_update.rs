//! Issue update workflow.

use chrono::Utc;
use std::fs;
use std::path::Path;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;
use crate::issue_creation::resolve_issue_identifier;
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
    priority: Option<u8>,
    claim: bool,
    validate: bool,
    add_labels: &[String],
    remove_labels: &[String],
    set_labels: Option<&str>,
    parent: Option<&str>,
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

    let mut updated_priority: Option<i32> = None;
    if let Some(new_priority) = priority {
        if validate && !configuration.priorities.contains_key(&new_priority) {
            return Err(KanbusError::IssueOperation("invalid priority".to_string()));
        }
        if updated_issue.priority != new_priority as i32 {
            updated_priority = Some(new_priority as i32);
        }
    }

    if resolved_status.is_some() && resolved_status == Some(updated_issue.status.as_str()) {
        resolved_status = None;
    }

    let mut updated_labels: Option<Vec<String>> = None;
    if set_labels.is_some() || !add_labels.is_empty() || !remove_labels.is_empty() {
        let mut labels = if let Some(value) = set_labels {
            value
                .split(',')
                .map(|label| label.trim().to_string())
                .filter(|l| !l.is_empty())
                .collect::<Vec<_>>()
        } else {
            updated_issue.labels.clone()
        };
        for label in add_labels {
            let trimmed = label.trim();
            if !trimmed.is_empty() && !labels.iter().any(|l| l.eq_ignore_ascii_case(trimmed)) {
                labels.push(trimmed.to_string());
            }
        }
        if !remove_labels.is_empty() {
            labels.retain(|label| {
                !remove_labels
                    .iter()
                    .any(|r| label.eq_ignore_ascii_case(r.trim()))
            })
        }
        if labels != updated_issue.labels {
            updated_labels = Some(labels);
        }
    }

    let mut updated_parent: Option<String> = None;
    if let Some(parent_candidate) = parent {
        let issues_dir = lookup.project_dir.join("issues");
        let resolved_parent =
            resolve_issue_identifier(&issues_dir, &configuration.project_key, parent_candidate)?;
        if updated_issue.parent.as_deref() != Some(resolved_parent.as_str()) {
            if validate {
                let parent_path = issues_dir.join(format!("{resolved_parent}.json"));
                if !parent_path.exists() {
                    return Err(KanbusError::IssueOperation("not found".to_string()));
                }
                let parent_issue = read_issue_from_file(&parent_path)?;
                crate::hierarchy::validate_parent_child_relationship(
                    &configuration,
                    &parent_issue.issue_type,
                    &updated_issue.issue_type,
                )?;
            }
            updated_parent = Some(resolved_parent);
        }
    }

    if resolved_status.is_none()
        && updated_title.is_none()
        && updated_description.is_none()
        && updated_assignee.is_none()
        && updated_priority.is_none()
        && updated_labels.is_none()
        && updated_parent.is_none()
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
    if let Some(new_priority) = updated_priority {
        updated_issue.priority = new_priority;
    }
    if let Some(new_labels) = updated_labels {
        updated_issue.labels = new_labels;
    }
    if let Some(new_parent) = updated_parent {
        updated_issue.parent = Some(new_parent);
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
    if priority.is_some() {
        fields_changed.push("priority".to_string());
    }
    if parent.is_some() {
        fields_changed.push("parent".to_string());
    }
    let _ = publish_notification(
        root,
        NotificationEvent::IssueUpdated {
            issue_id: updated_issue.identifier.clone(),
            fields_changed,
            issue_data: updated_issue.clone(),
        },
    );

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

#[cfg(test)]
mod tests {
    use super::find_duplicate_title;
    use crate::issue_files::{issue_path_for_identifier, write_issue_to_file};
    use crate::models::IssueData;
    use chrono::{TimeZone, Utc};
    use std::collections::BTreeMap;
    use tempfile::tempdir;

    fn sample_issue(identifier: &str, title: &str) -> IssueData {
        let now = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
        IssueData {
            identifier: identifier.to_string(),
            title: title.to_string(),
            description: String::new(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: now,
            updated_at: now,
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    #[test]
    fn finds_duplicate_title_excluding_current() {
        let temp = tempdir().unwrap();
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).unwrap();

        let first = sample_issue("kanbus-abc", "Same");
        let second = sample_issue("kanbus-def", "Same");
        write_issue_to_file(
            &first,
            &issue_path_for_identifier(&issues_dir, &first.identifier),
        )
        .unwrap();
        write_issue_to_file(
            &second,
            &issue_path_for_identifier(&issues_dir, &second.identifier),
        )
        .unwrap();

        let duplicate = find_duplicate_title(&issues_dir, "Same", &first.identifier).unwrap();
        assert_eq!(duplicate, Some(second.identifier));
    }

    #[test]
    fn ignores_missing_duplicates() {
        let temp = tempdir().unwrap();
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).unwrap();
        let issue = sample_issue("kanbus-abc", "Title");
        write_issue_to_file(
            &issue,
            &issue_path_for_identifier(&issues_dir, &issue.identifier),
        )
        .unwrap();

        let duplicate = find_duplicate_title(&issues_dir, "Other", &issue.identifier).unwrap();
        assert_eq!(duplicate, None);
    }
}
