use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::thread::JoinHandle;
use std::time::SystemTime;

use cucumber::{given, then, World};
use tempfile::TempDir;

use crate::step_definitions::console_ui_steps::{ConsoleLocalStorage, ConsoleState};
use kanbus::daemon_client;
use kanbus::index::IssueIndex;
use kanbus::models::ProjectConfiguration;
use serde_json::Value;

#[derive(Debug, Default, World)]
pub struct KanbusWorld {
    pub temp_dir: Option<TempDir>,
    pub working_directory: Option<PathBuf>,
    pub exit_code: Option<i32>,
    pub stdout: Option<String>,
    pub stderr: Option<String>,
    pub configuration: Option<ProjectConfiguration>,
    pub generated_id: Option<String>,
    pub generated_ids: Option<HashSet<String>>,
    pub id_generation_error: Option<String>,
    pub id_prefix: Option<String>,
    pub existing_ids: Option<HashSet<String>>,
    pub project_dirs: Option<Vec<PathBuf>>,
    pub project_error: Option<String>,
    pub cache_path: Option<PathBuf>,
    pub cache_mtime: Option<SystemTime>,
    pub daemon_spawned: bool,
    pub daemon_connected: bool,
    pub stale_socket_removed: bool,
    pub stale_socket_mtime: Option<SystemTime>,
    pub daemon_rebuilt_index: bool,
    pub daemon_simulation: bool,
    pub protocol_errors: Vec<String>,
    pub protocol_error: Option<String>,
    pub daemon_response_code: Option<String>,
    pub daemon_response_status: Option<String>,
    pub daemon_error_message: Option<String>,
    pub daemon_index_issues: Option<Vec<String>>,
    pub daemon_status_payload: Option<BTreeMap<String, Value>>,
    pub daemon_spawn_called: bool,
    pub daemon_entry_running: bool,
    pub daemon_list_error: bool,
    pub local_listing_error: bool,
    pub daemon_use_real: bool,
    pub ready_issue_ids: Option<Vec<String>>,
    pub shared_only_results: Option<Vec<String>>,
    pub expected_project_dir: Option<PathBuf>,
    pub expected_project_path: Option<PathBuf>,
    pub force_empty_projects: bool,
    pub migration_errors: Vec<String>,
    pub workflow_error: Option<String>,
    pub index: Option<IssueIndex>,
    pub daemon_thread: Option<JoinHandle<()>>,
    pub daemon_fake_server: bool,
    pub daemon_mode_disabled: bool,
    pub current_user: Option<String>,
    pub original_kanbus_user: Option<Option<String>>,
    pub original_user_env: Option<Option<String>>,
    pub original_canonicalize_failure_env: Option<Option<String>>,
    pub original_configuration_path_failure_env: Option<Option<String>>,
    pub original_local_listing_env: Option<Option<String>>,
    pub formatted_output: Option<String>,
    pub display_context: Option<String>,
    pub formatted_issue_key: Option<String>,
    pub last_beads_issue_id: Option<String>,
    pub existing_kanbus_ids: Option<HashSet<String>>,
    pub last_kanbus_issue_id: Option<String>,
    pub unreadable_path: Option<PathBuf>,
    pub unreadable_mode: Option<u32>,
    pub console_state: Option<ConsoleState>,
    pub console_local_storage: ConsoleLocalStorage,
    pub console_time_zone: Option<String>,
    pub console_port: Option<u16>,
}

