use std::fs;
use std::path::PathBuf;

use chrono::Utc;
use cucumber::{given, then, when};

use kanbus::agent_metadata::{resolve_agent_metadata, AgentMetadataRequest};
use kanbus::file_io::load_project_directory;
use kanbus::models::{AgentMetadata, IssueComment, IssueData};

use crate::step_definitions::initialization_steps::KanbusWorld;

fn build_issue(identifier: &str, title: &str, issue_type: &str, status: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: String::new(),
        issue_type: issue_type.to_string(),
        status: status.to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        agent: None,
        custom: Default::default(),
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

fn save_issue(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

#[given(expr = "KANBUS_AGENT_PLATFORM is set to {string}")]
fn given_kanbus_agent_platform(_world: &mut KanbusWorld, value: String) {
    std::env::set_var("KANBUS_AGENT_PLATFORM", value);
}

#[given(expr = "KANBUS_AGENT_MODEL is set to {string}")]
fn given_kanbus_agent_model(_world: &mut KanbusWorld, value: String) {
    std::env::set_var("KANBUS_AGENT_MODEL", value);
}

#[given("KANBUS_AGENT_MODEL is unset")]
fn given_kanbus_agent_model_unset(_world: &mut KanbusWorld) {
    std::env::remove_var("KANBUS_AGENT_MODEL");
}

#[given("an issue {string} exists with agent metadata platform {string} and model {string}")]
fn given_issue_with_agent_metadata(
    _world: &mut KanbusWorld,
    identifier: String,
    platform: String,
    model: String,
) {
    let project_dir = load_project_dir(_world);
    let mut issue = build_issue(&identifier, "Agent tagged issue", "task", "open");
    issue.agent = Some(AgentMetadata {
        platform,
        model,
        settings: Default::default(),
    });
    save_issue(&project_dir, &issue);
}

#[then("the created issue should have agent metadata platform {string} and model {string}")]
fn then_created_issue_has_agent_metadata(world: &mut KanbusWorld, platform: String, model: String) {
    let identifier = world.last_kanbus_issue_id.as_ref().expect("issue id");
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, identifier);
    let agent = issue.agent.as_ref().expect("agent metadata");
    assert_eq!(agent.platform, platform);
    assert_eq!(agent.model, model);
}

#[then("the latest comment should have agent platform {string} and model {string}")]
fn then_latest_comment_has_agent_metadata(
    world: &mut KanbusWorld,
    platform: String,
    model: String,
) {
    let project_dir = load_project_dir(world);
    let issue = load_issue(&project_dir, "kanbus-aaa");
    let latest = issue.comments.last().expect("comment");
    let agent = latest.agent.as_ref().expect("agent metadata");
    assert_eq!(agent.platform, platform);
    assert_eq!(agent.model, model);
}

#[given(
    "issue {string} has a comment from {string} with text {string} and agent metadata platform {string} and model {string}"
)]
fn given_issue_comment_with_agent_metadata(
    _world: &mut KanbusWorld,
    identifier: String,
    author: String,
    text: String,
    platform: String,
    model: String,
) {
    let project_dir = load_project_dir(_world);
    let mut issue = load_issue(&project_dir, &identifier);
    issue.comments.push(IssueComment {
        id: Some("abc123def456".to_string()),
        author,
        text: Some(text),
        created_at: Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap(),
        comment_type: "default".to_string(),
        data: Default::default(),
        agent: Some(AgentMetadata {
            platform,
            model,
            settings: Default::default(),
        }),
    });
    save_issue(&project_dir, &issue);
}

#[when("I resolve agent metadata with no CLI overrides")]
fn when_resolve_agent_metadata(world: &mut KanbusWorld) {
    world.resolved_agent_metadata =
        resolve_agent_metadata(&AgentMetadataRequest::default()).expect("resolve agent metadata");
}

#[then(expr = "the resolved agent platform should be {string}")]
fn then_resolved_agent_platform(world: &mut KanbusWorld, platform: String) {
    let metadata = world.resolved_agent_metadata.as_ref().expect("metadata");
    assert_eq!(metadata.platform, platform);
}

#[then(expr = "the resolved agent model should be {string}")]
fn then_resolved_agent_model(world: &mut KanbusWorld, model: String) {
    let metadata = world.resolved_agent_metadata.as_ref().expect("metadata");
    assert_eq!(metadata.model, model);
}

#[then("agent metadata should be absent")]
fn then_agent_metadata_absent(world: &mut KanbusWorld) {
    assert!(world.resolved_agent_metadata.is_none());
}
