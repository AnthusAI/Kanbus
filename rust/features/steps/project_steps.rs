use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};
use serde_yaml;

use taskulus::config::default_project_configuration;
use taskulus::file_io::{discover_taskulus_projects, get_configuration_path};
use taskulus::models::IssueData;
use taskulus::project::{discover_project_directories, load_project_directory};

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

fn set_canonicalize_failure(world: &mut TaskulusWorld) {
    if world.original_canonicalize_failure_env.is_none() {
        world.original_canonicalize_failure_env =
            Some(env::var("TASKULUS_TEST_CANONICALIZE_FAILURE").ok());
    }
    env::set_var("TASKULUS_TEST_CANONICALIZE_FAILURE", "1");
}

fn set_configuration_path_failure(world: &mut TaskulusWorld) {
    if world.original_configuration_path_failure_env.is_none() {
        world.original_configuration_path_failure_env =
            Some(env::var("TASKULUS_TEST_CONFIGURATION_PATH_FAILURE").ok());
    }
    env::set_var("TASKULUS_TEST_CONFIGURATION_PATH_FAILURE", "1");
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

#[given("a repository with a project directory that cannot be canonicalized")]
fn given_repo_project_cannot_canonicalize(world: &mut TaskulusWorld) {
    let root = create_repo(world, "canonicalize-failure");
    let project_dir = root.join("project");
    fs::create_dir_all(&project_dir).expect("create project dir");
    set_canonicalize_failure(world);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&project_dir)
            .expect("project metadata")
            .permissions();
        let original = permissions.mode();
        permissions.set_mode(0o000);
        fs::set_permissions(&project_dir, permissions).expect("set permissions");
        world.unreadable_path = Some(project_dir);
        world.unreadable_mode = Some(original);
    }
}

#[given("project directory canonicalization will fail")]
fn given_project_directory_canonicalization_failure(world: &mut TaskulusWorld) {
    set_canonicalize_failure(world);
}

#[given("configuration path lookup will fail")]
fn given_configuration_path_lookup_failure(world: &mut TaskulusWorld) {
    set_configuration_path_failure(world);
}

#[given("a repository directory that is unreadable")]
fn given_repo_unreadable(world: &mut TaskulusWorld) {
    let root = create_repo(world, "unreadable-projects");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&root).expect("root metadata").permissions();
        let original = permissions.mode();
        permissions.set_mode(0o000);
        fs::set_permissions(&root, permissions).expect("set permissions");
        world.unreadable_path = Some(root.clone());
        world.unreadable_mode = Some(original);
    }
    world.working_directory = Some(root);
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

#[given("a repository with a .taskulus.yml file referencing another project")]
fn given_repo_taskulus_external_project(world: &mut TaskulusWorld) {
    let root = create_repo(world, "taskulus-external");
    let internal_project = root.join("project");
    fs::create_dir_all(internal_project.join("issues")).expect("create internal issues");
    write_issue(
        &internal_project,
        &build_issue("tsk-internal", "Internal task"),
    );
    let temp_dir = world.temp_dir.as_ref().expect("tempdir");
    let external_root = temp_dir.path().join("external-project");
    let external_project = external_root.join("project");
    fs::create_dir_all(external_project.join("issues")).expect("create external issues");
    write_issue(
        &external_project,
        &build_issue("tsk-external", "External task"),
    );
    let mut configuration = default_project_configuration();
    configuration.external_projects = vec![external_project.display().to_string()];
    let payload = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(root.join(".taskulus.yml"), payload).expect("write config");
    world.expected_project_path = Some(external_project);
}

#[given("a repository with a .taskulus.yml file referencing a missing path")]
fn given_repo_taskulus_missing(world: &mut TaskulusWorld) {
    let root = create_repo(world, "taskulus-missing");
    let mut configuration = default_project_configuration();
    configuration.external_projects = vec!["missing/project".to_string()];
    let payload = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(root.join(".taskulus.yml"), payload).expect("write config");
}

#[given("a repository with an invalid .taskulus.yml file")]
fn given_repo_taskulus_invalid(world: &mut TaskulusWorld) {
    let root = create_repo(world, "taskulus-invalid");
    fs::write(root.join(".taskulus.yml"), "unknown_field: value\n").expect("write config");
}

#[given("a repository with a project directory above the current directory")]
fn given_repo_project_above(world: &mut TaskulusWorld) {
    let root = create_repo(world, "project-above");
    let project_dir = root.join("project");
    fs::create_dir_all(project_dir.join("issues")).expect("create project issues");
    write_issue(&project_dir, &build_issue("tsk-above", "Above task"));
    let subdir = root.join("subdir");
    fs::create_dir_all(&subdir).expect("create subdir");
    world.working_directory = Some(subdir);
}

#[given("a project directory with a sibling project-local directory")]
fn given_project_with_local_sibling(world: &mut TaskulusWorld) {
    let root = create_repo(world, "project-local-sibling");
    let shared_dir = root.join("project");
    let local_dir = root.join("project-local");
    fs::create_dir_all(shared_dir.join("issues")).expect("create shared issues");
    fs::create_dir_all(local_dir.join("issues")).expect("create local issues");
    write_issue(&shared_dir, &build_issue("tsk-shared", "Shared task"));
    write_issue(&local_dir, &build_issue("tsk-local", "Local task"));
}

