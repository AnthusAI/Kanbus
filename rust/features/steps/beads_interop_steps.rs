use std::fs;
use std::path::{Path, PathBuf};

use chrono::Utc;
use cucumber::{given, then, when};
use serde_json::{json, Value};
use tempfile::TempDir;

use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;
use kanbus::ids::format_issue_key;
use kanbus::models::IssueData;
use kanbus::users::get_current_user;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn run_cli(world: &mut KanbusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse command");
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(String::new());

            // Capture last created beads issue id for follow-up steps.
            if command.contains("--beads create") {
                capture_last_beads_issue_id(world);
            }
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

fn fixture_beads_dir() -> PathBuf {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("repo root");
    root.join("specs")
        .join("fixtures")
        .join("beads_repo")
        .join(".beads")
}

fn beads_issues_path(world: &KanbusWorld) -> PathBuf {
    world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".beads")
        .join("issues.jsonl")
}

fn load_beads_records(path: &Path) -> Vec<Value> {
    let text = fs::read_to_string(path).expect("read issues.jsonl");
    text.lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(
                    serde_json::from_str::<serde_json::Value>(trimmed).expect("parse beads record"),
                )
            }
        })
        .collect()
}

/// Retrieve and cache the most recent beads issue id from the issues file.
fn capture_last_beads_issue_id(world: &mut KanbusWorld) -> Option<String> {
    if let Some(id) = world.last_beads_issue_id.clone() {
        return Some(id);
    }
    let path = beads_issues_path(world);
    if let Ok(records) = std::fs::read_to_string(&path) {
        if let Some(last_line) = records.lines().filter(|l| !l.trim().is_empty()).last() {
            if let Ok(value) = serde_json::from_str::<Value>(last_line) {
                if let Some(id) = value.get("id").and_then(Value::as_str) {
                    let owned = id.to_string();
                    world.last_beads_issue_id = Some(owned.clone());
                    return Some(owned);
                }
            }
        }
    }
    None
}

fn upsert_beads_issue(
    world: &mut KanbusWorld,
    identifier: &str,
    parent: Option<&str>,
    status: Option<&str>,
) {
    let path = beads_issues_path(world);
    let mut records = load_beads_records(&path);
    let mut found = false;
    for record in &mut records {
        if record.get("id").and_then(Value::as_str) == Some(identifier) {
            if let Some(status_value) = status {
                record
                    .as_object_mut()
                    .expect("record object")
                    .insert("status".to_string(), json!(status_value));
            }
            if let Some(parent_value) = parent {
                record
                    .as_object_mut()
                    .expect("record object")
                    .insert("parent".to_string(), json!(parent_value));
            }
            found = true;
            break;
        }
    }
    if !found {
        let created_at = Utc::now().to_rfc3339();
        let mut object = serde_json::Map::new();
        object.insert("id".to_string(), json!(identifier));
        object.insert("title".to_string(), json!(identifier));
        object.insert("description".to_string(), json!(""));
        object.insert("status".to_string(), json!(status.unwrap_or("open")));
        object.insert("priority".to_string(), json!(2));
        object.insert("issue_type".to_string(), json!("task"));
        object.insert("created_at".to_string(), json!(created_at));
        object.insert("created_by".to_string(), json!(get_current_user()));
        object.insert("updated_at".to_string(), json!(created_at));
        object.insert("owner".to_string(), json!(get_current_user()));
        if let Some(parent_value) = parent {
            object.insert("parent".to_string(), json!(parent_value));
        }
        object.insert("comments".to_string(), Value::Array(Vec::new()));
        records.push(Value::Object(object));
    }
    fs::write(
        &path,
        records
            .iter()
            .map(|v| v.to_string() + "\n")
            .collect::<String>(),
    )
    .expect("write beads issues");
}

