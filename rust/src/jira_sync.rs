//! Jira synchronization support.
//!
//! Pulls issues from a remote Jira project into the local Kanbus project.
//! Secrets are read from environment variables JIRA_API_TOKEN and JIRA_USER_EMAIL.

use std::collections::{BTreeMap, HashSet};
use std::path::Path;

use chrono::{DateTime, Utc};
use serde_json::Value;

use crate::error::KanbusError;
use crate::file_io::load_project_directory;
use crate::ids::{generate_issue_identifier, IssueIdentifierRequest};
use crate::issue_files::{
    issue_path_for_identifier, list_issue_identifiers, read_issue_from_file, write_issue_to_file,
};
use crate::models::{IssueComment, IssueData, JiraConfiguration};

/// Result of a Jira pull operation.
#[derive(Debug)]
pub struct JiraPullResult {
    pub pulled: usize,
    pub updated: usize,
}

/// Pull issues from a Jira project into the local Kanbus project.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `jira_config` - Jira configuration from .kanbus.yml.
/// * `project_key` - Kanbus project key (issue ID prefix).
/// * `dry_run` - If true, print what would be done without writing any files.
///
/// # Errors
/// Returns `KanbusError` if config, authentication, or file operations fail.
pub fn pull_from_jira(
    root: &Path,
    jira_config: &JiraConfiguration,
    project_key: &str,
    dry_run: bool,
) -> Result<JiraPullResult, KanbusError> {
    let api_token = std::env::var("JIRA_API_TOKEN").map_err(|_| {
        KanbusError::Configuration("JIRA_API_TOKEN environment variable is not set".to_string())
    })?;
    let user_email = std::env::var("JIRA_USER_EMAIL").map_err(|_| {
        KanbusError::Configuration("JIRA_USER_EMAIL environment variable is not set".to_string())
    })?;

    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");

    if !issues_dir.exists() {
        return Err(KanbusError::IssueOperation(
            "issues directory does not exist".to_string(),
        ));
    }

    let jira_issues = fetch_all_jira_issues(jira_config, &user_email, &api_token)?;

    // Build index: jira_key -> kanbus identifier, for idempotency
    let existing_ids = list_issue_identifiers(&issues_dir)?;
    let jira_key_index = build_jira_key_index(&existing_ids, &issues_dir);

    let mut pulled = 0usize;
    let mut updated = 0usize;

    // First pass: collect all Jira keys and their Kanbus IDs so parent links can be resolved
    let mut jira_key_to_kanbus_id: BTreeMap<String, String> = jira_key_index.clone();

    // Pre-assign IDs for new issues so parents can be resolved
    let mut new_issues_ids: BTreeMap<String, String> = BTreeMap::new();
    let mut all_existing = existing_ids.clone();
    for jira_issue in &jira_issues {
        let jira_key = jira_issue_key(jira_issue);
        let entry = jira_key_to_kanbus_id.entry(jira_key.clone());
        if let std::collections::btree_map::Entry::Vacant(vacant) = entry {
            let request = IssueIdentifierRequest {
                title: jira_issue_summary(jira_issue),
                existing_ids: all_existing.clone(),
                prefix: project_key.to_string(),
            };
            let result = generate_issue_identifier(&request)?;
            all_existing.insert(result.identifier.clone());
            new_issues_ids.insert(jira_key, result.identifier.clone());
            vacant.insert(result.identifier);
        }
    }

    for jira_issue in &jira_issues {
        let jira_key = jira_issue_key(jira_issue);
        let kanbus_issue = map_jira_to_kanbus(jira_issue, jira_config, &jira_key_to_kanbus_id)?;

        let existing_kanbus_id = jira_key_index.get(&jira_key);
        let (kanbus_id, action) = if let Some(id) = existing_kanbus_id {
            (id.clone(), "updated")
        } else {
            (
                new_issues_ids
                    .get(&jira_key)
                    .expect("pre-assigned id")
                    .clone(),
                "pulled ",
            )
        };

        let mut issue = kanbus_issue;
        issue.identifier = kanbus_id.clone();

        // For updates, preserve fields not managed by Jira
        let issue_path = issue_path_for_identifier(&issues_dir, &kanbus_id);
        if action == "updated" {
            if let Ok(existing) = read_issue_from_file(&issue_path) {
                issue.created_at = existing.created_at;
            }
        }

        let short_key = &kanbus_id[..kanbus_id
            .len()
            .min(kanbus_id.find('-').map_or(6, |i| i + 7))];
        println!(
            "{action}  {jira_key:<12}  {short_key:<14}  \"{}\"",
            issue.title
        );

        if !dry_run {
            write_issue_to_file(&issue, &issue_path)?;
        }

        if action == "updated" {
            updated += 1;
        } else {
            pulled += 1;
        }
    }

    Ok(JiraPullResult { pulled, updated })
}

