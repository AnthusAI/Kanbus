//! Maintenance command implementations.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{get_configuration_path, load_project_directory};
use crate::hierarchy::validate_parent_child_relationship;
use crate::models::IssueData;
use crate::workflows::get_workflow_for_issue_type;

const ALLOWED_DEPENDENCY_TYPES: [&str; 2] = ["blocked-by", "relates-to"];

/// Aggregate issue statistics for a project.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectStats {
    pub total: usize,
    pub open_count: usize,
    pub closed_count: usize,
    pub type_counts: BTreeMap<String, usize>,
}

/// Validate issue data and configuration for a Kanbus project.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if validation fails.
pub fn validate_project(root: &Path) -> Result<(), KanbusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    if !issues_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "issues directory missing".to_string(),
        ));
    }

    let configuration =
        load_project_configuration(&get_configuration_path(project_dir.as_path())?)?;

    let mut errors: Vec<String> = Vec::new();
    let mut issues: BTreeMap<String, IssueData> = BTreeMap::new();

    let mut paths: Vec<_> = fs::read_dir(&issues_dir)
        .map_err(|error| KanbusError::Io(error.to_string()))?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some("json"))
        .collect();
    paths.sort_by(|left, right| left.file_name().cmp(&right.file_name()));

    for path in paths {
        let filename = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("unknown");
        let contents = match fs::read_to_string(&path) {
            Ok(contents) => contents,
            Err(error) => {
                errors.push(format!("{filename}: unable to read issue: {error}"));
                continue;
            }
        };

        let payload: serde_json::Value = match serde_json::from_str(&contents) {
            Ok(payload) => payload,
            Err(error) => {
                errors.push(format!("{filename}: invalid json: {error}"));
                continue;
            }
        };

        let issue: IssueData = match serde_json::from_value(payload) {
            Ok(issue) => issue,
            Err(error) => {
                errors.push(format!("{filename}: invalid issue data: {error}"));
                continue;
            }
        };

        if issues.contains_key(&issue.identifier) {
            errors.push(format!(
                "{filename}: duplicate issue id '{}'",
                issue.identifier
            ));
            continue;
        }

        validate_issue_fields(filename, &issue, &configuration, &mut errors);
        issues.insert(issue.identifier.clone(), issue);
    }

    validate_references(&issues, &configuration, &mut errors);

    if errors.is_empty() {
        Ok(())
    } else {
        Err(KanbusError::IssueOperation(format_errors(&errors)))
    }
}

/// Collect project statistics from issue data.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Returns
/// Aggregated project statistics.
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if stats cannot be computed.
pub fn collect_project_stats(root: &Path) -> Result<ProjectStats, KanbusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    if !issues_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "issues directory missing".to_string(),
        ));
    }

    let mut issues: Vec<IssueData> = Vec::new();
    for entry in fs::read_dir(&issues_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let contents =
            fs::read_to_string(&path).map_err(|error| KanbusError::Io(error.to_string()))?;
        let filename = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("unknown");
        let payload: serde_json::Value = serde_json::from_str(&contents).map_err(|error| {
            KanbusError::IssueOperation(format!("{filename}: invalid json: {error}"))
        })?;
        let issue: IssueData = serde_json::from_value(payload).map_err(|error| {
            KanbusError::IssueOperation(format!("{filename}: invalid issue data: {error}"))
        })?;
        issues.push(issue);
    }

    let total = issues.len();
    let closed_count = issues
        .iter()
        .filter(|issue| issue.status == "closed")
        .count();
    let open_count = total - closed_count;
    let mut type_counts: BTreeMap<String, usize> = BTreeMap::new();
    for issue in issues {
        *type_counts.entry(issue.issue_type).or_insert(0) += 1;
    }

    Ok(ProjectStats {
        total,
        open_count,
        closed_count,
        type_counts,
    })
}

fn validate_issue_fields(
    filename: &str,
    issue: &IssueData,
    configuration: &crate::models::ProjectConfiguration,
    errors: &mut Vec<String>,
) {
    let expected_id = Path::new(filename)
        .file_stem()
        .and_then(|stem| stem.to_str())
        .unwrap_or(filename);
    if issue.identifier != expected_id {
        errors.push(format!(
            "{filename}: issue id '{}' does not match filename",
            issue.identifier
        ));
    }

    let mut valid_types = configuration.hierarchy.clone();
    valid_types.extend(configuration.types.clone());
    if !valid_types.iter().any(|entry| entry == &issue.issue_type) {
        errors.push(format!(
            "{filename}: unknown issue type '{}'",
            issue.issue_type
        ));
    }

    let priority_value = if (0..=u8::MAX as i32).contains(&issue.priority) {
        Some(issue.priority as u8)
    } else {
        None
    };
    let priority_valid =
        priority_value.is_some_and(|value| configuration.priorities.contains_key(&value));
    if !priority_valid {
        errors.push(format!("{filename}: invalid priority '{}'", issue.priority));
    }

    if let Ok(statuses) = collect_workflow_statuses(configuration, &issue.issue_type) {
        if !statuses.contains(&issue.status) {
            errors.push(format!("{filename}: invalid status '{}'", issue.status));
        }
    }

    if issue.status == "closed" && issue.closed_at.is_none() {
        errors.push(format!("{filename}: closed issues must have closed_at set"));
    }
    if issue.status != "closed" && issue.closed_at.is_some() {
        errors.push(format!(
            "{filename}: non-closed issues must not set closed_at"
        ));
    }

    for dependency in &issue.dependencies {
        if !ALLOWED_DEPENDENCY_TYPES
            .iter()
            .any(|entry| *entry == dependency.dependency_type)
        {
            errors.push(format!(
                "{filename}: invalid dependency type '{}'",
                dependency.dependency_type
            ));
        }
    }
}

fn collect_workflow_statuses(
    configuration: &crate::models::ProjectConfiguration,
    issue_type: &str,
) -> Result<BTreeSet<String>, KanbusError> {
    let workflow = get_workflow_for_issue_type(configuration, issue_type)?;
    let mut statuses: BTreeSet<String> = workflow.keys().cloned().collect();
    for transitions in workflow.values() {
        statuses.extend(transitions.iter().cloned());
    }
    Ok(statuses)
}

fn validate_references(
    issues: &BTreeMap<String, IssueData>,
    configuration: &crate::models::ProjectConfiguration,
    errors: &mut Vec<String>,
) {
    for issue in issues.values() {
        if let Some(parent_id) = &issue.parent {
            match issues.get(parent_id) {
                Some(parent_issue) => {
                    if let Err(error) = validate_parent_child_relationship(
                        configuration,
                        &parent_issue.issue_type,
                        &issue.issue_type,
                    ) {
                        errors.push(format!("{}: {}", issue.identifier, error));
                    }
                }
                None => errors.push(format!(
                    "{}: parent '{}' does not exist",
                    issue.identifier, parent_id
                )),
            }
        }

        for dependency in &issue.dependencies {
            if !issues.contains_key(&dependency.target) {
                errors.push(format!(
                    "{}: dependency target '{}' does not exist",
                    issue.identifier, dependency.target
                ));
            }
        }
    }
}

fn format_errors(errors: &[String]) -> String {
    format!("validation failed:\n{}", errors.join("\n"))
}
