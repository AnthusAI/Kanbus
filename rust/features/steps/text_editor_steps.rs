//! Step definitions for text editor CLI (edit subcommands).

use std::fs;
use std::path::PathBuf;

use cucumber::{gherkin::Step, given, then};

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given(expr = "a file {string} with content {string}")]
fn given_file_with_content_string(world: &mut KanbusWorld, path: String, content: String) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let full_path = cwd.join(path);
    if let Some(parent) = full_path.parent() {
        fs::create_dir_all(parent).expect("create parent dir");
    }
    let normalized = content.replace("\\n", "\n");
    fs::write(&full_path, normalized).expect("write file");
}

#[given(expr = "a file {string} with content")]
#[given(expr = "a file {string} with content:")]
fn given_file_with_content(world: &mut KanbusWorld, path: String, step: &Step) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let full_path: PathBuf = cwd.join(path);
    if let Some(parent) = full_path.parent() {
        fs::create_dir_all(parent).expect("create parent dir");
    }
    let content = step.docstring().expect("content not found");
    fs::write(&full_path, content).expect("write file");
}

#[then(expr = "{string} should appear after {string} in the file {string}")]
fn then_first_after_second_in_file(
    world: &mut KanbusWorld,
    first: String,
    second: String,
    path: String,
) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let full_path = cwd.join(path);
    let content = fs::read_to_string(&full_path).expect("read file");
    let first_index = content.find(&first).expect("first value not found in file");
    let second_index = content.find(&second).expect("second value not found in file");
    assert!(
        second_index < first_index,
        "{first:?} did not appear after {second:?}"
    );
}

#[then(expr = "{string} should appear before {string} in the file {string}")]
fn then_first_before_second_in_file(
    world: &mut KanbusWorld,
    first: String,
    second: String,
    path: String,
) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let full_path = cwd.join(path);
    let content = fs::read_to_string(&full_path).expect("read file");
    let first_index = content.find(&first).expect("first value not found in file");
    let second_index = content.find(&second).expect("second value not found in file");
    assert!(
        first_index < second_index,
        "{first:?} did not appear before {second:?}"
    );
}
