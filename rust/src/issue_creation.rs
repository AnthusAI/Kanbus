//! Issue creation workflow.

use chrono::Utc;
use std::path::{Path, PathBuf};

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::hierarchy::validate_parent_child_relationship;
use crate::ids::{generate_issue_identifier, IssueIdentifierRequest};
use crate::issue_files::{
    issue_path_for_identifier, list_issue_identifiers, read_issue_from_file, write_issue_to_file,
};
use crate::models::{IssueData, ProjectConfiguration};
use crate::users::get_current_user;
use crate::event_history::{
    events_dir_for_local, events_dir_for_project, issue_created_payload, now_timestamp,
    write_events_batch, EventRecord, EventType,
};
use crate::workflows::validate_status_value;
use crate::{
    file_io::{
        ensure_project_local_directory, find_project_local_directory, get_configuration_path,
        load_project_directory,
    },
    models::DependencyLink,
};

/// Request payload for issue creation.
#[derive(Debug, Clone)]
pub struct IssueCreationRequest {
    pub root: PathBuf,
    pub title: String,
    pub issue_type: Option<String>,
    pub priority: Option<u8>,
    pub assignee: Option<String>,
    pub parent: Option<String>,
    pub labels: Vec<String>,
    pub description: Option<String>,
    pub local: bool,
    pub validate: bool,
}

/// Result payload for issue creation.
#[derive(Debug, Clone)]
pub struct IssueCreationResult {
    pub issue: IssueData,
    pub configuration: ProjectConfiguration,
}

/// Create a new issue and write it to disk.
///
/// # Arguments
/// * `request` - Issue creation request payload.
///
/// # Errors
/// Returns `KanbusError` if validation or file operations fail.
pub fn create_issue(request: &IssueCreationRequest) -> Result<IssueCreationResult, KanbusError> {
    let project_dir = load_project_directory(request.root.as_path())?;
    let mut issues_dir = project_dir.join("issues");
    let mut local_dir = find_project_local_directory(&project_dir);
    if request.local {
        local_dir = Some(ensure_project_local_directory(&project_dir)?);
        issues_dir = local_dir.as_ref().expect("local dir").join("issues");
    }
    let config_path = get_configuration_path(request.root.as_path())?;
    let configuration = load_project_configuration(&config_path)?;

    let resolved_type = request.issue_type.as_deref().unwrap_or("task");
    let resolved_priority = request.priority.unwrap_or(configuration.default_priority);
    // Resolve parent: accept full id or unique short id (projectkey-<prefix>).
    let mut resolved_parent = request.parent.clone();
    if let Some(parent_identifier) = resolved_parent.clone() {
        let full_id =
            resolve_issue_identifier(&issues_dir, &configuration.project_key, &parent_identifier)?;
        resolved_parent = Some(full_id);
    }
    if request.validate {
        validate_issue_type(&configuration, resolved_type)?;
        if !configuration.priorities.contains_key(&resolved_priority) {
            return Err(KanbusError::IssueOperation("invalid priority".to_string()));
        }

        if let Some(parent_identifier) = resolved_parent.as_deref() {
            let parent_path = issue_path_for_identifier(&issues_dir, parent_identifier);
            if !parent_path.exists() {
                return Err(KanbusError::IssueOperation("not found".to_string()));
            }
            let parent_issue = read_issue_from_file(&parent_path)?;
            validate_parent_child_relationship(
                &configuration,
                &parent_issue.issue_type,
                resolved_type,
            )?;
        }

        if let Some(duplicate_identifier) = find_duplicate_title(&issues_dir, &request.title)? {
            return Err(KanbusError::IssueOperation(format!(
                "duplicate title: \"{}\" already exists as {}",
                request.title, duplicate_identifier
            )));
        }

        validate_status_value(&configuration, resolved_type, &configuration.initial_status)?;
    }

    let mut existing_ids = list_issue_identifiers(&project_dir.join("issues"))?;
    if let Some(local_dir) = local_dir {
        let local_issues = local_dir.join("issues");
        if local_issues.exists() {
            existing_ids.extend(list_issue_identifiers(&local_issues)?);
        }
    }
    let created_at = Utc::now();
    let identifier_request = IssueIdentifierRequest {
        title: request.title.clone(),
        existing_ids,
        prefix: configuration.project_key.clone(),
    };
    let identifier = generate_issue_identifier(&identifier_request)?.identifier;
    let updated_at = created_at;

    let resolved_assignee = request
        .assignee
        .clone()
        .or_else(|| configuration.assignee.clone());

    let issue = IssueData {
        identifier,
        title: request.title.clone(),
        description: request.description.clone().unwrap_or_default(),
        issue_type: resolved_type.to_string(),
        status: configuration.initial_status.clone(),
        priority: resolved_priority as i32,
        assignee: resolved_assignee,
        creator: None,
        parent: resolved_parent.clone(),
        labels: request.labels.clone(),
        dependencies: Vec::<DependencyLink>::new(),
        comments: Vec::new(),
        created_at,
        updated_at,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    };

    let issue_path = issue_path_for_identifier(&issues_dir, &issue.identifier);
    write_issue_to_file(&issue, &issue_path)?;

    let occurred_at = now_timestamp();
    let actor_id = get_current_user();
    let event = EventRecord::new(
        issue.identifier.clone(),
        EventType::IssueCreated,
        actor_id,
        issue_created_payload(&issue),
        occurred_at,
    );
    let events_dir = if request.local {
        match events_dir_for_local(&project_dir) {
            Ok(path) => path,
            Err(error) => {
                std::fs::remove_file(&issue_path)
                    .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
                return Err(error);
            }
        }
    } else {
        events_dir_for_project(&project_dir)
    };
    match write_events_batch(&events_dir, &[event]) {
        Ok(_paths) => {}
        Err(error) => {
            std::fs::remove_file(&issue_path)
                .map_err(|io_error| KanbusError::Io(io_error.to_string()))?;
            return Err(error);
        }
    }

    // Publish real-time notification
    use crate::notification_events::NotificationEvent;
    use crate::notification_publisher::publish_notification;
    let _ = publish_notification(
        request.root.as_path(),
        NotificationEvent::IssueCreated {
            issue_id: issue.identifier.clone(),
            issue_data: issue.clone(),
        },
    );

    Ok(IssueCreationResult {
        issue,
        configuration,
    })
}

