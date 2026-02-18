use std::process::Command;

use cucumber::when;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[when("I run the CLI entrypoint with --help")]
fn when_run_cli_entrypoint_help(world: &mut KanbusWorld) {
    run_cli_binary(world, vec!["--help".to_string()]);
}

#[when(expr = "I run the CLI entrypoint with {string}")]
fn when_run_cli_entrypoint_args(world: &mut KanbusWorld, arguments: String) {
    let args = arguments
        .split_whitespace()
        .map(|value| value.to_string())
        .collect();
    run_cli_binary(world, args);
}

fn run_cli_binary(world: &mut KanbusWorld, args: Vec<String>) {
    let manifest_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let binary_path = manifest_dir.join("target").join("debug").join("kbs");
    if !binary_path.exists() {
        let status = Command::new("cargo")
            .args(["build", "--bin", "kbs"])
            .current_dir(&manifest_dir)
            .status()
            .expect("build kbs binary");
        if !status.success() {
            panic!("failed to build kbs binary");
        }
    }
    let cwd = world
        .working_directory
        .clone()
        .unwrap_or_else(|| std::env::current_dir().expect("current dir"));
    let mut command = Command::new(binary_path);
    command.args(args);
    let output = command
        .current_dir(cwd)
        .env("KANBUS_NO_DAEMON", "1")
        .output()
        .expect("run kbs --help");
    world.exit_code = Some(output.status.code().unwrap_or(1));
    world.stdout = Some(String::from_utf8_lossy(&output.stdout).to_string());
    world.stderr = Some(String::from_utf8_lossy(&output.stderr).to_string());
}
