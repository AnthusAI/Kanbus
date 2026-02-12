use std::path::PathBuf;

use cucumber::{then, when};

use taskulus::cli::run_from_args_with_output;
use taskulus::file_io::load_project_directory;
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

fn load_project_dir(world: &TaskulusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

#[when("I run \"tsk close tsk-aaa\"")]
fn when_run_close(world: &mut TaskulusWorld) {
    run_cli(world, "tsk close tsk-aaa");
}

#[when("I run \"tsk close tsk-missing\"")]
fn when_run_close_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk close tsk-missing");
}

#[when("I run \"tsk delete tsk-aaa\"")]
fn when_run_delete(world: &mut TaskulusWorld) {
    run_cli(world, "tsk delete tsk-aaa");
}

#[when("I run \"tsk delete tsk-missing\"")]
fn when_run_delete_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk delete tsk-missing");
}

#[then("issue \"tsk-aaa\" should not exist")]
fn then_issue_not_exists(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("tsk-aaa.json");
    assert!(!issue_path.exists());
}
