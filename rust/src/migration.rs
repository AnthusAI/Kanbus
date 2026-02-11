//! Beads to Taskulus migration helpers.

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::Path;

use chrono::{DateTime, Utc};
use serde::Deserialize;

use crate::config_loader::load_project_configuration;
use crate::error::TaskulusError;
use crate::file_io::{ensure_git_repository, initialize_project};
use crate::hierarchy::validate_parent_child_relationship;
use crate::issue_files::write_issue_to_file;
use crate::models::{DependencyLink, IssueComment, IssueData, ProjectConfiguration};
use crate::workflows::get_workflow_for_issue_type;

/// Result of a migration run.
#[derive(Debug, Clone)]
pub struct MigrationResult {
    pub issue_count: usize,
}

#[derive(Debug, Deserialize)]
struct BeadsDependency {
    depends_on_id: String,
    #[serde(rename = "type")]
    dependency_type: String,
}

#[derive(Debug, Deserialize)]
struct BeadsComment {
    author: String,
    text: String,
    created_at: String,
}

#[derive(Debug, Deserialize)]
struct BeadsIssue {
    id: String,
    title: String,
    description: Option<String>,
    status: String,
    priority: i32,
    issue_type: String,
    assignee: Option<String>,
    owner: Option<String>,
    created_at: String,
    created_by: Option<String>,
    updated_at: String,
    closed_at: Option<String>,
    close_reason: Option<String>,
    notes: Option<String>,
    acceptance_criteria: Option<String>,
    dependencies: Option<Vec<BeadsDependency>>,
    comments: Option<Vec<BeadsComment>>,
}

/// Migrate Beads issues.jsonl into a Taskulus project.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `TaskulusError` if migration fails.
pub fn migrate_from_beads(root: &Path) -> Result<MigrationResult, TaskulusError> {
    ensure_git_repository(root)?;

    let beads_dir = root.join(".beads");
    if !beads_dir.exists() {
        return Err(TaskulusError::IssueOperation(
            "no .beads directory".to_string(),
        ));
    }

    let issues_path = beads_dir.join("issues.jsonl");
    if !issues_path.exists() {
        return Err(TaskulusError::IssueOperation("no issues.jsonl".to_string()));
    }

    initialize_project(root, "project")?;
    let project_dir = root.join("project");
    let configuration = load_project_configuration(&project_dir.join("config.yaml"))?;

    let records = load_beads_records(&issues_path)?;
    let mut record_by_id = HashMap::new();
    for record in &records {
        record_by_id.insert(record.id.clone(), record);
    }

    for record in &records {
        let issue = convert_record(record, &record_by_id, &configuration)?;
        let issue_path = project_dir
            .join("issues")
            .join(format!("{}.json", issue.identifier));
        write_issue_to_file(&issue, &issue_path)?;
    }

    Ok(MigrationResult {
        issue_count: records.len(),
    })
}

fn load_beads_records(path: &Path) -> Result<Vec<BeadsIssue>, TaskulusError> {
    let contents =
        fs::read_to_string(path).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let mut records = Vec::new();
    for line in contents.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let record: BeadsIssue =
            serde_json::from_str(line).map_err(|error| TaskulusError::Io(error.to_string()))?;
        records.push(record);
    }
    Ok(records)
}

fn convert_record(
    record: &BeadsIssue,
    record_by_id: &HashMap<String, &BeadsIssue>,
    configuration: &ProjectConfiguration,
) -> Result<IssueData, TaskulusError> {
    if record.title.trim().is_empty() {
        return Err(TaskulusError::IssueOperation(
            "title is required".to_string(),
        ));
    }
    if record.issue_type.trim().is_empty() {
        return Err(TaskulusError::IssueOperation(
            "issue_type is required".to_string(),
        ));
    }
    validate_issue_type(configuration, &record.issue_type)?;

    if record.status.trim().is_empty() {
        return Err(TaskulusError::IssueOperation(
            "status is required".to_string(),
        ));
    }
    validate_status(configuration, &record.issue_type, &record.status)?;

    if !configuration
        .priorities
        .contains_key(&(record.priority as u8))
    {
        return Err(TaskulusError::IssueOperation(
            "invalid priority".to_string(),
        ));
    }

    let created_at = parse_timestamp(&record.created_at, "created_at")?;
    let updated_at = parse_timestamp(&record.updated_at, "updated_at")?;
    let closed_at = match &record.closed_at {
        Some(value) => Some(parse_timestamp(value, "closed_at")?),
        None => None,
    };

    let (parent, dependencies) = convert_dependencies(
        record.dependencies.as_ref(),
        record_by_id,
        configuration,
        &record.issue_type,
    )?;

    let comments = convert_comments(record.comments.as_ref())?;

    let mut custom = BTreeMap::new();
    if let Some(owner) = &record.owner {
        custom.insert(
            "beads_owner".to_string(),
            serde_json::Value::String(owner.clone()),
        );
    }
    if let Some(notes) = &record.notes {
        custom.insert(
            "beads_notes".to_string(),
            serde_json::Value::String(notes.clone()),
        );
    }
    if let Some(criteria) = &record.acceptance_criteria {
        custom.insert(
            "beads_acceptance_criteria".to_string(),
            serde_json::Value::String(criteria.clone()),
        );
    }
    if let Some(reason) = &record.close_reason {
        custom.insert(
            "beads_close_reason".to_string(),
            serde_json::Value::String(reason.clone()),
        );
    }

    Ok(IssueData {
        identifier: record.id.clone(),
        title: record.title.clone(),
        description: record.description.clone().unwrap_or_default(),
        issue_type: record.issue_type.clone(),
        status: record.status.clone(),
        priority: record.priority,
        assignee: record.assignee.clone(),
        creator: record.created_by.clone(),
        parent,
        labels: Vec::new(),
        dependencies,
        comments,
        created_at,
        updated_at,
        closed_at,
        custom,
    })
}

