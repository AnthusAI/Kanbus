use std::fs;
use std::path::PathBuf;
use std::time::SystemTime;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};
use tempfile::TempDir;

use kanbus::cache::{collect_issue_file_mtimes, load_cache_if_valid, write_cache};
use kanbus::cli::run_from_args_with_output;
use kanbus::daemon_paths::get_index_cache_path;
use kanbus::file_io::load_project_directory;
use kanbus::index::build_index_from_directory;
use kanbus::models::{DependencyLink, IssueData};

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn initialize_project(world: &mut KanbusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    std::process::Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
    let args = shell_words::split("kanbus init").expect("parse command");
    let cwd = world.working_directory.as_ref().expect("cwd");
    let _ = run_from_args_with_output(args, cwd.as_path()).expect("init");
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn build_issue(
    identifier: &str,
    title: &str,
    issue_type: &str,
    status: &str,
    parent: Option<&str>,
) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: "".to_string(),
        issue_type: issue_type.to_string(),
        status: status.to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: parent.map(str::to_string),
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    }
}

#[given("a Kanbus project with 5 issues of varying types and statuses")]
fn given_project_with_varied_issues(world: &mut KanbusWorld) {
    initialize_project(world);
    let project_dir = load_project_dir(world);
    let issues = vec![
        build_issue("kanbus-parent", "Parent", "epic", "open", None),
        build_issue("kanbus-child", "Child", "task", "open", Some("kanbus-parent")),
        build_issue("kanbus-closed", "Closed", "bug", "closed", None),
        build_issue("kanbus-deferred", "Deferred", "task", "deferred", None),
        build_issue("kanbus-other", "Other", "story", "open", None),
    ];
    for issue in issues {
        write_issue_file(&project_dir, &issue);
    }
}

#[when("the index is built")]
fn when_index_built(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issues_dir = project_dir.join("issues");
    let index = build_index_from_directory(&issues_dir).expect("build index");
    world.index = Some(index);
}

#[then("the index should contain 5 issues")]
fn then_index_contains_five(world: &mut KanbusWorld) {
    let index = world.index.as_ref().expect("index");
    assert_eq!(index.by_id.len(), 5);
}

#[then("querying by status \"open\" should return the correct issues")]
fn then_index_status_open(world: &mut KanbusWorld) {
    let index = world.index.as_ref().expect("index");
    let mut identifiers: Vec<String> = index
        .by_status
        .get("open")
        .unwrap_or(&Vec::new())
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect();
    identifiers.sort();
    assert_eq!(identifiers, vec!["kanbus-child", "kanbus-other", "kanbus-parent"]);
}

#[then("querying by type \"task\" should return the correct issues")]
fn then_index_type_task(world: &mut KanbusWorld) {
    let index = world.index.as_ref().expect("index");
    let mut identifiers: Vec<String> = index
        .by_type
        .get("task")
        .unwrap_or(&Vec::new())
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect();
    identifiers.sort();
    assert_eq!(identifiers, vec!["kanbus-child", "kanbus-deferred"]);
}

#[then("querying by parent should return the correct children")]
fn then_index_parent_children(world: &mut KanbusWorld) {
    let index = world.index.as_ref().expect("index");
    let children = index.by_parent.get("kanbus-parent").expect("children");
    let identifiers: Vec<String> = children
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect();
    assert_eq!(identifiers, vec!["kanbus-child"]);
}

#[given("issue \"kanbus-aaa\" exists with a blocked-by dependency on \"kanbus-bbb\"")]
fn given_issue_with_dependency(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let mut issue = build_issue("kanbus-aaa", "Title", "task", "open", None);
    issue.dependencies = vec![DependencyLink {
        target: "kanbus-bbb".to_string(),
        dependency_type: "blocked-by".to_string(),
    }];
    write_issue_file(&project_dir, &issue);
    write_issue_file(
        &project_dir,
        &build_issue("kanbus-bbb", "Target", "task", "open", None),
    );
}

#[then("the reverse dependency index should show \"kanbus-bbb\" blocks \"kanbus-aaa\"")]
fn then_reverse_dependency_index(world: &mut KanbusWorld) {
    let index = world.index.as_ref().expect("index");
    let dependents = index
        .reverse_dependencies
        .get("kanbus-bbb")
        .expect("dependents");
    let identifiers: Vec<String> = dependents
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect();
    assert_eq!(identifiers, vec!["kanbus-aaa"]);
}

