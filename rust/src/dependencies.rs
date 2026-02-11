//! Dependency management utilities.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use crate::error::TaskulusError;
use crate::file_io::load_project_directory;
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
    let IssueLookupResult { issue, issue_path } = load_issue_from_project(root, source_id)?;

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
pub fn list_ready_issues(root: &Path) -> Result<Vec<IssueData>, TaskulusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    let mut issues = Vec::new();
    for entry in
        std::fs::read_dir(&issues_dir).map_err(|error| TaskulusError::Io(error.to_string()))?
    {
        let entry = entry.map_err(|error| TaskulusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        issues.push(read_issue_from_file(&path)?);
    }
    issues.sort_by(|left, right| left.identifier.cmp(&right.identifier));

    let ready: Vec<IssueData> = issues
        .into_iter()
        .filter(|issue| issue.status != "closed" && !is_blocked(issue))
        .collect();
    Ok(ready)
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