fn convert_dependencies(
    dependencies: Option<&Vec<BeadsDependency>>,
    record_by_id: &HashMap<String, &BeadsIssue>,
    configuration: &ProjectConfiguration,
    issue_type: &str,
) -> Result<(Option<String>, Vec<DependencyLink>), TaskulusError> {
    let mut parent: Option<String> = None;
    let mut links: Vec<DependencyLink> = Vec::new();

    if let Some(dependencies) = dependencies {
        for dependency in dependencies {
            if dependency.depends_on_id.is_empty() || dependency.dependency_type.is_empty() {
                return Err(TaskulusError::IssueOperation(
                    "invalid dependency".to_string(),
                ));
            }
            if !record_by_id.contains_key(&dependency.depends_on_id) {
                return Err(TaskulusError::IssueOperation(
                    "missing dependency".to_string(),
                ));
            }
            if dependency.dependency_type == "parent-child" {
                if parent.is_some() {
                    return Err(TaskulusError::IssueOperation(
                        "multiple parents".to_string(),
                    ));
                }
                parent = Some(dependency.depends_on_id.clone());
            } else {
                links.push(DependencyLink {
                    target: dependency.depends_on_id.clone(),
                    dependency_type: dependency.dependency_type.clone(),
                });
            }
        }
    }

    if let Some(parent_id) = parent.as_ref() {
        let parent_record = record_by_id
            .get(parent_id)
            .ok_or_else(|| TaskulusError::IssueOperation("missing parent".to_string()))?;
        if parent_record.issue_type.trim().is_empty() {
            return Err(TaskulusError::IssueOperation(
                "parent issue_type is required".to_string(),
            ));
        }
        validate_parent_child_relationship(configuration, &parent_record.issue_type, issue_type)?;
    }

    Ok((parent, links))
}

fn convert_comments(
    comments: Option<&Vec<BeadsComment>>,
) -> Result<Vec<IssueComment>, TaskulusError> {
    let mut results = Vec::new();
    if let Some(comments) = comments {
        for comment in comments {
            if comment.author.trim().is_empty() || comment.text.trim().is_empty() {
                return Err(TaskulusError::IssueOperation("invalid comment".to_string()));
            }
            let created_at = parse_timestamp(&comment.created_at, "comment.created_at")?;
            results.push(IssueComment {
                author: comment.author.clone(),
                text: comment.text.clone(),
                created_at,
            });
        }
    }
    Ok(results)
}

fn parse_timestamp(value: &str, field_name: &str) -> Result<DateTime<Utc>, TaskulusError> {
    let normalized = value.replace('Z', "+00:00");
    let parsed = DateTime::parse_from_rfc3339(&normalized)
        .map_err(|_| TaskulusError::IssueOperation(format!("invalid {field_name}")))?;
    Ok(parsed.with_timezone(&Utc))
}

fn validate_issue_type(
    configuration: &ProjectConfiguration,
    issue_type: &str,
) -> Result<(), TaskulusError> {
    let known = configuration
        .hierarchy
        .iter()
        .chain(configuration.types.iter())
        .any(|value| value == issue_type);
    if !known {
        return Err(TaskulusError::IssueOperation(
            "unknown issue type".to_string(),
        ));
    }
    Ok(())
}

fn validate_status(
    configuration: &ProjectConfiguration,
    issue_type: &str,
    status: &str,
) -> Result<(), TaskulusError> {
    let workflow = get_workflow_for_issue_type(configuration, issue_type)?;
    let mut statuses = std::collections::HashSet::new();
    for (key, values) in workflow.iter() {
        statuses.insert(key.as_str());
        for value in values {
            statuses.insert(value.as_str());
        }
    }
    if !statuses.contains(status) {
        return Err(TaskulusError::IssueOperation("invalid status".to_string()));
    }
    Ok(())
}