#[given("a Kanbus project with issues but no cache file")]
fn given_project_with_no_cache(world: &mut KanbusWorld) {
    initialize_project(world);
    let project_dir = load_project_dir(world);
    write_issue_file(
        &project_dir,
        &build_issue("kanbus-cache", "Cache", "task", "open", None),
    );
    let cache_path =
        get_index_cache_path(world.working_directory.as_ref().expect("cwd")).expect("cache path");
    if cache_path.exists() {
        fs::remove_file(&cache_path).expect("remove cache");
    }
    world.cache_path = Some(cache_path);
}

#[given("the cache file is unreadable")]
fn given_cache_file_unreadable(world: &mut KanbusWorld) {
    let _project_dir = load_project_dir(world);
    let cache_path =
        get_index_cache_path(world.working_directory.as_ref().expect("cwd")).expect("cache path");
    if let Some(parent) = cache_path.parent() {
        fs::create_dir_all(parent).expect("create cache dir");
    }
    if cache_path.exists() {
        fs::remove_file(&cache_path).expect("remove cache file");
    }
    fs::create_dir_all(&cache_path).expect("create cache directory");
    world.cache_path = Some(cache_path);
}

#[given("a non-issue file exists in the issues directory")]
fn given_non_issue_file_exists(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let notes_path = project_dir.join("issues").join("notes.txt");
    fs::write(notes_path, "ignore").expect("write notes");
}

#[given("a non-issue file exists in the local issues directory")]
fn given_non_issue_file_exists_local(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let local_dir = project_dir
        .parent()
        .expect("project parent")
        .join("project-local")
        .join("issues");
    fs::create_dir_all(&local_dir).expect("create local issues");
    let notes_path = local_dir.join("notes.txt");
    fs::write(notes_path, "ignore").expect("write notes");
}

#[when("any kanbus command is run")]
fn when_any_command(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issues_dir = project_dir.join("issues");
    let cache_path =
        get_index_cache_path(world.working_directory.as_ref().expect("cwd")).expect("cache path");
    let cached = load_cache_if_valid(&cache_path, &issues_dir).expect("cache load");
    if cached.is_none() {
        let index = build_index_from_directory(&issues_dir).expect("build index");
        let mtimes = collect_issue_file_mtimes(&issues_dir).expect("mtimes");
        write_cache(&index, &cache_path, &mtimes).expect("write cache");
    }
}

#[then("a cache file should be created in project/.cache/index.json")]
fn then_cache_file_created(world: &mut KanbusWorld) {
    let cache_path = world.cache_path.as_ref().expect("cache path");
    assert!(cache_path.exists());
}

#[given("a Kanbus project with a valid cache")]
fn given_project_with_valid_cache(world: &mut KanbusWorld) {
    initialize_project(world);
    let project_dir = load_project_dir(world);
    write_issue_file(
        &project_dir,
        &build_issue("kanbus-cache", "Cache", "task", "open", None),
    );
    let cache_path =
        get_index_cache_path(world.working_directory.as_ref().expect("cwd")).expect("cache path");
    if cache_path.exists() {
        fs::remove_file(&cache_path).expect("remove cache");
    }
    let index = build_index_from_directory(&project_dir.join("issues")).expect("build index");
    let mtimes = collect_issue_file_mtimes(&project_dir.join("issues")).expect("mtimes");
    write_cache(&index, &cache_path, &mtimes).expect("write cache");
    let _ = load_cache_if_valid(&cache_path, &project_dir.join("issues")).expect("cache load");
    world.cache_path = Some(cache_path.clone());
    world.cache_mtime = Some(
        cache_path
            .metadata()
            .expect("meta")
            .modified()
            .expect("mtime"),
    );
}

#[then("the cache should be loaded without re-scanning issue files")]
fn then_cache_loaded(world: &mut KanbusWorld) {
    let cache_path = world.cache_path.as_ref().expect("cache path");
    let project_dir = load_project_dir(world);
    let cached = load_cache_if_valid(cache_path, &project_dir.join("issues")).expect("cache load");
    assert!(cached.is_some());
    let current = cache_path
        .metadata()
        .expect("meta")
        .modified()
        .expect("mtime");
    assert_eq!(Some(current), world.cache_mtime);
}

