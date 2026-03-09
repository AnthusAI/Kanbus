//! Issue deletion workflow.

use std::collections::{HashMap, HashSet, VecDeque};
use std::path::Path;

use crate::error::KanbusError;
use crate::event_history::{delete_events_for_issues, events_dir_for_issue_path};
use crate::file_io::find_project_local_directory;
use crate::issue_files::write_issue_to_file;
use crate::issue_listing::load_issues_from_directory;
use crate::issue_lookup::load_issue_from_project;

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

/// Delete an issue file and all its event history from disk.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier.
///
/// # Errors
/// Returns `KanbusError` if deletion fails.
pub fn delete_issue(root: &Path, identifier: &str) -> Result<(), KanbusError> {
    let lookup = load_issue_from_project(root, identifier)?;
    let issue_id = lookup.issue.identifier.clone();
    let events_dir = events_dir_for_issue_path(&lookup.project_dir, &lookup.issue_path)?;

    std::fs::remove_file(&lookup.issue_path).map_err(|error| KanbusError::Io(error.to_string()))?;

    let mut ids = HashSet::new();
    ids.insert(issue_id.clone());
    if let Err(error) = delete_events_for_issues(&events_dir, &ids) {
        let _ = write_issue_to_file(&lookup.issue, &lookup.issue_path);
        return Err(error);
    }
    if lookup.issue_path.parent() == Some(lookup.project_dir.join("issues").as_path()) {
        crate::gossip::publish_issue_deleted(root, &lookup.project_dir, &issue_id, None);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use std::collections::BTreeMap;
    use std::fs;

    fn write_project_config(root: &Path) {
        fs::write(
            root.join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\n",
        )
        .expect("write config");
        fs::create_dir_all(root.join("project/issues")).expect("create project issues");
    }

    fn make_issue(id: &str, parent: Option<&str>) -> crate::models::IssueData {
        crate::models::IssueData {
            identifier: id.to_string(),
            title: format!("Issue {id}"),
            description: String::new(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: parent.map(std::string::ToString::to_string),
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    fn write_issue(path: &Path, id: &str, parent: Option<&str>) {
        let issue = make_issue(id, parent);
        fs::create_dir_all(path.parent().expect("issue parent")).expect("create issue parent");
        fs::write(path, serde_json::to_string_pretty(&issue).expect("serialize issue"))
            .expect("write issue");
    }

    fn write_event(path: &Path, issue_id: &str) {
        fs::create_dir_all(path.parent().expect("event parent")).expect("create event parent");
        let payload = serde_json::json!({
            "issue_id": issue_id,
            "event_id": format!("evt-{issue_id}"),
        });
        fs::write(path, serde_json::to_string_pretty(&payload).expect("serialize event"))
            .expect("write event");
    }

    #[test]
    fn get_descendant_identifiers_returns_leaf_first_across_shared_and_local() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        write_issue(
            &temp.path().join("project/issues/kanbus-parent.json"),
            "kanbus-parent",
            None,
        );
        write_issue(
            &temp.path().join("project/issues/kanbus-child.json"),
            "kanbus-child",
            Some("kanbus-parent"),
        );
        write_issue(
            &temp.path().join("project/issues/kanbus-grandchild.json"),
            "kanbus-grandchild",
            Some("kanbus-child"),
        );
        write_issue(
            &temp.path().join("project-local/issues/kanbus-local-child.json"),
            "kanbus-local-child",
            Some("kanbus-parent"),
        );

        let descendants =
            get_descendant_identifiers(&temp.path().join("project"), "kanbus-parent")
                .expect("descendants");
        assert_eq!(descendants.len(), 3);
        assert_eq!(descendants[0], "kanbus-grandchild");
        assert!(descendants.contains(&"kanbus-child".to_string()));
        assert!(descendants.contains(&"kanbus-local-child".to_string()));
    }

    #[test]
    fn delete_issue_removes_shared_issue_and_matching_events() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        let issue_path = temp.path().join("project/issues/kanbus-1.json");
        write_issue(&issue_path, "kanbus-1", None);

        let events_dir = temp.path().join("project/events");
        let delete_me = events_dir.join("2026-03-09T00:00:00Z-evt1.json");
        let keep_me = events_dir.join("2026-03-09T00:00:01Z-evt2.json");
        write_event(&delete_me, "kanbus-1");
        write_event(&keep_me, "kanbus-2");

        delete_issue(temp.path(), "kanbus-1").expect("delete shared issue");
        assert!(!issue_path.exists());
        assert!(!delete_me.exists());
        assert!(keep_me.exists());
    }

    #[test]
    fn delete_issue_removes_local_issue_and_local_events() {
        let temp = tempfile::tempdir().expect("tempdir");
        write_project_config(temp.path());
        let issue_path = temp.path().join("project-local/issues/kanbus-local.json");
        write_issue(&issue_path, "kanbus-local", None);

        let events_dir = temp.path().join("project-local/events");
        let delete_me = events_dir.join("2026-03-09T00:00:00Z-evt1.json");
        let keep_me = events_dir.join("2026-03-09T00:00:01Z-evt2.json");
        write_event(&delete_me, "kanbus-local");
        write_event(&keep_me, "kanbus-other");

        delete_issue(temp.path(), "kanbus-local").expect("delete local issue");
        assert!(!issue_path.exists());
        assert!(!delete_me.exists());
        assert!(keep_me.exists());
    }
}
