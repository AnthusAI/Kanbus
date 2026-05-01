use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use cucumber::{given, then, when};

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

#[given(expr = "an orchestration workflow {string} with worker runtime {string}")]
fn given_orchestration_workflow_with_worker_runtime(
    world: &mut KanbusWorld,
    filename: String,
    runtime: String,
) {
    write_orchestration_workflow_with_runtime(
        world,
        &filename,
        "push-only",
        workspace_root_outside(world),
        "agent/{{ issue.identifier }}/{{ run.short_id }}",
        &runtime,
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

#[given("repo-level orchestration config")]
fn given_repo_level_orchestration_config(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let fake_app_server = write_fake_app_server(cwd);
    let target_repo = world
        .orchestration_target_repo
        .as_ref()
        .expect("target repo");
    let config_path = cwd.join(".kanbus.yml");
    append_repo_orchestration_config(
        &config_path,
        &format!(
            "orchestration:\n  target:\n    repo: {}\n    branch: develop\n    validation: \"true\"\n    publish: push-only\n  workspace:\n    root: {}\n  worker:\n    branch_pattern: agent/{{{{ issue.identifier }}}}/{{{{ run.short_id }}}}\n  codex:\n    command: {}\n",
            target_repo.to_string_lossy(),
            workspace_root_outside(world).to_string_lossy(),
            fake_app_server.to_string_lossy()
        ),
    );
}

fn append_repo_orchestration_config(config_path: &Path, orchestration_block: &str) {
    let config = fs::read_to_string(config_path).expect("read config");
    let mut config = config.replace("\norchestration: null\n", "\n");
    config.push('\n');
    config.push_str(orchestration_block);
    fs::write(config_path, config).expect("write config");
}

#[given("repo-level orchestration config using the Tactus worker runtime")]
fn given_repo_level_tactus_orchestration_config(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let fake_tactus_python = write_fake_tactus_python(cwd);
    let target_repo = world
        .orchestration_target_repo
        .as_ref()
        .expect("target repo");
    let config_path = cwd.join(".kanbus.yml");
    append_repo_orchestration_config(
        &config_path,
        &format!(
            "orchestration:\n  target:\n    repo: {}\n    branch: develop\n    validation: \"true\"\n    publish: push-only\n  workspace:\n    root: {}\n  worker:\n    branch_pattern: agent/{{{{ issue.identifier }}}}/{{{{ run.short_id }}}}\n    runtime: tactus\n    procedure:\n      runtime: tactus\n      command: {}\n      source: |\n        Procedure {{}}\n",
            target_repo.to_string_lossy(),
            workspace_root_outside(world).to_string_lossy(),
            fake_tactus_python.to_string_lossy()
        ),
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

#[when(expr = "I run the orchestration worker for issue {string} without a workflow")]
fn when_run_orchestration_worker_without_workflow(world: &mut KanbusWorld, issue_id: String) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let command = format!("kanbus worker run {issue_id}");
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
    write_orchestration_workflow_with_runtime(
        world,
        filename,
        publish_mode,
        workspace_root,
        branch_pattern,
        "codex-app-server",
    );
}

fn write_orchestration_workflow_with_runtime(
    world: &KanbusWorld,
    filename: &str,
    publish_mode: &str,
    workspace_root: PathBuf,
    branch_pattern: &str,
    worker_runtime: &str,
) {
    let cwd = world.working_directory.as_ref().expect("working directory");
    let fake_app_server = write_fake_app_server(cwd);
    let target_repo = world
        .orchestration_target_repo
        .as_ref()
        .map(|path| format!("  repo: {}\n", path.to_string_lossy()))
        .unwrap_or_default();
    let workflow = format!(
        "---\ntarget:\n{}  branch: develop\n  validation: \"true\"\n  publish: {publish_mode}\nworkspace:\n  root: {}\nworker:\n  branch_pattern: {}\n  runtime: {}\ncodex:\n  command: {}\n---\nDo harmless work for {{{{ issue.identifier }}}}.\n",
        target_repo,
        workspace_root.to_string_lossy(),
        branch_pattern,
        worker_runtime,
        fake_app_server.to_string_lossy()
    );
    let path = cwd.join(filename);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).expect("create workflow parent");
    }
    fs::write(path, workflow).expect("write workflow");
}

fn write_fake_app_server(cwd: &Path) -> PathBuf {
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
    fake_app_server
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

#[then(expr = "the target checkout should not contain {string}")]
fn then_target_checkout_should_not_contain(world: &mut KanbusWorld, relative_path: String) {
    let root = workspace_root_outside(world);
    if !root.exists() {
        return;
    }
    assert!(
        !contains_relative_path(&root, Path::new(&relative_path)),
        "target checkout contains {relative_path}"
    );
}

#[then("the generic Tactus worker should expose constrained edit tools")]
fn then_generic_tactus_worker_exposes_constrained_edit_tools(_: &mut KanbusWorld) {
    let source = read_generic_tactus_worker_source();
    assert!(source.contains("append_text = Tool"));
    assert!(source.contains("replace_text = Tool"));
    assert!(source.contains("create_file = Tool"));
}

#[then("the generic Tactus worker should not expose an existing-file overwrite tool")]
fn then_generic_tactus_worker_has_no_existing_file_overwrite_tool(_: &mut KanbusWorld) {
    let source = read_generic_tactus_worker_source();
    assert!(!source.contains("tools = {read_file, write_file"));
}

fn read_generic_tactus_worker_source() -> String {
    let repo_root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("repo root");
    fs::read_to_string(repo_root.join("workflows/kanbus-worker.tac"))
        .expect("read worker procedure")
}

fn write_fake_tactus_python(cwd: &Path) -> PathBuf {
    let fake_python = cwd.join("fake-tactus-python.sh");
    fs::write(
        &fake_python,
        r#"#!/bin/sh
if [ "$1" != "-c" ]; then
  echo "expected -c" >&2
  exit 1
fi
script="$2"
payload=$(cat)
case "$script" in
  *"def append_text(self, path, text):"*) ;;
  *) echo "missing append_text host tool" >&2; exit 2 ;;
esac
case "$script" in
  *"def replace_text(self, path, old_text, new_text):"*) ;;
  *) echo "missing replace_text host tool" >&2; exit 3 ;;
esac
case "$script" in
  *"def write_file(self, path, content):"*) echo "unsafe write_file host tool exposed" >&2; exit 4 ;;
esac
case "$payload" in
  *"\"storage_dir\":\""*".kanbus-capabilities/tactus/worker\""*) ;;
  *) echo "worker storage is not outside target checkout" >&2; exit 5 ;;
esac
printf '{"status":"completed","summary":"fake tactus worker","changed_files":[],"notes":[]}\n'
"#,
    )
    .expect("write fake tactus python");
    run_command(cwd, Command::new("chmod").arg("+x").arg(&fake_python));
    fake_python
}

fn contains_relative_path(root: &Path, relative_path: &Path) -> bool {
    let entries = fs::read_dir(root).expect("read directory");
    for entry in entries {
        let path = entry.expect("directory entry").path();
        if path.ends_with(relative_path) {
            return true;
        }
        if path.is_dir() && contains_relative_path(&path, relative_path) {
            return true;
        }
    }
    false
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