fn add_beads_dependency(world: &mut KanbusWorld, source: &str, target: &str, dep_type: &str) {
    let path = beads_issues_path(world);
    let mut records = load_beads_records(&path);
    let mut updated = false;
    for record in &mut records {
        if record.get("id").and_then(Value::as_str) != Some(source) {
            continue;
        }
        let deps = record
            .as_object_mut()
            .expect("record object")
            .entry("dependencies")
            .or_insert_with(|| Value::Array(Vec::new()))
            .as_array_mut()
            .expect("dependencies array");
        deps.push(json!({
            "issue_id": source,
            "depends_on_id": target,
            "type": dep_type,
            "created_at": Utc::now().to_rfc3339(),
            "created_by": get_current_user(),
        }));
        updated = true;
        break;
    }
    if updated {
        fs::write(
            &path,
            records
                .iter()
                .map(|v| v.to_string() + "\n")
                .collect::<String>(),
        )
        .expect("write beads issues");
    }
}

#[given("a Beads fixture repository")]
fn given_beads_fixture_repo(world: &mut KanbusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("beads-interop");
    if repo_path.exists() {
        fs::remove_dir_all(&repo_path).expect("clean existing repo");
    }
    fs::create_dir_all(repo_path.join(".beads")).expect("create beads dir");
    let fixture = fixture_beads_dir();
    fs::copy(
        fixture.join("issues.jsonl"),
        repo_path.join(".beads").join("issues.jsonl"),
    )
    .expect("copy issues");
    fs::copy(
        fixture.join("metadata.json"),
        repo_path.join(".beads").join("metadata.json"),
    )
    .expect("copy metadata");
    fs::write(repo_path.join(".kanbus.yml"), "").expect("write kanbus config");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
    world.last_beads_issue_id = None;
}

#[when("I run \"kanbus --beads create Interop child via Kanbus --parent bdx-epic\"")]
fn when_create_interop_child(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create Interop child via Kanbus --parent bdx-epic",
    );
}

#[when("I run \"kanbus --beads create Interop updatable --parent bdx-epic\"")]
fn when_create_interop_updatable(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create Interop updatable --parent bdx-epic",
    );
}

#[when("I run \"kanbus --beads create Interop deletable --parent bdx-epic\"")]
fn when_create_interop_deletable(world: &mut KanbusWorld) {
    run_cli(
        world,
        "kanbus --beads create Interop deletable --parent bdx-epic",
    );
}

#[given(regex = r#"a kanbus issue "(?P<child>[^"]+)" exists with parent "(?P<parent_id>[^"]+)""#)]
fn given_kanbus_child_issue(world: &mut KanbusWorld, child: String, parent: String) {
    upsert_beads_issue(world, &parent, None, None);
    upsert_beads_issue(world, &child, Some(&parent), None);
    world.last_beads_issue_id = Some(child);
}

#[given(
    regex = r#"a kanbus issue "(?P<identifier>[^"]+)" exists with dependency "(?P<dependency>[^"]+)""#
)]
fn given_kanbus_issue_with_dependency(world: &mut KanbusWorld, issue: String, dep: String) {
    let parts: Vec<&str> = dep.split_whitespace().collect();
    if parts.len() != 2 {
        panic!("dependency must be '<type> <target>'");
    }
    let dep_type = parts[0];
    let target = parts[1];
    upsert_beads_issue(world, target, None, None);
    upsert_beads_issue(world, &issue, None, None);
    add_beads_dependency(world, &issue, target, dep_type);
    world.last_beads_issue_id = Some(issue);
}

#[given(
    regex = r#"a kanbus issue "(?P<identifier>[^"]+)" exists with status "(?P<status>[^"]+)""#
)]
fn given_kanbus_issue_with_status(world: &mut KanbusWorld, issue: String, status: String) {
    upsert_beads_issue(world, &issue, None, Some(&status));
    world.last_beads_issue_id = Some(issue);
}

#[when(expr = "I update the last created beads issue to status {string}")]
fn when_update_last_beads_issue(world: &mut KanbusWorld, status: String) {
    let identifier = capture_last_beads_issue_id(world).expect("last beads issue id missing");
    run_cli(
        world,
        &format!("kanbus --beads update {} --status {}", identifier, status),
    );
}

