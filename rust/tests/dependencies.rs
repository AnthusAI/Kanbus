use std::fs;
use std::process::Command;

use chrono::{TimeZone, Utc};
use tempfile::TempDir;

use taskulus::dependencies::{add_dependency, list_ready_issues, remove_dependency};
use taskulus::error::TaskulusError;
use taskulus::file_io::initialize_project;
use taskulus::issue_files::write_issue_to_file;
use taskulus::models::{DependencyLink, IssueData};

fn init_repo(root: &std::path::Path) {
    Command::new("git")
        .args(["init"])
        .current_dir(root)
        .output()
        .expect("git init failed");
}

fn write_issue(project_dir: &std::path::Path, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    write_issue_to_file(issue, &issue_path).expect("write issue");
}

fn make_issue(identifier: &str) -> IssueData {
    let now = Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: "Title".to_string(),
        description: "".to_string(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    }
}

#[test]
fn add_dependency_rejects_invalid_type() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    init_repo(&repo_path);
    initialize_project(&repo_path, "project").expect("init");

    let error = add_dependency(&repo_path, "tsk-1", "tsk-2", "invalid").unwrap_err();
    assert_eq!(error.to_string(), "invalid dependency type");
}

#[test]
fn add_dependency_rejects_missing_issue() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    init_repo(&repo_path);
    initialize_project(&repo_path, "project").expect("init");

    let error = add_dependency(&repo_path, "tsk-1", "tsk-2", "blocked-by").unwrap_err();
    assert_eq!(error.to_string(), "not found");
}

#[test]
fn add_dependency_writes_link() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    init_repo(&repo_path);
    initialize_project(&repo_path, "project").expect("init");
    let project_dir = repo_path.join("project");

    let issue = make_issue("tsk-1");
    let other = make_issue("tsk-2");
    write_issue(&project_dir, &issue);
    write_issue(&project_dir, &other);

    let updated = add_dependency(&repo_path, "tsk-1", "tsk-2", "blocked-by").expect("add");
    assert_eq!(updated.dependencies.len(), 1);
    assert_eq!(updated.dependencies[0].target, "tsk-2");
    assert_eq!(updated.dependencies[0].dependency_type, "blocked-by");
}

#[test]
fn add_dependency_detects_cycle() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    init_repo(&repo_path);
    initialize_project(&repo_path, "project").expect("init");
    let project_dir = repo_path.join("project");

    let mut issue_a = make_issue("tsk-a");
    issue_a.dependencies.push(DependencyLink {
        target: "tsk-b".to_string(),
        dependency_type: "blocked-by".to_string(),
    });
    let issue_b = make_issue("tsk-b");
    write_issue(&project_dir, &issue_a);
    write_issue(&project_dir, &issue_b);

    let error = add_dependency(&repo_path, "tsk-b", "tsk-a", "blocked-by").unwrap_err();
    assert_eq!(error.to_string(), "cycle detected");
}

#[test]
fn remove_dependency_removes_existing_link() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    init_repo(&repo_path);
    initialize_project(&repo_path, "project").expect("init");
    let project_dir = repo_path.join("project");

    let mut issue = make_issue("tsk-1");
    issue.dependencies.push(DependencyLink {
        target: "tsk-2".to_string(),
        dependency_type: "blocked-by".to_string(),
    });
    let other = make_issue("tsk-2");
    write_issue(&project_dir, &issue);
    write_issue(&project_dir, &other);

    let updated = remove_dependency(&repo_path, "tsk-1", "tsk-2", "blocked-by").expect("remove");
    assert!(updated.dependencies.is_empty());
}

#[test]
fn remove_dependency_noops_when_missing_link() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    init_repo(&repo_path);
    initialize_project(&repo_path, "project").expect("init");
    let project_dir = repo_path.join("project");

    let issue = make_issue("tsk-1");
    let other = make_issue("tsk-2");
    write_issue(&project_dir, &issue);
    write_issue(&project_dir, &other);

    let updated = remove_dependency(&repo_path, "tsk-1", "tsk-2", "blocked-by").expect("remove");
    assert!(updated.dependencies.is_empty());
}

#[test]
fn list_ready_issues_filters_blocked() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    init_repo(&repo_path);
    initialize_project(&repo_path, "project").expect("init");
    let project_dir = repo_path.join("project");

    let ready_issue = make_issue("tsk-ready");
    let mut blocked_issue = make_issue("tsk-blocked");
    blocked_issue.dependencies.push(DependencyLink {
        target: "tsk-ready".to_string(),
        dependency_type: "blocked-by".to_string(),
    });
    write_issue(&project_dir, &ready_issue);
    write_issue(&project_dir, &blocked_issue);

    let ready = list_ready_issues(&repo_path).expect("ready");
    let identifiers: Vec<String> = ready.into_iter().map(|issue| issue.identifier).collect();
    assert!(identifiers.contains(&"tsk-ready".to_string()));
    assert!(!identifiers.contains(&"tsk-blocked".to_string()));
}

#[test]
fn list_ready_issues_excludes_closed() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    init_repo(&repo_path);
    initialize_project(&repo_path, "project").expect("init");
    let project_dir = repo_path.join("project");

    let mut closed_issue = make_issue("tsk-closed");
    closed_issue.status = "closed".to_string();
    let ready_issue = make_issue("tsk-ready");
    write_issue(&project_dir, &closed_issue);
    write_issue(&project_dir, &ready_issue);

    let ready = list_ready_issues(&repo_path).expect("ready");
    let identifiers: Vec<String> = ready.into_iter().map(|issue| issue.identifier).collect();
    assert!(identifiers.contains(&"tsk-ready".to_string()));
    assert!(!identifiers.contains(&"tsk-closed".to_string()));
}

#[test]
fn list_ready_issues_requires_project_marker() {
    let temp_dir = TempDir::new().expect("temp dir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo");
    init_repo(&repo_path);

    let error = list_ready_issues(&repo_path).unwrap_err();
    match error {
        TaskulusError::IssueOperation(message) => {
            assert_eq!(message, "project not initialized")
        }
        _ => panic!("unexpected error"),
    }
}