#[given("a repository with a .taskulus.yml file referencing a valid path with blank lines")]
fn given_repo_taskulus_blank(world: &mut TaskulusWorld) {
    let root = create_repo(world, "taskulus-blank");
    let extras = root.join("extras").join("project");
    fs::create_dir_all(&extras).expect("create extras project");
    let mut configuration = default_project_configuration();
    configuration.project_directory = "extras/project".to_string();
    let payload = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(root.join(".taskulus.yml"), payload).expect("write config");
    world.expected_project_dir = Some(extras);
}

#[given("a repository with a .taskulus file referencing another project")]
fn given_repo_taskulus_dotfile(world: &mut TaskulusWorld) {
    let root = create_repo(world, "taskulus-dotfile");
    let temp_dir = world.temp_dir.as_ref().expect("tempdir");
    let external_root = temp_dir.path().join("dotfile-external");
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
}

#[given("a repository with a .taskulus file referencing a missing path")]
fn given_repo_taskulus_dotfile_missing(world: &mut TaskulusWorld) {
    let root = create_repo(world, "taskulus-dotfile-missing");
    fs::write(root.join(".taskulus"), "missing/project\n").expect("write dotfile");
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

#[when("taskulus configuration paths are discovered from the filesystem root")]
fn when_configuration_paths_from_root(world: &mut TaskulusWorld) {
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

#[when("the configuration path is requested")]
fn when_configuration_path_requested(world: &mut TaskulusWorld) {
    let root = world.working_directory.as_ref().expect("cwd");
    match get_configuration_path(root) {
        Ok(_) => world.project_error = None,
        Err(error) => world.project_error = Some(error.to_string()),
    }
}

#[then("exactly one project directory should be returned")]
fn then_one_project(world: &mut TaskulusWorld) {
    let dirs = world.project_dirs.as_ref().expect("dirs");
    assert_eq!(dirs.len(), 1);
}

#[then("project discovery should fail with \"project not initialized\"")]
fn then_project_not_initialized(world: &mut TaskulusWorld) {
    assert_eq!(
        world.project_error.as_deref(),
        Some("project not initialized")
    );
}

#[then("project discovery should fail with \"multiple projects found\"")]
fn then_project_multiple(world: &mut TaskulusWorld) {
    let error = world.project_error.as_deref().unwrap_or("");
    assert!(error.contains("multiple projects found"));
}

#[then("configuration path lookup should fail with \"project not initialized\"")]
fn then_configuration_path_missing(world: &mut TaskulusWorld) {
    assert_eq!(
        world.project_error.as_deref(),
        Some("project not initialized")
    );
}

#[then("project discovery should fail with \"Permission denied\"")]
fn then_project_permission_denied(world: &mut TaskulusWorld) {
    let error = world.project_error.as_deref().unwrap_or("");
    assert!(error.contains("Permission denied"));
}

#[then("project discovery should fail with \"taskulus path not found\"")]
fn then_project_missing(world: &mut TaskulusWorld) {
    let error = world.project_error.as_ref().expect("error");
    assert!(error.starts_with("taskulus path not found"));
}

#[then("project discovery should fail with \"unknown configuration fields\"")]
fn then_project_unknown_fields(world: &mut TaskulusWorld) {
    assert_eq!(
        world.project_error.as_deref(),
        Some("unknown configuration fields")
    );
}

#[then("project discovery should include the referenced path")]
fn then_project_includes_path(world: &mut TaskulusWorld) {
    let expected = world.expected_project_dir.as_ref().expect("expected");
    let expected = expected.canonicalize().unwrap_or_else(|_| expected.clone());
    let dirs = world.project_dirs.as_ref().expect("dirs");
    let normalized = dirs
        .iter()
        .map(|dir| dir.canonicalize().unwrap_or_else(|_| dir.clone()))
        .collect::<Vec<_>>();
    assert!(normalized.contains(&expected));
}

#[then("project discovery should return no projects")]
fn then_project_returns_none(world: &mut TaskulusWorld) {
    let dirs = world.project_dirs.as_ref().expect("dirs");
    assert!(dirs.is_empty());
}

#[then("issues from all discovered projects should be listed")]
fn then_issues_from_discovered_projects(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("Root task"));
    assert!(stdout.contains("Nested task"));
}

#[then("no issues should be listed")]
fn then_no_issues_listed(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.trim().is_empty());
}

#[then("local issues should be included")]
fn then_local_issues_included(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("Shared task"));
    assert!(stdout.contains("Local task"));
}

#[then("local issues should not be listed")]
fn then_local_issues_excluded(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("Shared task"));
    assert!(!stdout.contains("Local task"));
}

#[then("only local issues should be listed")]
fn then_only_local_issues_listed(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("Local task"));
    assert!(!stdout.contains("Shared task"));
}

#[then("issues from the referenced project should be listed")]
fn then_issues_from_referenced_project(world: &mut TaskulusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("External task"));
}
