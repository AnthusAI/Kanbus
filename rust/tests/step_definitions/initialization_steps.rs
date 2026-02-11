use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then, when, World};
use tempfile::TempDir;

use taskulus::cli::run_from_args;

#[derive(Debug, Default, World)]
pub struct TaskulusWorld {
    temp_dir: Option<TempDir>,
    working_directory: Option<PathBuf>,
    exit_code: Option<i32>,
    stderr: Option<String>,
}

fn run_cli(world: &mut TaskulusWorld, command: &str) {
    let args: Vec<&str> = command.split_whitespace().collect();
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args(args, cwd.as_path()) {
        Ok(()) => {
            world.exit_code = Some(0);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
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
    fs::write(repo_path.join(".taskulus.yaml"), "project_dir: project\n").expect("write marker");
    fs::create_dir_all(repo_path.join("project")).expect("create project");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[when("I run \"tsk init\"")]
fn when_run_tsk_init(world: &mut TaskulusWorld) {
    run_cli(world, "tsk init");
}

#[when("I run \"tsk init --dir tracking\"")]
fn when_run_tsk_init_custom(world: &mut TaskulusWorld) {
    run_cli(world, "tsk init --dir tracking");
}

#[then("a \".taskulus.yaml\" file should exist in the repository root")]
fn then_marker_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join(".taskulus.yaml").is_file());
}

#[then("a \".taskulus.yaml\" file should exist pointing to \"tracking\"")]
fn then_marker_points_tracking(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let contents = fs::read_to_string(cwd.join(".taskulus.yaml")).expect("read marker");
    assert!(contents.contains("project_dir: tracking"));
}

#[then("a \"project\" directory should exist")]
fn then_project_directory_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("project").is_dir());
}

#[then("a \"tracking\" directory should exist")]
fn then_tracking_directory_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("tracking").is_dir());
}

#[then("a \"project/config.yaml\" file should exist with default configuration")]
fn then_default_config_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("project").join("config.yaml").is_file());
}

#[then("a \"tracking/config.yaml\" file should exist with default configuration")]
fn then_default_config_exists_tracking(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("tracking").join("config.yaml").is_file());
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

#[then("a \"project/wiki\" directory should exist")]
fn then_wiki_directory_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("project").join("wiki").is_dir());
}

#[then("a \"project/wiki/index.md\" file should exist")]
fn then_wiki_index_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join("project").join("wiki").join("index.md").is_file());
}

#[then("a \"project/.cache\" directory should not exist yet")]
fn then_cache_not_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(!cwd.join("project").join(".cache").exists());
}

#[then("the command should fail with exit code 1")]
fn then_command_failed(world: &mut TaskulusWorld) {
    assert_eq!(world.exit_code, Some(1));
}

#[then("stderr should contain \"already initialized\"")]
fn then_stderr_contains_initialized(world: &mut TaskulusWorld) {
    let stderr = world.stderr.as_ref().expect("stderr");
    assert!(stderr.contains("already initialized"));
}

#[then("stderr should contain \"not a git repository\"")]
fn then_stderr_contains_not_git(world: &mut TaskulusWorld) {
    let stderr = world.stderr.as_ref().expect("stderr");
    assert!(stderr.contains("not a git repository"));
}
