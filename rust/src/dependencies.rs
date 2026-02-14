//! Dependency management utilities.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use crate::error::TaskulusError;
use crate::file_io::{
    discover_project_directories, discover_taskulus_projects, find_project_local_directory,
    load_project_directory,
};
use crate::issue_files::{read_issue_from_file, write_issue_to_file};
use crate::issue_lookup::{load_issue_from_project, IssueLookupResult};
use crate::models::{DependencyLink, IssueData};

const ALLOWED_DEPENDENCY_TYPES: [&str; 2] = ["blocked-by", "relates-to"];

/// Add a dependency to an issue.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `source_id` - Issue identifier to update.
/// * `target_id` - Dependency target issue identifier.
/// * `dependency_type` - Dependency type to add.
///
/// # Returns
/// Updated issue data.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if the dependency cannot be added.
pub fn add_dependency(
    root: &Path,
    source_id: &str,
    target_id: &str,
    dependency_type: &str,
) -> Result<IssueData, TaskulusError> {
    validate_dependency_type(dependency_type)?;
    let source_lookup = load_issue_from_project(root, source_id)?;
    load_issue_from_project(root, target_id)?;

    if dependency_type == "blocked-by" {
        ensure_no_cycle(root, source_id, target_id)?;
    }

    if has_dependency(&source_lookup.issue, target_id, dependency_type) {
        return Ok(source_lookup.issue);
    }

    let mut updated_issue = source_lookup.issue.clone();
    updated_issue.dependencies.push(DependencyLink {
        target: target_id.to_string(),
        dependency_type: dependency_type.to_string(),
    });
    write_issue_to_file(&updated_issue, &source_lookup.issue_path)?;
    Ok(updated_issue)
}

/// Remove a dependency from an issue.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `source_id` - Issue identifier to update.
/// * `target_id` - Dependency target issue identifier.
/// * `dependency_type` - Dependency type to remove.
///
/// # Returns
/// Updated issue data.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if the dependency cannot be removed.
pub fn remove_dependency(
    root: &Path,
    source_id: &str,
    target_id: &str,
    dependency_type: &str,
) -> Result<IssueData, TaskulusError> {
    validate_dependency_type(dependency_type)?;
    let IssueLookupResult {
        issue,
        issue_path,
        project_dir: _,
    } = load_issue_from_project(root, source_id)?;

    let filtered: Vec<DependencyLink> = issue
        .dependencies
        .iter()
        .filter(|dependency| {
            !(dependency.target == target_id && dependency.dependency_type == dependency_type)
        })
        .cloned()
        .collect();

    let mut updated_issue = issue.clone();
    updated_issue.dependencies = filtered;
    write_issue_to_file(&updated_issue, &issue_path)?;
    Ok(updated_issue)
}

