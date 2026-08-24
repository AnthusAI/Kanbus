use crate::step_definitions::initialization_steps::KanbusWorld;
use cucumber::{given, then};
use std::fs;

#[given(expr = "the Kanbus configuration uses AI provider {string} with model {string}")]
fn given_ai_configuration(world: &mut KanbusWorld, provider: String, model: String) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let kanbus_yml_path = root.join(".kanbus.yml");
    let config_data = fs::read_to_string(&kanbus_yml_path).unwrap_or_default();

    let mut lines: Vec<&str> = config_data.lines().collect();
    lines.retain(|l| {
        !l.starts_with("ai:") && !l.starts_with("  provider:") && !l.starts_with("  model:")
    });
    let mut new_config = lines.join(
        "
",
    );

    new_config.push_str(&format!(
        "
ai:
  provider: {}
  model: {}
",
        provider, model
    ));
    fs::write(kanbus_yml_path, new_config).unwrap();
}

#[given(expr = "the issue {string} has a comment with text {string}")]
fn given_issue_has_comment(world: &mut KanbusWorld, issue_id: String, text: String) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let project_dir = root.join("project");
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));

    let mut issue_json: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let comment = serde_json::json!({
        "id": uuid::Uuid::new_v4().to_string(),
        "author": "testuser",
        "text": text,
        "created_at": chrono::Utc::now().to_rfc3339(),
        "comment_type": "default"
    });

    if let Some(comments) = issue_json
        .get_mut("comments")
        .and_then(|c| c.as_array_mut())
    {
        comments.push(comment);
    } else {
        issue_json["comments"] = serde_json::json!([comment]);
    }

    fs::write(
        &issue_path,
        serde_json::to_string_pretty(&issue_json).unwrap(),
    )
    .unwrap();
}

#[given(expr = "the issue {string} has a summary comment with rewritten description {string} and activity summary {string}")]
fn given_issue_has_structured_summary_comment(
    world: &mut KanbusWorld,
    issue_id: String,
    rewritten: String,
    activity: String,
) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let issue_path = root
        .join("project")
        .join("issues")
        .join(format!("{}.json", issue_id));
    let mut issue_json: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let comment = serde_json::json!({
        "id": uuid::Uuid::new_v4().to_string(),
        "author": "system:summary",
        "created_at": chrono::Utc::now().to_rfc3339(),
        "comment_type": "summary",
        "data": {
            "rewritten_description": rewritten,
            "activity_summary": activity
        }
    });

    if let Some(comments) = issue_json
        .get_mut("comments")
        .and_then(|c| c.as_array_mut())
    {
        comments.push(comment);
    } else {
        issue_json["comments"] = serde_json::json!([comment]);
    }

    fs::write(
        &issue_path,
        serde_json::to_string_pretty(&issue_json).unwrap(),
    )
    .unwrap();
}

#[given(expr = "the issue {string} has a summary comment containing {string}")]
fn given_issue_has_summary_comment(world: &mut KanbusWorld, issue_id: String, text: String) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let project_dir = root.join("project");
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));

    let mut issue_json: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let comment = serde_json::json!({
        "id": uuid::Uuid::new_v4().to_string(),
        "author": "system:summary",
        "text": text,
        "created_at": chrono::Utc::now().to_rfc3339(),
        "comment_type": "summary"
    });

    if let Some(comments) = issue_json
        .get_mut("comments")
        .and_then(|c| c.as_array_mut())
    {
        comments.push(comment);
    } else {
        issue_json["comments"] = serde_json::json!([comment]);
    }

    fs::write(
        &issue_path,
        serde_json::to_string_pretty(&issue_json).unwrap(),
    )
    .unwrap();
}

