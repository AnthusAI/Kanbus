use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;
use serde_yaml::{Mapping, Value as YamlValue};

use crate::step_definitions::command_steps::run_cli_command_with_stdin as run_command_with_standard_input;
use crate::step_definitions::initialization_steps::{
    run_from_args_in_blocking_thread, KanbusWorld,
};

#[derive(Debug, Clone)]
pub struct VirtualProject {
    #[allow(dead_code)]
    pub label: String,
    pub shared_dir: PathBuf,
    pub local_dir: PathBuf,
    pub events_dir: PathBuf,
}

#[derive(Debug, Clone)]
pub struct VirtualProjectState {
    pub root: PathBuf,
    pub current_label: String,
    pub current_project_dir: PathBuf,
    pub current_local_dir: PathBuf,
    pub virtual_projects: BTreeMap<String, VirtualProject>,
    pub pending_interactive_command: Option<String>,
    pub issue_snapshots: BTreeMap<PathBuf, String>,
}

fn create_repo(world: &mut KanbusWorld) -> PathBuf {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path.clone());
    world.temp_dir = Some(temp_dir);
    repo_path
}

fn initialize_virtual_repo(world: &mut KanbusWorld) -> VirtualProjectState {
    let root = create_repo(world);
    run_from_args_in_blocking_thread(vec!["kanbus".to_string(), "init".to_string()], &root)
        .expect("kanbus init");
    let config_path = root.join(".kanbus.yml");
    let mut mapping: Mapping =
        serde_yaml::from_str(&fs::read_to_string(&config_path).expect("read config"))
            .expect("parse config");
    mapping.insert(
        YamlValue::String("project_key".to_string()),
        YamlValue::String("kbs".to_string()),
    );
    fs::write(
        &config_path,
        serde_yaml::to_string(&mapping).expect("serialize config"),
    )
    .expect("write config");
    let shared_dir = root.join("project");
    let local_dir = root.join("project-local");
    fs::create_dir_all(local_dir.join("issues")).expect("create local issues dir");
    fs::create_dir_all(local_dir.join("events")).expect("create local events dir");
    VirtualProjectState {
        root,
        current_label: "kbs".to_string(),
        current_project_dir: shared_dir,
        current_local_dir: local_dir,
        virtual_projects: BTreeMap::new(),
        pending_interactive_command: None,
        issue_snapshots: BTreeMap::new(),
    }
}

fn ensure_virtual_state(world: &mut KanbusWorld) -> &mut VirtualProjectState {
    if world.virtual_project_state.is_none() {
        let state = initialize_virtual_repo(world);
        world.virtual_project_state = Some(state);
    }
    world
        .virtual_project_state
        .as_mut()
        .expect("virtual project state")
}

fn add_virtual_project_if_missing(state: &mut VirtualProjectState, label: &str) {
    if state.virtual_projects.contains_key(label) {
        return;
    }
    let base = state.root.join("virtual").join(label);
    let shared_dir = base.join("project");
    let local_dir = base.join("project-local");
    fs::create_dir_all(shared_dir.join("issues")).expect("create virtual issues");
    fs::create_dir_all(shared_dir.join("events")).expect("create virtual events");
    fs::create_dir_all(local_dir.join("issues")).expect("create virtual local issues");
    fs::create_dir_all(local_dir.join("events")).expect("create virtual local events");
    state.virtual_projects.insert(
        label.to_string(),
        VirtualProject {
            label: label.to_string(),
            shared_dir: shared_dir.clone(),
            local_dir,
            events_dir: shared_dir.join("events"),
        },
    );
}

fn configure_virtual_projects<'a>(
    world: &'a mut KanbusWorld,
    labels: Vec<&str>,
) -> &'a mut VirtualProjectState {
    let state = ensure_virtual_state(world);
    for label in labels {
        add_virtual_project_if_missing(state, label);
    }
    write_virtual_projects_configuration(state);
    state
}

