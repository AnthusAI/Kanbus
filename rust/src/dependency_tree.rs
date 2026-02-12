//! Dependency tree rendering utilities.

use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::Path;

use serde::Serialize;

use crate::error::TaskulusError;
use crate::file_io::load_project_directory;
use crate::issue_files::read_issue_from_file;
use crate::models::{DependencyLink, IssueData};

const MAX_TREE_NODES: usize = 25;

/// Dependency tree node.
#[derive(Debug, Clone, Serialize)]
pub struct DependencyTreeNode {
    #[serde(rename = "id")]
    pub identifier: String,
    pub title: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dependency_type: Option<String>,
    pub dependencies: Vec<DependencyTreeNode>,
}

/// Build a dependency tree for the given issue.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier to start from.
/// * `max_depth` - Optional maximum traversal depth.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if tree building fails.
pub fn build_dependency_tree(
    root: &Path,
    identifier: &str,
    max_depth: Option<usize>,
) -> Result<DependencyTreeNode, TaskulusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    let issues = load_issues(&issues_dir)?;
    let issue = issues
        .get(identifier)
        .ok_or_else(|| TaskulusError::IssueOperation("not found".to_string()))?;

    build_node(issue, &issues, max_depth, 0, &mut HashSet::new(), None)
}

/// Render a dependency tree in the requested format.
///
/// # Arguments
/// * `node` - Dependency tree root.
/// * `output_format` - Output format (text, json, dot).
/// * `max_nodes` - Maximum nodes to render for text output.
///
/// # Errors
/// Returns `TaskulusError::IssueOperation` if format is unsupported.
pub fn render_dependency_tree(
    node: &DependencyTreeNode,
    output_format: &str,
    max_nodes: Option<usize>,
) -> Result<String, TaskulusError> {
    match output_format {
        "json" => {
            serde_json::to_string_pretty(node).map_err(|error| TaskulusError::Io(error.to_string()))
        }
        "dot" => Ok(render_dot(node)),
        "text" => Ok(render_ascii(node, max_nodes.unwrap_or(MAX_TREE_NODES))),
        _ => Err(TaskulusError::IssueOperation("invalid format".to_string())),
    }
}

fn load_issues(issues_dir: &Path) -> Result<BTreeMap<String, IssueData>, TaskulusError> {
    let mut issues: BTreeMap<String, IssueData> = BTreeMap::new();
    for entry in fs::read_dir(issues_dir).map_err(|error| TaskulusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| TaskulusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let issue = read_issue_from_file(&path)?;
        issues.insert(issue.identifier.clone(), issue);
    }
    Ok(issues)
}

fn build_node(
    issue: &IssueData,
    issues: &BTreeMap<String, IssueData>,
    max_depth: Option<usize>,
    depth: usize,
    visited: &mut HashSet<String>,
    dependency_type: Option<String>,
) -> Result<DependencyTreeNode, TaskulusError> {
    if visited.contains(&issue.identifier) {
        return Ok(DependencyTreeNode {
            identifier: issue.identifier.clone(),
            title: issue.title.clone(),
            dependency_type,
            dependencies: Vec::new(),
        });
    }
    visited.insert(issue.identifier.clone());

    let mut dependencies = Vec::new();
    if max_depth.map_or(true, |limit| depth < limit) {
        for dependency in &issue.dependencies {
            dependencies.push(build_dependency(
                dependency,
                issues,
                max_depth,
                depth + 1,
                visited,
            )?);
        }
    }

    Ok(DependencyTreeNode {
        identifier: issue.identifier.clone(),
        title: issue.title.clone(),
        dependency_type,
        dependencies,
    })
}

fn build_dependency(
    dependency: &DependencyLink,
    issues: &BTreeMap<String, IssueData>,
    max_depth: Option<usize>,
    depth: usize,
    visited: &mut HashSet<String>,
) -> Result<DependencyTreeNode, TaskulusError> {
    let issue = issues.get(&dependency.target).ok_or_else(|| {
        TaskulusError::IssueOperation(format!(
            "dependency target '{}' does not exist",
            dependency.target
        ))
    })?;
    build_node(
        issue,
        issues,
        max_depth,
        depth,
        visited,
        Some(dependency.dependency_type.clone()),
    )
}

fn render_ascii(node: &DependencyTreeNode, max_nodes: usize) -> String {
    let mut lines: Vec<String> = Vec::new();
    let mut count = 0;
    let mut truncated = false;

    fn visit(
        current: &DependencyTreeNode,
        prefix: &str,
        is_last: bool,
        lines: &mut Vec<String>,
        count: &mut usize,
        truncated: &mut bool,
        max_nodes: usize,
    ) {
        if *count >= max_nodes {
            *truncated = true;
            return;
        }

        if prefix.is_empty() {
            lines.push(format!("{} {}", current.identifier, current.title));
        } else {
            let connector = if is_last { "`-- " } else { "|-- " };
            lines.push(format!(
                "{}{}{} {}",
                prefix, connector, current.identifier, current.title
            ));
        }
        *count += 1;

        if current.dependencies.is_empty() {
            return;
        }

        let child_prefix = format!("{}{}", prefix, if is_last { "    " } else { "|   " });
        let last_index = current.dependencies.len().saturating_sub(1);
        for (index, child) in current.dependencies.iter().enumerate() {
            visit(
                child,
                &child_prefix,
                index == last_index,
                lines,
                count,
                truncated,
                max_nodes,
            );
        }
    }

    visit(
        node,
        "",
        true,
        &mut lines,
        &mut count,
        &mut truncated,
        max_nodes,
    );
    if truncated {
        lines.push("additional nodes omitted".to_string());
    }
    lines.join("\n")
}

fn render_dot(node: &DependencyTreeNode) -> String {
    let mut edges: Vec<String> = Vec::new();

    fn visit(current: &DependencyTreeNode, edges: &mut Vec<String>) {
        for child in &current.dependencies {
            edges.push(format!(
                "  \"{}\" -> \"{}\";",
                current.identifier, child.identifier
            ));
            visit(child, edges);
        }
    }

    visit(node, &mut edges);
    let mut lines = Vec::new();
    lines.push("digraph dependencies {".to_string());
    lines.extend(edges);
    lines.push("}".to_string());
    lines.join("\n")
}