/// Fetch all issues from Jira using pagination.
fn fetch_all_jira_issues(
    jira_config: &JiraConfiguration,
    user_email: &str,
    api_token: &str,
) -> Result<Vec<Value>, KanbusError> {
    let base_url = jira_config.url.trim_end_matches('/');
    let project_key = &jira_config.project_key;
    let fields = "summary,description,issuetype,status,priority,assignee,reporter,parent,labels,comment,created,updated,resolutiondate";

    let client = reqwest::blocking::Client::new();
    let mut all_issues = Vec::new();
    let mut start_at = 0usize;
    let max_results = 100usize;

    loop {
        let url = format!(
            "{base_url}/rest/api/3/search/jql?jql=project={project_key}+ORDER+BY+created+ASC&fields={fields}&maxResults={max_results}&startAt={start_at}"
        );

        let response = client
            .get(&url)
            .basic_auth(user_email, Some(api_token))
            .header("Accept", "application/json")
            .send()
            .map_err(|e| KanbusError::IssueOperation(format!("Jira request failed: {e}")))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().unwrap_or_default();
            return Err(KanbusError::IssueOperation(format!(
                "Jira API returned {status}: {body}"
            )));
        }

        let body: Value = response.json().map_err(|e| {
            KanbusError::IssueOperation(format!("Failed to parse Jira response: {e}"))
        })?;

        let issues = body["issues"].as_array().ok_or_else(|| {
            KanbusError::IssueOperation("Jira response missing 'issues'".to_string())
        })?;

        all_issues.extend(issues.iter().cloned());

        let total = body["total"].as_u64().unwrap_or(0) as usize;
        start_at += issues.len();
        if start_at >= total || issues.is_empty() {
            break;
        }
    }

    Ok(all_issues)
}

/// Build a map from jira_key → kanbus identifier by scanning existing issue files.
fn build_jira_key_index(
    existing_ids: &HashSet<String>,
    issues_dir: &Path,
) -> BTreeMap<String, String> {
    let mut index = BTreeMap::new();
    for id in existing_ids {
        let path = issue_path_for_identifier(issues_dir, id);
        if let Ok(issue) = read_issue_from_file(&path) {
            if let Some(Value::String(jira_key)) = issue.custom.get("jira_key") {
                index.insert(jira_key.clone(), id.clone());
            }
        }
    }
    index
}

fn jira_issue_key(issue: &Value) -> String {
    issue["key"].as_str().unwrap_or("").to_string()
}

fn jira_issue_summary(issue: &Value) -> String {
    issue["fields"]["summary"]
        .as_str()
        .unwrap_or("Untitled")
        .to_string()
}

