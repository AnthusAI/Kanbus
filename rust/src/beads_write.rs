//! Beads compatibility write helpers.

use chrono::Utc;
use rand::Rng;
use serde_json::{json, Map, Value};
use std::collections::HashSet;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::sync::{Mutex, OnceLock};

use crate::error::KanbusError;
use crate::migration::load_beads_issue_by_id;
use crate::models::{DependencyLink, IssueData};
use crate::users::get_current_user;

/// Create a Beads-compatible issue in .beads/issues.jsonl.
pub fn create_beads_issue(
    root: &Path,
    title: &str,
    issue_type: Option<&str>,
    priority: Option<u8>,
    assignee: Option<&str>,
    parent: Option<&str>,
    description: Option<&str>,
) -> Result<IssueData, KanbusError> {
    let beads_dir = root.join(".beads");
    if !beads_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "no .beads directory".to_string(),
        ));
    }
    let issues_path = beads_dir.join("issues.jsonl");
    if !issues_path.exists() {
        return Err(KanbusError::IssueOperation("no issues.jsonl".to_string()));
    }
    let records = load_beads_records(&issues_path)?;
    if records.is_empty() {
        return Err(KanbusError::IssueOperation(
            "no beads issues available".to_string(),
        ));
    }
    let existing_ids = collect_ids(&records)?;
    if let Some(parent_id) = parent {
        if !existing_ids.contains(parent_id) {
            return Err(KanbusError::IssueOperation("not found".to_string()));
        }
    }
    let prefix = derive_prefix(&existing_ids)?;
    let identifier = generate_identifier(&existing_ids, &prefix, parent)?;

    let created_at = Utc::now();
    let created_at_text = created_at.to_rfc3339();
    let created_by = get_current_user();
    let resolved_type = issue_type.unwrap_or("task");
    let resolved_priority = priority.unwrap_or(2);
    let resolved_description = description.unwrap_or("");

    let mut dependencies = Vec::new();
    let mut dependency_links = Vec::new();
    if let Some(parent_id) = parent {
        dependencies.push(json!({
            "issue_id": identifier,
            "depends_on_id": parent_id,
            "type": "parent-child",
            "created_at": created_at_text,
            "created_by": created_by,
        }));
        dependency_links.push(DependencyLink {
            target: parent_id.to_string(),
            dependency_type: "parent-child".to_string(),
        });
    }

    let mut record = Map::new();
    record.insert("id".to_string(), json!(identifier));
    record.insert("title".to_string(), json!(title));
    record.insert("description".to_string(), json!(resolved_description));
    record.insert("status".to_string(), json!("open"));
    record.insert("priority".to_string(), json!(resolved_priority));
    record.insert("issue_type".to_string(), json!(resolved_type));
    record.insert("created_at".to_string(), json!(created_at_text));
    record.insert("created_by".to_string(), json!(created_by));
    record.insert("updated_at".to_string(), json!(created_at_text));
    record.insert("owner".to_string(), json!(get_current_user()));
    if let Some(assignee_value) = assignee {
        record.insert("assignee".to_string(), json!(assignee_value));
    }
    if !dependencies.is_empty() {
        record.insert("dependencies".to_string(), Value::Array(dependencies));
    }
    record.insert("comments".to_string(), Value::Array(Vec::new()));

    append_record(&issues_path, Value::Object(record))?;

    Ok(IssueData {
        identifier,
        title: title.to_string(),
        description: resolved_description.to_string(),
        issue_type: resolved_type.to_string(),
        status: "open".to_string(),
        priority: resolved_priority as i32,
        assignee: assignee.map(|value| value.to_string()),
        creator: Some(created_by),
        parent: parent.map(|value| value.to_string()),
        labels: Vec::new(),
        dependencies: dependency_links,
        comments: Vec::new(),
        created_at,
        updated_at: created_at,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    })
}

/// Update a Beads-compatible issue in .beads/issues.jsonl.
pub fn update_beads_issue(
    root: &Path,
    identifier: &str,
    status: Option<&str>,
) -> Result<IssueData, KanbusError> {
    let beads_dir = root.join(".beads");
    if !beads_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "no .beads directory".to_string(),
        ));
    }
    let issues_path = beads_dir.join("issues.jsonl");
    if !issues_path.exists() {
        return Err(KanbusError::IssueOperation("no issues.jsonl".to_string()));
    }

    let mut records = load_beads_records(&issues_path)?;
    let mut updated = false;
    let updated_at = Utc::now().to_rfc3339();
    for record in records.iter_mut() {
        if record.get("id").and_then(|id| id.as_str()) != Some(identifier) {
            continue;
        }
        if let Some(new_status) = status {
            record
                .as_object_mut()
                .expect("beads record")
                .insert("status".to_string(), json!(new_status));
        }
        record
            .as_object_mut()
            .expect("beads record")
            .insert("updated_at".to_string(), json!(updated_at));
        updated = true;
        break;
    }
    if !updated {
        return Err(KanbusError::IssueOperation("not found".to_string()));
    }

    write_beads_records(&issues_path, &records)?;
    load_beads_issue_by_id(root, identifier)
}

