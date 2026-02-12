//! Taskulus data models.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Dependency link between issues.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependencyLink {
    pub target: String,
    #[serde(rename = "type")]
    pub dependency_type: String,
}

/// Comment on an issue.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IssueComment {
    pub author: String,
    pub text: String,
    pub created_at: DateTime<Utc>,
}

/// Issue data representation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IssueData {
    #[serde(rename = "id")]
    pub identifier: String,
    pub title: String,
    pub description: String,
    #[serde(rename = "type")]
    pub issue_type: String,
    pub status: String,
    pub priority: i32,
    pub assignee: Option<String>,
    pub creator: Option<String>,
    pub parent: Option<String>,
    pub labels: Vec<String>,
    pub dependencies: Vec<DependencyLink>,
    pub comments: Vec<IssueComment>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub closed_at: Option<DateTime<Utc>>,
    pub custom: BTreeMap<String, serde_json::Value>,
}

/// Project configuration loaded from config.yaml.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectConfiguration {
    pub prefix: String,
    pub hierarchy: Vec<String>,
    pub types: Vec<String>,
    pub workflows: BTreeMap<String, BTreeMap<String, Vec<String>>>,
    pub initial_status: String,
    pub priorities: BTreeMap<u8, String>,
    pub default_priority: u8,
}
