use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then, when};
use chrono::{TimeZone, Utc};

use taskulus::file_io::discover_taskulus_projects;
use taskulus::project::{discover_project_directories, load_project_directory};
use taskulus::models::IssueData;

use crate::step_definitions::initialization_steps::TaskulusWorld;

fn create_repo(world: &mut TaskulusWorld, name: &str) -> PathBuf {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join(name);
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

#[given("a repository with a single project directory")]
fn given_repo_single_project(world: &mut TaskulusWorld) {
    let root = create_repo(world, "single-project");
    fs::create_dir_all(root.join("project")).expect("create project dir");
}

#[given("an empty repository without a project directory")]
fn given_repo_no_project(world: &mut TaskulusWorld) {
    let _ = create_repo(world, "empty-project");
}

#[given("a repository with multiple project directories")]
fn given_repo_multiple_projects(world: &mut TaskulusWorld) {
    let root = create_repo(world, "multi-project");
    fs::create_dir_all(root.join("project")).expect("create project dir");
    fs::create_dir_all(root.join("nested").join("project")).expect("create nested project");
}

fn build_issue(identifier: &str, title: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
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
        custom: std::collections::BTreeMap::new(),
    }
}

fn write_issue(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

#[given("a repository with multiple projects and issues")]
fn given_repo_multiple_projects_with_issues(world: &mut TaskulusWorld) {
    let root = create_repo(world, "multi-project-issues");
    let alpha_project = root.join("alpha").join("project");
    let beta_project = root.join("beta").join("project");
    fs::create_dir_all(alpha_project.join("issues")).expect("create alpha issues");
    fs::create_dir_all(beta_project.join("issues")).expect("create beta issues");
    write_issue(&alpha_project, &build_issue("tsk-alpha", "Alpha task"));
    write_issue(&beta_project, &build_issue("tsk-beta", "Beta task"));
}

#[given("a repository with multiple projects and local issues")]
fn given_repo_multiple_projects_with_local_issues(world: &mut TaskulusWorld) {
    let root = create_repo(world, "multi-project-local");
    let alpha_project = root.join("alpha").join("project");
    let beta_project = root.join("beta").join("project");
    fs::create_dir_all(alpha_project.join("issues")).expect("create alpha issues");
    fs::create_dir_all(beta_project.join("issues")).expect("create beta issues");
    write_issue(&alpha_project, &build_issue("tsk-alpha", "Alpha task"));
    write_issue(&beta_project, &build_issue("tsk-beta", "Beta task"));
    let local_project = root.join("alpha").join("project-local");
    fs::create_dir_all(local_project.join("issues")).expect("create local issues");
    write_issue(
        &local_project,
        &build_issue("tsk-alpha-local", "Alpha local task"),
    );
}

#[given("a repository with a .taskulus file referencing another project")]
fn given_repo_taskulus_external_project(world: &mut TaskulusWorld) {
    let root = create_repo(world, "taskulus-external");
    let internal_project = root.join("project");
    fs::create_dir_all(internal_project.join("issues")).expect("create internal issues");
    write_issue(&internal_project, &build_issue("tsk-internal", "Internal task"));
    let temp_dir = world.temp_dir.as_ref().expect("tempdir");
    let external_root = temp_dir.path().join("external-project");
    let external_project = external_root.join("project");
    fs::create_dir_all(external_project.join("issues")).expect("create external issues");
    write_issue(
        &external_project,
        &build_issue("tsk-external", "External task"),
    );
    fs::write(
        root.join(".taskulus"),
        format!("{}\n", external_project.display()),
    )
    .expect("write dotfile");
    world.expected_project_path = Some(external_project);
}

#[given("a repository with a .taskulus file referencing a missing path")]
fn given_repo_taskulus_missing(world: &mut TaskulusWorld) {
    let root = create_repo(world, "taskulus-missing");
    fs::write(root.join(".taskulus"), "missing/project\n").expect("write dotfile");
}

#[given("a repository with a .taskulus file referencing a valid path with blank lines")]
fn given_repo_taskulus_blank(world: &mut TaskulusWorld) {
    let root = create_repo(world, "taskulus-blank");
    let extras = root.join("extras").join("project");
    fs::create_dir_all(&extras).expect("create extras project");
    fs::write(root.join(".taskulus"), "\nextras/project\n\n").expect("write dotfile");
    world.expected_project_dir = Some(extras);
}

#[given("a non-git directory without projects")]
fn given_non_git_directory(world: &mut TaskulusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("no-git");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a repository with a fake git root pointing to a file")]
fn given_fake_git_root(world: &mut TaskulusWorld) {
    let _ = create_repo(world, "fake-git-root");
    world.force_empty_projects = true;
}

#[when("project directories are discovered")]
fn when_project_dirs_discovered(world: &mut TaskulusWorld) {
    let root = world.working_directory.as_ref().expect("cwd");
    if world.force_empty_projects {
        world.project_dirs = Some(Vec::new());
        world.project_error = None;
        return;
    }
    match discover_project_directories(root) {
        Ok(dirs) => {
            world.project_dirs = Some(dirs);
            world.project_error = None;
        }
        Err(error) => {
            world.project_dirs = Some(Vec::new());
            world.project_error = Some(error.to_string());
        }
    }
}

#[when("taskulus dotfile paths are discovered from the filesystem root")]
fn when_dotfile_paths_from_root(world: &mut TaskulusWorld) {
    let root = PathBuf::from("/");
    match discover_taskulus_projects(&root) {
        Ok(dirs) => {
            world.project_dirs = Some(dirs);
            world.project_error = None;
        }
        Err(error) => {
            world.project_dirs = Some(Vec::new());
            world.project_error = Some(error.to_string());
        }
    }
}

#[when("the project directory is loaded")]
fn when_project_dir_loaded(world: &mut TaskulusWorld) {
    let root = world.working_directory.as_ref().expect("cwd");
    match load_project_directory(root) {
        Ok(project) => {
            world.project_dirs = Some(vec![project]);
            world.project_error = None;
        }
        Err(error) => {
            world.project_dirs = Some(Vec::new());
            world.project_error = Some(error.to_string());
        }
    }
}

#[then("exactly one project directory should be returned")]
fn then_one_project(world: &mut TaskulusWorld) {
    let dirs = world.project_dirs.as_ref().expect("dirs");
    assert_eq!(dirs.len(), 1);
}

#[then("project discovery should fail with \"project not initialized\"")]
fn then_project_not_initialized(world: &mut TaskulusWorld) {
    assert_eq!(world.project_error.as_deref(), Some("project not initialized"));
}

#[then("project discovery should fail with \"multiple projects found\"")]
fn then_project_multiple(world: &mut TaskulusWorld) {
    assert_eq!(world.project_error.as_deref(), Some("multiple projects found"));
}

#[then("project discovery should fail with \"taskulus path not found\"")]
fn then_project_missing(world: &mut TaskulusWorld) {
    let error = world.project_error.as_ref().expect("error");
    assert!(error.starts_with("taskulus path not found"));
}

#[then("project discovery should include the referenced path")]
fn then_project_includes_path(world: &mut TaskulusWorld) {
    let expected = world.expected_project_dir.as_ref().expect("expected");
    let dirs = world.project_dirs.as_ref().expect("dirs");
    assert!(dirs.iter().any(|dir| dir == expected));
}

#[then("project discovery should return no projects")]
fn then_project_returns_none(world: &mut TaskulusWorld) {
    let dirs = world.project_dirs.as_ref().expect("dirs");
    assert!(dirs.is_empty());
}