#[when("an issue file is modified (mtime changes)")]
fn when_issue_file_modified(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("kanbus-cache.json");
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    fs::write(&issue_path, contents.replace("Cache", "Cache updated")).expect("write issue");
    std::thread::sleep(std::time::Duration::from_millis(10));
}

#[then("the cache should be rebuilt from the issue files")]
fn then_cache_rebuilt(world: &mut KanbusWorld) {
    let cache_path = world.cache_path.as_ref().expect("cache path");
    let current = cache_path
        .metadata()
        .expect("meta")
        .modified()
        .expect("mtime");
    assert!(current > world.cache_mtime.unwrap_or(SystemTime::UNIX_EPOCH));
}

#[when("a new issue file appears in the issues directory")]
fn when_new_issue_file(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    write_issue_file(
        &project_dir,
        &build_issue("kanbus-cache-new", "New", "task", "open", None),
    );
    std::thread::sleep(std::time::Duration::from_millis(10));
}

#[then("the cache should be rebuilt")]
fn then_cache_rebuilt_generic(world: &mut KanbusWorld) {
    let cache_path = world.cache_path.as_ref().expect("cache path");
    let current = cache_path
        .metadata()
        .expect("meta")
        .modified()
        .expect("mtime");
    assert!(current > world.cache_mtime.unwrap_or(SystemTime::UNIX_EPOCH));
}

#[when("an issue file is removed from the issues directory")]
fn when_issue_file_removed(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("kanbus-cache.json");
    if issue_path.exists() {
        fs::remove_file(&issue_path).expect("remove issue");
    }
    std::thread::sleep(std::time::Duration::from_millis(10));
}

#[given("a Kanbus project with cacheable issue metadata")]
fn given_project_with_cacheable_metadata(world: &mut KanbusWorld) {
    initialize_project(world);
    let project_dir = load_project_dir(world);
    let mut parent = build_issue("kanbus-parent", "Parent", "epic", "open", None);
    parent.labels = vec!["core".to_string()];
    let child = build_issue("kanbus-child", "Child", "task", "open", Some("kanbus-parent"));
    let mut blocked = build_issue("kanbus-blocked", "Blocked", "task", "open", None);
    blocked.dependencies = vec![DependencyLink {
        target: "kanbus-parent".to_string(),
        dependency_type: "blocked-by".to_string(),
    }];
    write_issue_file(&project_dir, &parent);
    write_issue_file(&project_dir, &child);
    write_issue_file(&project_dir, &blocked);
    let cache_path =
        get_index_cache_path(world.working_directory.as_ref().expect("cwd")).expect("cache path");
    let index = build_index_from_directory(&project_dir.join("issues")).expect("build index");
    let mtimes = collect_issue_file_mtimes(&project_dir.join("issues")).expect("mtimes");
    write_cache(&index, &cache_path, &mtimes).expect("write cache");
    world.cache_path = Some(cache_path);
}

#[when("the cache is loaded")]
fn when_cache_loaded_from_disk(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let cache_path = world.cache_path.as_ref().expect("cache path");
    let cached = load_cache_if_valid(cache_path, &project_dir.join("issues"))
        .expect("cache load")
        .expect("cache present");
    world.index = Some(cached);
}

#[then("the cached index should include parent relationships")]
fn then_cached_index_parents(world: &mut KanbusWorld) {
    let index = world.index.as_ref().expect("index");
    let children = index.by_parent.get("kanbus-parent").expect("children");
    let identifiers: Vec<_> = children
        .iter()
        .map(|issue| issue.identifier.as_str())
        .collect();
    assert_eq!(identifiers, vec!["kanbus-child"]);
}

#[then("the cached index should include label indexes")]
fn then_cached_index_labels(world: &mut KanbusWorld) {
    let index = world.index.as_ref().expect("index");
    let labeled = index.by_label.get("core").expect("label index");
    let identifiers: Vec<_> = labeled
        .iter()
        .map(|issue| issue.identifier.as_str())
        .collect();
    assert_eq!(identifiers, vec!["kanbus-parent"]);
}

#[then("the cached index should include reverse dependencies")]
fn then_cached_index_reverse(world: &mut KanbusWorld) {
    let index = world.index.as_ref().expect("index");
    let dependents = index
        .reverse_dependencies
        .get("kanbus-parent")
        .expect("reverse deps");
    let identifiers: Vec<_> = dependents
        .iter()
        .map(|issue| issue.identifier.as_str())
        .collect();
    assert_eq!(identifiers, vec!["kanbus-blocked"]);
}
