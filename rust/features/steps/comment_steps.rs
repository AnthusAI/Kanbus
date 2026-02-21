use std::fs;
use std::path::PathBuf;

use chrono::Utc;
use cucumber::{given, then, when};

use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;
use kanbus::models::{IssueComment, IssueData};

use crate::step_definitions::initialization_steps::KanbusWorld;

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

fn save_issue(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

#[given("the current user is \"dev@example.com\"")]
fn given_current_user(_world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_USER", "dev@example.com");
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

#[then(expr = "issue {string} has a comment from {string} with text {string} and id {string}")]
fn then_issue_has_comment_with_id(
    world: &mut KanbusWorld,
    identifier: String,
    author: String,
    text: String,
    comment_id: String,
) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, &identifier);
    let found = issue.comments.iter().any(|comment| {
        comment.author == author
            && comment.text == text
            && comment.id.as_deref() == Some(comment_id.as_str())
    });
    assert!(found, "expected comment not found");
}

#[given(expr = "issue {string} has a comment from {string} with text {string} and id {string}")]
fn given_issue_has_comment_with_id(
    world: &mut KanbusWorld,
    identifier: String,
    author: String,
    text: String,
    comment_id: String,
) {
    let project_dir = load_project_dir(world);
    let mut issue = load_issue(&project_dir, &identifier);
    issue.comments.push(IssueComment {
        id: Some(comment_id),
        author,
        text,
        created_at: Utc::now(),
    });
    save_issue(&project_dir, &issue);
}

#[then(expr = "issue {string} has a comment from {string} with text {string} and no id")]
fn then_issue_has_comment_without_id(
    world: &mut KanbusWorld,
    identifier: String,
    author: String,
    text: String,
) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, &identifier);
    let found = issue
        .comments
        .iter()
        .any(|comment| comment.author == author && comment.text == text && comment.id.is_none());
    assert!(found, "expected comment not found");
}

#[given(expr = "issue {string} has a comment from {string} with text {string} and no id")]
fn given_issue_has_comment_without_id(
    world: &mut KanbusWorld,
    identifier: String,
    author: String,
    text: String,
) {
    let project_dir = load_project_dir(world);
    let mut issue = load_issue(&project_dir, &identifier);
    issue.comments.push(IssueComment {
        id: None,
        author,
        text,
        created_at: Utc::now(),
    });
    save_issue(&project_dir, &issue);
}

// Additional Given steps for comment manipulation tests

#[given(expr = "an issue {string} exists with a comment missing an id")]
fn given_issue_with_comment_missing_id(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc::now();
    let issue = IssueData {
        identifier: identifier.clone(),
        title: "Test Issue".to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: vec![IssueComment {
            id: None, // missing id
            author: "user@example.com".to_string(),
            text: "Legacy comment".to_string(),
            created_at: timestamp,
        }],
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    };
    save_issue(&project_dir, &issue);
}

#[given(expr = "an issue {string} exists with comment id {string} and text {string}")]
fn given_issue_with_comment_id_and_text(
    world: &mut KanbusWorld,
    identifier: String,
    comment_id: String,
    text: String,
) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc::now();
    let issue = IssueData {
        identifier: identifier.clone(),
        title: "Test Issue".to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: vec![IssueComment {
            id: Some(comment_id),
            author: "user@example.com".to_string(),
            text,
            created_at: timestamp,
        }],
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    };
    save_issue(&project_dir, &issue);
}

#[given(expr = "an issue {string} exists with comment ids {string} and {string}")]
fn given_issue_with_two_comment_ids(
    world: &mut KanbusWorld,
    identifier: String,
    id1: String,
    id2: String,
) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc::now();
    let issue = IssueData {
        identifier: identifier.clone(),
        title: "Test Issue".to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: vec![
            IssueComment {
                id: Some(id1),
                author: "user@example.com".to_string(),
                text: "First".to_string(),
                created_at: timestamp,
            },
            IssueComment {
                id: Some(id2),
                author: "user@example.com".to_string(),
                text: "Second".to_string(),
                created_at: timestamp,
            },
        ],
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    };
    save_issue(&project_dir, &issue);
}

// When steps for comment operations

#[when(expr = "I ensure comment ids for {string}")]
fn when_ensure_comment_ids(world: &mut KanbusWorld, identifier: String) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let argv = vec![
        "kanbus".to_string(),
        "comment".to_string(),
        "ensure-ids".to_string(),
        identifier,
    ];

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

#[when(expr = "I update comment {string} on {string} to {string}")]
fn when_update_comment(
    world: &mut KanbusWorld,
    comment_prefix: String,
    identifier: String,
    new_text: String,
) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let argv = vec![
        "kanbus".to_string(),
        "comment".to_string(),
        "update".to_string(),
        identifier,
        comment_prefix,
        new_text,
    ];

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

#[when(expr = "I delete comment {string} on {string}")]
fn when_delete_comment(world: &mut KanbusWorld, comment_prefix: String, identifier: String) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let argv = vec![
        "kanbus".to_string(),
        "comment".to_string(),
        "delete".to_string(),
        identifier,
        comment_prefix,
    ];

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

#[when(expr = "I attempt to update comment {string} on {string} to {string}")]
fn when_attempt_update_comment(
    world: &mut KanbusWorld,
    comment_prefix: String,
    identifier: String,
    new_text: String,
) {
    // Replace <empty> with empty string
    let prefix = if comment_prefix == "<empty>" {
        String::new()
    } else {
        comment_prefix
    };
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let argv = vec![
        "kanbus".to_string(),
        "comment".to_string(),
        "update".to_string(),
        identifier,
        prefix,
        new_text,
    ];

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

#[when(expr = "I attempt to delete comment {string} on {string}")]
fn when_attempt_delete_comment(
    world: &mut KanbusWorld,
    comment_prefix: String,
    identifier: String,
) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let argv = vec![
        "kanbus".to_string(),
        "comment".to_string(),
        "delete".to_string(),
        identifier,
        comment_prefix,
    ];

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

#[when(expr = "I attempt to ensure comment ids for {string}")]
fn when_attempt_ensure_comment_ids(world: &mut KanbusWorld, identifier: String) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let argv = vec![
        "kanbus".to_string(),
        "comment".to_string(),
        "ensure-ids".to_string(),
        identifier,
    ];

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

// Then steps for comment assertions

#[then(expr = "issue {string} should have comment ids assigned")]
fn then_issue_has_comment_ids(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, &identifier);
    for comment in &issue.comments {
        assert!(comment.id.is_some(), "Comment missing id");
    }
}

#[then(expr = "issue {string} should have comment text {string}")]
fn then_issue_has_comment_text(world: &mut KanbusWorld, identifier: String, expected_text: String) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, &identifier);
    assert_eq!(issue.comments.len(), 1);
    assert_eq!(issue.comments[0].text, expected_text);
}

#[then(expr = "issue {string} should have {int} comments")]
fn then_issue_has_comment_count(world: &mut KanbusWorld, identifier: String, count: usize) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, &identifier);
    assert_eq!(issue.comments.len(), count);
}

#[then(expr = "the last comment operation should fail with {string}")]
fn then_last_comment_op_fails(world: &mut KanbusWorld, expected_error: String) {
    assert_eq!(world.exit_code, Some(1), "Expected operation to fail");
    let stderr = world.stderr.as_ref().expect("stderr");
    assert!(
        stderr.contains(&expected_error),
        "Expected error containing '{}', got: {}",
        expected_error,
        stderr
    );
}
