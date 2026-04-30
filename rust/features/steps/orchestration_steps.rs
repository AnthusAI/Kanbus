use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use cucumber::{given, when};

use kanbus::cli::run_from_args_with_output;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given("a local orchestration target repository")]
fn given_local_orchestration_target_repository(world: &mut KanbusWorld) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory")
        .join("target-repo");
    fs::create_dir_all(&root).expect("create target repo");
    run_git(&root, &["init"]);
    run_git(&root, &["checkout", "-b", "develop"]);
    fs::write(root.join("README.md"), "target repository\n").expect("write readme");
    run_git(&root, &["add", "."]);
    run_git(
        &root,
        &[
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "Initial develop commit",
        ],
    );
    world.orchestration_target_repo = Some(root);
}

#[given(expr = "an orchestration workflow {string} with publish mode {string}")]
fn given_orchestration_workflow_with_publish_mode(
    world: &mut KanbusWorld,
    filename: String,
    publish_mode: String,
) {
    write_orchestration_workflow(
        world,
        &filename,
        &publish_mode,
        workspace_root_outside(world),
    );
}

#[given(
    expr = "an orchestration workflow {string} with workspace root inside the Kanbus repository"
)]
fn given_orchestration_workflow_with_workspace_root_inside_repo(
    world: &mut KanbusWorld,
    filename: String,
) {
    let root = world.working_directory.as_ref().expect("working directory");
    write_orchestration_workflow(
        world,
        &filename,
        "push-only",
        root.join("unsafe-workspaces"),
    );
}

#[given(expr = "an orchestration workflow {string} with worker branch pattern {string}")]
fn given_orchestration_workflow_with_worker_branch_pattern(
    world: &mut KanbusWorld,
    filename: String,
    branch_pattern: String,
) {
    write_orchestration_workflow_with_branch(
        world,
        &filename,
        "push-only",
        workspace_root_outside(world),
        &branch_pattern,
    );
}

#[given(expr = "a repository orchestration workflow preset {string}")]
fn given_repository_orchestration_workflow_preset(world: &mut KanbusWorld, name: String) {
    write_orchestration_workflow(
        world,
        &format!("workflows/{name}.md"),
        "push-only",
        workspace_root_outside(world),
    );
}

#[when(expr = "I run the orchestration worker for issue {string} with workflow {string}")]
fn when_run_orchestration_worker(world: &mut KanbusWorld, issue_id: String, workflow: String) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let target_repo = world
        .orchestration_target_repo
        .as_ref()
        .expect("target repo");
    let command = format!(
        "kanbus worker run {} --workflow {} --target-repo {}",
        issue_id,
        workflow,
        target_repo.to_string_lossy()
    );
    let args = shell_words::split(&command).expect("parse command");
    let result = run_from_args_with_output(args, cwd);
    match result {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(output.stderr);
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

fn write_orchestration_workflow(
    world: &KanbusWorld,
    filename: &str,
    publish_mode: &str,
    workspace_root: PathBuf,
) {
    write_orchestration_workflow_with_branch(
        world,
        filename,
        publish_mode,
        workspace_root,
        "agent/{{ issue.identifier }}/{{ run.short_id }}",
    );
}

fn write_orchestration_workflow_with_branch(
    world: &KanbusWorld,
    filename: &str,
    publish_mode: &str,
    workspace_root: PathBuf,
    branch_pattern: &str,
) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let fake_app_server = cwd.join("fake-app-server.sh");
    fs::write(
        &fake_app_server,
        r#"#!/bin/sh
while IFS= read -r line; do
  id=$(printf '%s' "$line" | sed -n 's/.*"id":\([0-9][0-9]*\).*/\1/p')
  method=$(printf '%s' "$line" | sed -n 's/.*"method":"\([^"]*\)".*/\1/p')
  if [ "$method" = "thread/start" ]; then
    printf '{"id":%s,"result":{"thread":{"id":"thread-1"}}}\n' "$id"
  elif [ "$method" = "turn/start" ]; then
    printf '{"id":%s,"result":{"turn":{"id":"turn-1"}}}\n' "$id"
    printf '{"method":"turn/completed","params":{"threadId":"thread-1","turn":{"id":"turn-1"}}}\n'
  else
    printf '{"id":%s,"result":{}}\n' "$id"
  fi
done
"#,
    )
    .expect("write fake app server");
    run_command(cwd, Command::new("chmod").arg("+x").arg(&fake_app_server));
    let target_repo = world
        .orchestration_target_repo
        .as_ref()
        .map(|path| format!("  repo: {}\n", path.to_string_lossy()))
        .unwrap_or_default();
    let workflow = format!(
        "---\ntarget:\n{}  branch: develop\n  validation: \"true\"\n  publish: {publish_mode}\nworkspace:\n  root: {}\nworker:\n  branch_pattern: {}\ncodex:\n  command: {}\n---\nDo harmless work for {{{{ issue.identifier }}}}.\n",
        target_repo,
        workspace_root.to_string_lossy(),
        branch_pattern,
        fake_app_server.to_string_lossy()
    );
    let path = cwd.join(filename);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).expect("create workflow parent");
    }
    fs::write(path, workflow).expect("write workflow");
}

fn workspace_root_outside(world: &KanbusWorld) -> PathBuf {
    world
        .working_directory
        .as_ref()
        .expect("working directory")
        .parent()
        .expect("working directory parent")
        .join("orchestration-workspaces")
}

fn run_git(root: &Path, args: &[&str]) {
    let mut command = Command::new("git");
    command.args(args);
    run_command(root, &mut command);
}

fn run_command(root: &Path, command: &mut Command) {
    let output = command.current_dir(root).output().expect("run command");
    assert!(
        output.status.success(),
        "command failed\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}
