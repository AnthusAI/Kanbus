//! Issue creation workflow.

use chrono::Utc;
use std::path::PathBuf;

use crate::config_loader::load_project_configuration;
use crate::error::TaskulusError;
use crate::hierarchy::validate_parent_child_relationship;
use crate::ids::{generate_issue_identifier, IssueIdentifierRequest};
use crate::issue_files::{
    issue_path_for_identifier, list_issue_identifiers, read_issue_from_file, write_issue_to_file,
};
use crate::models::{IssueData, ProjectConfiguration};
use crate::{
    file_io::{
        ensure_project_local_directory, find_project_local_directory, load_project_directory,
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
}

/// Create a new issue and write it to disk.
///
/// # Arguments
/// * `request` - Issue creation request payload.
///
/// # Errors
/// Returns `TaskulusError` if validation or file operations fail.
pub fn create_issue(request: &IssueCreationRequest) -> Result<IssueData, TaskulusError> {
    let project_dir = load_project_directory(request.root.as_path())?;
    let mut issues_dir = project_dir.join("issues");
    let mut local_dir = find_project_local_directory(&project_dir);
    if request.local {
        local_dir = Some(ensure_project_local_directory(&project_dir)?);
        issues_dir = local_dir.as_ref().expect("local dir").join("issues");
    }
    let configuration = load_project_configuration(&project_dir.join("config.yaml"))?;

    let resolved_type = request.issue_type.as_deref().unwrap_or("task");
    validate_issue_type(&configuration, resolved_type)?;

    let resolved_priority = request.priority.unwrap_or(configuration.default_priority);
    if !configuration.priorities.contains_key(&resolved_priority) {
        return Err(TaskulusError::IssueOperation(
            "invalid priority".to_string(),
        ));
    }

    if let Some(parent_identifier) = request.parent.as_deref() {
        let parent_path = issue_path_for_identifier(&issues_dir, parent_identifier);
        if !parent_path.exists() {
            return Err(TaskulusError::IssueOperation("not found".to_string()));
        }
        let parent_issue = read_issue_from_file(&parent_path)?;
        validate_parent_child_relationship(
            &configuration,
            &parent_issue.issue_type,
            resolved_type,
        )?;
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
        prefix: configuration.prefix.clone(),
        created_at,
    };
    let identifier = generate_issue_identifier(&identifier_request)?.identifier;
    let updated_at = created_at;

    let issue = IssueData {
        identifier,
        title: request.title.clone(),
        description: request.description.clone().unwrap_or_default(),
        issue_type: resolved_type.to_string(),
        status: configuration.initial_status.clone(),
        priority: resolved_priority as i32,
        assignee: request.assignee.clone(),
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
    Ok(issue)
}

fn validate_issue_type(
    configuration: &ProjectConfiguration,
    issue_type: &str,
) -> Result<(), TaskulusError> {
    let is_known = configuration
        .hierarchy
        .iter()
        .chain(configuration.types.iter())
        .any(|entry| entry == issue_type);
    if !is_known {
        return Err(TaskulusError::IssueOperation(
            "unknown issue type".to_string(),
        ));
    }
    Ok(())
}
