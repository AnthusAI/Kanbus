//! Beads to Taskulus migration helpers.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs;
use std::path::Path;

use chrono::{DateTime, Utc};
use serde_json::Value;

use crate::config_loader::load_project_configuration;
use crate::error::TaskulusError;
use crate::file_io::{
    discover_project_directories, discover_taskulus_projects, ensure_git_repository,
    initialize_project,
};
use crate::hierarchy::validate_parent_child_relationship;
use crate::issue_files::write_issue_to_file;
use crate::models::{DependencyLink, IssueComment, IssueData, ProjectConfiguration};
use crate::workflows::get_workflow_for_issue_type;

/// Result of a migration run.
#[derive(Debug, Clone)]
pub struct MigrationResult {
    pub issue_count: usize,
}

/// Load Beads issues.jsonl without migrating to project files.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `TaskulusError` if Beads data is missing or invalid.
pub fn load_beads_issues(root: &Path) -> Result<Vec<IssueData>, TaskulusError> {
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

    let configuration = load_project_configuration(&root.join("config.yaml"))?;
    let records = load_beads_records(&issues_path)?;
    let mut record_by_id: HashMap<String, Value> = HashMap::new();
    for record in &records {
        let identifier = record
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| TaskulusError::IssueOperation("missing id".to_string()))?;
        record_by_id.insert(identifier.to_string(), record.clone());
    }

    let mut issues = Vec::with_capacity(records.len());
    for record in &records {
        issues.push(convert_record(record, &record_by_id, &configuration)?);
    }
    Ok(issues)
}

/// Load a single Beads issue by identifier.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier to locate.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if the issue is missing.
pub fn load_beads_issue_by_id(root: &Path, identifier: &str) -> Result<IssueData, TaskulusError> {
    let issues = load_beads_issues(root)?;
    for issue in issues {
        if issue.identifier == identifier {
            return Ok(issue);
        }
    }
    Err(TaskulusError::IssueOperation("not found".to_string()))
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

    let mut projects = Vec::new();
    discover_project_directories(root, &mut projects)?;
    let mut dotfile_projects = discover_taskulus_projects(root)?;
    projects.append(&mut dotfile_projects);
    if !projects.is_empty() {
        return Err(TaskulusError::IssueOperation(
            "already initialized".to_string(),
        ));
    }

    initialize_project(root, false)?;
    let project_dir = root.join("project");
    let configuration = load_project_configuration(&project_dir.join("config.yaml"))?;

    let records = load_beads_records(&issues_path)?;
    let mut record_by_id: HashMap<String, Value> = HashMap::new();
    for record in &records {
        let identifier = record
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| TaskulusError::IssueOperation("missing id".to_string()))?;
        record_by_id.insert(identifier.to_string(), record.clone());
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

fn load_beads_records(path: &Path) -> Result<Vec<Value>, TaskulusError> {
    let contents =
        fs::read_to_string(path).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let mut records = Vec::new();
    for line in contents.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let record: Value =
            serde_json::from_str(line).map_err(|error| TaskulusError::Io(error.to_string()))?;
        if record.get("id").is_none() {
            return Err(TaskulusError::IssueOperation("missing id".to_string()));
        }
        records.push(record);
    }
    Ok(records)
}