#[given(expr = "the issue {string} has a summary comment containing:")]
fn given_issue_has_multiline_summary_comment(
    world: &mut KanbusWorld,
    issue_id: String,
    text: String,
) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let project_dir = root.join("project");
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));

    let mut issue_json: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let created_at = (chrono::Utc::now() - chrono::Duration::days(5)).to_rfc3339();
    let comment = serde_json::json!({
        "id": uuid::Uuid::new_v4().to_string(),
        "author": "system:summary",
        "text": text.trim(),
        "created_at": created_at,
        "comment_type": "summary"
    });

    if let Some(comments) = issue_json
        .get_mut("comments")
        .and_then(|c| c.as_array_mut())
    {
        comments.push(comment);
    } else {
        issue_json["comments"] = serde_json::json!([comment]);
    }

    fs::write(
        &issue_path,
        serde_json::to_string_pretty(&issue_json).unwrap(),
    )
    .unwrap();
}

#[then(expr = "the issue {string} should have a summary comment")]
fn then_issue_should_have_summary_comment(world: &mut KanbusWorld, issue_id: String) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let project_dir = root.join("project");
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));

    let issue_json: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let comments = issue_json
        .get("comments")
        .and_then(|c| c.as_array())
        .unwrap();

    let has_summary = comments
        .iter()
        .any(|c| c.get("comment_type").and_then(|t| t.as_str()) == Some("summary"));
    assert!(has_summary, "Issue does not have a summary comment");
}

#[then(expr = "the system records a structured log entry for the LLM usage")]
fn then_system_records_log_entry(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let log_path = root.join("project").join("events").join("llm_usage.jsonl");
    assert!(log_path.exists(), "Log file does not exist");

    let contents = fs::read_to_string(&log_path).unwrap();
    let lines: Vec<&str> = contents.lines().collect();
    assert!(!lines.is_empty(), "Log file is empty");

    let last_entry: serde_json::Value = serde_json::from_str(lines.last().unwrap()).unwrap();
    assert!(last_entry.get("tokens").is_some(), "tokens missing");
    assert!(last_entry.get("cost").is_some(), "cost missing");
}

#[given(expr = "the issue {string} has status {string}")]
fn given_issue_status(world: &mut KanbusWorld, issue_id: String, status: String) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let project_dir = root.join("project");
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));

    let mut issue_data: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    issue_data["status"] = serde_json::Value::String(status);
    fs::write(
        issue_path,
        serde_json::to_string_pretty(&issue_data).unwrap(),
    )
    .unwrap();
}

#[given(expr = "the issue {string} was updated {int} days ago")]
fn given_issue_updated(world: &mut KanbusWorld, issue_id: String, days: u32) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let project_dir = root.join("project");
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));

    let mut issue_data: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let old_date = chrono::Utc::now() - chrono::Duration::days(days as i64);
    issue_data["updated_at"] = serde_json::Value::String(old_date.to_rfc3339());
    fs::write(
        issue_path,
        serde_json::to_string_pretty(&issue_data).unwrap(),
    )
    .unwrap();
}

#[then(expr = "the summary rewritten description for issue {string} should be shorter than the original description")]
fn then_summary_rewritten_shorter_than_original(world: &mut KanbusWorld, issue_id: String) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let issue_path = root
        .join("project")
        .join("issues")
        .join(format!("{}.json", issue_id));
    let issue_data: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let original_length = issue_data["description"].as_str().unwrap_or("").len();
    let comments = issue_data["comments"].as_array().unwrap();
    for comment in comments.iter().rev() {
        if comment["comment_type"].as_str().unwrap_or("default") == "summary" {
            let rewritten = comment["data"]["rewritten_description"]
                .as_str()
                .unwrap_or_default();
            assert!(
                rewritten.len() < original_length,
                "Expected rewritten description to be shorter than original. \
                 Original length={}, rewritten length={}",
                original_length,
                rewritten.len()
            );
            return;
        }
    }
    panic!("No summary comment found");
}

