use std::path::PathBuf;

use cucumber::then;

use crate::step_definitions::initialization_steps::KanbusWorld;
use kanbus::file_io::load_project_directory;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

#[then("issue \"kanbus-aaa\" should not exist")]
fn then_issue_not_exists(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue_path = project_dir.join("issues").join("kanbus-aaa.json");
    assert!(!issue_path.exists());
}
