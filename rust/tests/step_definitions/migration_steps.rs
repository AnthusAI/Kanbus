use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use cucumber::{given, then, when};

use taskulus::cli::run_from_args_with_output;

use crate::step_definitions::initialization_steps::TaskulusWorld;

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

fn fixture_beads_dir() -> PathBuf {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("repo root");
    root.join("specs")
        .join("fixtures")
        .join("beads_repo")
        .join(".beads")
}

fn copy_dir(source: &Path, destination: &Path) {
    fs::create_dir_all(destination).expect("create destination");
    for entry in fs::read_dir(source).expect("read source") {
        let entry = entry.expect("entry");
        let path = entry.path();
        let target = destination.join(entry.file_name());
        if path.is_dir() {
            copy_dir(&path, &target);
        } else {
            fs::copy(&path, &target).expect("copy file");
        }
    }
}

fn load_project_dir(world: &TaskulusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let contents = fs::read_to_string(cwd.join(".taskulus.yaml")).expect("read marker");
    let marker: serde_yaml::Value = serde_yaml::from_str(&contents).expect("parse marker");
    let project_dir = marker
        .get("project_dir")
        .and_then(|value| value.as_str())
        .expect("project_dir");
    cwd.join(project_dir)
}

#[given("a git repository with a .beads issues database")]
fn given_repo_with_beads(world: &mut TaskulusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    let target_beads = repo_path.join(".beads");
    copy_dir(&fixture_beads_dir(), &target_beads);
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

#[given("a Taskulus project already exists")]
fn given_taskulus_project_exists(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let marker_path = cwd.join(".taskulus.yaml");
    fs::write(marker_path, "project_dir: project\n").expect("write marker");
    fs::create_dir_all(cwd.join("project")).expect("create project");
}

#[given("a git repository without a .beads directory")]
fn given_repo_without_beads(world: &mut TaskulusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
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

#[when("I run \"tsk migrate\"")]
fn when_run_migrate(world: &mut TaskulusWorld) {
    run_cli(world, "tsk migrate");
}

#[then("a Taskulus project should be initialized")]
fn then_taskulus_initialized(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    assert!(cwd.join(".taskulus.yaml").is_file());
    let project_dir = load_project_dir(world);
    assert!(project_dir.is_dir());
}

#[then("all Beads issues should be converted to Taskulus issues")]
fn then_beads_converted(world: &mut TaskulusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let issues_path = cwd.join(".beads").join("issues.jsonl");
    let contents = fs::read_to_string(issues_path).expect("read issues");
    let line_count = contents
        .lines()
        .filter(|line| !line.trim().is_empty())
        .count();
    let project_dir = load_project_dir(world);
    let issue_files = fs::read_dir(project_dir.join("issues"))
        .expect("read issues dir")
        .filter_map(|entry| entry.ok())
        .filter(|entry| entry.path().extension().and_then(|ext| ext.to_str()) == Some("json"))
        .count();
    assert_eq!(issue_files, line_count);
}

#[then("stderr should contain \"no .beads directory\"")]
fn then_missing_beads_dir(world: &mut TaskulusWorld) {
    let stderr = world.stderr.as_ref().expect("stderr");
    assert!(stderr.contains("no .beads directory"));
}
