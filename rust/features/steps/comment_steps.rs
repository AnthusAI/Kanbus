use std::fs;
use std::path::PathBuf;

use cucumber::{given, then, when};

use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn run_cli_args(world: &mut KanbusWorld, args: &[&str]) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let argv: Vec<String> = args.iter().map(|value| (*value).to_string()).collect();

    match run_from_args_with_output(argv, cwd.as_path()) {
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

fn load_issue(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[given("the current user is \"dev@example.com\"")]
fn given_current_user(_world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_USER", "dev@example.com");
}

#[when("I run \"kanbus comment kanbus-aaa \\\"First comment\\\"\"")]
fn when_comment_first(world: &mut KanbusWorld) {
    run_cli_args(
        world,
        &["kanbus", "comment", "kanbus-aaa", "First", "comment"],
    );
}

#[when("I run \"kanbus comment kanbus-aaa \\\"Second comment\\\"\"")]
fn when_comment_second(world: &mut KanbusWorld) {
    run_cli_args(
        world,
        &["kanbus", "comment", "kanbus-aaa", "Second", "comment"],
    );
}

#[when("I run \"kanbus comment kanbus-missing \\\"Missing issue note\\\"\"")]
fn when_comment_missing(world: &mut KanbusWorld) {
    run_cli_args(
        world,
        &[
            "kanbus",
            "comment",
            "kanbus-missing",
            "Missing",
            "issue",
            "note",
        ],
    );
}

#[when("I run \"kanbus comment kanbus-note \\\"Searchable comment\\\"\"")]
fn when_comment_note(world: &mut KanbusWorld) {
    run_cli_args(
        world,
        &["kanbus", "comment", "kanbus-note", "Searchable", "comment"],
    );
}

#[when("I run \"kanbus comment kanbus-dup \\\"Dup keyword\\\"\"")]
fn when_comment_dup(world: &mut KanbusWorld) {
    run_cli_args(
        world,
        &["kanbus", "comment", "kanbus-dup", "Dup", "keyword"],
    );
}

#[then("issue \"kanbus-aaa\" should have 1 comment")]
fn then_issue_has_one_comment(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "kanbus-aaa");
    assert_eq!(issue.comments.len(), 1);
}

#[then("the latest comment should have author \"dev@example.com\"")]
fn then_latest_author(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "kanbus-aaa");
    let latest = issue.comments.last().expect("comment");
    assert_eq!(latest.author, "dev@example.com");
}

#[then("the latest comment should have text \"First comment\"")]
fn then_latest_text(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "kanbus-aaa");
    let latest = issue.comments.last().expect("comment");
    assert_eq!(latest.text, "First comment");
}

#[then("the latest comment should have a created_at timestamp")]
fn then_latest_timestamp(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "kanbus-aaa");
    let latest = issue.comments.last().expect("comment");
    assert!(latest.created_at.timestamp() > 0);
}

#[then("issue \"kanbus-aaa\" should have comments in order \"First comment\", \"Second comment\"")]
fn then_comments_order(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "kanbus-aaa");
    let texts: Vec<String> = issue
        .comments
        .iter()
        .map(|comment| comment.text.clone())
        .collect();
    assert_eq!(
        texts,
        vec!["First comment".to_string(), "Second comment".to_string()]
    );
}