fn load_beads_records(path: &Path) -> Result<Vec<Value>, KanbusError> {
    let contents =
        fs::read_to_string(path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let mut records = Vec::new();
    for line in contents.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let record: Value =
            serde_json::from_str(line).map_err(|error| KanbusError::Io(error.to_string()))?;
        records.push(record);
    }
    Ok(records)
}

fn write_beads_records(path: &Path, records: &[Value]) -> Result<(), KanbusError> {
    let mut file = OpenOptions::new()
        .write(true)
        .truncate(true)
        .open(path)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    for record in records {
        let line =
            serde_json::to_string(record).map_err(|error| KanbusError::Io(error.to_string()))?;
        writeln!(file, "{}", line).map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    Ok(())
}

/// Delete a Beads-compatible issue in .beads/issues.jsonl.
pub fn delete_beads_issue(root: &Path, identifier: &str) -> Result<(), KanbusError> {
    let beads_dir = root.join(".beads");
    if !beads_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "no .beads directory".to_string(),
        ));
    }
    let issues_path = beads_dir.join("issues.jsonl");
    if !issues_path.exists() {
        return Err(KanbusError::IssueOperation("no issues.jsonl".to_string()));
    }
    let records = load_beads_records(&issues_path)?;
    let original_count = records.len();
    let remaining: Vec<Value> = records
        .into_iter()
        .filter(|record| record.get("id").and_then(|id| id.as_str()) != Some(identifier))
        .collect();
    if remaining.len() == original_count {
        return Err(KanbusError::IssueOperation("not found".to_string()));
    }
    write_beads_records(&issues_path, &remaining)?;
    Ok(())
}

fn collect_ids(records: &[Value]) -> Result<HashSet<String>, KanbusError> {
    let mut ids = HashSet::new();
    for record in records {
        let identifier = record
            .get("id")
            .and_then(|value| value.as_str())
            .ok_or_else(|| KanbusError::IssueOperation("missing id".to_string()))?;
        ids.insert(identifier.to_string());
    }
    Ok(ids)
}

fn derive_prefix(existing_ids: &HashSet<String>) -> Result<String, KanbusError> {
    for identifier in existing_ids {
        if let Some((prefix, _rest)) = identifier.split_once('-') {
            return Ok(prefix.to_string());
        }
    }
    Err(KanbusError::IssueOperation(
        "invalid beads id".to_string(),
    ))
}

fn generate_identifier(
    existing_ids: &HashSet<String>,
    prefix: &str,
    parent: Option<&str>,
) -> Result<String, KanbusError> {
    if let Some(parent_id) = parent {
        let suffix = next_child_suffix(existing_ids, parent_id);
        return Ok(format!("{parent_id}.{suffix}"));
    }
    for _ in 0..10 {
        let slug = generate_slug();
        let identifier = format!("{prefix}-{slug}");
        if !existing_ids.contains(&identifier) {
            return Ok(identifier);
        }
    }
    Err(KanbusError::IdGenerationFailed(
        "unable to generate unique id after 10 attempts".to_string(),
    ))
}

fn next_child_suffix(existing_ids: &HashSet<String>, parent: &str) -> i32 {
    let prefix = format!("{parent}.");
    let mut max_suffix = 0;
    for identifier in existing_ids {
        if !identifier.starts_with(&prefix) {
            continue;
        }
        let suffix = identifier.trim_start_matches(&prefix);
        if let Ok(value) = suffix.parse::<i32>() {
            max_suffix = max_suffix.max(value);
        }
    }
    max_suffix + 1
}

fn generate_slug() -> String {
    if let Some(value) = next_beads_slug() {
        return value;
    }
    let alphabet: Vec<char> = "abcdefghijklmnopqrstuvwxyz0123456789".chars().collect();
    let mut rng = rand::thread_rng();
    (0..3)
        .map(|_| {
            let index = rng.gen_range(0..alphabet.len());
            alphabet[index]
        })
        .collect()
}

fn append_record(path: &Path, record: Value) -> Result<(), KanbusError> {
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    writeln!(file, "{record}").map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(())
}
static TEST_BEADS_SLUG_SEQUENCE: OnceLock<Mutex<Vec<String>>> = OnceLock::new();

/// Set a deterministic Beads slug sequence for tests.
///
/// # Arguments
/// * `sequence` - Optional list of slug values to consume before random generation.
pub fn set_test_beads_slug_sequence(sequence: Option<Vec<String>>) {
    let cell = TEST_BEADS_SLUG_SEQUENCE.get_or_init(|| Mutex::new(Vec::new()));
    let mut guard = cell.lock().expect("lock test beads slug sequence");
    *guard = sequence.unwrap_or_default();
}

fn next_beads_slug() -> Option<String> {
    let cell = TEST_BEADS_SLUG_SEQUENCE.get_or_init(|| Mutex::new(Vec::new()));
    let mut guard = cell.lock().expect("lock test beads slug sequence");
    if guard.is_empty() {
        return None;
    }
    Some(guard.remove(0))
}
