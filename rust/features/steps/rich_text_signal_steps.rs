//! Step definitions for rich text quality signal scenarios.

use cucumber::{then, when};

use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;
use kanbus::issue_files::read_issue_from_file;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn run_and_capture(world: &mut KanbusWorld, args: Vec<String>) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(output.stderr);
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

#[when(expr = "I create an issue with a literal backslash-n description {string}")]
fn when_create_with_literal_backslash_n_description(world: &mut KanbusWorld, description: String) {
    run_and_capture(
        world,
        vec![
            "kanbus".to_string(),
            "create".to_string(),
            "Test".to_string(),
            "Issue".to_string(),
            "--description".to_string(),
            description,
        ],
    );
}

#[when(expr = "I create an issue with a plain-text description {string}")]
fn when_create_with_plain_text_description(world: &mut KanbusWorld, description: String) {
    run_and_capture(
        world,
        vec![
            "kanbus".to_string(),
            "create".to_string(),
            "Test".to_string(),
            "Issue".to_string(),
            "--description".to_string(),
            description,
        ],
    );
}

#[when("I create an issue with a clean multi-line description")]
fn when_create_with_clean_multi_line_description(world: &mut KanbusWorld) {
    let description = "First line\nSecond line\nThird line".to_string();
    run_and_capture(
        world,
        vec![
            "kanbus".to_string(),
            "create".to_string(),
            "Test".to_string(),
            "Issue".to_string(),
            "--description".to_string(),
            description,
        ],
    );
}

#[when(expr = "I comment on {string} with literal backslash-n text {string}")]
fn when_comment_with_literal_backslash_n_text(
    world: &mut KanbusWorld,
    identifier: String,
    text: String,
) {
    std::env::set_var("KANBUS_USER", "dev@example.com");
    run_and_capture(
        world,
        vec![
            "kanbus".to_string(),
            "comment".to_string(),
            identifier,
            text,
        ],
    );
}

#[when(expr = "I comment on {string} with plain text {string}")]
fn when_comment_with_plain_text(world: &mut KanbusWorld, identifier: String, text: String) {
    std::env::set_var("KANBUS_USER", "dev@example.com");
    run_and_capture(
        world,
        vec![
            "kanbus".to_string(),
            "comment".to_string(),
            identifier,
            text,
        ],
    );
}

#[when(expr = "I update {string} with plain-text description {string}")]
fn when_update_with_plain_text_description(
    world: &mut KanbusWorld,
    identifier: String,
    description: String,
) {
    run_and_capture(
        world,
        vec![
            "kanbus".to_string(),
            "update".to_string(),
            identifier,
            "--description".to_string(),
            description,
        ],
    );
}

#[then("the stored description contains real newlines")]
fn then_stored_description_contains_real_newlines(world: &mut KanbusWorld) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = load_project_directory(cwd).expect("project dir");
    let issues_dir = project_dir.join("issues");

    let mut issue_files: Vec<_> = std::fs::read_dir(&issues_dir)
        .expect("read issues dir")
        .filter_map(|entry| entry.ok())
        .filter(|entry| {
            entry
                .path()
                .extension()
                .and_then(|ext| ext.to_str())
                == Some("json")
        })
        .collect();

    issue_files.sort_by_key(|entry| {
        entry.metadata().and_then(|m| m.modified()).ok()
    });

    let issue_path = issue_files
        .last()
        .expect("at least one issue file")
        .path();
    let issue = read_issue_from_file(&issue_path).expect("read issue");

    assert!(
        issue.description.contains('\n'),
        "Expected real newlines in description, got: {:?}",
        issue.description
    );
    assert!(
        !issue.description.contains("\\n"),
        "Expected no literal backslash-n sequences in description, got: {:?}",
        issue.description
    );
}
