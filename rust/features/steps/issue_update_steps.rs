use std::fs;
use std::path::PathBuf;

use cucumber::then;

use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn load_issue_json(project_dir: &PathBuf, identifier: &str) -> serde_json::Value {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[then(expr = "issue {string} should have parent {string}")]
fn then_issue_should_have_parent(world: &mut KanbusWorld, identifier: String, parent: String) {
    let project_dir = load_project_dir(world);
    let payload = load_issue_json(&project_dir, &identifier);
    assert_eq!(payload["parent"], parent);
}

fn load_issue(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[then(expr = "issue {string} should have title {string}")]
fn then_issue_has_title(world: &mut KanbusWorld, identifier: String, title: String) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, &identifier);
    assert_eq!(issue.title, title);
}

#[then("issue \"kanbus-aaa\" should have description \"Updated description\"")]
fn then_issue_has_description(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "kanbus-aaa");
    assert_eq!(issue.description, "Updated description");
}

#[then("issue \"kanbus-aaa\" should have an updated_at timestamp")]
fn then_issue_has_updated_at(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "kanbus-aaa");
    assert!(issue.updated_at.timestamp() > 0);
}
