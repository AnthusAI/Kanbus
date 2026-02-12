use std::collections::HashSet;
use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::time::SystemTime;
use std::thread::JoinHandle;

use cucumber::{given, then, when, World};
use tempfile::TempDir;

use taskulus::cli::run_from_args_with_output;
use taskulus::index::IssueIndex;
use taskulus::models::ProjectConfiguration;
use taskulus::daemon_client;

#[derive(Debug, Default, World)]
pub struct TaskulusWorld {
    pub temp_dir: Option<TempDir>,
    pub working_directory: Option<PathBuf>,
    pub exit_code: Option<i32>,
    pub stdout: Option<String>,
    pub stderr: Option<String>,
    pub configuration: Option<ProjectConfiguration>,
    pub generated_id: Option<String>,
    pub generated_ids: Option<HashSet<String>>,
    pub id_prefix: Option<String>,
    pub existing_ids: Option<HashSet<String>>,
    pub project_dirs: Option<Vec<PathBuf>>,
    pub project_error: Option<String>,
    pub cache_path: Option<PathBuf>,
    pub cache_mtime: Option<SystemTime>,
    pub daemon_spawned: bool,
    pub daemon_connected: bool,
    pub stale_socket_removed: bool,
    pub daemon_rebuilt_index: bool,
    pub daemon_simulation: bool,
    pub protocol_errors: Vec<String>,
    pub protocol_error: Option<String>,
    pub daemon_response_code: Option<String>,
    pub daemon_error_message: Option<String>,
    pub daemon_index_issues: Option<Vec<String>>,
    pub daemon_spawn_called: bool,
    pub daemon_entry_running: bool,
    pub daemon_list_error: bool,
    pub local_listing_error: bool,
    pub shared_only_results: Option<Vec<String>>,
    pub expected_project_dir: Option<PathBuf>,
    pub expected_project_path: Option<PathBuf>,
    pub force_empty_projects: bool,
    pub hash_sequence: Option<Vec<String>>,
    pub random_bytes_override: Option<String>,
    pub migration_errors: Vec<String>,
    pub workflow_error: Option<String>,
    pub index: Option<IssueIndex>,
    pub daemon_thread: Option<JoinHandle<()>>,
    pub daemon_fake_server: bool,
    pub daemon_mode_disabled: bool,
    pub current_user: Option<String>,
    pub original_taskulus_user: Option<Option<String>>,
    pub original_user_env: Option<Option<String>>,
    pub formatted_output: Option<String>,
}

impl Drop for TaskulusWorld {
    fn drop(&mut self) {
        if let Some(handle) = self.daemon_thread.take() {
            if !self.daemon_fake_server {
                if let Some(root) = self.working_directory.as_ref() {
                    let _ = daemon_client::request_shutdown(root);
                }
            }
            let _ = handle.join();
        }
        if let Some(original) = self.original_taskulus_user.take() {
            match original {
                Some(value) => std::env::set_var("TASKULUS_USER", value),
                None => std::env::remove_var("TASKULUS_USER"),
            }
        }
        if let Some(original) = self.original_user_env.take() {
            match original {
                Some(value) => std::env::set_var("USER", value),
                None => std::env::remove_var("USER"),
            }
        }
    }
}

fn run_cli(world: &mut TaskulusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse command");
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

#[given("an empty git repository")]
fn given_empty_git_repository(world: &mut TaskulusWorld) {
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
fn given_directory_not_git_repository(world: &mut TaskulusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("not-a-repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a git repository with an existing Taskulus project")]
fn given_existing_taskulus_project(world: &mut TaskulusWorld) {
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
fn given_git_metadata_directory(world: &mut TaskulusWorld) {
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

#[when("I run \"tsk init\"")]
fn when_run_tsk_init(world: &mut TaskulusWorld) {
    run_cli(world, "tsk init");
}

#[when("I run \"tsk init --local\"")]
fn when_run_tsk_init_local(world: &mut TaskulusWorld) {
    run_cli(world, "tsk init --local");
}

#[then("a \".taskulus.yaml\" file should not exist")]
fn then_marker_missing(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(!cwd.join(".taskulus.yaml").exists());
}

#[then("a \"project\" directory should exist")]
fn then_project_directory_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("project").is_dir());
}

#[then("a \"project/config.yaml\" file should not exist")]
fn then_default_config_missing(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(!cwd.join("project").join("config.yaml").exists());
}

#[then("a \"project/issues\" directory should exist and be empty")]
fn then_issues_directory_empty(world: &mut TaskulusWorld) {
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
fn then_wiki_directory_missing(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(!cwd.join("project").join("wiki").exists());
}

#[then("a \"project-local/issues\" directory should exist")]
fn then_local_issues_directory_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("project-local").join("issues").is_dir());
}

#[then("the command should fail with exit code 1")]
fn then_command_failed(world: &mut TaskulusWorld) {
    assert_eq!(world.exit_code, Some(1));
}

#[then("the command should fail")]
fn then_command_failed_generic(world: &mut TaskulusWorld) {
    assert_ne!(world.exit_code, Some(0));
}
