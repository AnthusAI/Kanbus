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
    if request.validate {
        validate_issue_type(&configuration, resolved_type)?;
        if !configuration.priorities.contains_key(&resolved_priority) {
            return Err(KanbusError::IssueOperation("invalid priority".to_string()));
        }

        if let Some(parent_identifier) = request.parent.as_deref() {
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
        parent: request.parent.clone(),
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