fn adopt_existing_repository_for_virtual_projects(
    world: &mut KanbusWorld,
) -> &mut VirtualProjectState {
    let root = world.working_directory.clone().expect("working directory");
    let current_project_dir = load_project_directory(&root).expect("project dir");
    let current_local_dir = root.join("project-local");
    fs::create_dir_all(current_local_dir.join("issues")).expect("create local issues");
    fs::create_dir_all(current_local_dir.join("events")).expect("create local events");
    let state = VirtualProjectState {
        root,
        current_label: "kbs".to_string(),
        current_project_dir,
        current_local_dir,
        virtual_projects: BTreeMap::new(),
        pending_interactive_command: None,
        issue_snapshots: BTreeMap::new(),
    };
    world.virtual_project_state = Some(state);
    world
        .virtual_project_state
        .as_mut()
        .expect("virtual project state")
}

fn set_primary_configuration_value(state: &VirtualProjectState, key: &str, value: YamlValue) {
    let config_path = state.root.join(".kanbus.yml");
    let mut mapping: Mapping =
        serde_yaml::from_str(&fs::read_to_string(&config_path).expect("read config"))
            .expect("parse config");
    mapping.insert(YamlValue::String(key.to_string()), value);
    fs::write(
        config_path,
        serde_yaml::to_string(&mapping).expect("serialize config"),
    )
    .expect("write config");
}

fn remember_issue_snapshot(state: &mut VirtualProjectState, project_dir: &Path, identifier: &str) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue snapshot");
    state.issue_snapshots.insert(issue_path, contents);
}

fn assert_issue_changed_since_snapshot(state: &VirtualProjectState, project_dir: &Path) {
    let changed = state.issue_snapshots.iter().any(|(path, original)| {
        path.starts_with(project_dir)
            && fs::read_to_string(path)
                .map(|current| &current != original)
                .unwrap_or(false)
    });
    assert!(
        changed,
        "no issue file under {} changed since it was created",
        project_dir.display()
    );
}

fn write_virtual_projects_configuration(state: &VirtualProjectState) {
    let config_path = state.root.join(".kanbus.yml");
    let mut mapping: Mapping =
        serde_yaml::from_str(&fs::read_to_string(&config_path).expect("read config"))
            .expect("parse config");
    let virtual_projects_key = YamlValue::String("virtual_projects".to_string());
    let mut virtual_projects = match mapping.get(&virtual_projects_key) {
        Some(YamlValue::Mapping(existing)) => existing.clone(),
        _ => Mapping::new(),
    };
    for (label, project) in &state.virtual_projects {
        let label_key = YamlValue::String(label.clone());
        if virtual_projects.contains_key(&label_key) {
            continue;
        }
        let relative_path = project
            .shared_dir
            .strip_prefix(&state.root)
            .expect("virtual project path")
            .to_string_lossy()
            .replace('\\', "/");
        let mut entry = Mapping::new();
        entry.insert(
            YamlValue::String("path".to_string()),
            YamlValue::String(relative_path),
        );
        virtual_projects.insert(label_key, YamlValue::Mapping(entry));
    }
    mapping.insert(virtual_projects_key, YamlValue::Mapping(virtual_projects));
    fs::write(
        config_path,
        serde_yaml::to_string(&mapping).expect("serialize config"),
    )
    .expect("write config");
}

fn build_issue(identifier: &str, title: &str, status: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: status.to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        agent: None,
        right_now_summary: None,
        right_now_updated_at: None,
        custom: BTreeMap::new(),
    }
}