impl Drop for KanbusWorld {
    fn drop(&mut self) {
        kanbus::beads_write::set_test_beads_slug_sequence(None);
        kanbus::ids::set_test_uuid_sequence(None);
        if let Some(handle) = self.daemon_thread.take() {
            if !self.daemon_fake_server {
                if let Some(root) = self.working_directory.as_ref() {
                    let _ = daemon_client::request_shutdown(root);
                }
            }
            let _ = handle.join();
        }
        if let (Some(path), Some(mode)) = (self.unreadable_path.take(), self.unreadable_mode) {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Ok(mut permissions) = fs::metadata(&path).map(|meta| meta.permissions()) {
                    permissions.set_mode(mode);
                    let _ = fs::set_permissions(&path, permissions);
                }
            }
        }
        if let Some(original) = self.original_kanbus_user.take() {
            match original {
                Some(value) => std::env::set_var("KANBUS_USER", value),
                None => std::env::remove_var("KANBUS_USER"),
            }
        }
        if let Some(original) = self.original_user_env.take() {
            match original {
                Some(value) => std::env::set_var("USER", value),
                None => std::env::remove_var("USER"),
            }
        }
        if let Some(original) = self.original_canonicalize_failure_env.take() {
            match original {
                Some(value) => std::env::set_var("KANBUS_TEST_CANONICALIZE_FAILURE", value),
                None => std::env::remove_var("KANBUS_TEST_CANONICALIZE_FAILURE"),
            }
        }
        if let Some(original) = self.original_configuration_path_failure_env.take() {
            match original {
                Some(value) => std::env::set_var("KANBUS_TEST_CONFIGURATION_PATH_FAILURE", value),
                None => std::env::remove_var("KANBUS_TEST_CONFIGURATION_PATH_FAILURE"),
            }
        }
        if let Some(original) = self.original_local_listing_env.take() {
            match original {
                Some(value) => std::env::set_var("KANBUS_TEST_LOCAL_LISTING_ERROR", value),
                None => std::env::remove_var("KANBUS_TEST_LOCAL_LISTING_ERROR"),
            }
        }
        daemon_client::set_test_daemon_response(None);
        daemon_client::set_test_daemon_spawn_disabled(false);
    }
}

#[given("an empty git repository")]
fn given_empty_git_repository(world: &mut KanbusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a directory that is not a git repository")]
fn given_directory_not_git_repository(world: &mut KanbusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("not-a-repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with an existing Kanbus project")]
fn given_existing_kanbus_project(world: &mut KanbusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("existing");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    fs::create_dir_all(repo_path.join("project").join("issues")).expect("create project");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository metadata directory")]
fn given_git_metadata_directory(world: &mut KanbusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("metadata");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path.join(".git"));
    world.temp_dir = Some(temp_dir);
}

#[then("a \".kanbus.yml\" file should be created")]
fn then_marker_created(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join(".kanbus.yml").is_file());
}

#[then("a \"CONTRIBUTING_AGENT.template.md\" file should be created")]
fn then_project_management_template_created(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("CONTRIBUTING_AGENT.template.md").is_file());
}

#[then(expr = "CONTRIBUTING_AGENT.template.md should contain {string}")]
fn then_project_management_template_contains_text(world: &mut KanbusWorld, text: String) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let content = fs::read_to_string(cwd.join("CONTRIBUTING_AGENT.template.md"))
        .expect("read project management template");
    let normalized = text.replace("\\\"", "\"");
    assert!(content.contains(&normalized));
}

#[then("a \"project\" directory should exist")]
fn then_project_directory_exists(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("project").is_dir());
}

#[then("a \"project/config.yaml\" file should not exist")]
fn then_default_config_missing(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(!cwd.join("project").join("config.yaml").exists());
}

#[then("a \"project/issues\" directory should exist and be empty")]
fn then_issues_directory_empty(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let issues_dir = cwd.join("project").join("issues");
    assert!(issues_dir.is_dir());
    assert!(issues_dir
        .read_dir()
        .expect("read issues dir")
        .next()
        .is_none());
}

#[then("a \"project/wiki\" directory should not exist")]
fn then_wiki_directory_missing(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(!cwd.join("project").join("wiki").exists());
}

#[then("a \"project-local/issues\" directory should exist")]
fn then_local_issues_directory_exists(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("project-local").join("issues").is_dir());
}

#[then("the command should fail with exit code 1")]
fn then_command_failed(world: &mut KanbusWorld) {
    assert_eq!(world.exit_code, Some(1));
}

#[then("the command should fail")]
fn then_command_failed_generic(world: &mut KanbusWorld) {
    assert_ne!(world.exit_code, Some(0));
}

#[then("project/AGENTS.md should be created with the warning")]
fn then_project_agents_created(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let path = cwd.join("project").join("AGENTS.md");
    assert!(path.is_file());
    let content = std::fs::read_to_string(path).expect("read project AGENTS");
    assert!(content.contains("DO NOT EDIT HERE"));
    assert!(content.contains("sin against The Way"));
}

#[then("project/DO_NOT_EDIT should be created with the warning")]
fn then_project_do_not_edit_created(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let path = cwd.join("project").join("DO_NOT_EDIT");
    assert!(path.is_file());
    let content = std::fs::read_to_string(path).expect("read DO_NOT_EDIT");
    assert!(content.contains("DO NOT EDIT ANYTHING IN project/"));
    assert!(content.contains("The Way"));
}
