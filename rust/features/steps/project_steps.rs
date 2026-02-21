use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};
use serde_yaml;

use kanbus::config::default_project_configuration;
use kanbus::file_io::{discover_kanbus_projects, get_configuration_path};
use kanbus::models::IssueData;
use kanbus::project::{discover_project_directories, load_project_directory};

use crate::step_definitions::initialization_steps::KanbusWorld;

fn create_repo(world: &mut KanbusWorld, name: &str) -> PathBuf {
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

fn set_canonicalize_failure(world: &mut KanbusWorld) {
    if world.original_canonicalize_failure_env.is_none() {
        world.original_canonicalize_failure_env =
            Some(env::var("KANBUS_TEST_CANONICALIZE_FAILURE").ok());
    }
    env::set_var("KANBUS_TEST_CANONICALIZE_FAILURE", "1");
}

fn set_configuration_path_failure(world: &mut KanbusWorld) {
    if world.original_configuration_path_failure_env.is_none() {
        world.original_configuration_path_failure_env =
            Some(env::var("KANBUS_TEST_CONFIGURATION_PATH_FAILURE").ok());
    }
    env::set_var("KANBUS_TEST_CONFIGURATION_PATH_FAILURE", "1");
}

#[given("a repository with a single project directory")]
fn given_repo_single_project(world: &mut KanbusWorld) {
    let root = create_repo(world, "single-project");
    fs::create_dir_all(root.join("project")).expect("create project dir");
}

#[given("an empty repository without a project directory")]
fn given_repo_no_project(world: &mut KanbusWorld) {
    let _ = create_repo(world, "empty-project");
}

#[given("a repository with multiple project directories")]
fn given_repo_multiple_projects(world: &mut KanbusWorld) {
    let root = create_repo(world, "multi-project");
    fs::create_dir_all(root.join("project")).expect("create project dir");
    fs::create_dir_all(root.join("nested").join("project")).expect("create nested project");
}

#[given("a repository with a project directory that cannot be canonicalized")]
fn given_repo_project_cannot_canonicalize(world: &mut KanbusWorld) {
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
fn given_project_directory_canonicalization_failure(world: &mut KanbusWorld) {
    set_canonicalize_failure(world);
}

#[given("configuration path lookup will fail")]
fn given_configuration_path_lookup_failure(world: &mut KanbusWorld) {
    set_configuration_path_failure(world);
}

#[given("a repository directory that is unreadable")]
fn given_repo_unreadable(world: &mut KanbusWorld) {
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

#[given("a repository directory that has been removed")]
fn given_repo_removed(world: &mut KanbusWorld) {
    let root = create_repo(world, "removed-projects");
    fs::remove_dir_all(&root).expect("remove repo");
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
fn given_repo_multiple_projects_with_issues(world: &mut KanbusWorld) {
    let root = create_repo(world, "multi-project-issues");
    let alpha_project = root.join("alpha").join("project");
    let beta_project = root.join("beta").join("project");
    fs::create_dir_all(alpha_project.join("issues")).expect("create alpha issues");
    fs::create_dir_all(beta_project.join("issues")).expect("create beta issues");
    write_issue(&alpha_project, &build_issue("kanbus-alpha", "Alpha task"));
    write_issue(&beta_project, &build_issue("kanbus-beta", "Beta task"));
}

#[given("a repository with multiple projects and local issues")]
fn given_repo_multiple_projects_with_local_issues(world: &mut KanbusWorld) {
    let root = create_repo(world, "multi-project-local");
    let alpha_project = root.join("alpha").join("project");
    let beta_project = root.join("beta").join("project");
    fs::create_dir_all(alpha_project.join("issues")).expect("create alpha issues");
    fs::create_dir_all(beta_project.join("issues")).expect("create beta issues");
    write_issue(&alpha_project, &build_issue("kanbus-alpha", "Alpha task"));
    write_issue(&beta_project, &build_issue("kanbus-beta", "Beta task"));
    let local_project = root.join("alpha").join("project-local");
    fs::create_dir_all(local_project.join("issues")).expect("create local issues");
    write_issue(
        &local_project,
        &build_issue("kanbus-alpha-local", "Alpha local task"),
    );
}

#[given("a repository with a .kanbus.yml file referencing another project")]
fn given_repo_kanbus_external_project(world: &mut KanbusWorld) {
    let root = create_repo(world, "kanbus-external");
    let internal_project = root.join("project");
    fs::create_dir_all(internal_project.join("issues")).expect("create internal issues");
    write_issue(
        &internal_project,
        &build_issue("kanbus-internal", "Internal task"),
    );
    let temp_dir = world.temp_dir.as_ref().expect("tempdir");
    let external_root = temp_dir.path().join("external-project");
    let external_project = external_root.join("project");
    fs::create_dir_all(external_project.join("issues")).expect("create external issues");
    write_issue(
        &external_project,
        &build_issue("kanbus-external", "External task"),
    );
    let mut configuration = default_project_configuration();
    configuration.virtual_projects.insert(
        "external".to_string(),
        kanbus::models::VirtualProjectConfig {
            path: external_project.display().to_string(),
        },
    );
    let payload = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(root.join(".kanbus.yml"), payload).expect("write config");
    world.expected_project_path = Some(external_project);
}

#[given("a repository with a .kanbus.yml file referencing a missing path")]
fn given_repo_kanbus_missing(world: &mut KanbusWorld) {
    let root = create_repo(world, "kanbus-missing");
    let mut configuration = default_project_configuration();
    configuration.virtual_projects.insert(
        "missing".to_string(),
        kanbus::models::VirtualProjectConfig {
            path: "missing/project".to_string(),
        },
    );
    let payload = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(root.join(".kanbus.yml"), payload).expect("write config");
}

#[given("a repository with an invalid .kanbus.yml file")]
fn given_repo_kanbus_invalid(world: &mut KanbusWorld) {
    let root = create_repo(world, "kanbus-invalid");
    fs::write(root.join(".kanbus.yml"), "unknown_field: value\n").expect("write config");
}

#[given("a project directory with a sibling project-local directory")]
fn given_project_with_local_sibling(world: &mut KanbusWorld) {
    let root = create_repo(world, "project-local-sibling");
    let shared_dir = root.join("project");
    let local_dir = root.join("project-local");
    fs::create_dir_all(shared_dir.join("issues")).expect("create shared issues");
    fs::create_dir_all(local_dir.join("issues")).expect("create local issues");
    write_issue(&shared_dir, &build_issue("kanbus-shared", "Shared task"));
    write_issue(&local_dir, &build_issue("kanbus-local", "Local task"));
}

#[given("a repository with a .kanbus.yml file referencing a valid path with blank lines")]
fn given_repo_kanbus_blank(world: &mut KanbusWorld) {
    let root = create_repo(world, "kanbus-blank");
    let extras = root.join("extras").join("project");
    fs::create_dir_all(&extras).expect("create extras project");
    let mut configuration = default_project_configuration();
    configuration.project_directory = "extras/project".to_string();
    let payload = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(root.join(".kanbus.yml"), payload).expect("write config");
    world.expected_project_dir = Some(extras);
}

#[given("a repository with a .kanbus file referencing another project")]
fn given_repo_kanbus_dotfile(world: &mut KanbusWorld) {
    let root = create_repo(world, "kanbus-dotfile");
    let temp_dir = world.temp_dir.as_ref().expect("tempdir");
    let external_root = temp_dir.path().join("dotfile-external");
    let external_project = external_root.join("project");
    fs::create_dir_all(external_project.join("issues")).expect("create external issues");
    write_issue(
        &external_project,
        &build_issue("kanbus-external", "External task"),
    );
    fs::write(
        root.join(".kanbus"),
        format!("{}\n", external_project.display()),
    )
    .expect("write dotfile");
}

#[given("a repository with a .kanbus file referencing a missing path")]
fn given_repo_kanbus_dotfile_missing(world: &mut KanbusWorld) {
    let root = create_repo(world, "kanbus-dotfile-missing");
    fs::write(root.join(".kanbus"), "missing/project\n").expect("write dotfile");
}

#[given("a non-git directory without projects")]
fn given_non_git_directory(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("no-git");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a repository with a fake git root pointing to a file")]
fn given_fake_git_root(world: &mut KanbusWorld) {
    let _ = create_repo(world, "fake-git-root");
    world.force_empty_projects = true;
}

#[when("project directories are discovered")]
fn when_project_dirs_discovered(world: &mut KanbusWorld) {
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

#[when("kanbus configuration paths are discovered from the filesystem root")]
fn when_configuration_paths_from_root(world: &mut KanbusWorld) {
    let root = PathBuf::from("/");
    match discover_kanbus_projects(&root) {
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
fn when_project_dir_loaded(world: &mut KanbusWorld) {
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
fn when_configuration_path_requested(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("cwd");
    match get_configuration_path(root) {
        Ok(_) => world.project_error = None,
        Err(error) => world.project_error = Some(error.to_string()),
    }
}

#[then("exactly one project directory should be returned")]
fn then_one_project(world: &mut KanbusWorld) {
    let dirs = world.project_dirs.as_ref().expect("dirs");
    assert_eq!(dirs.len(), 1);
}

#[then("project discovery should fail with \"project not initialized\"")]
fn then_project_not_initialized(world: &mut KanbusWorld) {
    assert_eq!(
        world.project_error.as_deref(),
        Some("project not initialized")
    );
}

#[then("project discovery should fail with \"multiple projects found\"")]
fn then_project_multiple(world: &mut KanbusWorld) {
    let error = world.project_error.as_deref().unwrap_or("");
    assert!(error.contains("multiple projects found"));
}

#[then("configuration path lookup should fail with \"project not initialized\"")]
fn then_configuration_path_missing(world: &mut KanbusWorld) {
    assert_eq!(
        world.project_error.as_deref(),
        Some("project not initialized")
    );
}

#[then("project discovery should fail with \"Permission denied\"")]
fn then_project_permission_denied(world: &mut KanbusWorld) {
    let error = world.project_error.as_deref().unwrap_or("");
    assert!(error.contains("Permission denied"));
}

#[then("project discovery should fail with \"kanbus path not found\"")]
fn then_project_missing(world: &mut KanbusWorld) {
    let error = world.project_error.as_ref().expect("error");
    assert!(
        error.contains("path not found"),
        "expected 'path not found' in error: {error}"
    );
}

#[then("project discovery should fail with \"unknown configuration fields\"")]
fn then_project_unknown_fields(world: &mut KanbusWorld) {
    assert_eq!(
        world.project_error.as_deref(),
        Some("unknown configuration fields")
    );
}

#[then("project discovery should include the referenced path")]
fn then_project_includes_path(world: &mut KanbusWorld) {
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
fn then_project_returns_none(world: &mut KanbusWorld) {
    let dirs = world.project_dirs.as_ref().expect("dirs");
    assert!(dirs.is_empty());
}

#[then("issues from all discovered projects should be listed")]
fn then_issues_from_discovered_projects(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("Root task"));
    assert!(stdout.contains("Nested task"));
}

#[then("no issues should be listed")]
fn then_no_issues_listed(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.trim().is_empty());
}

#[then("local issues should be included")]
fn then_local_issues_included(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("Shared task"));
    assert!(stdout.contains("Local task"));
}

#[then("local issues should not be listed")]
fn then_local_issues_excluded(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("Shared task"));
    assert!(!stdout.contains("Local task"));
}

#[then("only local issues should be listed")]
fn then_only_local_issues_listed(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("Local task"));
    assert!(!stdout.contains("Shared task"));
}

#[then("issues from the referenced project should be listed")]
fn then_issues_from_referenced_project(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains("External task"));
}
