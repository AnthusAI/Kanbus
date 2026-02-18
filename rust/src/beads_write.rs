//! Beads compatibility write helpers.

use chrono::Utc;
use rand::Rng;
use serde_json::{json, Map, Value};
use std::collections::HashSet;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::sync::{Mutex, OnceLock};
use uuid::Uuid;

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

fn beads_comment_uuid(issue_id: &str, comment_id: &str) -> String {
    let key = format!("kanbus-comment:{issue_id}:{comment_id}");
    Uuid::new_v5(&Uuid::NAMESPACE_URL, key.as_bytes()).to_string()
}

fn comment_id_value(comment: &Value) -> Option<String> {
    match comment.get("id")? {
        Value::String(value) => Some(value.clone()),
        Value::Number(value) => Some(value.to_string()),
        _ => None,
    }
}

fn match_comment_prefix(
    issue_id: &str,
    comments: &[Value],
    prefix: &str,
) -> Result<usize, KanbusError> {
    let normalized = prefix.trim().to_ascii_lowercase();
    if normalized.is_empty() {
        return Err(KanbusError::IssueOperation(
            "comment id is required".to_string(),
        ));
    }
    let mut matches = Vec::new();
    for (index, comment) in comments.iter().enumerate() {
        let Some(comment_id) = comment_id_value(comment) else {
            continue;
        };
        let uuid = beads_comment_uuid(issue_id, &comment_id);
        if uuid.to_ascii_lowercase().starts_with(&normalized) {
            matches.push((index, uuid));
        }
    }
    match matches.len() {
        0 => Err(KanbusError::IssueOperation("comment not found".to_string())),
        1 => Ok(matches[0].0),
        _ => {
            let ids = matches
                .iter()
                .map(|(_index, uuid)| uuid.chars().take(6).collect::<String>())
                .collect::<Vec<_>>()
                .join(", ");
            Err(KanbusError::IssueOperation(format!(
                "comment id prefix is ambiguous; matches: {ids}"
            )))
        }
    }
}

/// Add a comment to a Beads-compatible issue.
pub fn add_beads_comment(
    root: &Path,
    identifier: &str,
    author: &str,
    text: &str,
) -> Result<(), KanbusError> {
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
    let mut found = false;
    for record in &mut records {
        if record.get("id").and_then(|id| id.as_str()) != Some(identifier) {
            continue;
        }
        found = true;
        let comments_value = record
            .get_mut("comments")
            .and_then(Value::as_array_mut);
        let comments = if let Some(existing) = comments_value {
            existing
        } else {
            record
                .as_object_mut()
                .expect("record object")
                .insert("comments".to_string(), Value::Array(Vec::new()));
            record
                .get_mut("comments")
                .and_then(Value::as_array_mut)
                .expect("comments array")
        };
        let comment_id = (comments.len() + 1) as i64;
        let created_at = Utc::now().to_rfc3339();
        comments.push(json!({
            "id": comment_id,
            "issue_id": identifier,
            "author": author,
            "text": text,
            "created_at": created_at,
        }));
        if let Some(updated_at) = record.get_mut("updated_at") {
            *updated_at = json!(created_at);
        } else if let Some(object) = record.as_object_mut() {
            object.insert("updated_at".to_string(), json!(created_at));
        }
        break;
    }
    if !found {
        return Err(KanbusError::IssueOperation("not found".to_string()));
    }
    write_beads_records(&issues_path, &records)?;
    Ok(())
}

/// Update a Beads-compatible comment by id prefix.
pub fn update_beads_comment(
    root: &Path,
    identifier: &str,
    comment_id_prefix: &str,
    text: &str,
) -> Result<(), KanbusError> {
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
    let mut found = false;
    for record in &mut records {
        if record.get("id").and_then(|id| id.as_str()) != Some(identifier) {
            continue;
        }
        found = true;
        let Some(comments) = record.get_mut("comments").and_then(Value::as_array_mut) else {
            return Err(KanbusError::IssueOperation("comment not found".to_string()));
        };
        let index = match_comment_prefix(identifier, comments, comment_id_prefix)?;
        if let Some(comment) = comments.get_mut(index).and_then(Value::as_object_mut) {
            comment.insert("text".to_string(), json!(text));
        }
        let updated_at = Utc::now().to_rfc3339();
        if let Some(updated) = record.get_mut("updated_at") {
            *updated = json!(updated_at);
        } else if let Some(object) = record.as_object_mut() {
            object.insert("updated_at".to_string(), json!(updated_at));
        }
        break;
    }
    if !found {
        return Err(KanbusError::IssueOperation("not found".to_string()));
    }
    write_beads_records(&issues_path, &records)?;
    Ok(())
}

