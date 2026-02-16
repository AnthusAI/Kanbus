#![cfg_attr(tarpaulin, skip)]
//! Beads to Kanbus migration helpers.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs;
use std::path::Path;

use chrono::{DateTime, TimeZone, Utc};
use serde_json::Value;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{
    discover_kanbus_projects, discover_project_directories, ensure_git_repository,
    get_configuration_path, initialize_project,
};
use crate::hierarchy::validate_parent_child_relationship;
use crate::issue_files::write_issue_to_file;
use crate::models::{
    DependencyLink, IssueComment, IssueData, PriorityDefinition, ProjectConfiguration,
};
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
/// Returns `KanbusError` if Beads data is missing or invalid.
pub fn load_beads_issues(root: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let beads_dir = root.join(".beads");
    if !beads_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "no .beads directory".to_string(),
        ));
    }

    let issues_path = beads_dir.join("issues.jsonl");
    if !issues_path.exists() {
        return Err(KanbusError::IssueOperation("no issues.jsonl".to_string()));
    }

    let records = load_beads_records(&issues_path)?;
    let configuration = build_beads_configuration(&records);
    let mut record_by_id: HashMap<String, Value> = HashMap::new();
    for record in &records {
        let identifier = record
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| KanbusError::IssueOperation("missing id".to_string()))?;
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
/// Returns `KanbusError::IssueOperation` if the issue is missing.
pub fn load_beads_issue_by_id(root: &Path, identifier: &str) -> Result<IssueData, KanbusError> {
    let issues = load_beads_issues(root)?;
    let mut exact_matches = Vec::new();
    let mut partial_matches = Vec::new();

    for issue in issues {
        if issue.identifier == identifier {
            exact_matches.push(issue);
        } else if issue_id_matches(identifier, &issue.identifier) {
            partial_matches.push(issue);
        }
    }

    if !exact_matches.is_empty() {
        return Ok(exact_matches.into_iter().next().unwrap());
    }

    match partial_matches.len() {
        0 => Err(KanbusError::IssueOperation("not found".to_string())),
        1 => Ok(partial_matches.into_iter().next().unwrap()),
        _ => {
            let ids: Vec<String> = partial_matches
                .iter()
                .map(|i| i.identifier.clone())
                .collect();
            Err(KanbusError::IssueOperation(format!(
                "ambiguous identifier, matches: {}",
                ids.join(", ")
            )))
        }
    }
}

/// Check if an abbreviated identifier matches a full identifier.
///
/// # Arguments
/// * `abbreviated` - Abbreviated ID (e.g., "tskl-abcdef", "custom-uuid00").
/// * `full_id` - Full ID (e.g., "tskl-abcdef2", "custom-uuid-0000001").
///
/// # Returns
/// True if abbreviated ID matches the full ID.
fn issue_id_matches(abbreviated: &str, full_id: &str) -> bool {
    use crate::ids::format_issue_key;

    let abbreviated_formatted = format_issue_key(full_id, false);

    if abbreviated == abbreviated_formatted {
        return true;
    }

    if abbreviated.len() >= full_id.len() {
        return false;
    }

    full_id.starts_with(abbreviated)
}

/// Migrate Beads issues.jsonl into a Kanbus project.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` if migration fails.
pub fn migrate_from_beads(root: &Path) -> Result<MigrationResult, KanbusError> {
    ensure_git_repository(root)?;

    let beads_dir = root.join(".beads");
    if !beads_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "no .beads directory".to_string(),
        ));
    }

    let issues_path = beads_dir.join("issues.jsonl");
    if !issues_path.exists() {
        return Err(KanbusError::IssueOperation("no issues.jsonl".to_string()));
    }

    let mut projects = Vec::new();
    discover_project_directories(root, &mut projects)?;
    let mut dotfile_projects = discover_kanbus_projects(root)?;
    projects.append(&mut dotfile_projects);
    if !projects.is_empty() {
        return Err(KanbusError::IssueOperation(
            "already initialized".to_string(),
        ));
    }

    initialize_project(root, false)?;
    let project_dir = root.join("project");
    let configuration =
        load_project_configuration(&get_configuration_path(project_dir.as_path())?)?;

    let records = load_beads_records(&issues_path)?;
    let mut record_by_id: HashMap<String, Value> = HashMap::new();
    for record in &records {
        let identifier = record
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| KanbusError::IssueOperation("missing id".to_string()))?;
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