fn write_issue(project_dir: &Path, issue: &IssueData) {
    let issues_dir = project_dir.join("issues");
    fs::create_dir_all(&issues_dir).expect("create issues dir");
    let issue_path = issues_dir.join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn read_issue(project_dir: &Path, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

fn create_issue(project_dir: &Path, identifier: &str, title: &str, status: &str) {
    let issue = build_issue(identifier, title, status);
    write_issue(project_dir, &issue);
}

fn issue_project_label(state: &VirtualProjectState, identifier: &str) -> Option<String> {
    if state
        .current_project_dir
        .join("issues")
        .join(format!("{identifier}.json"))
        .exists()
    {
        return Some(state.current_label.clone());
    }
    if state
        .current_local_dir
        .join("issues")
        .join(format!("{identifier}.json"))
        .exists()
    {
        return Some(state.current_label.clone());
    }
    for (label, project) in &state.virtual_projects {
        if project
            .shared_dir
            .join("issues")
            .join(format!("{identifier}.json"))
            .exists()
        {
            return Some(label.clone());
        }
        if project
            .local_dir
            .join("issues")
            .join(format!("{identifier}.json"))
            .exists()
        {
            return Some(label.clone());
        }
    }
    None
}

#[given("a Kanbus project with virtual projects configured")]
fn given_project_with_virtual_projects(world: &mut KanbusWorld) {
    if world.virtual_project_state.is_none() {
        if world.working_directory.is_some() {
            adopt_existing_repository_for_virtual_projects(world);
        } else {
            ensure_virtual_state(world);
        }
    } else {
        ensure_virtual_state(world);
    }
    configure_virtual_projects(world, vec!["alpha", "beta"]);
    let state = world
        .virtual_project_state
        .as_mut()
        .expect("virtual project state");
    write_virtual_projects_configuration(state);
    for dir in [
        state.current_project_dir.join("issues"),
        state.current_local_dir.join("issues"),
    ] {
        if let Ok(entries) = fs::read_dir(&dir) {
            for entry in entries.filter_map(|e| e.ok()) {
                let _ = fs::remove_file(entry.path());
            }
        }
    }
    for project in state.virtual_projects.values() {
        for dir in [
            project.shared_dir.join("issues"),
            project.local_dir.join("issues"),
        ] {
            if let Ok(entries) = fs::read_dir(&dir) {
                for entry in entries.filter_map(|e| e.ok()) {
                    let _ = fs::remove_file(entry.path());
                }
            }
        }
    }
}

#[given(expr = "virtual projects {string} and {string} are configured")]
fn given_virtual_projects_alpha_beta(world: &mut KanbusWorld, alpha: String, beta: String) {
    configure_virtual_projects(world, vec![alpha.as_str(), beta.as_str()]);
}

#[given(expr = "virtual project {string} has display name {string}")]
fn given_virtual_project_display_name(
    world: &mut KanbusWorld,
    label: String,
    display_name: String,
) {
    let needs_configure = {
        let state = ensure_virtual_state(world);
        !state.virtual_projects.contains_key(&label) && label != state.current_label
    };
    if needs_configure {
        configure_virtual_projects(world, vec![label.as_str()]);
    }
    let state = ensure_virtual_state(world);
    let config_path = state.root.join(".kanbus.yml");
    let mut mapping: Mapping =
        serde_yaml::from_str(&fs::read_to_string(&config_path).expect("read config"))
            .expect("parse config");
    let virtual_projects = mapping
        .get_mut(YamlValue::String("virtual_projects".to_string()))
        .and_then(YamlValue::as_mapping_mut)
        .expect("virtual_projects mapping");
    let entry = virtual_projects
        .entry(YamlValue::String(label.clone()))
        .or_insert_with(|| {
            let project = state.virtual_projects.get(&label).expect("virtual project");
            let relative_path = project
                .shared_dir
                .strip_prefix(&state.root)
                .expect("virtual project path")
                .to_string_lossy()
                .replace('\\', "/");
            let mut new_entry = Mapping::new();
            new_entry.insert(
                YamlValue::String("path".to_string()),
                YamlValue::String(relative_path),
            );
            YamlValue::Mapping(new_entry)
        });
    let entry_mapping = entry.as_mapping_mut().expect("virtual project entry");
    entry_mapping.insert(
        YamlValue::String("display_name".to_string()),
        YamlValue::String(display_name),
    );
    fs::write(
        config_path,
        serde_yaml::to_string(&mapping).expect("serialize config"),
    )
    .expect("write config");
}

#[given(expr = "congregation primary display name is {string}")]
fn given_congregation_primary_display_name(world: &mut KanbusWorld, display_name: String) {
    let state = ensure_virtual_state(world);
    let config_path = state.root.join(".kanbus.yml");
    let mut mapping: Mapping =
        serde_yaml::from_str(&fs::read_to_string(&config_path).expect("read config"))
            .expect("parse config");
    mapping.insert(
        YamlValue::String("name".to_string()),
        YamlValue::String(display_name),
    );
    fs::write(
        config_path,
        serde_yaml::to_string(&mapping).expect("serialize config"),
    )
    .expect("write config");
}

#[given(expr = "a Kanbus project with new_issue_project set to {string}")]
fn given_project_with_new_issue_project(world: &mut KanbusWorld, label: String) {
    let state = configure_virtual_projects(world, vec!["alpha", "beta"]);
    set_primary_configuration_value(state, "new_issue_project", YamlValue::String(label));
}

#[when("I run \"kanbus create Interactive task\" interactively")]
fn when_run_interactive_create(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    state.pending_interactive_command = Some("kanbus create Interactive task".to_string());
}

#[when(expr = "I select {string} from the project prompt")]
fn when_select_project_from_prompt(world: &mut KanbusWorld, label: String) {
    let command = ensure_virtual_state(world)
        .pending_interactive_command
        .clone()
        .expect("interactive command was not started");
    run_command_with_standard_input(world, &command, &format!("{label}\n"));
}

#[then(expr = "the project prompt should list {string}")]
fn then_prompt_should_list(world: &mut KanbusWorld, label: String) {
    let command = ensure_virtual_state(world)
        .pending_interactive_command
        .clone()
        .expect("interactive command was not started");
    run_command_with_standard_input(world, &command, "");
    let output = format!(
        "{}{}",
        world.stdout.as_deref().unwrap_or(""),
        world.stderr.as_deref().unwrap_or("")
    );
    assert!(
        output.contains(&label),
        "project prompt output did not list {label}: {output}"
    );
}

#[then("an issue file should be created in the current project issues directory")]
fn then_issue_created_current_project(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    let issues = fs::read_dir(state.current_project_dir.join("issues"))
        .expect("read issues dir")
        .filter_map(|entry| entry.ok())
        .collect::<Vec<_>>();
    assert!(!issues.is_empty());
}

#[then(expr = "an issue file should be created in the {string} project issues directory")]
fn then_issue_created_virtual_project(world: &mut KanbusWorld, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let issues = fs::read_dir(project.shared_dir.join("issues"))
        .expect("read issues dir")
        .filter_map(|entry| entry.ok())
        .collect::<Vec<_>>();
    assert!(!issues.is_empty());
}

#[then("a local issue file should be created in the current project local directory")]
fn then_local_issue_created_current(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    let issues = fs::read_dir(state.current_local_dir.join("issues"))
        .expect("read local issues dir")
        .filter_map(|entry| entry.ok())
        .collect::<Vec<_>>();
    assert!(!issues.is_empty());
}

#[then(expr = "a local issue file should be created in the {string} project local directory")]
fn then_local_issue_created_virtual(world: &mut KanbusWorld, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let issues = fs::read_dir(project.local_dir.join("issues"))
        .expect("read local issues dir")
        .filter_map(|entry| entry.ok())
        .collect::<Vec<_>>();
    assert!(!issues.is_empty());
}

#[then("no issue file should be created in any virtual project")]
fn then_no_issue_created_virtual(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    for project in state.virtual_projects.values() {
        let shared = fs::read_dir(project.shared_dir.join("issues"))
            .expect("read issues dir")
            .filter_map(|entry| entry.ok())
            .collect::<Vec<_>>();
        let local = fs::read_dir(project.local_dir.join("issues"))
            .expect("read issues dir")
            .filter_map(|entry| entry.ok())
            .collect::<Vec<_>>();
        assert!(shared.is_empty() && local.is_empty());
    }
}

#[then("no issue file should be created in the current project")]
fn then_no_issue_created_current(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    let issues = fs::read_dir(state.current_project_dir.join("issues"))
        .expect("read issues dir")
        .filter_map(|entry| entry.ok())
        .collect::<Vec<_>>();
    assert!(issues.is_empty());
}

#[given(expr = "an issue {string} exists in virtual project {string}")]
fn given_issue_exists_virtual(world: &mut KanbusWorld, identifier: String, label: String) {
    let state = configure_virtual_projects(world, vec![label.as_str()]);
    let shared_dir = state.virtual_projects[&label].shared_dir.clone();
    create_issue(&shared_dir, &identifier, "Virtual issue", "open");
    remember_issue_snapshot(state, &shared_dir, &identifier);
}

#[given(expr = "a local issue {string} exists in virtual project {string}")]
fn given_local_issue_exists_virtual(world: &mut KanbusWorld, identifier: String, label: String) {
    let state = configure_virtual_projects(world, vec![label.as_str()]);
    let local_dir = state.virtual_projects[&label].local_dir.clone();
    create_issue(&local_dir, &identifier, "Local virtual issue", "open");
}

#[given(expr = "an issue {string} exists in the primary project")]
fn given_issue_exists_primary(world: &mut KanbusWorld, identifier: String) {
    let state = ensure_virtual_state(world);
    let project_dir = state.current_project_dir.clone();
    create_issue(&project_dir, &identifier, "Primary issue", "open");
    remember_issue_snapshot(state, &project_dir, &identifier);
}

#[then(expr = "the issue file in virtual project {string} should be updated")]
fn then_issue_file_updated_virtual(world: &mut KanbusWorld, label: String) {
    let state = ensure_virtual_state(world);
    let shared_dir = state.virtual_projects[&label].shared_dir.clone();
    assert_issue_changed_since_snapshot(state, &shared_dir);
}

#[then("the issue file in the primary project should be updated")]
fn then_issue_file_updated_primary(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    let project_dir = state.current_project_dir.clone();
    assert_issue_changed_since_snapshot(state, &project_dir);
}

#[then(expr = "the issue file in virtual project {string} should have status {string}")]
fn then_issue_status_virtual(world: &mut KanbusWorld, label: String, status: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let mut entries = fs::read_dir(project.shared_dir.join("issues"))
        .expect("read issues dir")
        .filter_map(|entry| entry.ok());
    let issue_path = entries.next().expect("issue file").path();
    let stem = issue_path
        .file_stem()
        .and_then(|s| s.to_str())
        .expect("stem");
    let issue = read_issue(&project.shared_dir, stem);
    assert_eq!(issue.status, status);
}

#[then(expr = "issue {string} in virtual project {string} should have 1 comment")]
fn then_issue_comment_virtual(world: &mut KanbusWorld, identifier: String, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let issue = read_issue(&project.shared_dir, &identifier);
    assert_eq!(issue.comments.len(), 1);
}

#[then(expr = "the issue file should not exist in virtual project {string}")]
fn then_issue_not_exist_virtual(world: &mut KanbusWorld, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let issues = fs::read_dir(project.shared_dir.join("issues"))
        .expect("read issues dir")
        .filter_map(|entry| entry.ok())
        .collect::<Vec<_>>();
    assert!(issues.is_empty());
}

#[then(expr = "issue {string} should exist in virtual project {string} shared directory")]
fn then_issue_exists_shared_virtual(world: &mut KanbusWorld, identifier: String, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let path = project
        .shared_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    assert!(path.exists());
}

#[then(expr = "issue {string} should not exist in virtual project {string} local directory")]
fn then_issue_missing_local_virtual(world: &mut KanbusWorld, identifier: String, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let path = project
        .local_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    assert!(!path.exists());
}

#[then(expr = "issue {string} should exist in virtual project {string} local directory")]
fn then_issue_exists_local_virtual(world: &mut KanbusWorld, identifier: String, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let path = project
        .local_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    assert!(path.exists());
}

#[then(expr = "issue {string} should not exist in virtual project {string} shared directory")]
fn then_issue_missing_shared_virtual(world: &mut KanbusWorld, identifier: String, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let path = project
        .shared_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    assert!(!path.exists());
}

#[then(expr = "an event file should be created in virtual project {string} events directory")]
fn then_event_file_created_virtual(world: &mut KanbusWorld, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let events = fs::read_dir(&project.events_dir)
        .expect("read events dir")
        .filter_map(|entry| entry.ok())
        .collect::<Vec<_>>();
    assert!(!events.is_empty());
}

#[given("issues exist in multiple virtual projects")]
fn given_issues_multiple_virtual(world: &mut KanbusWorld) {
    let state = configure_virtual_projects(world, vec!["alpha", "beta"]);
    create_issue(
        &state.current_project_dir,
        "kbs-001",
        "Current issue",
        "open",
    );
    create_issue(
        &state.virtual_projects["alpha"].shared_dir,
        "alpha-001",
        "Alpha issue",
        "open",
    );
    create_issue(
        &state.virtual_projects["beta"].shared_dir,
        "beta-001",
        "Beta issue",
        "open",
    );
}

#[given("issues exist in multiple virtual projects with various statuses")]
fn given_issues_multiple_statuses(world: &mut KanbusWorld) {
    let state = configure_virtual_projects(world, vec!["alpha", "beta"]);
    create_issue(
        &state.virtual_projects["alpha"].shared_dir,
        "alpha-open",
        "Alpha open",
        "open",
    );
    create_issue(
        &state.virtual_projects["alpha"].shared_dir,
        "alpha-closed",
        "Alpha closed",
        "closed",
    );
}

#[given(expr = "a virtual project {string} has local issues")]
fn given_virtual_project_local(world: &mut KanbusWorld, label: String) {
    let state = configure_virtual_projects(world, vec![label.as_str()]);
    create_issue(
        &state.virtual_projects[&label].local_dir,
        "alpha-local",
        "Local alpha",
        "open",
    );
}

#[given(expr = "a virtual project {string} has shared and local issues")]
fn given_virtual_project_shared_local(world: &mut KanbusWorld, label: String) {
    let state = configure_virtual_projects(world, vec![label.as_str()]);
    create_issue(
        &state.virtual_projects[&label].shared_dir,
        "alpha-shared",
        "Shared alpha",
        "open",
    );
    create_issue(
        &state.virtual_projects[&label].local_dir,
        "alpha-local",
        "Local alpha",
        "open",
    );
}

#[then(expr = "stdout should contain issues from {string}")]
fn then_stdout_contains_issues_from(world: &mut KanbusWorld, label: String) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains(&label));
}