/// Delete a Beads-compatible comment by id prefix.
pub fn delete_beads_comment(
    root: &Path,
    identifier: &str,
    comment_id_prefix: &str,
) -> Result<(), KanbusError> {
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
    let mut found = false;
    for record in &mut records {
        if record.get("id").and_then(|id| id.as_str()) != Some(identifier) {
            continue;
        }
        found = true;
        let Some(comments) = record.get_mut("comments").and_then(Value::as_array_mut) else {
            return Err(KanbusError::IssueOperation("comment not found".to_string()));
        };
        let index = match_comment_prefix(identifier, comments, comment_id_prefix)?;
        comments.remove(index);
        let updated_at = Utc::now().to_rfc3339();
        if let Some(updated) = record.get_mut("updated_at") {
            *updated = json!(updated_at);
        } else if let Some(object) = record.as_object_mut() {
            object.insert("updated_at".to_string(), json!(updated_at));
        }
        break;
    }
    if !found {
        return Err(KanbusError::IssueOperation("not found".to_string()));
    }
    write_beads_records(&issues_path, &records)?;
    Ok(())
}

/// Update a Beads-compatible issue in .beads/issues.jsonl.
pub fn update_beads_issue(
    root: &Path,
    identifier: &str,
    status: Option<&str>,
    title: Option<&str>,
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

    let mut records = load_beads_records(&issues_path)?;
    let mut exact_match_index = None;
    let mut partial_match_indices = Vec::new();

    for (index, record) in records.iter().enumerate() {
        if let Some(record_id) = record.get("id").and_then(|id| id.as_str()) {
            if record_id == identifier {
                exact_match_index = Some(index);
                break;
            } else if issue_id_matches_beads(identifier, record_id) {
                partial_match_indices.push((index, record_id.to_string()));
            }
        }
    }

    let match_index = if let Some(index) = exact_match_index {
        index
    } else {
        match partial_match_indices.len() {
            0 => return Err(KanbusError::IssueOperation("not found".to_string())),
            1 => partial_match_indices[0].0,
            _ => {
                let ids: Vec<String> = partial_match_indices
                    .iter()
                    .map(|(_, id)| id.clone())
                    .collect();
                return Err(KanbusError::IssueOperation(format!(
                    "ambiguous identifier, matches: {}",
                    ids.join(", ")
                )));
            }
        }
    };

    let updated_at = Utc::now().to_rfc3339();
    let record = &mut records[match_index];

    let mut updated = false;
    if let Some(new_status) = status {
        record
            .as_object_mut()
            .expect("beads record")
            .insert("status".to_string(), json!(new_status));
        updated = true;
    }
    if let Some(new_title) = title {
        record
            .as_object_mut()
            .expect("beads record")
            .insert("title".to_string(), json!(new_title));
        updated = true;
    }
    if let Some(new_description) = description {
        record
            .as_object_mut()
            .expect("beads record")
            .insert("description".to_string(), json!(new_description));
        updated = true;
    }
    if !updated {
        return Err(KanbusError::IssueOperation(
            "no updates requested".to_string(),
        ));
    }
    record
        .as_object_mut()
        .expect("beads record")
        .insert("updated_at".to_string(), json!(updated_at));

    write_beads_records(&issues_path, &records)?;
    load_beads_issue_by_id(root, identifier)
}

/// Check if an abbreviated identifier matches a full identifier for beads.
///
/// # Arguments
/// * `abbreviated` - Abbreviated ID (e.g., "tskl-abcdef", "custom-uuid00").
/// * `full_id` - Full ID (e.g., "tskl-abcdef2", "custom-uuid-0000001").
///
/// # Returns
/// True if abbreviated ID matches the full ID.
fn issue_id_matches_beads(abbreviated: &str, full_id: &str) -> bool {
    use crate::ids::format_issue_key;

    let abbreviated_formatted = format_issue_key(full_id, false);

    if abbreviated == abbreviated_formatted {
        return true;
    }

    if abbreviated.len() >= full_id.len() {
        return false;
    }

    full_id.starts_with(abbreviated)
}

fn load_beads_records(path: &Path) -> Result<Vec<Value>, KanbusError> {
    let contents = fs::read_to_string(path).map_err(|error| KanbusError::Io(error.to_string()))?;
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
    Err(KanbusError::IssueOperation("invalid beads id".to_string()))
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
