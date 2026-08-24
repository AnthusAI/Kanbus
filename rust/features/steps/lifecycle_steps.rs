use std::fs;

use chrono::{Duration, Utc};
use cucumber::given;
use serde_json::json;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given(regex = r#"^the AI provider is configured as "litellm"$"#)]
fn the_ai_provider_is_configured_as_litellm(world: &mut KanbusWorld) {
    let project_dir = world.working_directory.as_ref().unwrap();
    let config_path = project_dir.join(".kanbus.yml");
    let config_data = if config_path.exists() {
        fs::read_to_string(&config_path).unwrap_or_default()
    } else {
        "project_directory: project\n".to_string()
    };

    let lines: Vec<&str> = config_data
        .lines()
        .filter(|line| {
            !line.starts_with("ai:")
                && !line.starts_with("  provider:")
                && !line.starts_with("  model:")
        })
        .collect();
    let mut updated = lines.join("\n");
    if !updated.is_empty() {
        updated.push('\n');
    }
    updated.push_str("ai:\n  provider: litellm\n  model: gpt-5.6-luna\n");
    fs::write(&config_path, updated).unwrap();
}

#[given(regex = r#"^mock AI is enabled$"#)]
fn mock_ai_is_enabled(_world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
}

#[given(regex = r#"^an issue "([^"]+)" of type "([^"]+)" in status "([^"]+)"$"#)]
fn an_issue_of_type_in_status(
    world: &mut KanbusWorld,
    issue_id: String,
    issue_type: String,
    status: String,
) {
    let now = Utc::now();
    let issue_json = json!({
        "id": issue_id,
        "title": format!("Test {}", issue_id),
        "description": "Test description",
        "type": issue_type,
        "status": status,
        "priority": 1,
        "created_at": now.to_rfc3339_opts(chrono::SecondsFormat::Secs, true),
        "updated_at": now.to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
    });
    let issues_dir = world
        .working_directory
        .as_ref()
        .unwrap()
        .join("project")
        .join("issues");
    fs::create_dir_all(&issues_dir).unwrap();
    fs::write(
        issues_dir.join(format!("{}.json", issue_id)),
        issue_json.to_string(),
    )
    .unwrap();
}

#[given(regex = r#"^issue "([^"]+)" was updated (\d+) days ago$"#)]
fn issue_was_updated_days_ago(world: &mut KanbusWorld, issue_id: String, days: i64) {
    let issues_dir = world
        .working_directory
        .as_ref()
        .unwrap()
        .join("project")
        .join("issues");
    let issue_path = issues_dir.join(format!("{}.json", issue_id));
    let content = fs::read_to_string(&issue_path).unwrap();
    let mut issue_json: serde_json::Value = serde_json::from_str(&content).unwrap();
    let past_date = Utc::now() - Duration::days(days);
    issue_json["updated_at"] = json!(past_date.to_rfc3339_opts(chrono::SecondsFormat::Secs, true));
    fs::write(issue_path, issue_json.to_string()).unwrap();
}

#[given(regex = r#"^issue "([^"]+)" has (\d+) comments$"#)]
fn issue_has_comments(world: &mut KanbusWorld, issue_id: String, count: i64) {
    let issues_dir = world
        .working_directory
        .as_ref()
        .unwrap()
        .join("project")
        .join("issues");
    let issue_path = issues_dir.join(format!("{}.json", issue_id));
    let content = fs::read_to_string(&issue_path).unwrap();
    let mut issue_json: serde_json::Value = serde_json::from_str(&content).unwrap();

    let mut comments = vec![];
    for i in 0..count {
        comments.push(json!({
            "id": format!("comment-{}", i),
            "author": "user",
            "text": format!("Comment {}", i),
            "created_at": issue_json["updated_at"].clone()
        }));
    }
    issue_json["comments"] = json!(comments);
    fs::write(issue_path, issue_json.to_string()).unwrap();
}

#[given(regex = r#"^issue "([^"]+)" has a summary comment$"#)]
fn issue_has_a_summary_comment(world: &mut KanbusWorld, issue_id: String) {
    let issues_dir = world
        .working_directory
        .as_ref()
        .unwrap()
        .join("project")
        .join("issues");
    let issue_path = issues_dir.join(format!("{}.json", issue_id));
    let content = fs::read_to_string(&issue_path).unwrap();
    let mut issue_json: serde_json::Value = serde_json::from_str(&content).unwrap();

    let mut comments = issue_json["comments"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    comments.push(json!({
        "id": "summary-123",
        "author": "system:summary",
        "text": "Summary",
        "created_at": issue_json["updated_at"].clone(),
        "comment_type": "summary"
    }));
    issue_json["comments"] = json!(comments);
    fs::write(issue_path, issue_json.to_string()).unwrap();
}
