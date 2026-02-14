use std::path::PathBuf;

use cucumber::{then, when};

use crate::step_definitions::initialization_steps::KanbusWorld;
use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;

fn run_cli(world: &mut KanbusWorld, command: &str) {
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

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

#[when("I run \"kanbus close kanbus-aaa\"")]
fn when_run_close(world: &mut KanbusWorld) {
    run_cli(world, "kanbus close kanbus-aaa");
}

#[when("I run \"kanbus close kanbus-missing\"")]
fn when_run_close_missing(world: &mut KanbusWorld) {
    run_cli(world, "kanbus close kanbus-missing");
}

#[when("I run \"kanbus delete kanbus-aaa\"")]
fn when_run_delete(world: &mut KanbusWorld) {
    run_cli(world, "kanbus delete kanbus-aaa");
}

#[when("I run \"kanbus delete kanbus-missing\"")]
fn when_run_delete_missing(world: &mut KanbusWorld) {
    run_cli(world, "kanbus delete kanbus-missing");
}

#[then("issue \"kanbus-aaa\" should not exist")]
fn then_issue_not_exists(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("kanbus-aaa.json");
    assert!(!issue_path.exists());
}