fn convert_record(
    record: &Value,
    record_by_id: &HashMap<String, Value>,
    configuration: &ProjectConfiguration,
) -> Result<IssueData, TaskulusError> {
    let identifier = required_string(record, "id")?;
    let title = required_string(record, "title")?;
    let issue_type = required_string(record, "issue_type")?;
    validate_issue_type(configuration, &issue_type)?;

    let status = required_string(record, "status")?;
    validate_status(configuration, &issue_type, &status)?;

    let priority_value = record.get("priority").ok_or_else(|| {
        TaskulusError::IssueOperation("priority is required".to_string())
    })?;
    let priority = priority_value.as_i64().ok_or_else(|| {
        TaskulusError::IssueOperation("priority is required".to_string())
    })?;
    if !configuration.priorities.contains_key(&(priority as u8)) {
        return Err(TaskulusError::IssueOperation("invalid priority".to_string()));
    }

    let created_at = parse_timestamp(record.get("created_at"), "created_at")?;
    let updated_at = parse_timestamp(record.get("updated_at"), "updated_at")?;
    let closed_at = match record.get("closed_at") {
        None => None,
        Some(Value::Null) => None,
        Some(Value::String(value)) if value.is_empty() => None,
        Some(value) => Some(parse_timestamp(Some(value), "closed_at")?),
    };

    let (parent, dependencies) = convert_dependencies(
        record.get("dependencies").and_then(Value::as_array),
        record_by_id,
        configuration,
        &issue_type,
    )?;

    let comments = convert_comments(record.get("comments").and_then(Value::as_array))?;

    let mut custom = BTreeMap::new();
    if let Some(owner) = record.get("owner").and_then(Value::as_str) {
        if !owner.is_empty() {
            custom.insert("beads_owner".to_string(), Value::String(owner.to_string()));
        }
    }
    if let Some(notes) = record.get("notes").and_then(Value::as_str) {
        if !notes.is_empty() {
            custom.insert("beads_notes".to_string(), Value::String(notes.to_string()));
        }
    }
    if let Some(criteria) = record.get("acceptance_criteria").and_then(Value::as_str) {
        if !criteria.is_empty() {
            custom.insert(
                "beads_acceptance_criteria".to_string(),
                Value::String(criteria.to_string()),
            );
        }
    }
    if let Some(reason) = record.get("close_reason").and_then(Value::as_str) {
        if !reason.is_empty() {
            custom.insert(
                "beads_close_reason".to_string(),
                Value::String(reason.to_string()),
            );
        }
    }

    Ok(IssueData {
        identifier,
        title,
        description: record
            .get("description")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        issue_type,
        status,
        priority: priority as i32,
        assignee: record.get("assignee").and_then(Value::as_str).map(str::to_string),
        creator: record.get("created_by").and_then(Value::as_str).map(str::to_string),
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
    dependencies: Option<&Vec<Value>>,
    record_by_id: &HashMap<String, Value>,
    configuration: &ProjectConfiguration,
    issue_type: &str,
) -> Result<(Option<String>, Vec<DependencyLink>), TaskulusError> {
    let mut parent: Option<String> = None;
    let mut links: Vec<DependencyLink> = Vec::new();

    if let Some(dependencies) = dependencies {
        for dependency in dependencies {
            let dependency_type = dependency
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or("");
            let depends_on_id = dependency
                .get("depends_on_id")
                .and_then(Value::as_str)
                .unwrap_or("");
            if dependency_type.is_empty() || depends_on_id.is_empty() {
                return Err(TaskulusError::IssueOperation(
                    "invalid dependency".to_string(),
                ));
            }
            if !record_by_id.contains_key(depends_on_id) {
                return Err(TaskulusError::IssueOperation(
                    "missing dependency".to_string(),
                ));
            }
            if dependency_type == "parent-child" {
                if parent.is_some() {
                    return Err(TaskulusError::IssueOperation(
                        "multiple parents".to_string(),
                    ));
                }
                parent = Some(depends_on_id.to_string());
            } else {
                links.push(DependencyLink {
                    target: depends_on_id.to_string(),
                    dependency_type: dependency_type.to_string(),
                });
            }
        }
    }

    if let Some(parent_id) = &parent {
        let parent_record = record_by_id
            .get(parent_id)
            .expect("missing dependency");
        let parent_issue_type = parent_record
            .get("issue_type")
            .and_then(Value::as_str)
            .unwrap_or("");
        if parent_issue_type.is_empty() {
            return Err(TaskulusError::IssueOperation(
                "parent issue_type is required".to_string(),
            ));
        }
        validate_parent_child_relationship(configuration, parent_issue_type, issue_type)?;
    }

    Ok((parent, links))
}

fn convert_comments(comments: Option<&Vec<Value>>) -> Result<Vec<IssueComment>, TaskulusError> {
    let mut results = Vec::new();
    if let Some(comments) = comments {
        for comment in comments {
            let author = comment.get("author").and_then(Value::as_str).unwrap_or("");
            let text = comment.get("text").and_then(Value::as_str).unwrap_or("");
            if author.trim().is_empty() || text.trim().is_empty() {
                return Err(TaskulusError::IssueOperation("invalid comment".to_string()));
            }
            let created_at = parse_timestamp(comment.get("created_at"), "comment.created_at")?;
            results.push(IssueComment {
                author: author.to_string(),
                text: text.to_string(),
                created_at,
            });
        }
    }
    Ok(results)
}

fn parse_timestamp(value: Option<&Value>, field_name: &str) -> Result<DateTime<Utc>, TaskulusError> {
    let Some(value) = value else {
        return Err(TaskulusError::IssueOperation(format!(
            "{field_name} is required"
        )));
    };
    if value.is_null() {
        return Err(TaskulusError::IssueOperation(format!(
            "{field_name} is required"
        )));
    }
    let Some(text) = value.as_str() else {
        return Err(TaskulusError::IssueOperation(format!(
            "{field_name} must be a string"
        )));
    };
    if text.is_empty() {
        return Err(TaskulusError::IssueOperation(format!(
            "{field_name} is required"
        )));
    }
    let normalized = if text.ends_with('Z') {
        text.replace('Z', "+00:00")
    } else {
        text.to_string()
    };
    let parsed = DateTime::parse_from_rfc3339(&normalized)
        .map_err(|_| TaskulusError::IssueOperation(format!("invalid {field_name}")))?;
    Ok(parsed.with_timezone(&Utc))
}

fn required_string(record: &Value, key: &str) -> Result<String, TaskulusError> {
    let value = record.get(key).and_then(Value::as_str).unwrap_or("");
    if value.trim().is_empty() {
        return Err(TaskulusError::IssueOperation(format!("{key} is required")));
    }
    Ok(value.to_string())
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
    let mut statuses = HashSet::new();
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