#[when("I delete the last created beads issue")]
fn when_delete_last_beads_issue(world: &mut KanbusWorld) {
    let identifier = capture_last_beads_issue_id(world).expect("last beads issue id missing");
    run_cli(world, &format!("kanbus --beads delete {}", identifier));
}

#[then("the last created beads issue should exist in beads issues.jsonl")]
fn then_last_issue_exists(world: &mut KanbusWorld) {
    let identifier = capture_last_beads_issue_id(world).expect("last beads issue id missing");
    let records = load_beads_records(&beads_issues_path(world));
    assert!(records
        .iter()
        .any(|record| record.get("id").and_then(|id| id.as_str()) == Some(identifier.as_str())));
}

#[then("beads issues.jsonl should contain the last created beads issue")]
fn then_beads_contains_last_issue(world: &mut KanbusWorld) {
    then_last_issue_exists(world);
}

#[then(expr = "beads issues.jsonl should show the last created beads issue with status {string}")]
fn then_last_issue_has_status(world: &mut KanbusWorld, status: String) {
    let identifier = capture_last_beads_issue_id(world).expect("last beads issue id missing");
    let records = load_beads_records(&beads_issues_path(world));
    let match_record = records.iter().find(|record| {
        record
            .get("id")
            .and_then(|id| id.as_str())
            .map(|value| value == identifier)
            .unwrap_or(false)
    });
    assert!(match_record.is_some(), "issue not found in beads JSONL");
    let found_status = match_record
        .and_then(|record| record.get("status"))
        .and_then(|value| value.as_str())
        .unwrap_or("");
    assert_eq!(found_status, status);
}

#[then("beads issues.jsonl should not contain the last created beads issue")]
fn then_beads_missing_last_issue(world: &mut KanbusWorld) {
    let identifier = capture_last_beads_issue_id(world).expect("last beads issue id missing");
    let records = load_beads_records(&beads_issues_path(world));
    assert!(records.iter().all(|record| {
        record
            .get("id")
            .and_then(|id| id.as_str())
            .map(|value| value != identifier)
            .unwrap_or(true)
    }));
}

#[then("the last created beads issue should appear in the Kanbus beads list output")]
fn then_last_issue_in_list_output(world: &mut KanbusWorld) {
    let identifier = capture_last_beads_issue_id(world).expect("last beads issue id missing");
    let stdout = world.stdout.as_ref().expect("command result missing");
    let display_key = format_issue_key(&identifier, true);
    assert!(
        stdout.to_lowercase().contains(&display_key.to_lowercase()),
        "issue id not in list output"
    );
}

#[then("the last created beads issue should not appear in the Kanbus beads list output")]
fn then_last_issue_not_in_list_output(world: &mut KanbusWorld) {
    let identifier = capture_last_beads_issue_id(world).expect("last beads issue id missing");
    let stdout = world.stdout.as_ref().expect("command result missing");
    let display_key = format_issue_key(&identifier, true);
    assert!(
        !stdout.to_lowercase().contains(&display_key.to_lowercase()),
        "issue id unexpectedly present in list output"
    );
}

// Additional steps for comments interoperability

#[given(regex = r#"a kanbus issue "(?P<identifier>[^"]+)" exists"#)]
fn given_kanbus_issue_exists(world: &mut KanbusWorld, identifier: String) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = load_project_directory(cwd).expect("project dir");
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
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    };

    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", identifier));
    let contents = serde_json::to_string_pretty(&issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");

    // Also add to beads issues.jsonl for compatibility
    let beads_path = cwd.join(".beads").join("issues.jsonl");
    let now = timestamp.to_rfc3339();
    let beads_record = json!({
        "id": identifier,
        "title": "Test Issue",
        "description": "",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "created_at": now,
        "created_by": "fixture",
        "updated_at": now,
    });
    let mut beads_content = fs::read_to_string(&beads_path).unwrap_or_default();
    beads_content.push_str(&serde_json::to_string(&beads_record).expect("serialize beads record"));
    beads_content.push('\n');
    fs::write(beads_path, beads_content).expect("write beads issues");
}

