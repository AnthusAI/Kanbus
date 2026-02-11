use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use chrono::{TimeZone, Utc};
use tempfile::tempdir;

use taskulus::index::build_index_from_directory;
use taskulus::models::{DependencyLink, IssueData};

fn write_issue_file(directory: &Path, issue: &IssueData) {
    let issue_path = directory.join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue file");
}

fn build_issue(
    identifier: &str,
    issue_type: &str,
    status: &str,
    parent: Option<&str>,
    labels: Vec<&str>,
    dependencies: Vec<DependencyLink>,
) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: format!("Title {}", identifier),
        description: "".to_string(),
        issue_type: issue_type.to_string(),
        status: status.to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: parent.map(str::to_string),
        labels: labels.into_iter().map(str::to_string).collect(),
        dependencies,
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: BTreeMap::new(),
    }
}

#[test]
fn build_index_populates_lookup_maps() {
    let directory = tempdir().expect("temp dir");
    let parent_issue = build_issue("tsk-parent", "epic", "open", None, vec!["planning"], vec![]);
    let child_one = build_issue(
        "tsk-child1",
        "task",
        "open",
        Some("tsk-parent"),
        vec!["implementation"],
        vec![],
    );
    let child_two = build_issue(
        "tsk-child2",
        "task",
        "in_progress",
        Some("tsk-parent"),
        vec![],
        vec![],
    );
    let bug_issue = build_issue(
        "tsk-bug01",
        "bug",
        "open",
        Some("tsk-parent"),
        vec![],
        vec![],
    );
    let story_issue = build_issue("tsk-story01", "story", "closed", None, vec![], vec![]);

    for issue in [parent_issue, child_one, child_two, bug_issue, story_issue] {
        write_issue_file(directory.path(), &issue);
    }

    let index = build_index_from_directory(directory.path()).expect("index");
    assert_eq!(index.by_id.len(), 5);
    assert_eq!(
        index
            .by_status
            .get("open")
            .expect("open issues")
            .iter()
            .map(|issue| issue.identifier.as_str())
            .collect::<Vec<_>>(),
        vec!["tsk-bug01", "tsk-child1", "tsk-parent"]
    );
    assert_eq!(
        index
            .by_type
            .get("task")
            .expect("task issues")
            .iter()
            .map(|issue| issue.identifier.as_str())
            .collect::<Vec<_>>(),
        vec!["tsk-child1", "tsk-child2"]
    );
    assert_eq!(
        index
            .by_parent
            .get("tsk-parent")
            .expect("children")
            .iter()
            .map(|issue| issue.identifier.as_str())
            .collect::<Vec<_>>(),
        vec!["tsk-bug01", "tsk-child1", "tsk-child2"]
    );
}

#[test]
fn build_index_tracks_reverse_dependencies() {
    let directory = tempdir().expect("temp dir");
    let blocked_by = DependencyLink {
        target: "tsk-bbb".to_string(),
        dependency_type: "blocked-by".to_string(),
    };
    let blocker = build_issue("tsk-bbb", "task", "open", None, vec![], vec![]);
    let dependent = build_issue("tsk-aaa", "task", "open", None, vec![], vec![blocked_by]);

    for issue in [blocker, dependent] {
        write_issue_file(directory.path(), &issue);
    }

    let index = build_index_from_directory(directory.path()).expect("index");
    assert_eq!(
        index
            .reverse_dependencies
            .get("tsk-bbb")
            .expect("reverse dependencies")
            .iter()
            .map(|issue| issue.identifier.as_str())
            .collect::<Vec<_>>(),
        vec!["tsk-aaa"]
    );
}