#[then("stdout should not contain issues from other projects")]
fn then_stdout_not_contains_other_projects(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(!stdout.contains("beta") && !stdout.contains("kbs"));
}

#[then("stdout should contain issues from the current project only")]
fn then_stdout_current_only(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains("kbs") && !stdout.contains("alpha") && !stdout.contains("beta"));
}

#[then("stdout should not contain issues from the current project")]
fn then_stdout_not_current(world: &mut KanbusWorld) {
    let label = ensure_virtual_state(world).current_label.clone();
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(!stdout.contains(&label));
}

#[then("stdout should contain only local issues from \"alpha\"")]
fn then_stdout_only_local_alpha(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains("alpha") && stdout.contains("local") && !stdout.contains("shared"));
}

#[then("stdout should contain only shared issues from \"alpha\"")]
fn then_stdout_only_shared_alpha(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains("alpha") && stdout.contains("shared") && !stdout.contains("local"));
}

#[then("stdout should contain only open issues from \"alpha\"")]
fn then_stdout_only_open_alpha(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains("alpha") && !stdout.contains("closed"));
}

#[then("stdout should contain issues from all projects")]
fn then_stdout_all_projects(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains("kbs") && stdout.contains("alpha") && stdout.contains("beta"));
}

#[then("issues from all virtual projects should be listed")]
fn then_issues_from_all_virtual_projects(world: &mut KanbusWorld) {
    let labels: Vec<String> = ensure_virtual_state(world)
        .virtual_projects
        .keys()
        .cloned()
        .collect();
    let stdout = world.stdout.as_deref().unwrap_or("");
    for label in &labels {
        assert!(stdout.contains(label));
    }
}