#[given(
    regex = r#"a kanbus issue "(?P<identifier>[^"]+)" exists with labels "(?P<labels>[^"]+)""#
)]
fn given_kanbus_issue_exists_with_labels(
    world: &mut KanbusWorld,
    identifier: String,
    labels: String,
) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = load_project_directory(cwd).expect("project dir");
    let timestamp = Utc::now();
    let label_list: Vec<String> = labels
        .split(',')
        .map(|label| label.trim().to_string())
        .filter(|label| !label.is_empty())
        .collect();

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
        labels: label_list.clone(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    };

    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", identifier));
    let contents = serde_json::to_string_pretty(&issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");

    let beads_path = cwd.join(".beads").join("issues.jsonl");
    let now = timestamp.to_rfc3339();
    let beads_record = json!({
        "id": identifier,
        "title": "Test Issue",
        "description": "",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "labels": label_list,
        "created_at": now,
        "created_by": "fixture",
        "updated_at": now,
    });
    let mut beads_content = fs::read_to_string(&beads_path).unwrap_or_default();
    beads_content.push_str(&serde_json::to_string(&beads_record).expect("serialize beads record"));
    beads_content.push('\n');
    fs::write(beads_path, beads_content).expect("write beads issues");
}

#[given(
    regex = r#"a kanbus issue "(?P<identifier>[^"]+)" exists with title "(?P<title>[^"]+)""#
)]
fn given_kanbus_issue_exists_with_title(
    world: &mut KanbusWorld,
    identifier: String,
    title: String,
) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = load_project_directory(cwd).expect("project dir");
    let timestamp = Utc::now();

    let issue = IssueData {
        identifier: identifier.clone(),
        title: title.clone(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
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
        custom: std::collections::BTreeMap::new(),
    };

    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", identifier));
    let contents = serde_json::to_string_pretty(&issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");

    let beads_path = cwd.join(".beads").join("issues.jsonl");
    let now = timestamp.to_rfc3339();
    let beads_record = json!({
        "id": identifier,
        "title": title,
        "description": "",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "created_at": now,
        "created_by": "fixture",
        "updated_at": now,
    });
    let mut beads_content = fs::read_to_string(&beads_path).unwrap_or_default();
    beads_content.push_str(&serde_json::to_string(&beads_record).expect("serialize beads record"));
    beads_content.push('\n');
    fs::write(beads_path, beads_content).expect("write beads issues");
}

#[given(
    regex = r#"a kanbus issue "(?P<identifier>[^"]+)" exists with priority (?P<priority>\d+)"#
)]
fn given_kanbus_issue_exists_with_priority(
    world: &mut KanbusWorld,
    identifier: String,
    priority: i32,
) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = load_project_directory(cwd).expect("project dir");
    let timestamp = Utc::now();

    let issue = IssueData {
        identifier: identifier.clone(),
        title: "Test Issue".to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    };

    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", identifier));
    let contents = serde_json::to_string_pretty(&issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");

    let beads_path = cwd.join(".beads").join("issues.jsonl");
    let now = timestamp.to_rfc3339();
    let beads_record = json!({
        "id": identifier,
        "title": "Test Issue",
        "description": "",
        "status": "open",
        "priority": priority,
        "issue_type": "task",
        "created_at": now,
        "created_by": "fixture",
        "updated_at": now,
    });
    let mut beads_content = fs::read_to_string(&beads_path).unwrap_or_default();
    beads_content.push_str(&serde_json::to_string(&beads_record).expect("serialize beads record"));
    beads_content.push('\n');
    fs::write(beads_path, beads_content).expect("write beads issues");
}

