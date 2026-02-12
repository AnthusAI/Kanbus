use cucumber::when;

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

#[when("I run \"tsk --beads list\"")]
fn when_run_list_beads(world: &mut TaskulusWorld) {
    run_cli(world, "tsk --beads list");
}

#[when("I run \"tsk --beads list --no-local\"")]
fn when_run_list_beads_no_local(world: &mut TaskulusWorld) {
    run_cli(world, "tsk --beads list --no-local");
}

#[when("I run \"tsk --beads ready\"")]
fn when_run_ready_beads(world: &mut TaskulusWorld) {
    run_cli(world, "tsk --beads ready");
}

#[when("I run \"tsk --beads ready --no-local\"")]
fn when_run_ready_beads_no_local(world: &mut TaskulusWorld) {
    run_cli(world, "tsk --beads ready --no-local");
}

#[when("I run \"tsk --beads show bdx-epic\"")]
fn when_run_show_beads(world: &mut TaskulusWorld) {
    run_cli(world, "tsk --beads show bdx-epic");
}

#[when("I run \"tsk --beads show bdx-missing\"")]
fn when_run_show_beads_missing(world: &mut TaskulusWorld) {
    run_cli(world, "tsk --beads show bdx-missing");
}