#[then("issues from the current project should be listed")]
fn then_issues_from_current_project(world: &mut KanbusWorld) {
    let label = ensure_virtual_state(world).current_label.clone();
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains(&label));
}

#[then("each issue should display its source project label")]
fn then_each_issue_has_label(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains("alpha") || stdout.contains("beta"));
}

#[given("a virtual project has local issues")]
fn given_virtual_project_has_local(world: &mut KanbusWorld) {
    let state = configure_virtual_projects(world, vec!["alpha"]);
    create_issue(
        &state.virtual_projects["alpha"].local_dir,
        "alpha-local",
        "Local issue",
        "open",
    );
}

#[then("local issues from the virtual project should be listed")]
fn then_local_issues_listed(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains("local"));
}

#[given("a Kanbus project with a virtual project pointing to a missing path")]
fn given_virtual_project_missing_path(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    let mut entry = Mapping::new();
    entry.insert(
        YamlValue::String("path".to_string()),
        YamlValue::String("virtual/missing/project".to_string()),
    );
    let mut virtual_projects = Mapping::new();
    virtual_projects.insert(
        YamlValue::String("missing".to_string()),
        YamlValue::Mapping(entry),
    );
    set_primary_configuration_value(
        state,
        "virtual_projects",
        YamlValue::Mapping(virtual_projects),
    );
}

