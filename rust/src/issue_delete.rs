//! Issue deletion workflow.

use std::collections::{HashMap, VecDeque};
use std::path::Path;

use crate::error::KanbusError;
use crate::file_io::find_project_local_directory;
use crate::issue_listing::load_issues_from_directory;
use crate::issue_lookup::load_issue_from_project;
use crate::issue_mutation::persist_issue_deletion;
use crate::users::get_current_user;

/// Return descendant issue identifiers in leaf-first order (children before parents).
///
/// # Arguments
/// * `project_dir` - Shared project directory.
/// * `identifier` - Root issue identifier.
///
/// # Returns
/// List of descendant IDs, deepest first.
pub fn get_descendant_identifiers(
    project_dir: &Path,
    identifier: &str,
) -> Result<Vec<String>, KanbusError> {
    let mut parent_to_children: HashMap<String, Vec<String>> = HashMap::new();
    let issues_dir = project_dir.join("issues");
    if issues_dir.is_dir() {
        for issue in load_issues_from_directory(&issues_dir)? {
            if let Some(parent) = &issue.parent {
                parent_to_children
                    .entry(parent.clone())
                    .or_default()
                    .push(issue.identifier.clone());
            }
        }
    }
    if let Some(local_dir) = find_project_local_directory(project_dir) {
        let local_issues_dir = local_dir.join("issues");
        if local_issues_dir.is_dir() {
            for issue in load_issues_from_directory(&local_issues_dir)? {
                if let Some(parent) = &issue.parent {
                    parent_to_children
                        .entry(parent.clone())
                        .or_default()
                        .push(issue.identifier.clone());
                }
            }
        }
    }
    let mut depth: HashMap<String, usize> = HashMap::new();
    depth.insert(identifier.to_string(), 0);
    let mut queue = VecDeque::new();
    queue.push_back(identifier.to_string());
    while let Some(parent_id) = queue.pop_front() {
        let d = *depth.get(&parent_id).unwrap_or(&0);
        for child_id in parent_to_children
            .get(&parent_id)
            .cloned()
            .unwrap_or_default()
        {
            if !depth.contains_key(&child_id) {
                depth.insert(child_id.clone(), d + 1);
                queue.push_back(child_id);
            }
        }
    }
    let mut descendants: Vec<(String, usize)> =
        depth.into_iter().filter(|(k, _)| k != identifier).collect();
    descendants.sort_by_key(|(_, d)| std::cmp::Reverse(*d));
    Ok(descendants.into_iter().map(|(id, _)| id).collect())
}

/// Delete an issue file and its event history from disk.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
/// * `retain_audit_event` - Whether to keep a final issue_deleted event.
///
/// # Errors
/// Returns `KanbusError` if deletion fails.
pub fn delete_issue(
    root: &Path,
    identifier: &str,
    retain_audit_event: bool,
) -> Result<(), KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let issue_id = lookup.issue.identifier.clone();
    let actor_id = get_current_user();
    let result = persist_issue_deletion(
        root,
        &lookup.project_dir,
        &lookup.issue_path,
        &lookup.issue,
        &actor_id,
        retain_audit_event,
        true,
    )?;
    if lookup.issue_path.parent() == Some(lookup.project_dir.join("issues").as_path()) {
        let event_id = result.event.as_ref().map(|event| event.event_id.clone());
        crate::gossip::publish_issue_deleted(root, &lookup.project_dir, &issue_id, event_id);
    }
    Ok(())
}
