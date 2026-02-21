//! Issue listing utilities.

use std::io::ErrorKind;
use std::path::Path;

use crate::daemon_client::{is_daemon_enabled, request_index_list};
use crate::error::KanbusError;
use crate::config_loader::load_project_configuration;
use crate::file_io::{
    canonicalize_path, discover_kanbus_projects, discover_project_directories,
    find_project_local_directory, get_configuration_path, load_project_directory,
    resolve_labeled_projects,
};
use crate::models::IssueData;
use crate::queries::{filter_issues, search_issues, sort_issues};
use std::collections::HashSet;

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
    project_filter: &[String],
    include_local: bool,
    local_only: bool,
) -> Result<Vec<IssueData>, KanbusError> {
    if local_only && !include_local {
        return Err(KanbusError::IssueOperation(
            "local-only conflicts with no-local".to_string(),
        ));
    }
    if !project_filter.is_empty() {
        return list_with_project_filter(
            root,
            project_filter,
            status,
            issue_type,
            assignee,
            label,
            sort,
            search,
            include_local,
            local_only,
        );
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
    if let Ok(config_path) = get_configuration_path(root) {
        if let Ok(configuration) = load_project_configuration(&config_path) {
            let base = config_path.parent().unwrap_or_else(|| Path::new(""));
            normalized.retain(|project_path| {
                !crate::file_io::is_path_ignored(project_path, base, &configuration.ignore_paths)
            });
        }
    }
    let mut permission_error = None;
    normalized.retain(|path| {
        let issues_dir = path.join("issues");
        match std::fs::metadata(&issues_dir) {
            Ok(metadata) => metadata.is_dir(),
            Err(error) => {
                if error.kind() == ErrorKind::PermissionDenied {
                    permission_error = Some(error);
                }
                false
            }
        }
    });
    if let Some(error) = permission_error {
        return Err(KanbusError::Io(error.to_string()));
    }
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
        if !local_only && is_daemon_enabled() {
            let payloads = request_index_list(root)?;
            let mut issues: Vec<IssueData> = payloads
                .into_iter()
                .map(serde_json::from_value::<IssueData>)
                .map(|result| result.map_err(|error| KanbusError::Io(error.to_string())))
                .collect::<Result<Vec<IssueData>, KanbusError>>()?;
            if let Some(local_dir) = local_dir {
                let local_issues_dir = local_dir.join("issues");
                if local_issues_dir.exists() {
                    issues.extend(load_issues_from_directory(&local_issues_dir)?);
                }
            }
            return apply_query(issues, status, issue_type, assignee, label, sort, search);
        }
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

#[allow(clippy::too_many_arguments)]
fn list_with_project_filter(
    root: &Path,
    project_filter: &[String],
    status: Option<&str>,
    issue_type: Option<&str>,
    assignee: Option<&str>,
    label: Option<&str>,
    sort: Option<&str>,
    search: Option<&str>,
    include_local: bool,
    local_only: bool,
) -> Result<Vec<IssueData>, KanbusError> {
    let labeled = resolve_labeled_projects(root)?;
    if labeled.is_empty() {
        return Err(KanbusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }
    let known: HashSet<&str> = labeled.iter().map(|p| p.label.as_str()).collect();
    for name in project_filter {
        if !known.contains(name.as_str()) {
            return Err(KanbusError::IssueOperation(format!("unknown project: {name}")));
        }
    }
    let allowed: HashSet<&str> = project_filter.iter().map(|s| s.as_str()).collect();
    let project_dirs: Vec<std::path::PathBuf> = labeled
        .into_iter()
        .filter(|p| allowed.contains(p.label.as_str()))
        .map(|p| p.project_dir)
        .collect();
    let issues = list_issues_across_projects(root, &project_dirs, include_local, local_only)?;
    apply_query(issues, status, issue_type, assignee, label, sort, search)
}

fn list_issues_local(root: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let project_dir = load_project_directory(root)?;
    list_issues_for_project(&project_dir)
}

fn list_issues_for_project(project_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let issues_dir = project_dir.join("issues");
    if !issues_dir.is_dir() {
        return Err(KanbusError::IssueOperation(format!(
            "issues directory not found: {}. Run 'kanbus migrate' if you need to migrate from an older format.",
            issues_dir.display()
        )));
    }
    load_issues_from_directory(&issues_dir)
}

fn list_issues_with_local(
    project_dir: &Path,
    local_dir: Option<&Path>,
    local_only: bool,
) -> Result<Vec<IssueData>, KanbusError> {
    if std::env::var("KANBUS_TEST_LOCAL_LISTING_ERROR").is_ok() {
        return Err(KanbusError::IssueOperation(
            "local listing failed".to_string(),
        ));
    }
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
        let issues_dir = project_dir.join("issues");
        if !issues_dir.is_dir() {
            continue;
        }
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
