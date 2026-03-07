use chrono::Utc;
use kanbus::console_backend::FileStore;
use kanbus::console_wiki::{
    create_page, delete_page, get_page, list_pages, render_page, rename_page, update_page,
    WikiCreateRequest, WikiRenameRequest, WikiRenderRequestPayload, WikiUpdateRequest,
};
use kanbus::issue_files::write_issue_to_file;
use kanbus::models::{DependencyLink, IssueData};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::PathBuf;

fn temp_store() -> (tempfile::TempDir, FileStore) {
    let dir = tempfile::tempdir().expect("tempdir");
    let store = FileStore::new(dir.path());
    (dir, store)
}

fn write_config(dir: &PathBuf) {
    let contents = r#"
project_directory: project
project_key: kanbus
hierarchy: [initiative, epic, task, sub-task]
types: [bug, story, chore]
workflows:
  default:
    open: [in_progress, closed, backlog]
    in_progress: [open, blocked, closed]
    blocked: [in_progress, closed]
    closed: [open]
    backlog: [open, closed]
transition_labels:
  default:
    open:
      in_progress: "Start work"
      closed: "Close"
      backlog: "Backlog"
    in_progress:
      open: "Reopen"
      blocked: "Block"
      closed: "Close"
    blocked:
      in_progress: "Unblock"
      closed: "Close"
    closed:
      open: "Reopen"
    backlog:
      open: "Start"
      closed: "Close"
initial_status: open
priorities:
  0: { name: critical }
  1: { name: high }
  2: { name: medium }
  3: { name: low }
  4: { name: trivial }
default_priority: 2
statuses:
  - { key: open, name: Open, category: todo }
  - { key: in_progress, name: In Progress, category: doing }
  - { key: blocked, name: Blocked, category: todo }
  - { key: closed, name: Closed, category: done }
  - { key: backlog, name: Backlog, category: todo }
categories:
  - { name: todo }
  - { name: doing }
  - { name: done }
type_colors: {}
beads_compatibility: false
"#;
    fs::write(dir.join(".kanbus.yml"), contents).expect("write config");
    env::set_var("KANBUS_NO_DAEMON", "1");
    let project_dir = dir.join("project");
    let issues_dir = project_dir.join("issues");
    fs::create_dir_all(&issues_dir).expect("create issues dir");
    let issue = IssueData {
        identifier: "kanbus-1".to_string(),
        title: "Seed issue".to_string(),
        description: "Seed".to_string(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: vec![],
        dependencies: vec![DependencyLink {
            target: "kanbus-2".to_string(),
            dependency_type: "blocks".to_string(),
        }],
        comments: vec![],
        created_at: Utc::now(),
        updated_at: Utc::now(),
        closed_at: None,
        custom: BTreeMap::new(),
    };
    write_issue_to_file(&issue, &issues_dir.join("kanbus-1.json")).expect("write issue");
}

#[test]
fn wiki_path_accepts_nested_md() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let request = WikiCreateRequest {
        path: "docs/notes.md".to_string(),
        content: Some("# notes".to_string()),
        overwrite: None,
    };
    let result = create_page(&store, &request).expect("create page");
    assert_eq!(result.path, "docs/notes.md");
}

#[test]
fn wiki_path_rejects_traversal() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let request = WikiCreateRequest {
        path: "../outside.md".to_string(),
        content: Some("# nope".to_string()),
        overwrite: None,
    };
    let result = create_page(&store, &request);
    assert!(result.is_err());
}

#[test]
fn wiki_path_rejects_non_markdown() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let request = WikiCreateRequest {
        path: "docs/readme.txt".to_string(),
        content: Some("text".to_string()),
        overwrite: None,
    };
    let result = create_page(&store, &request);
    assert!(result.is_err());
}

#[test]
fn wiki_create_conflict_without_overwrite() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let request = WikiCreateRequest {
        path: "index.md".to_string(),
        content: Some("# a".to_string()),
        overwrite: None,
    };
    create_page(&store, &request).expect("first create");
    let second = create_page(&store, &request);
    assert!(second.is_err());
}

#[test]
fn wiki_create_overwrite_allowed() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let mut request = WikiCreateRequest {
        path: "index.md".to_string(),
        content: Some("# a".to_string()),
        overwrite: Some(false),
    };
    create_page(&store, &request).expect("first create");
    request.content = Some("# b".to_string());
    request.overwrite = Some(true);
    create_page(&store, &request).expect("overwrite create");
    let page = get_page(&store, "index.md").expect("get page");
    assert_eq!(page.content, "# b");
}

#[test]
fn wiki_update_missing_returns_not_found() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let request = WikiUpdateRequest {
        path: "missing.md".to_string(),
        content: "x".to_string(),
    };
    let result = update_page(&store, &request);
    assert!(result.is_err());
}

#[test]
fn wiki_rename_conflict_without_overwrite() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let request = WikiCreateRequest {
        path: "a.md".to_string(),
        content: Some("# a".to_string()),
        overwrite: None,
    };
    create_page(&store, &request).expect("create a");
    let request_b = WikiCreateRequest {
        path: "b.md".to_string(),
        content: Some("# b".to_string()),
        overwrite: None,
    };
    create_page(&store, &request_b).expect("create b");
    let rename = WikiRenameRequest {
        from_path: "a.md".to_string(),
        to_path: "b.md".to_string(),
        overwrite: Some(false),
    };
    let result = rename_page(&store, &rename);
    assert!(result.is_err());
}

#[test]
fn wiki_delete_missing_returns_not_found() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let result = delete_page(&store, "missing.md");
    assert!(result.is_err());
}

#[test]
fn wiki_list_pages_only_markdown() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let wiki_root = store.root().join("project/wiki");
    fs::create_dir_all(&wiki_root).expect("create wiki");
    fs::write(wiki_root.join("a.md"), "a").expect("write a");
    fs::write(wiki_root.join("b.txt"), "b").expect("write b");
    let list = list_pages(&store).expect("list pages");
    assert_eq!(list.pages, vec!["a.md"]);
}

#[test]
fn wiki_render_draft_success() {
    let (_dir, store) = temp_store();
    write_config(&store.root().to_path_buf());
    let create = WikiCreateRequest {
        path: "index.md".to_string(),
        content: Some("Open: {{ count(status=\"open\") }}".to_string()),
        overwrite: None,
    };
    create_page(&store, &create).expect("create page");
    let render = WikiRenderRequestPayload {
        path: "index.md".to_string(),
        content: Some("Open: {{ count(status=\"open\") }}".to_string()),
    };
    let result = render_page(&store, &render).expect("render");
    assert!(result.rendered_markdown.contains("Open: "));
}
