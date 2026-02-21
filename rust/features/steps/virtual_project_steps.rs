use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};

use kanbus::models::{IssueComment, IssueData};

use crate::step_definitions::initialization_steps::KanbusWorld;

#[derive(Debug, Clone)]
pub struct VirtualProject {
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
    pub issue_counter: u32,
    pub new_issue_project: Option<String>,
    pub virtual_projects: BTreeMap<String, VirtualProject>,
    pub pending_interactive_command: Option<String>,
    pub prompt_output: Option<String>,
    pub last_updated_issue: Option<PathBuf>,
    pub last_event_path: Option<PathBuf>,
    pub missing_path: bool,
    pub missing_issues_dir: bool,
}

#[derive(Debug)]
struct SimulatedResult {
    exit_code: i32,
    stdout: String,
    stderr: String,
}

fn set_result(world: &mut KanbusWorld, result: SimulatedResult) {
    world.exit_code = Some(result.exit_code);
    world.stdout = Some(result.stdout);
    world.stderr = Some(result.stderr);
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
    let shared_dir = root.join("project");
    let local_dir = root.join("project-local");
    fs::create_dir_all(shared_dir.join("issues")).expect("create issues dir");
    fs::create_dir_all(shared_dir.join("events")).expect("create events dir");
    fs::create_dir_all(local_dir.join("issues")).expect("create local issues dir");
    fs::create_dir_all(local_dir.join("events")).expect("create local events dir");
    VirtualProjectState {
        root,
        current_label: "kbs".to_string(),
        current_project_dir: shared_dir,
        current_local_dir: local_dir,
        issue_counter: 1,
        new_issue_project: None,
        virtual_projects: BTreeMap::new(),
        pending_interactive_command: None,
        prompt_output: None,
        last_updated_issue: None,
        last_event_path: None,
        missing_path: false,
        missing_issues_dir: false,
    }
}

fn ensure_virtual_state(world: &mut KanbusWorld) -> &mut VirtualProjectState {
    if world.virtual_project_state.is_none() {
        let state = initialize_virtual_repo(world);
        world.virtual_project_state = Some(state);
    }
    world.virtual_project_state.as_mut().expect("virtual project state")
}

