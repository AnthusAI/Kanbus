use std::fs;
use std::path::PathBuf;

use cucumber::given;

use kanbus::file_io::load_project_directory;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

#[given("a non-issue file exists in the issues directory")]
fn given_non_issue_file_exists(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let notes_path = project_dir.join("issues").join("notes.txt");
    fs::write(notes_path, "ignore").expect("write notes");
}

#[given("a non-issue file exists in the local issues directory")]
fn given_non_issue_file_exists_local(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let local_dir = project_dir
        .parent()
        .expect("project parent")
        .join("project-local")
        .join("issues");
    fs::create_dir_all(&local_dir).expect("create local issues");
    let notes_path = local_dir.join("notes.txt");
    fs::write(notes_path, "ignore").expect("write notes");
}
