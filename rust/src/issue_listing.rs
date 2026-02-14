//! Issue listing utilities.

use std::path::Path;

use crate::cache::{collect_issue_file_mtimes, load_cache_if_valid, write_cache};
use crate::daemon_client::{is_daemon_enabled, request_index_list};
use crate::error::KanbusError;
use crate::file_io::{
    canonicalize_path, discover_kanbus_projects, discover_project_directories,
    find_project_local_directory, load_project_directory,
};
use crate::index::build_index_from_directory;
use crate::models::IssueData;
use crate::queries::{filter_issues, search_issues, sort_issues};

/// List issues for the project.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` when listing fails.
#[allow(clippy::too_many_arguments)]
pub fn list_issues(
    root: &Path,
    status: Option<&str>,
    issue_type: Option<&str>,
    assignee: Option<&str>,
    label: Option<&str>,
    sort: Option<&str>,
    search: Option<&str>,
    include_local: bool,
    local_only: bool,
) -> Result<Vec<IssueData>, KanbusError> {
    if local_only && !include_local {
        return Err(KanbusError::IssueOperation(
            "local-only conflicts with no-local".to_string(),
        ));
    }
    let mut projects = Vec::new();
    discover_project_directories(root, &mut projects)?;
    let mut dotfile_projects = discover_kanbus_projects(root)?;
    projects.append(&mut dotfile_projects);
    let mut normalized = Vec::new();
    for path in projects {
        match canonicalize_path(&path) {
            Ok(canonical) => normalized.push(canonical),
            Err(_) => normalized.push(path),
        }
    }
    normalized.sort();
    normalized.dedup();
    let projects = normalized;
    if projects.is_empty() {
        return Err(KanbusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }
    if projects.len() > 1 {
        let issues = list_issues_across_projects(root, &projects, include_local, local_only)?;
        return apply_query(issues, status, issue_type, assignee, label, sort, search);
    }

    if include_local || local_only {
        let project_dir = load_project_directory(root)?;
        let local_dir = find_project_local_directory(&project_dir);
        let issues = list_issues_with_local(&project_dir, local_dir.as_deref(), local_only)?;
        return apply_query(issues, status, issue_type, assignee, label, sort, search);
    }
    if is_daemon_enabled() {
        let payloads = request_index_list(root)?;
        let issues: Vec<IssueData> = payloads
            .into_iter()
            .map(serde_json::from_value::<IssueData>)
            .map(|result| result.map_err(|error| KanbusError::Io(error.to_string())))
            .collect::<Result<Vec<IssueData>, KanbusError>>()?;
        return apply_query(issues, status, issue_type, assignee, label, sort, search);
    }
    let issues = list_issues_local(root)?;
    apply_query(issues, status, issue_type, assignee, label, sort, search)
}

fn list_issues_local(root: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let project_dir = load_project_directory(root)?;
    list_issues_for_project(&project_dir)
}

fn list_issues_for_project(project_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let issues_dir = project_dir.join("issues");
    let cache_path = project_dir.join(".cache").join("index.json");
    if let Some(index) = load_cache_if_valid(&cache_path, &issues_dir)? {
        return Ok(index
            .by_id
            .values()
            .map(|issue| issue.as_ref().clone())
            .collect());
    }
    let index = build_index_from_directory(&issues_dir)?;
    let mtimes = collect_issue_file_mtimes(&issues_dir)?;
    write_cache(&index, &cache_path, &mtimes)?;
    Ok(index
        .by_id
        .values()
        .map(|issue| issue.as_ref().clone())
        .collect())
}

fn list_issues_with_local(
    project_dir: &Path,
    local_dir: Option<&Path>,
    local_only: bool,
) -> Result<Vec<IssueData>, KanbusError> {
    let shared_issues = list_issues_for_project(project_dir)?;
    let mut local_issues = Vec::new();
    if let Some(local_dir) = local_dir {
        let issues_dir = local_dir.join("issues");
        if issues_dir.exists() {
            local_issues = load_issues_from_directory(&issues_dir)?;
        }
    }
    if local_only {
        return Ok(local_issues);
    }
    Ok([shared_issues, local_issues].concat())
}

fn list_issues_across_projects(
    root: &Path,
    projects: &[std::path::PathBuf],
    include_local: bool,
    local_only: bool,
) -> Result<Vec<IssueData>, KanbusError> {
    let mut issues = Vec::new();
    for project_dir in projects {
        let local_dir = if include_local || local_only {
            find_project_local_directory(project_dir)
        } else {
            None
        };
        if local_only && local_dir.is_none() {
            continue;
        }
        let mut project_issues =
            list_issues_with_local(project_dir, local_dir.as_deref(), local_only)?;
        for issue in &mut project_issues {
            tag_issue_project(issue, root, project_dir);
        }
        issues.extend(project_issues);
    }
    Ok(issues)
}

fn tag_issue_project(issue: &mut IssueData, root: &Path, project_dir: &Path) {
    let project_path = project_dir
        .strip_prefix(root)
        .map(|path| path.to_path_buf())
        .unwrap_or_else(|_| project_dir.to_path_buf());
    issue.custom.insert(
        "project_path".to_string(),
        serde_json::Value::String(project_path.to_string_lossy().to_string()),
    );
}

fn load_issues_from_directory(issues_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let mut issues = Vec::new();
    for entry in
        std::fs::read_dir(issues_dir).map_err(|error| KanbusError::Io(error.to_string()))?
    {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        issues.push(crate::issue_files::read_issue_from_file(&path)?);
    }
    issues.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    Ok(issues)
}

fn apply_query(
    issues: Vec<IssueData>,
    status: Option<&str>,
    issue_type: Option<&str>,
    assignee: Option<&str>,
    label: Option<&str>,
    sort: Option<&str>,
    search: Option<&str>,
) -> Result<Vec<IssueData>, KanbusError> {
    let filtered = filter_issues(issues, status, issue_type, assignee, label);
    let searched = search_issues(filtered, search);
    sort_issues(searched, sort)
}