#[then(expr = "the summary comment for issue {string} should have rewritten description {string}")]
fn then_summary_comment_rewritten_description(
    world: &mut KanbusWorld,
    issue_id: String,
    text: String,
) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let issue_path = root
        .join("project")
        .join("issues")
        .join(format!("{}.json", issue_id));
    let issue_data: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let comments = issue_data["comments"].as_array().unwrap();
    for comment in comments.iter().rev() {
        if comment["comment_type"].as_str().unwrap_or("default") == "summary" {
            let rewritten = comment["data"]["rewritten_description"]
                .as_str()
                .unwrap_or_default();
            assert_eq!(
                rewritten, text,
                "Expected rewritten description {:?}, got {:?}",
                text, rewritten
            );
            return;
        }
    }
    panic!("No summary comment found");
}

#[then(expr = "the summary comment for issue {string} should contain {string}")]
fn then_summary_comment_contains(world: &mut KanbusWorld, issue_id: String, text: String) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let project_dir = root.join("project");
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue_id));

    let issue_data: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let comments = issue_data["comments"].as_array().unwrap();
    let mut found = false;
    for comment in comments.iter().rev() {
        if comment["comment_type"].as_str().unwrap_or("default") == "summary" {
            let activity_summary = comment["data"]["activity_summary"]
                .as_str()
                .unwrap_or_default();
            assert!(
                activity_summary.contains(&text),
                "Summary did not contain '{}'. Full activity summary:\n{}",
                text,
                activity_summary
            );
            found = true;
            break;
        }
    }
    assert!(found, "No summary comment found");
}

#[then(expr = "the summary comment for issue {string} should not contain {string}")]
fn then_summary_comment_does_not_contain(world: &mut KanbusWorld, issue_id: String, text: String) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let issue_path = root
        .join("project")
        .join("issues")
        .join(format!("{}.json", issue_id));
    let issue_data: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let comments = issue_data["comments"].as_array().unwrap();
    for comment in comments.iter().rev() {
        if comment["comment_type"].as_str().unwrap_or("default") == "summary" {
            let activity_summary = comment["data"]["activity_summary"]
                .as_str()
                .unwrap_or_default();
            assert!(
                !activity_summary.contains(&text),
                "Did not expect '{}' in summary comment. Full activity summary:\n{}",
                text,
                activity_summary
            );
            return;
        }
    }
    panic!("No summary comment found");
}

#[then(expr = "issue {string} description should equal {string}")]
fn then_issue_should_have_description(
    world: &mut KanbusWorld,
    issue_id: String,
    description: String,
) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let issue_path = root
        .join("project")
        .join("issues")
        .join(format!("{}.json", issue_id));
    let issue_data: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let actual = issue_data["description"].as_str().unwrap_or_default();
    assert_eq!(
        actual, description,
        "Expected description {:?}, got {:?}",
        description, actual
    );
}

#[then(expr = "issue {string} should have custom field {string}")]
fn then_issue_should_have_custom_field(
    world: &mut KanbusWorld,
    issue_id: String,
    field_name: String,
) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let issue_path = root
        .join("project")
        .join("issues")
        .join(format!("{}.json", issue_id));
    let issue_data: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let custom = issue_data
        .get("custom")
        .and_then(|value| value.as_object())
        .cloned()
        .unwrap_or_default();
    assert!(
        custom.contains_key(&field_name),
        "Expected custom field {:?}, got {:?}",
        field_name,
        custom
    );
}

#[given(expr = "issue {string} has custom field {string} with value {string}")]
fn given_issue_custom_field_with_value(
    world: &mut KanbusWorld,
    issue_id: String,
    field_name: String,
    value: String,
) {
    let root = world.working_directory.as_ref().unwrap().clone();
    let issue_path = root
        .join("project")
        .join("issues")
        .join(format!("{}.json", issue_id));
    let mut issue_data: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&issue_path).unwrap()).unwrap();
    let custom = issue_data
        .as_object_mut()
        .expect("issue json object")
        .entry("custom")
        .or_insert_with(|| serde_json::json!({}));
    if let Some(custom_map) = custom.as_object_mut() {
        custom_map.insert(field_name, serde_json::Value::String(value));
    }
    fs::write(
        issue_path,
        serde_json::to_string_pretty(&issue_data).unwrap(),
    )
    .unwrap();
}
