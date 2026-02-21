//! Event history recording and retrieval.

use chrono::{SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use uuid::Uuid;

use crate::error::KanbusError;
use crate::file_io::find_project_local_directory;
use crate::models::IssueData;

pub const EVENT_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EventType {
    IssueCreated,
    StateTransition,
    FieldUpdated,
    CommentAdded,
    CommentUpdated,
    CommentDeleted,
    DependencyAdded,
    DependencyRemoved,
    IssueDeleted,
    IssueLocalized,
    IssuePromoted,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventRecord {
    pub schema_version: u32,
    pub event_id: String,
    pub issue_id: String,
    pub event_type: EventType,
    pub occurred_at: String,
    pub actor_id: String,
    pub payload: Value,
}

impl EventRecord {
    pub fn new(
        issue_id: impl Into<String>,
        event_type: EventType,
        actor_id: impl Into<String>,
        payload: Value,
        occurred_at: String,
    ) -> Self {
        Self {
            schema_version: EVENT_SCHEMA_VERSION,
            event_id: Uuid::new_v4().to_string(),
            issue_id: issue_id.into(),
            event_type,
            occurred_at,
            actor_id: actor_id.into(),
            payload,
        }
    }
}

pub fn now_timestamp() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

pub fn event_filename(occurred_at: &str, event_id: &str) -> String {
    format!("{occurred_at}__{event_id}.json")
}

pub fn events_dir_for_project(project_dir: &Path) -> PathBuf {
    project_dir.join("events")
}

pub fn events_dir_for_local(project_dir: &Path) -> Result<PathBuf, KanbusError> {
    let parent = project_dir
        .parent()
        .ok_or_else(|| KanbusError::Io("project-local path unavailable".to_string()))?;
    Ok(parent.join("project-local").join("events"))
}

pub fn events_dir_for_issue_path(
    project_dir: &Path,
    issue_path: &Path,
) -> Result<PathBuf, KanbusError> {
    if let Some(local_dir) = find_project_local_directory(project_dir) {
        if issue_path.starts_with(&local_dir) {
            return Ok(local_dir.join("events"));
        }
    }
    Ok(events_dir_for_project(project_dir))
}

pub fn events_dir_for_issue(project_dir: &Path, issue_id: &str) -> PathBuf {
    if let Some(local_dir) = find_project_local_directory(project_dir) {
        let local_issue = local_dir.join("issues").join(format!("{issue_id}.json"));
        if local_issue.exists() {
            return local_dir.join("events");
        }
    }
    events_dir_for_project(project_dir)
}

pub fn write_events_batch(
    events_dir: &Path,
    events: &[EventRecord],
) -> Result<Vec<PathBuf>, KanbusError> {
    if events.is_empty() {
        return Ok(Vec::new());
    }
    fs::create_dir_all(events_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let mut written = Vec::new();
    for event in events {
        let filename = event_filename(&event.occurred_at, &event.event_id);
        let final_path = events_dir.join(&filename);
        let temp_path = events_dir.join(format!(".{filename}.tmp"));
        let result = (|| {
            let payload = serde_json::to_string_pretty(event)
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&temp_path)
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            file.write_all(payload.as_bytes())
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            file.flush()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            fs::rename(&temp_path, &final_path)
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            Ok(final_path)
        })();
        match result {
            Ok(path) => written.push(path),
            Err(error) => {
                let _ = fs::remove_file(&temp_path);
                rollback_event_files(&written);
                return Err(error);
            }
        }
    }
    Ok(written)
}

pub fn rollback_event_files(paths: &[PathBuf]) {
    for path in paths {
        let _ = fs::remove_file(path);
    }
}

pub fn issue_created_payload(issue: &IssueData) -> Value {
    json!({
        "title": issue.title,
        "description": issue.description,
        "issue_type": issue.issue_type,
        "status": issue.status,
        "priority": issue.priority,
        "assignee": issue.assignee,
        "parent": issue.parent,
        "labels": issue.labels,
    })
}

pub fn issue_deleted_payload(issue: &IssueData) -> Value {
    json!({
        "title": issue.title,
        "issue_type": issue.issue_type,
        "status": issue.status,
    })
}

pub fn state_transition_payload(from_status: &str, to_status: &str) -> Value {
    json!({
        "from_status": from_status,
        "to_status": to_status,
    })
}

pub fn comment_payload(comment_id: &str, comment_author: &str) -> Value {
    json!({
        "comment_id": comment_id,
        "comment_author": comment_author,
    })
}

pub fn comment_updated_payload(comment_id: &str, comment_author: &str) -> Value {
    json!({
        "comment_id": comment_id,
        "comment_author": comment_author,
        "changed_fields": ["text"],
    })
}

pub fn dependency_payload(dependency_type: &str, target_id: &str) -> Value {
    json!({
        "dependency_type": dependency_type,
        "target_id": target_id,
    })
}

pub fn transfer_payload(from_location: &str, to_location: &str) -> Value {
    json!({
        "from_location": from_location,
        "to_location": to_location,
    })
}

pub fn field_update_payload(before: &IssueData, after: &IssueData) -> Option<Value> {
    let mut changes = Map::new();
    push_change(&mut changes, "title", json!(before.title), json!(after.title));
    push_change(
        &mut changes,
        "description",
        json!(before.description),
        json!(after.description),
    );
    push_change(
        &mut changes,
        "assignee",
        json!(before.assignee),
        json!(after.assignee),
    );
    push_change(
        &mut changes,
        "priority",
        json!(before.priority),
        json!(after.priority),
    );
    push_change(&mut changes, "labels", json!(before.labels), json!(after.labels));
    push_change(&mut changes, "parent", json!(before.parent), json!(after.parent));
    if changes.is_empty() {
        None
    } else {
        Some(json!({ "changes": changes }))
    }
}

fn push_change(changes: &mut Map<String, Value>, field: &str, from: Value, to: Value) {
    if from == to {
        return;
    }
    changes.insert(field.to_string(), json!({ "from": from, "to": to }));
}

pub fn build_update_events(
    before: &IssueData,
    after: &IssueData,
    actor_id: &str,
    occurred_at: &str,
) -> Vec<EventRecord> {
    let mut events = Vec::new();
    if before.status != after.status {
        events.push(EventRecord::new(
            after.identifier.clone(),
            EventType::StateTransition,
            actor_id,
            state_transition_payload(&before.status, &after.status),
            occurred_at.to_string(),
        ));
    }
    if let Some(payload) = field_update_payload(before, after) {
        events.push(EventRecord::new(
            after.identifier.clone(),
            EventType::FieldUpdated,
            actor_id,
            payload,
            occurred_at.to_string(),
        ));
    }
    events
}

pub fn load_issue_events(
    project_dir: &Path,
    issue_id: &str,
    before: Option<&str>,
    limit: usize,
) -> Result<(Vec<EventRecord>, Option<String>), KanbusError> {
    let events_dir = events_dir_for_issue(project_dir, issue_id);
    if !events_dir.exists() {
        return Ok((Vec::new(), None));
    }
    let mut filenames = Vec::new();
    for entry in fs::read_dir(&events_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        if let Some(name) = path.file_name().and_then(|value| value.to_str()) {
            filenames.push(name.to_string());
        }
    }
    if let Some(cursor) = before {
        filenames.retain(|name| name.as_str() < cursor);
    }
    filenames.sort();
    filenames.reverse();

    let mut results = Vec::new();
    let mut next_before = None;
    for filename in filenames {
        if results.len() >= limit {
            break;
        }
        let path = events_dir.join(&filename);
        let bytes = fs::read(&path).map_err(|error| KanbusError::Io(error.to_string()))?;
        let record: EventRecord =
            serde_json::from_slice(&bytes).map_err(|error| KanbusError::Io(error.to_string()))?;
        if record.issue_id == issue_id {
            results.push(record);
            next_before = Some(filename);
        }
    }
    let cursor = if results.len() >= limit { next_before } else { None };
    Ok((results, cursor))
}