fn load_beads_records(path: &Path) -> Result<Vec<Value>, KanbusError> {
    let contents = fs::read_to_string(path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let mut records = Vec::new();
    for line in contents.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let record: Value =
            serde_json::from_str(line).map_err(|error| KanbusError::Io(error.to_string()))?;
        if record.get("id").is_none() {
            return Err(KanbusError::IssueOperation("missing id".to_string()));
        }
        records.push(record);
    }
    Ok(records)
}

fn convert_record(
    record: &Value,
    record_by_id: &HashMap<String, Value>,
    configuration: &ProjectConfiguration,
) -> Result<IssueData, KanbusError> {
    let identifier = required_string(record, "id")?;
    let title = required_string(record, "title")?;
    let issue_type_raw = required_string(record, "issue_type")?;
    let issue_type = map_issue_type(&issue_type_raw);
    validate_issue_type(configuration, &issue_type)?;

    let status = required_string(record, "status")?;
    validate_status(configuration, &issue_type, &status)?;

    let priority_value = record
        .get("priority")
        .ok_or_else(|| KanbusError::IssueOperation("priority is required".to_string()))?;
    let priority = priority_value
        .as_i64()
        .ok_or_else(|| KanbusError::IssueOperation("priority is required".to_string()))?;
    if !configuration.priorities.contains_key(&(priority as u8)) {
        return Err(KanbusError::IssueOperation("invalid priority".to_string()));
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
        &identifier,
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
    if issue_type != issue_type_raw {
        custom.insert(
            "beads_issue_type".to_string(),
            Value::String(issue_type_raw.to_string()),
        );
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
        assignee: record
            .get("assignee")
            .and_then(Value::as_str)
            .map(str::to_string),
        creator: record
            .get("created_by")
            .and_then(Value::as_str)
            .map(str::to_string),
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
    identifier: &str,
    issue_type: &str,
) -> Result<(Option<String>, Vec<DependencyLink>), KanbusError> {
    let mut parent: Option<String> = None;
    let mut extra_parents: Vec<String> = Vec::new();
    let mut links: Vec<DependencyLink> = Vec::new();

    if let Some(dependencies) = dependencies {
        for dependency in dependencies {
            let dependency_type = dependency.get("type").and_then(Value::as_str).unwrap_or("");
            let depends_on_id = dependency
                .get("depends_on_id")
                .and_then(Value::as_str)
                .unwrap_or("");
            if dependency_type.is_empty() || depends_on_id.is_empty() {
                return Err(KanbusError::IssueOperation(
                    "invalid dependency".to_string(),
                ));
            }
            if !record_by_id.contains_key(depends_on_id) {
                return Err(KanbusError::IssueOperation(
                    "missing dependency".to_string(),
                ));
            }
            if dependency_type == "parent-child" {
                if parent.is_some() {
                    extra_parents.push(depends_on_id.to_string());
                } else {
                    parent = Some(depends_on_id.to_string());
                }
            } else {
                links.push(DependencyLink {
                    target: depends_on_id.to_string(),
                    dependency_type: dependency_type.to_string(),
                });
            }
        }
    }

    if let Some(parent_id) = &parent {
        if !extra_parents.is_empty() {
            let extras = extra_parents.join(", ");
            eprintln!(
                "Suggestion: '{identifier}' has multiple parents ({parent_id}, {extras}). Using '{parent_id}' and ignoring the rest. Remove extra parents in Beads or migrate to a single parent-child relationship."
            );
        }
        let parent_record = record_by_id.get(parent_id).expect("missing dependency");
        let parent_issue_type = parent_record
            .get("issue_type")
            .and_then(Value::as_str)
            .unwrap_or("");
        if parent_issue_type.is_empty() {
            return Err(KanbusError::IssueOperation(
                "parent issue_type is required".to_string(),
            ));
        }
        let canonical_parent = map_issue_type(parent_issue_type);
        let skip_validation = canonical_parent == issue_type
            && (canonical_parent == "epic" || canonical_parent == "task");
        if !skip_validation {
            let validation_result =
                if cfg!(tarpaulin) && std::env::var_os("KANBUS_TEST_HIERARCHY_ERROR").is_some() {
                    Err(KanbusError::Io("forced hierarchy error".to_string()))
                } else {
                    validate_parent_child_relationship(configuration, &canonical_parent, issue_type)
                };
            match validation_result {
                Ok(()) => {}
                Err(KanbusError::InvalidHierarchy(_message)) => {
                    parent = None;
                }
                Err(error) => return Err(error),
            }
        }
    }

    Ok((parent, links))
}

fn convert_comments(comments: Option<&Vec<Value>>) -> Result<Vec<IssueComment>, KanbusError> {
    let mut results = Vec::new();
    if let Some(comments) = comments {
        for comment in comments {
            let author = comment.get("author").and_then(Value::as_str).unwrap_or("");
            let text = comment.get("text").and_then(Value::as_str).unwrap_or("");
            if author.trim().is_empty() || text.trim().is_empty() {
                return Err(KanbusError::IssueOperation("invalid comment".to_string()));
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

fn parse_timestamp(value: Option<&Value>, field_name: &str) -> Result<DateTime<Utc>, KanbusError> {
    let Some(value) = value else {
        return Err(KanbusError::IssueOperation(format!(
            "{field_name} is required"
        )));
    };
    if value.is_null() {
        return Err(KanbusError::IssueOperation(format!(
            "{field_name} is required"
        )));
    }
    let Some(text) = value.as_str() else {
        return Err(KanbusError::IssueOperation(format!(
            "{field_name} must be a string"
        )));
    };
    if text.is_empty() {
        return Err(KanbusError::IssueOperation(format!(
            "{field_name} is required"
        )));
    }
    let mut normalized = if text.ends_with('Z') {
        text.replace('Z', "+00:00")
    } else {
        text.to_string()
    };
    normalized = normalize_fractional_seconds(&normalized);
    if has_timezone(&normalized) {
        let parsed = DateTime::parse_from_rfc3339(&normalized)
            .map_err(|_| KanbusError::IssueOperation(format!("invalid {field_name}")))?;
        return Ok(parsed.with_timezone(&Utc));
    }
    let parsed = chrono::NaiveDateTime::parse_from_str(&normalized, "%Y-%m-%dT%H:%M:%S%.f")
        .or_else(|_| chrono::NaiveDateTime::parse_from_str(&normalized, "%Y-%m-%dT%H:%M:%S"))
        .map_err(|_| KanbusError::IssueOperation(format!("invalid {field_name}")))?;
    Ok(Utc.from_utc_datetime(&parsed))
}

fn required_string(record: &Value, key: &str) -> Result<String, KanbusError> {
    let value = record.get(key).and_then(Value::as_str).unwrap_or("");
    if value.trim().is_empty() {
        return Err(KanbusError::IssueOperation(format!("{key} is required")));
    }
    Ok(value.to_string())
}

fn normalize_fractional_seconds(text: &str) -> String {
    let Some(dot_index) = text.rfind('.') else {
        return text.to_string();
    };
    let prefix = &text[..dot_index + 1];
    let remainder = &text[dot_index + 1..];
    let plus_index = remainder.rfind('+');
    let minus_index = remainder.rfind('-');
    let tz_index = match (plus_index, minus_index) {
        (Some(plus), Some(minus)) => Some(plus.max(minus)),
        (Some(plus), None) => Some(plus),
        (None, Some(minus)) => Some(minus),
        (None, None) => None,
    };
    let Some(tz_index) = tz_index else {
        return text.to_string();
    };
    let fractional = &remainder[..tz_index];
    if !fractional.chars().all(|ch| ch.is_ascii_digit()) {
        return text.to_string();
    }
    let timezone_part = &remainder[tz_index..];
    let mut adjusted = fractional.to_string();
    if adjusted.len() > 6 {
        adjusted.truncate(6);
    } else if adjusted.len() < 6 {
        while adjusted.len() < 6 {
            adjusted.push('0');
        }
    }
    format!("{prefix}{adjusted}{timezone_part}")
}

fn has_timezone(text: &str) -> bool {
    let Some(time_index) = text.find('T') else {
        return false;
    };
    let time_part = &text[time_index..];
    time_part.contains('+') || time_part[1..].contains('-')
}

fn validate_issue_type(
    configuration: &ProjectConfiguration,
    issue_type: &str,
) -> Result<(), KanbusError> {
    let known = configuration
        .hierarchy
        .iter()
        .chain(configuration.types.iter())
        .any(|value| value == issue_type);
    if !known {
        return Err(KanbusError::IssueOperation(
            "unknown issue type".to_string(),
        ));
    }
    Ok(())
}

fn validate_status(
    configuration: &ProjectConfiguration,
    issue_type: &str,
    status: &str,
) -> Result<(), KanbusError> {
    let workflow = get_workflow_for_issue_type(configuration, issue_type)?;
    let mut statuses = HashSet::new();
    for (key, values) in workflow.iter() {
        statuses.insert(key.as_str());
        for value in values {
            statuses.insert(value.as_str());
        }
    }
    if !statuses.contains(status) {
        return Err(KanbusError::IssueOperation("invalid status".to_string()));
    }
    Ok(())
}

fn map_issue_type(raw: &str) -> String {
    for (source, target) in BEADS_ISSUE_TYPE_MAP {
        if raw == *source {
            return target.to_string();
        }
    }
    raw.to_string()
}

fn build_beads_configuration(records: &[Value]) -> ProjectConfiguration {
    let mut types: HashSet<String> = HashSet::new();
    let mut statuses: HashSet<String> = HashSet::new();
    let mut priorities: HashSet<u8> = HashSet::new();

    for record in records {
        if let Some(issue_type) = record.get("issue_type").and_then(Value::as_str) {
            types.insert(map_issue_type(issue_type));
        }
        if let Some(status) = record.get("status").and_then(Value::as_str) {
            statuses.insert(status.to_string());
        }
        if let Some(priority) = record.get("priority").and_then(Value::as_i64) {
            priorities.insert(priority as u8);
        }
    }

    statuses.extend(["open", "in_progress", "blocked", "deferred", "closed"].map(str::to_string));
    priorities.extend([0, 1, 2, 3, 4]);

    let mut status_vec: Vec<String> = statuses.into_iter().collect();
    status_vec.sort();
    let mut workflow_state: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for status in &status_vec {
        workflow_state.insert(status.clone(), status_vec.clone());
    }
    let mut workflows: BTreeMap<String, BTreeMap<String, Vec<String>>> = BTreeMap::new();
    workflows.insert("default".to_string(), workflow_state.clone());
    workflows.insert("epic".to_string(), workflow_state.clone());
    workflows.insert("task".to_string(), workflow_state.clone());

    let mut priority_defs: BTreeMap<u8, PriorityDefinition> = BTreeMap::new();
    for value in priorities {
        priority_defs.insert(
            value,
            PriorityDefinition {
                name: format!("P{value}"),
                color: None,
            },
        );
    }

    ProjectConfiguration {
        project_directory: "project".to_string(),
        external_projects: Vec::new(),
        ignore_paths: Vec::new(),
        project_key: "BD".to_string(),
        project_management_template: None,
        hierarchy: vec![
            "epic".to_string(),
            "task".to_string(),
            "sub-task".to_string(),
        ],
        types: types.into_iter().collect(),
        workflows,
        initial_status: "open".to_string(),
        priorities: priority_defs,
        default_priority: 2,
        assignee: None,
        time_zone: None,
        status_colors: BTreeMap::new(),
        type_colors: BTreeMap::new(),
        beads_compatibility: false,
    }
}
const BEADS_ISSUE_TYPE_MAP: &[(&str, &str)] = &[("feature", "story"), ("message", "task")];
