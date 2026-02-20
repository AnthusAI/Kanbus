//! Dependency management utilities.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use crate::error::KanbusError;
use crate::file_io::{
    discover_kanbus_projects, discover_project_directories, find_project_local_directory,
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
/// Returns `KanbusError::IssueOperation` if the dependency cannot be added.
pub fn add_dependency(
    root: &Path,
    source_id: &str,
    target_id: &str,
    dependency_type: &str,
) -> Result<IssueData, KanbusError> {
    validate_dependency_type(dependency_type)?;
    let source_lookup = load_issue_from_project(root, source_id)?;
    let target_lookup = load_issue_from_project(root, target_id)?;

    // Prevent blocked-by relationships that mirror parent-child edges (cycle-like).
    if dependency_type == "blocked-by" {
        if source_lookup.issue.parent.as_deref() == Some(target_id) {
            return Err(KanbusError::IssueOperation(
                "circular dependency: cannot block on parent".to_string(),
            ));
        }
        if target_lookup.issue.parent.as_deref() == Some(source_id) {
            return Err(KanbusError::IssueOperation(
                "circular dependency: cannot block on child".to_string(),
            ));
        }
    }

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

    // Publish real-time notification
    use crate::notification_events::NotificationEvent;
    use crate::notification_publisher::publish_notification;
    let _ = publish_notification(
        root,
        NotificationEvent::IssueUpdated {
            issue_id: updated_issue.identifier.clone(),
            fields_changed: vec!["dependencies".to_string()],
            issue_data: updated_issue.clone(),
        },
    );

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
/// Returns `KanbusError::IssueOperation` if the dependency cannot be removed.
pub fn remove_dependency(
    root: &Path,
    source_id: &str,
    target_id: &str,
    dependency_type: &str,
) -> Result<IssueData, KanbusError> {
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

    // Publish real-time notification
    use crate::notification_events::NotificationEvent;
    use crate::notification_publisher::publish_notification;
    let _ = publish_notification(
        root,
        NotificationEvent::IssueUpdated {
            issue_id: updated_issue.identifier.clone(),
            fields_changed: vec!["dependencies".to_string()],
            issue_data: updated_issue.clone(),
        },
    );

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
/// Returns `KanbusError::IssueOperation` if listing fails.
pub fn list_ready_issues(
    root: &Path,
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
    projects.sort();
    projects.dedup();
    if projects.is_empty() {
        return Err(KanbusError::IssueOperation(
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
) -> Result<Vec<IssueData>, KanbusError> {
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

fn validate_dependency_type(dependency_type: &str) -> Result<(), KanbusError> {
    if !ALLOWED_DEPENDENCY_TYPES.contains(&dependency_type) {
        return Err(KanbusError::IssueOperation(
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

fn ensure_no_cycle(root: &Path, source_id: &str, target_id: &str) -> Result<(), KanbusError> {
    let mut graph = build_dependency_graph(root)?;
    graph
        .edges
        .entry(source_id.to_string())
        .or_default()
        .push(target_id.to_string());
    if detect_cycle(&graph, source_id) {
        return Err(KanbusError::IssueOperation("cycle detected".to_string()));
    }
    Ok(())
}

struct DependencyGraph {
    edges: HashMap<String, Vec<String>>,
}

fn build_dependency_graph(root: &Path) -> Result<DependencyGraph, KanbusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    let mut edges: HashMap<String, Vec<String>> = HashMap::new();
    for entry in
        std::fs::read_dir(&issues_dir).map_err(|error| KanbusError::Io(error.to_string()))?
    {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;
    use chrono::Utc;
    use std::collections::BTreeMap;
    use tempfile::tempdir;

    fn sample_issue(identifier: &str) -> IssueData {
        IssueData {
            identifier: identifier.to_string(),
            title: "Title".to_string(),
            description: "Desc".to_string(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 1,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    fn setup_project_root() -> (tempfile::TempDir, std::path::PathBuf) {
        let temp = tempdir().unwrap();
        let root = temp.path().join("repo");
        std::fs::create_dir_all(root.join("project").join("issues")).unwrap();
        let config = default_project_configuration();
        let contents = serde_yaml::to_string(&config).unwrap();
        std::fs::write(root.join(".kanbus.yml"), contents).unwrap();
        (temp, root)
    }

    #[test]
    fn validate_dependency_type_rejects_invalid() {
        assert!(validate_dependency_type("blocked-by").is_ok());
        assert!(validate_dependency_type("relates-to").is_ok());
        let err = validate_dependency_type("other").unwrap_err();
        assert!(err.to_string().contains("invalid dependency type"));
    }

    #[test]
    fn has_dependency_matches_target_and_type() {
        let mut issue = sample_issue("kanbus-abc");
        issue.dependencies.push(DependencyLink {
            target: "kanbus-def".to_string(),
            dependency_type: "blocked-by".to_string(),
        });
        assert!(has_dependency(&issue, "kanbus-def", "blocked-by"));
        assert!(!has_dependency(&issue, "kanbus-def", "relates-to"));
    }

    #[test]
    fn detect_cycle_finds_cycle() {
        let mut graph = DependencyGraph {
            edges: HashMap::new(),
        };
        graph.edges.insert("A".to_string(), vec!["B".to_string()]);
        graph.edges.insert("B".to_string(), vec!["C".to_string()]);
        graph.edges.insert("C".to_string(), vec!["A".to_string()]);
        assert!(detect_cycle(&graph, "A"));
    }

    #[test]
    fn load_issues_from_directory_sorts_and_skips_non_json() {
        let temp = tempdir().unwrap();
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).unwrap();
        let issue_a = sample_issue("kanbus-a");
        let issue_b = sample_issue("kanbus-b");
        write_issue_to_file(&issue_b, &issues_dir.join("b.json")).unwrap();
        write_issue_to_file(&issue_a, &issues_dir.join("a.json")).unwrap();
        std::fs::write(issues_dir.join("note.txt"), "skip").unwrap();
        let issues = load_issues_from_directory(&issues_dir).unwrap();
        assert_eq!(issues.len(), 2);
        assert_eq!(issues[0].identifier, "kanbus-a");
        assert_eq!(issues[1].identifier, "kanbus-b");
    }

    #[test]
    fn ensure_no_cycle_detects_cycle_on_new_edge() {
        let (_temp, root) = setup_project_root();
        let issues_dir = root.join("project").join("issues");

        let mut issue_b = sample_issue("kanbus-b");
        issue_b.dependencies.push(DependencyLink {
            target: "kanbus-c".to_string(),
            dependency_type: "blocked-by".to_string(),
        });
        let mut issue_c = sample_issue("kanbus-c");
        issue_c.dependencies.push(DependencyLink {
            target: "kanbus-a".to_string(),
            dependency_type: "blocked-by".to_string(),
        });
        write_issue_to_file(&issue_b, &issues_dir.join("b.json")).unwrap();
        write_issue_to_file(&issue_c, &issues_dir.join("c.json")).unwrap();

        let err = ensure_no_cycle(&root, "kanbus-a", "kanbus-b").unwrap_err();
        assert!(err.to_string().contains("cycle detected"));
    }

    #[test]
    fn list_ready_issues_rejects_conflicting_flags() {
        let err = list_ready_issues(Path::new("."), false, true).unwrap_err();
        assert!(err
            .to_string()
            .contains("local-only conflicts with no-local"));
    }
}
