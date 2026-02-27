//! Step definitions for policy feature tests.

use std::fs;

use cucumber::{gherkin, given};

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given(expr = r#"a policy file {string} with content"#)]
async fn create_policy_file(world: &mut KanbusWorld, step: &gherkin::Step, filename: String) {
    let working_dir = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = working_dir.join("project");
    let policies_dir = project_dir.join("policies");
    fs::create_dir_all(&policies_dir).expect("failed to create policies directory");

    let policy_path = policies_dir.join(&filename);
    let content = step.docstring.as_ref().expect("policy content required");
    fs::write(&policy_path, content).expect("failed to write policy file");
}

#[given("no policies directory exists")]
async fn no_policies_directory(world: &mut KanbusWorld) {
    let working_dir = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = working_dir.join("project");
    let policies_dir = project_dir.join("policies");
    if policies_dir.exists() {
        fs::remove_dir_all(&policies_dir).expect("failed to remove policies directory");
    }
}

#[given("an empty policies directory exists")]
async fn empty_policies_directory(world: &mut KanbusWorld) {
    let working_dir = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = working_dir.join("project");
    let policies_dir = project_dir.join("policies");
    fs::create_dir_all(&policies_dir).expect("failed to create policies directory");

    if let Ok(entries) = fs::read_dir(&policies_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|ext| ext.to_str()) == Some("policy") {
                fs::remove_file(&path).ok();
            }
        }
    }
}