#[given("a Kanbus project with a virtual project pointing to a directory without issues")]
fn given_virtual_project_missing_issues(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    fs::create_dir_all(state.root.join("virtual").join("hollow").join("project"))
        .expect("create hollow project directory");
    let mut entry = Mapping::new();
    entry.insert(
        YamlValue::String("path".to_string()),
        YamlValue::String("virtual/hollow/project".to_string()),
    );
    let mut virtual_projects = Mapping::new();
    virtual_projects.insert(
        YamlValue::String("hollow".to_string()),
        YamlValue::Mapping(entry),
    );
    set_primary_configuration_value(
        state,
        "virtual_projects",
        YamlValue::Mapping(virtual_projects),
    );
}

#[given("a Kanbus project with duplicate virtual project labels")]
fn given_duplicate_virtual_labels(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    let config_path = state.root.join(".kanbus.yml");
    let mut mapping: Mapping =
        serde_yaml::from_str(&fs::read_to_string(&config_path).expect("read config"))
            .expect("parse config");
    mapping.remove(YamlValue::String("virtual_projects".to_string()));
    let mut contents = serde_yaml::to_string(&mapping).expect("serialize config");
    contents.push_str(
        "virtual_projects:\n  alpha:\n    path: virtual/alpha/project\n  alpha:\n    path: virtual/beta/project\n",
    );
    fs::write(config_path, contents).expect("write config");
}