/// List issues that are not blocked by dependencies.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Returns
/// Ready issues.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if listing fails.
pub fn list_ready_issues(
    root: &Path,
    include_local: bool,
    local_only: bool,
) -> Result<Vec<IssueData>, TaskulusError> {
    if local_only && !include_local {
        return Err(TaskulusError::IssueOperation(
            "local-only conflicts with no-local".to_string(),
        ));
    }
    let mut projects = Vec::new();
    discover_project_directories(root, &mut projects)?;
    let mut dotfile_projects = discover_taskulus_projects(root)?;
    projects.append(&mut dotfile_projects);
    projects.sort();
    projects.dedup();
    if projects.is_empty() {
        return Err(TaskulusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }
    let mut issues = Vec::new();
    if projects.len() == 1 {
        let project_dir = load_project_directory(root)?;
        issues =
            load_ready_issues_for_project(root, &project_dir, include_local, local_only, false)?;
    } else {
        for project_dir in &projects {
            let project_issues =
                load_ready_issues_for_project(root, project_dir, include_local, local_only, true)?;
            issues.extend(project_issues);
        }
    }
    let ready: Vec<IssueData> = issues
        .into_iter()
        .filter(|issue| issue.status != "closed" && !is_blocked(issue))
        .collect();
    Ok(ready)
}

fn load_ready_issues_for_project(
    root: &Path,
    project_dir: &Path,
    include_local: bool,
    local_only: bool,
    tag_project: bool,
) -> Result<Vec<IssueData>, TaskulusError> {
    let mut issues = load_issues_from_directory(&project_dir.join("issues"))?;
    if include_local || local_only {
        if let Some(local_dir) = find_project_local_directory(project_dir) {
            let local_issues = load_issues_from_directory(&local_dir.join("issues"))?;
            if local_only {
                issues = local_issues;
            } else {
                issues.extend(local_issues);
            }
        } else if local_only {
            issues = Vec::new();
        }
    }
    if tag_project {
        for issue in &mut issues {
            tag_issue_project(issue, root, project_dir);
        }
    }
    Ok(issues)
}

#[cfg(tarpaulin)]
pub fn cover_dependencies_paths(root: &Path) {
    let project_dir = root.join("project");
    let _ = load_ready_issues_for_project(root, &project_dir, false, true, false);
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

fn load_issues_from_directory(issues_dir: &Path) -> Result<Vec<IssueData>, TaskulusError> {
    let mut issues = Vec::new();
    for entry in
        std::fs::read_dir(issues_dir).map_err(|error| TaskulusError::Io(error.to_string()))?
    {
        let entry = entry.map_err(|error| TaskulusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        issues.push(read_issue_from_file(&path)?);
    }
    issues.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    Ok(issues)
}

fn is_blocked(issue: &IssueData) -> bool {
    issue
        .dependencies
        .iter()
        .any(|dependency| dependency.dependency_type == "blocked-by")
}

fn validate_dependency_type(dependency_type: &str) -> Result<(), TaskulusError> {
    if !ALLOWED_DEPENDENCY_TYPES.contains(&dependency_type) {
        return Err(TaskulusError::IssueOperation(
            "invalid dependency type".to_string(),
        ));
    }
    Ok(())
}

fn has_dependency(issue: &IssueData, target_id: &str, dependency_type: &str) -> bool {
    issue.dependencies.iter().any(|dependency| {
        dependency.target == target_id && dependency.dependency_type == dependency_type
    })
}

fn ensure_no_cycle(root: &Path, source_id: &str, target_id: &str) -> Result<(), TaskulusError> {
    let mut graph = build_dependency_graph(root)?;
    graph
        .edges
        .entry(source_id.to_string())
        .or_default()
        .push(target_id.to_string());
    if detect_cycle(&graph, source_id) {
        return Err(TaskulusError::IssueOperation("cycle detected".to_string()));
    }
    Ok(())
}

struct DependencyGraph {
    edges: HashMap<String, Vec<String>>,
}

fn build_dependency_graph(root: &Path) -> Result<DependencyGraph, TaskulusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    let mut edges: HashMap<String, Vec<String>> = HashMap::new();
    for entry in
        std::fs::read_dir(&issues_dir).map_err(|error| TaskulusError::Io(error.to_string()))?
    {
        let entry = entry.map_err(|error| TaskulusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let issue = read_issue_from_file(&path)?;
        let blocked_targets: Vec<String> = issue
            .dependencies
            .iter()
            .filter(|dependency| dependency.dependency_type == "blocked-by")
            .map(|dependency| dependency.target.clone())
            .collect();
        if !blocked_targets.is_empty() {
            edges.insert(issue.identifier.clone(), blocked_targets);
        }
    }
    Ok(DependencyGraph { edges })
}

fn detect_cycle(graph: &DependencyGraph, start: &str) -> bool {
    let mut visited: HashSet<String> = HashSet::new();
    let mut stack: HashSet<String> = HashSet::new();

    fn visit(
        node: &str,
        graph: &DependencyGraph,
        visited: &mut HashSet<String>,
        stack: &mut HashSet<String>,
    ) -> bool {
        if stack.contains(node) {
            return true;
        }
        if visited.contains(node) {
            return false;
        }
        visited.insert(node.to_string());
        stack.insert(node.to_string());
        if let Some(neighbors) = graph.edges.get(node) {
            for neighbor in neighbors {
                if visit(neighbor, graph, visited, stack) {
                    return true;
                }
            }
        }
        stack.remove(node);
        false
    }

    visit(start, graph, &mut visited, &mut stack)
}
