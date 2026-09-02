use std::fs;

use cucumber::given;

use kanbus::kanbus_version::parse_semver_core;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given(expr = "the project requires kanbus version {string}")]
fn given_project_requires_kanbus_version(world: &mut KanbusWorld, version: String) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    fs::write(cwd.join("kanbus-version"), format!("{version}\n")).expect("write kanbus-version");
}

#[given("the project requires the running kanbus CLI core version")]
fn given_project_requires_running_core_version(world: &mut KanbusWorld) {
    let running = env!("GIT_VERSION");
    let core = parse_semver_core(running).expect("running CLI version is not parseable");
    let cwd = world.working_directory.as_ref().expect("cwd");
    fs::write(
        cwd.join("kanbus-version"),
        format!("{}.{}.{}\n", core.0, core.1, core.2),
    )
    .expect("write kanbus-version");
}

#[given("kanbus-version contains invalid contents")]
fn given_invalid_kanbus_version_contents(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    fs::write(cwd.join("kanbus-version"), "not-a-version\n").expect("write kanbus-version");
}