#[given("a Kanbus project with a virtual project label matching the project key")]
fn given_virtual_label_conflict(world: &mut KanbusWorld) {
    configure_virtual_projects(world, vec!["kbs"]);
}

#[given("a Kanbus repository with a .kanbus.yml file using external_projects")]
fn given_external_projects_config(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    let config_path = state.root.join(".kanbus.yml");
    let mut contents = fs::read_to_string(&config_path).expect("read config");
    contents.push_str("external_projects:\n  - ../elsewhere\n");
    fs::write(config_path, contents).expect("write config");
}

#[given("a repository with a .kanbus.yml file with virtual projects configured")]
fn given_repo_with_virtual_projects_config(world: &mut KanbusWorld) {
    let state = configure_virtual_projects(world, vec!["extern"]);
    create_issue(
        &state.virtual_projects["extern"].shared_dir,
        "kanbus-extern",
        "Extern",
        "open",
    );
}

#[then(expr = "stdout should contain the virtual project label for {string}")]
fn then_stdout_contains_virtual_label(world: &mut KanbusWorld, identifier: String) {
    let state = ensure_virtual_state(world);
    let label = issue_project_label(state, &identifier).expect("label");
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains(&label));
}

#[then("issues from the virtual projects should be listed")]
fn then_issues_from_virtual_projects_listed(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains("extern") || stdout.contains("alpha"));
}

#[then(expr = "stdout should contain the source project label {string}")]
fn then_stdout_contains_source_label(world: &mut KanbusWorld, label: String) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    assert!(stdout.contains(&label));
}
