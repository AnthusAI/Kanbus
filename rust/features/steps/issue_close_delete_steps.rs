use std::path::PathBuf;

use cucumber::then;

use crate::step_definitions::initialization_steps::KanbusWorld;
use kanbus::file_io::{find_project_local_directory, load_project_directory};

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn issue_path_for_identifier(world: &KanbusWorld, identifier: &str) -> PathBuf {
    let project_dir = load_project_dir(world);
    let path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    if path.exists() {
        return path;
    }
    if let Some(local_dir) = find_project_local_directory(&project_dir) {
        let local_path = local_dir.join("issues").join(format!("{identifier}.json"));
        if local_path.exists() {
            return local_path;
        }
    }
    project_dir
        .join("issues")
        .join(format!("{identifier}.json"))
}

#[then(expr = "issue {string} should not exist")]
fn then_issue_not_exists(world: &mut KanbusWorld, identifier: String) {
    let path = issue_path_for_identifier(world, &identifier);
    assert!(
        !path.exists(),
        "Expected issue {} to be deleted",
        identifier
    );
}

#[then(expr = "issue {string} should exist")]
fn then_issue_exists(world: &mut KanbusWorld, identifier: String) {
    let path = issue_path_for_identifier(world, &identifier);
    assert!(path.exists(), "Expected issue {} to exist", identifier);
}
