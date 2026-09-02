use std::fs;
use std::path::PathBuf;

use chrono::{DateTime, Utc};
use cucumber::{given, then, when};
use serde_yaml::{Mapping, Value};

use kanbus::config::default_project_configuration;
use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;
use kanbus::right_now::{
    build_leaf_right_now_context, generate_right_now_summary, get_right_now_summary,
    project_events_directory, read_right_now_llm_usage_entries, summary_contains_status_keyword,
};

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn read_issue_file(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

#[given(expr = "issue {string} has right now summary {string}")]
fn given_issue_has_right_now_summary(world: &mut KanbusWorld, identifier: String, summary: String) {
    let project_dir = load_project_dir(world);
    let mut issue = read_issue_file(&project_dir, &identifier);
    issue.right_now_summary = Some(summary);
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "issue {string} has right now updated at {string}")]
fn given_issue_has_right_now_updated_at(
    world: &mut KanbusWorld,
    identifier: String,
    timestamp: String,
) {
    let project_dir = load_project_dir(world);
    let mut issue = read_issue_file(&project_dir, &identifier);
    let parsed: DateTime<Utc> = timestamp.parse().expect("parse timestamp");
    issue.right_now_updated_at = Some(parsed);
    write_issue_file(&project_dir, &issue);
}

#[when(expr = "issue {string} is saved and reloaded from disk")]
fn when_issue_saved_and_reloaded(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    write_issue_file(&project_dir, &issue);
    world.reloaded_issue = Some(read_issue_file(&project_dir, &identifier));
}

#[when(expr = "issue {string} is loaded from disk")]
fn when_issue_loaded_from_disk(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    world.reloaded_issue = Some(read_issue_file(&project_dir, &identifier));
}

#[when(expr = "I read the right now summary for issue {string}")]
fn when_read_right_now_summary(world: &mut KanbusWorld, identifier: String) {
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    world.right_now_summary_result = Some(get_right_now_summary(&issue).map(str::to_string));
}

#[then(expr = "issue {string} should have right now summary {string}")]
fn then_issue_has_right_now_summary(world: &mut KanbusWorld, identifier: String, expected: String) {
    let issue = if let Some(issue) = world.reloaded_issue.clone() {
        issue
    } else {
        let project_dir = load_project_dir(world);
        read_issue_file(&project_dir, &identifier)
    };
    assert_eq!(issue.right_now_summary.as_deref(), Some(expected.as_str()));
}

#[then(expr = "issue {string} should have right now updated at {string}")]
fn then_issue_has_right_now_updated_at(
    world: &mut KanbusWorld,
    identifier: String,
    expected: String,
) {
    let issue = if let Some(issue) = world.reloaded_issue.clone() {
        issue
    } else {
        let project_dir = load_project_dir(world);
        read_issue_file(&project_dir, &identifier)
    };
    let expected_timestamp: DateTime<Utc> = expected.parse().expect("parse timestamp");
    assert_eq!(issue.right_now_updated_at, Some(expected_timestamp));
}

#[then(expr = "issue {string} should have no right now summary")]
fn then_issue_has_no_right_now_summary(world: &mut KanbusWorld, identifier: String) {
    let issue = if let Some(issue) = world.reloaded_issue.clone() {
        issue
    } else {
        let project_dir = load_project_dir(world);
        read_issue_file(&project_dir, &identifier)
    };
    assert!(issue.right_now_summary.is_none());
}

#[then(expr = "issue {string} should have no right now updated at")]
fn then_issue_has_no_right_now_updated_at(world: &mut KanbusWorld, identifier: String) {
    let issue = if let Some(issue) = world.reloaded_issue.clone() {
        issue
    } else {
        let project_dir = load_project_dir(world);
        read_issue_file(&project_dir, &identifier)
    };
    assert!(issue.right_now_updated_at.is_none());
}

#[then(expr = "the right now summary result should be {string}")]
fn then_right_now_summary_result(world: &mut KanbusWorld, expected: String) {
    let result = world
        .right_now_summary_result
        .as_ref()
        .expect("right now summary result not set");
    assert_eq!(result.as_deref(), Some(expected.as_str()));
}

#[then("the right now summary result should be unset")]
fn then_right_now_summary_result_unset(world: &mut KanbusWorld) {
    let result = world
        .right_now_summary_result
        .as_ref()
        .expect("right now summary result not set");
    assert!(result.is_none());
}

#[given("mock AI is enabled")]
fn given_mock_ai_enabled(world: &mut KanbusWorld) {
    world.ai_mock_env = Some(std::env::var("KANBUS_TEST_AI_MOCK").ok());
    world.litellm_called_env = Some(std::env::var("KANBUS_RIGHT_NOW_LITELLM_CALLED").ok());
    std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
    std::env::remove_var("KANBUS_RIGHT_NOW_LITELLM_CALLED");
}