#[given(regex = r#"a beads issue "(?P<identifier>[^"]+)" exists"#)]
fn given_beads_issue_exists(world: &mut KanbusWorld, identifier: String) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let timestamp = Utc::now();
    let now = timestamp.to_rfc3339();

    // Add to beads issues.jsonl only (not in Kanbus project/issues)
    let beads_path = cwd.join(".beads").join("issues.jsonl");
    let beads_record = json!({
        "id": identifier,
        "title": "Beads-only Issue",
        "description": "",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "created_at": now,
        "created_by": "fixture",
        "updated_at": now,
    });
    let mut beads_content = fs::read_to_string(&beads_path).unwrap_or_default();
    beads_content.push_str(&serde_json::to_string(&beads_record).expect("serialize beads record"));
    beads_content.push('\n');
    fs::write(beads_path, beads_content).expect("write beads issues");
}

// Stdin test implementation removed - these tests will be skipped until implemented

#[then(
    regex = r#"the comments should appear in order: "(?P<comment1>[^"]+)", "(?P<comment2>[^"]+)", "(?P<comment3>[^"]+)""#
)]
fn then_comments_in_order(
    world: &mut KanbusWorld,
    comment1: String,
    comment2: String,
    comment3: String,
) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let pos1 = stdout.find(&comment1).expect("comment 1 not found");
    let pos2 = stdout.find(&comment2).expect("comment 2 not found");
    let pos3 = stdout.find(&comment3).expect("comment 3 not found");

    assert!(pos1 < pos2, "comments 1 and 2 not in order");
    assert!(pos2 < pos3, "comments 2 and 3 not in order");
}

// Additional steps for delete interoperability

#[given(regex = r#"a kanbus-only issue "(?P<identifier>[^"]+)" exists"#)]
fn given_kanbus_only_issue(world: &mut KanbusWorld, identifier: String) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let project_dir = load_project_directory(cwd).expect("project dir");
    let timestamp = Utc::now();

    let issue = IssueData {
        identifier: identifier.clone(),
        title: "Kanbus-only Issue".to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
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
        custom: std::collections::BTreeMap::new(),
    };

    // Only write to Kanbus project/issues, NOT to beads
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", identifier));
    let contents = serde_json::to_string_pretty(&issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

#[given(
    regex = r#"a beads issue "(?P<child>[^"]+)" exists with parent "(?P<parent_id>[^"]+)""#
)]
fn given_beads_issue_with_parent(world: &mut KanbusWorld, identifier: String, parent_id: String) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let timestamp = Utc::now();
    let now = timestamp.to_rfc3339();

    let beads_path = cwd.join(".beads").join("issues.jsonl");
    let beads_record = json!({
        "id": identifier,
        "title": "Child Issue",
        "description": "",
        "status": "open",
        "priority": 2,
        "issue_type": "task",
        "parent": parent_id,
        "created_at": now,
        "created_by": "fixture",
        "updated_at": now,
    });
    let mut beads_content = fs::read_to_string(&beads_path).unwrap_or_default();
    beads_content.push_str(&serde_json::to_string(&beads_record).expect("serialize beads record"));
    beads_content.push('\n');
    fs::write(beads_path, beads_content).expect("write beads issues");
}

#[then(regex = r#"beads issues\.jsonl should contain "(?P<identifier>[^"]+)""#)]
fn then_beads_jsonl_contains(world: &mut KanbusWorld, identifier: String) {
    let beads_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".beads")
        .join("issues.jsonl");
    let contents = fs::read_to_string(beads_path).expect("read beads issues");
    assert!(contents.contains(&identifier), "identifier not found in issues.jsonl");
}

#[then(regex = r#"beads issues\.jsonl should not contain "(?P<identifier>[^"]+)""#)]
fn then_beads_jsonl_not_contains(world: &mut KanbusWorld, identifier: String) {
    let beads_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".beads")
        .join("issues.jsonl");
    let contents = fs::read_to_string(beads_path).expect("read beads issues");
    assert!(
        !contents.contains(&identifier),
        "identifier still present in issues.jsonl"
    );
}