fn validate_issue_type(
    configuration: &ProjectConfiguration,
    issue_type: &str,
) -> Result<(), KanbusError> {
    let is_known = configuration
        .hierarchy
        .iter()
        .chain(configuration.types.iter())
        .any(|entry| entry == issue_type);
    if !is_known {
        return Err(KanbusError::IssueOperation(
            "unknown issue type".to_string(),
        ));
    }
    Ok(())
}

fn find_duplicate_title(issues_dir: &Path, title: &str) -> Result<Option<String>, KanbusError> {
    let normalized_title = title.trim().to_lowercase();
    for entry in
        std::fs::read_dir(issues_dir).map_err(|error| KanbusError::Io(error.to_string()))?
    {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let issue = read_issue_from_file(&path)?;
        if issue.title.trim().to_lowercase() == normalized_title {
            return Ok(Some(issue.identifier));
        }
    }
    Ok(None)
}

/// Resolve an issue identifier from a user-provided value.
///
/// Accepts a full id or a unique short id (`{project_key}-{prefix}` up to 6 chars).
pub fn resolve_issue_identifier(
    issues_dir: &Path,
    project_key: &str,
    candidate: &str,
) -> Result<String, KanbusError> {
    // First, try exact match on filename.
    let exact_path = issue_path_for_identifier(issues_dir, candidate);
    if exact_path.exists() {
        return Ok(candidate.to_string());
    }

    // Otherwise, attempt a unique short-id match.
    let identifiers = list_issue_identifiers(issues_dir)?;
    let mut matches: Vec<String> = identifiers
        .into_iter()
        .filter(|full_id| short_id_matches(candidate, project_key, full_id))
        .collect();

    match matches.len() {
        1 => Ok(matches.pop().expect("single match")),
        0 => Err(KanbusError::IssueOperation("not found".to_string())),
        _ => Err(KanbusError::IssueOperation(
            "ambiguous short id".to_string(),
        )),
    }
}

/// Determine whether a short identifier matches a full identifier.
pub fn short_id_matches(candidate: &str, project_key: &str, full_id: &str) -> bool {
    if !candidate.starts_with(project_key) {
        return false;
    }
    let mut parts = candidate.splitn(2, '-');
    let prefix_key = parts.next().unwrap_or("");
    let prefix = parts.next().unwrap_or("");
    if prefix_key != project_key {
        return false;
    }
    if prefix.is_empty() || prefix.len() > 6 {
        return false;
    }
    let mut full_parts = full_id.splitn(2, '-');
    let full_key = full_parts.next().unwrap_or("");
    let full_suffix = full_parts.next().unwrap_or("");
    if full_key != project_key {
        return false;
    }
    full_suffix.starts_with(prefix)
}