#[given(expr = "the Kanbus configuration uses AI provider {string} with model {string}")]
fn given_kanbus_configuration_uses_ai_provider(
    world: &mut KanbusWorld,
    provider: String,
    model: String,
) {
    let root = world.working_directory.as_ref().expect("cwd");
    let config_path = root.join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut mapping: Mapping = serde_yaml::from_str(&contents).expect("parse config");
    let mut ai_block = Mapping::new();
    ai_block.insert(
        Value::String("provider".to_string()),
        Value::String(provider),
    );
    ai_block.insert(Value::String("model".to_string()), Value::String(model));
    mapping.insert(Value::String("ai".to_string()), Value::Mapping(ai_block));
    let yaml = serde_yaml::to_string(&mapping).expect("serialize config");
    fs::write(config_path, yaml).expect("write config");
}

#[given("the Kanbus project has no AI configuration")]
fn given_kanbus_project_has_no_ai_configuration(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("cwd");
    let config_path = root.join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut mapping: Mapping = serde_yaml::from_str(&contents).expect("parse config");
    mapping.remove(&Value::String("ai".to_string()));
    let yaml = serde_yaml::to_string(&mapping).expect("serialize config");
    fs::write(config_path, yaml).expect("write config");
}

#[given(expr = "the right now max length is set to {int}")]
fn given_right_now_max_length(world: &mut KanbusWorld, max_length: usize) {
    let root = world.working_directory.as_ref().expect("cwd");
    let config_path = root.join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut mapping: Mapping = serde_yaml::from_str(&contents).expect("parse config");
    let mut right_now_block = mapping
        .get(&Value::String("right_now".to_string()))
        .and_then(Value::as_mapping)
        .cloned()
        .unwrap_or_else(|| {
            let defaults = default_project_configuration();
            serde_yaml::to_value(defaults.right_now)
                .expect("serialize defaults")
                .as_mapping()
                .cloned()
                .expect("right_now mapping")
        });
    right_now_block.insert(
        Value::String("max_length".to_string()),
        Value::Number(max_length.into()),
    );
    mapping.insert(
        Value::String("right_now".to_string()),
        Value::Mapping(right_now_block),
    );
    let yaml = serde_yaml::to_string(&mapping).expect("serialize config");
    fs::write(config_path, yaml).expect("write config");
}

#[when(expr = "I generate the right now summary for issue {string}")]
fn when_generate_right_now_summary(world: &mut KanbusWorld, identifier: String) {
    let root = world.working_directory.as_ref().expect("cwd");
    let project_dir = load_project_dir(world);
    let issue = read_issue_file(&project_dir, &identifier);
    let context = build_leaf_right_now_context(&issue);
    world.right_now_generation_error = None;
    world.generated_right_now_summary = None;
    match generate_right_now_summary(root, &issue, &context) {
        Ok(summary) => {
            world.generated_right_now_summary = Some(summary);
            world.exit_code = Some(0);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            let message = error.to_string();
            world.right_now_generation_error = Some(message.clone());
            world.exit_code = Some(1);
            world.stderr = Some(message);
        }
    }
}

#[then("the generated right now summary should be non-empty")]
fn then_generated_right_now_summary_non_empty(world: &mut KanbusWorld) {
    let summary = world
        .generated_right_now_summary
        .as_ref()
        .expect("generated right now summary not set");
    assert!(!summary.trim().is_empty());
}

#[then(expr = "the generated right now summary should equal {string}")]
fn then_generated_right_now_summary_equals(world: &mut KanbusWorld, expected: String) {
    assert_eq!(
        world.generated_right_now_summary.as_deref(),
        Some(expected.as_str())
    );
}

#[then(expr = "the generated right now summary length should be at most {int}")]
fn then_generated_right_now_summary_length_at_most(world: &mut KanbusWorld, max_length: usize) {
    let summary = world
        .generated_right_now_summary
        .as_ref()
        .expect("generated right now summary not set");
    assert!(summary.len() <= max_length);
}

#[then("the generated right now summary should not contain status keywords")]
fn then_generated_right_now_summary_no_status_keywords(world: &mut KanbusWorld) {
    let summary = world
        .generated_right_now_summary
        .as_ref()
        .expect("generated right now summary not set");
    assert!(!summary_contains_status_keyword(summary));
}

#[then("the LLM usage log should contain a right_now_summary entry")]
fn then_llm_usage_log_contains_right_now_summary(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("cwd");
    let events_dir = project_events_directory(root).expect("events dir");
    let entries = read_right_now_llm_usage_entries(&events_dir).expect("read llm usage");
    assert!(
        !entries.is_empty(),
        "expected right_now_summary entry in llm usage log"
    );
}

#[then("the LiteLLM API should not be called")]
fn then_litellm_api_not_called(_world: &mut KanbusWorld) {
    assert_ne!(
        std::env::var("KANBUS_RIGHT_NOW_LITELLM_CALLED")
            .ok()
            .as_deref(),
        Some("1")
    );
}

#[then(expr = "right now summary generation should fail with {string}")]
fn then_right_now_summary_generation_fails(world: &mut KanbusWorld, message: String) {
    assert_eq!(
        world.right_now_generation_error.as_deref(),
        Some(message.as_str())
    );
}