/// Map a Jira issue JSON to a Kanbus IssueData.
fn map_jira_to_kanbus(
    jira_issue: &Value,
    jira_config: &JiraConfiguration,
    jira_key_to_kanbus_id: &BTreeMap<String, String>,
) -> Result<IssueData, KanbusError> {
    let fields = &jira_issue["fields"];
    let jira_key = jira_issue_key(jira_issue);

    let title = fields["summary"].as_str().unwrap_or("Untitled").to_string();

    let description = extract_adf_text(&fields["description"]);

    let jira_type = fields["issuetype"]["name"].as_str().unwrap_or("Task");
    let issue_type = jira_config
        .type_mappings
        .get(jira_type)
        .cloned()
        .unwrap_or_else(|| jira_type.to_lowercase());

    let jira_status = fields["status"]["name"].as_str().unwrap_or("open");
    let status = map_jira_status(jira_status);

    let jira_priority = fields["priority"]["name"].as_str().unwrap_or("Medium");
    let priority = map_jira_priority(jira_priority);

    let assignee = fields["assignee"]["displayName"]
        .as_str()
        .map(str::to_string);

    let creator = fields["reporter"]["displayName"]
        .as_str()
        .map(str::to_string);

    let parent = fields["parent"]["key"]
        .as_str()
        .and_then(|key| jira_key_to_kanbus_id.get(key))
        .cloned();

    let labels: Vec<String> = fields["labels"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default();

    let comments = extract_comments(&fields["comment"]);

    let created_at =
        parse_jira_datetime(fields["created"].as_str().unwrap_or("")).unwrap_or_else(Utc::now);
    let updated_at =
        parse_jira_datetime(fields["updated"].as_str().unwrap_or("")).unwrap_or_else(Utc::now);
    let closed_at = fields["resolutiondate"]
        .as_str()
        .filter(|s| !s.is_empty())
        .and_then(parse_jira_datetime);

    let mut custom: BTreeMap<String, serde_json::Value> = BTreeMap::new();
    custom.insert("jira_key".to_string(), serde_json::Value::String(jira_key));

    Ok(IssueData {
        identifier: String::new(), // filled in by caller
        title,
        description,
        issue_type,
        status,
        priority,
        assignee,
        creator,
        parent,
        labels,
        dependencies: Vec::new(),
        comments,
        created_at,
        updated_at,
        closed_at,
        custom,
    })
}

/// Extract plain text from Atlassian Document Format (ADF) or plain string description.
fn extract_adf_text(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        Value::Object(_) => extract_adf_content(value),
        Value::Null => String::new(),
        _ => String::new(),
    }
}

fn extract_adf_content(node: &Value) -> String {
    let mut parts = Vec::new();

    if let Some(content) = node["content"].as_array() {
        for child in content {
            let node_type = child["type"].as_str().unwrap_or("");
            match node_type {
                "paragraph" | "heading" | "bulletList" | "orderedList" | "listItem"
                | "blockquote" | "codeBlock" | "panel" => {
                    let text = extract_adf_content(child);
                    if !text.is_empty() {
                        parts.push(text);
                    }
                }
                "text" => {
                    if let Some(text) = child["text"].as_str() {
                        parts.push(text.to_string());
                    }
                }
                "hardBreak" => parts.push("\n".to_string()),
                _ => {
                    let text = extract_adf_content(child);
                    if !text.is_empty() {
                        parts.push(text);
                    }
                }
            }
        }
    }

    parts.join(" ")
}

fn extract_comments(comment_field: &Value) -> Vec<IssueComment> {
    let empty = Vec::new();
    let comments_arr = match comment_field["comments"].as_array() {
        Some(arr) => arr,
        None => &empty,
    };

    comments_arr
        .iter()
        .map(|c| {
            let author = c["author"]["displayName"]
                .as_str()
                .unwrap_or("Unknown")
                .to_string();
            let text = extract_adf_text(&c["body"]);
            let created_at =
                parse_jira_datetime(c["created"].as_str().unwrap_or("")).unwrap_or_else(Utc::now);
            IssueComment {
                id: c["id"].as_str().map(str::to_string),
                author,
                text: if text.is_empty() {
                    "(empty)".to_string()
                } else {
                    text
                },
                created_at,
            }
        })
        .collect()
}

/// Map a Jira status name to a Kanbus status key.
fn map_jira_status(jira_status: &str) -> String {
    match jira_status.to_lowercase().as_str() {
        "to do" | "open" | "new" | "backlog" => "open".to_string(),
        "in progress" | "in review" | "in development" => "in_progress".to_string(),
        "done" | "closed" | "resolved" | "complete" | "completed" => "closed".to_string(),
        "blocked" | "impediment" => "blocked".to_string(),
        _ => "open".to_string(),
    }
}

/// Map a Jira priority name to a Kanbus priority integer.
fn map_jira_priority(jira_priority: &str) -> i32 {
    match jira_priority.to_lowercase().as_str() {
        "highest" | "critical" | "blocker" => 0,
        "high" => 1,
        "medium" | "normal" => 2,
        "low" => 3,
        "lowest" | "trivial" | "minor" => 4,
        _ => 2,
    }
}

fn parse_jira_datetime(s: &str) -> Option<DateTime<Utc>> {
    if s.is_empty() {
        return None;
    }
    DateTime::parse_from_rfc3339(s)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
}