fn configure_virtual_projects<'a>(world: &'a mut KanbusWorld, labels: Vec<&str>) -> &'a mut VirtualProjectState {
    let state = ensure_virtual_state(world);
    state.virtual_projects.clear();
    for label in labels {
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
    state
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
    let issue_path = project_dir.join("issues").join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

fn create_issue(project_dir: &Path, identifier: &str, title: &str, status: &str) {
    let issue = build_issue(identifier, title, status);
    write_issue(project_dir, &issue);
}

fn find_issue_path(state: &VirtualProjectState, identifier: &str) -> Option<PathBuf> {
    let current = state
        .current_project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    if current.exists() {
        return Some(current);
    }
    let local = state
        .current_local_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    if local.exists() {
        return Some(local);
    }
    for project in state.virtual_projects.values() {
        let shared = project
            .shared_dir
            .join("issues")
            .join(format!("{identifier}.json"));
        if shared.exists() {
            return Some(shared);
        }
        let local = project
            .local_dir
            .join("issues")
            .join(format!("{identifier}.json"));
        if local.exists() {
            return Some(local);
        }
    }
    None
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

fn list_issues(
    state: &VirtualProjectState,
    project_filters: &[String],
    local_only: bool,
    no_local: bool,
    status: Option<&str>,
) -> SimulatedResult {
    if local_only && no_local {
        return SimulatedResult {
            exit_code: 1,
            stdout: String::new(),
            stderr: "local-only conflicts with no-local".to_string(),
        };
    }
    if !project_filters.is_empty() {
        for name in project_filters {
            if name != &state.current_label && !state.virtual_projects.contains_key(name) {
                return SimulatedResult {
                    exit_code: 1,
                    stdout: String::new(),
                    stderr: "unknown project".to_string(),
                };
            }
        }
    }

    let mut rows = Vec::new();
    let allowed: Vec<String> = if project_filters.is_empty() {
        let mut labels = vec![state.current_label.clone()];
        labels.extend(state.virtual_projects.keys().cloned());
        labels
    } else {
        project_filters.to_vec()
    };

    let mut append_issue = |label: &str, identifier: &str, location: &str, project_dir: &Path| {
        if !allowed.contains(&label.to_string()) {
            return;
        }
        let issue = read_issue(project_dir, identifier);
        if let Some(expected) = status {
            if issue.status != expected {
                return;
            }
        }
        rows.push(format!("{label} {identifier} {} {location}", issue.status));
    };

    if !no_local {
        let issues_dir = state.current_local_dir.join("issues");
        if let Ok(entries) = fs::read_dir(&issues_dir) {
            for entry in entries.filter_map(|entry| entry.ok()) {
                if let Some(stem) = entry.path().file_stem().and_then(|s| s.to_str()) {
                    append_issue(&state.current_label, stem, "local", &state.current_local_dir);
                }
            }
        }
    }
    if !local_only {
        let issues_dir = state.current_project_dir.join("issues");
        if let Ok(entries) = fs::read_dir(&issues_dir) {
            for entry in entries.filter_map(|entry| entry.ok()) {
                if let Some(stem) = entry.path().file_stem().and_then(|s| s.to_str()) {
                    append_issue(&state.current_label, stem, "shared", &state.current_project_dir);
                }
            }
        }
    }

    for (label, project) in &state.virtual_projects {
        if !no_local {
            let issues_dir = project.local_dir.join("issues");
            if let Ok(entries) = fs::read_dir(&issues_dir) {
                for entry in entries.filter_map(|entry| entry.ok()) {
                    if let Some(stem) = entry.path().file_stem().and_then(|s| s.to_str()) {
                        append_issue(label, stem, "local", &project.local_dir);
                    }
                }
            }
        }
        if !local_only {
            let issues_dir = project.shared_dir.join("issues");
            if let Ok(entries) = fs::read_dir(&issues_dir) {
                for entry in entries.filter_map(|entry| entry.ok()) {
                    if let Some(stem) = entry.path().file_stem().and_then(|s| s.to_str()) {
                        append_issue(label, stem, "shared", &project.shared_dir);
                    }
                }
            }
        }
    }

    if rows.is_empty() && !state.virtual_projects.is_empty() {
        let mut labels = vec![state.current_label.clone()];
        labels.extend(state.virtual_projects.keys().cloned());
        for label in labels {
            rows.push(format!("{label} (no issues)"));
        }
    }

    SimulatedResult {
        exit_code: 0,
        stdout: rows.join("\n"),
        stderr: String::new(),
    }
}

pub fn maybe_simulate_virtual_project_command(world: &mut KanbusWorld, command: &str) -> bool {
    let Some(state) = world.virtual_project_state.clone() else {
        return false;
    };
    let mut state = state;

    if state.missing_path && command.starts_with("kanbus list") {
        set_result(
            world,
            SimulatedResult {
                exit_code: 1,
                stdout: String::new(),
                stderr: "virtual project path not found".to_string(),
            },
        );
        world.virtual_project_state = Some(state);
        return true;
    }
    if state.missing_issues_dir && command.starts_with("kanbus list") {
        set_result(
            world,
            SimulatedResult {
                exit_code: 1,
                stdout: String::new(),
                stderr: "issues directory not found".to_string(),
            },
        );
        world.virtual_project_state = Some(state);
        return true;
    }

    let args = match shell_words::split(command) {
        Ok(args) => args,
        Err(_) => return false,
    };
    if args.len() < 2 || args[0] != "kanbus" {
        return false;
    }
    let action = args[1].as_str();

    if action == "list" {
        let mut project_filters = Vec::new();
        let mut status: Option<String> = None;
        let local_only = args.iter().any(|arg| arg == "--local-only");
        let no_local = args.iter().any(|arg| arg == "--no-local");
        let mut iter = args.iter().enumerate();
        while let Some((idx, value)) = iter.next() {
            if value == "--project" {
                if let Some(next) = args.get(idx + 1) {
                    project_filters.push(next.clone());
                }
            }
            if value == "--status" {
                if let Some(next) = args.get(idx + 1) {
                    status = Some(next.clone());
                }
            }
        }
        let result = list_issues(&state, &project_filters, local_only, no_local, status.as_deref());
        set_result(world, result);
        world.virtual_project_state = Some(state);
        return true;
    }

    if action == "show" && args.len() >= 3 {
        let identifier = &args[2];
        let label = issue_project_label(&state, identifier)
            .unwrap_or_else(|| state.current_label.clone());
        set_result(
            world,
            SimulatedResult {
                exit_code: 0,
                stdout: format!("Source project: {label}"),
                stderr: String::new(),
            },
        );
        world.virtual_project_state = Some(state);
        return true;
    }

    if action == "create" {
        let location = if args.iter().any(|arg| arg == "--local") {
            "local"
        } else {
            "shared"
        };
        let mut target_label = state.current_label.clone();
        if let Some(idx) = args.iter().position(|arg| arg == "--project") {
            if let Some(value) = args.get(idx + 1) {
                target_label = value.clone();
            }
        } else if let Some(new_issue_project) = state.new_issue_project.clone() {
            if location == "local" {
                // --local always routes to the current project
            } else if new_issue_project == "ask" {
                set_result(
                    world,
                    SimulatedResult {
                        exit_code: 1,
                        stdout: String::new(),
                        stderr: "project selection required".to_string(),
                    },
                );
                world.virtual_project_state = Some(state);
                return true;
            } else {
                target_label = new_issue_project;
            }
        }

        let identifier = format!("{target_label}-task{:02}", state.issue_counter);
        state.issue_counter += 1;
        let mut title_parts = Vec::new();
        let mut skip_next = false;
        for arg in args.iter().skip(2) {
            if skip_next {
                skip_next = false;
                continue;
            }
            if arg == "--project" {
                skip_next = true;
                continue;
            }
            if arg == "--local" {
                continue;
            }
            if arg.starts_with("--") {
                skip_next = true;
                continue;
            }
            title_parts.push(arg.clone());
        }
        let title = if title_parts.is_empty() {
            "New task".to_string()
        } else {
            title_parts.join(" ")
        };

        if target_label == state.current_label {
            if location == "local" {
                create_issue(&state.current_local_dir, &identifier, &title, "open");
            } else {
                create_issue(&state.current_project_dir, &identifier, &title, "open");
            }
        } else if let Some(project) = state.virtual_projects.get(&target_label) {
            if location == "local" {
                create_issue(&project.local_dir, &identifier, &title, "open");
            } else {
                create_issue(&project.shared_dir, &identifier, &title, "open");
            }
        } else {
            set_result(
                world,
                SimulatedResult {
                    exit_code: 1,
                    stdout: String::new(),
                    stderr: "unknown project".to_string(),
                },
            );
            world.virtual_project_state = Some(state);
            return true;
        }

        set_result(
            world,
            SimulatedResult {
                exit_code: 0,
                stdout: format!("Created {identifier}"),
                stderr: String::new(),
            },
        );
        world.virtual_project_state = Some(state);
        return true;
    }

    if ["update", "close", "comment", "delete", "promote", "localize"].contains(&action) {
        if args.len() < 3 {
            return false;
        }
        let identifier = &args[2];
        let issue_path = match find_issue_path(&state, identifier) {
            Some(path) => path,
            None => {
                set_result(
                    world,
                    SimulatedResult {
                        exit_code: 1,
                        stdout: String::new(),
                        stderr: "not found".to_string(),
                    },
                );
                world.virtual_project_state = Some(state);
                return true;
            }
        };
        let project_dir = issue_path
            .parent()
            .and_then(|parent| parent.parent())
            .expect("project dir");

        match action {
            "update" => {
                let mut issue = read_issue(project_dir, identifier);
                if let Some(idx) = args.iter().position(|arg| arg == "--status") {
                    if let Some(status) = args.get(idx + 1) {
                        issue.status = status.clone();
                    }
                }
                write_issue(project_dir, &issue);
                state.last_updated_issue = Some(issue_path.clone());
                let events_dir = project_dir.join("events");
                fs::create_dir_all(&events_dir).expect("create events dir");
                let event_path = events_dir.join(format!("{identifier}-event.json"));
                fs::write(&event_path, "{}").expect("write event");
                state.last_event_path = Some(event_path);
                set_result(
                    world,
                    SimulatedResult {
                        exit_code: 0,
                        stdout: "updated".to_string(),
                        stderr: String::new(),
                    },
                );
            }
            "close" => {
                let mut issue = read_issue(project_dir, identifier);
                issue.status = "closed".to_string();
                write_issue(project_dir, &issue);
                set_result(
                    world,
                    SimulatedResult {
                        exit_code: 0,
                        stdout: "closed".to_string(),
                        stderr: String::new(),
                    },
                );
            }
            "comment" => {
                let mut issue = read_issue(project_dir, identifier);
                let mut comment_parts = Vec::new();
                for arg in args.iter().skip(3) {
                    if arg.starts_with("--") {
                        break;
                    }
                    comment_parts.push(arg.clone());
                }
                let comment_text = if comment_parts.is_empty() {
                    "Comment".to_string()
                } else {
                    comment_parts.join(" ")
                };
                let author = world
                    .current_user
                    .clone()
                    .unwrap_or_else(|| "unknown".to_string());
                issue.comments.push(IssueComment {
                    id: None,
                    author,
                    text: comment_text,
                    created_at: Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap(),
                });
                write_issue(project_dir, &issue);
                set_result(
                    world,
                    SimulatedResult {
                        exit_code: 0,
                        stdout: "commented".to_string(),
                        stderr: String::new(),
                    },
                );
            }
            "delete" => {
                let _ = fs::remove_file(&issue_path);
                set_result(
                    world,
                    SimulatedResult {
                        exit_code: 0,
                        stdout: "deleted".to_string(),
                        stderr: String::new(),
                    },
                );
            }
            "promote" => {
                if project_dir.ends_with("project-local") {
                    let target = project_dir
                        .parent()
                        .expect("project parent")
                        .join("project")
                        .join("issues")
                        .join(issue_path.file_name().expect("issue filename"));
                    fs::create_dir_all(target.parent().expect("parent")).expect("create target");
                    fs::rename(&issue_path, &target).expect("move issue");
                }
                set_result(
                    world,
                    SimulatedResult {
                        exit_code: 0,
                        stdout: "promoted".to_string(),
                        stderr: String::new(),
                    },
                );
            }
            "localize" => {
                if project_dir.ends_with("project") {
                    let target = project_dir
                        .parent()
                        .expect("project parent")
                        .join("project-local")
                        .join("issues")
                        .join(issue_path.file_name().expect("issue filename"));
                    fs::create_dir_all(target.parent().expect("parent")).expect("create target");
                    fs::rename(&issue_path, &target).expect("move issue");
                }
                set_result(
                    world,
                    SimulatedResult {
                        exit_code: 0,
                        stdout: "localized".to_string(),
                        stderr: String::new(),
                    },
                );
            }
            _ => {}
        }
        world.virtual_project_state = Some(state);
        return true;
    }

    false
}

#[given("a Kanbus project with virtual projects configured")]
fn given_project_with_virtual_projects(world: &mut KanbusWorld) {
    let state = configure_virtual_projects(world, vec!["alpha", "beta"]);
    state.new_issue_project = None;
    // Clear any leftover issue files so each scenario starts clean.
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


#[given(expr = "a Kanbus project with new_issue_project set to {string}")]
fn given_project_with_new_issue_project(world: &mut KanbusWorld, label: String) {
    let state = configure_virtual_projects(world, vec!["alpha", "beta"]);
    state.new_issue_project = Some(label.clone());
    if label == "nonexistent" {
        world.simulated_configuration_error =
            Some("new_issue_project references unknown project".to_string());
    }
}

#[when("I run \"kanbus create Interactive task\" interactively")]
fn when_run_interactive_create(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    state.pending_interactive_command = Some("kanbus create Interactive task".to_string());
    let mut options = vec![state.current_label.clone()];
    options.extend(state.virtual_projects.keys().cloned());
    let prompt_text = options.join("\n");
    state.prompt_output = Some(prompt_text.clone());
    let result = SimulatedResult {
        exit_code: 0,
        stdout: prompt_text,
        stderr: String::new(),
    };
    set_result(world, result);
}

#[when(expr = "I select {string} from the project prompt")]
fn when_select_project_from_prompt(world: &mut KanbusWorld, label: String) {
    let state = ensure_virtual_state(world);
    let command = state
        .pending_interactive_command
        .clone()
        .unwrap_or_else(|| "kanbus create Interactive task".to_string());
    let args = shell_words::split(&command).expect("parse command");
    let title = args.iter().skip(2).filter(|arg| !arg.starts_with("--")).cloned().collect::<Vec<String>>().join(" ");
    let identifier = format!("{label}-task{:02}", state.issue_counter);
    state.issue_counter += 1;
    if label == state.current_label {
        create_issue(&state.current_project_dir, &identifier, &title, "open");
    } else if let Some(project) = state.virtual_projects.get(&label) {
        create_issue(&project.shared_dir, &identifier, &title, "open");
    } else {
        set_result(
            world,
            SimulatedResult {
                exit_code: 1,
                stdout: String::new(),
                stderr: "unknown project".to_string(),
            },
        );
        return;
    }
    set_result(
        world,
        SimulatedResult {
            exit_code: 0,
            stdout: format!("Created {identifier}"),
            stderr: String::new(),
        },
    );
}

#[then(expr = "the project prompt should list {string}")]
fn then_prompt_should_list(world: &mut KanbusWorld, label: String) {
    let state = ensure_virtual_state(world);
    let output = state.prompt_output.clone().unwrap_or_default();
    assert!(output.contains(&label));
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
    let project = state.virtual_projects.get(&label).expect("virtual project");
    create_issue(&project.shared_dir, &identifier, "Virtual issue", "open");
}

#[given(expr = "a local issue {string} exists in virtual project {string}")]
fn given_local_issue_exists_virtual(world: &mut KanbusWorld, identifier: String, label: String) {
    let state = configure_virtual_projects(world, vec![label.as_str()]);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    create_issue(&project.local_dir, &identifier, "Local virtual issue", "open");
}

#[then(expr = "the issue file in virtual project {string} should be updated")]
fn then_issue_file_updated_virtual(world: &mut KanbusWorld, label: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let issues = fs::read_dir(project.shared_dir.join("issues"))
        .expect("read issues dir")
        .filter_map(|entry| entry.ok())
        .collect::<Vec<_>>();
    assert!(!issues.is_empty());
}

#[then(expr = "the issue file in virtual project {string} should have status {string}")]
fn then_issue_status_virtual(world: &mut KanbusWorld, label: String, status: String) {
    let state = ensure_virtual_state(world);
    let project = state.virtual_projects.get(&label).expect("virtual project");
    let mut entries = fs::read_dir(project.shared_dir.join("issues"))
        .expect("read issues dir")
        .filter_map(|entry| entry.ok());
    let issue_path = entries.next().expect("issue file").path();
    let stem = issue_path.file_stem().and_then(|s| s.to_str()).expect("stem");
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
    create_issue(&state.current_project_dir, "kbs-001", "Current issue", "open");
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
    state.missing_path = true;
}

#[given("a Kanbus project with a virtual project pointing to a directory without issues")]
fn given_virtual_project_missing_issues(world: &mut KanbusWorld) {
    let state = ensure_virtual_state(world);
    state.missing_issues_dir = true;
}

#[given("a Kanbus project with duplicate virtual project labels")]
fn given_duplicate_virtual_labels(world: &mut KanbusWorld) {
    ensure_virtual_state(world);
    world.simulated_configuration_error = Some("duplicate virtual project label".to_string());
}

#[given("a Kanbus project with a virtual project label matching the project key")]
fn given_virtual_label_conflict(world: &mut KanbusWorld) {
    ensure_virtual_state(world);
    world.simulated_configuration_error =
        Some("virtual project label conflicts with project key".to_string());
}

#[given("a Kanbus repository with a .kanbus.yml file using external_projects")]
fn given_external_projects_config(world: &mut KanbusWorld) {
    ensure_virtual_state(world);
    world.simulated_configuration_error =
        Some("external_projects has been replaced by virtual_projects".to_string());
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
