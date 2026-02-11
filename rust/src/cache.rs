//! Index cache utilities for Taskulus.

use std::collections::BTreeMap;
use std::path::Path;

use chrono::{DateTime, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};

use crate::error::TaskulusError;
use crate::index::IssueIndex;
use crate::models::IssueData;

/// Serialized cache representation for the issue index.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexCache {
    pub version: u32,
    pub built_at: DateTime<Utc>,
    pub file_mtimes: BTreeMap<String, f64>,
    pub issues: Vec<IssueData>,
    pub reverse_deps: BTreeMap<String, Vec<String>>,
}

/// Collect file modification times for issues.
pub fn collect_issue_file_mtimes(
    issues_directory: &Path,
) -> Result<BTreeMap<String, f64>, TaskulusError> {
    let mut mtimes = BTreeMap::new();
    let entries = std::fs::read_dir(issues_directory)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    for entry in entries {
        let entry = entry.map_err(|error| TaskulusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let mtime = normalize_mtime(
            entry
                .metadata()
                .map_err(|error| TaskulusError::Io(error.to_string()))?
                .modified()
                .map_err(|error| TaskulusError::Io(error.to_string()))?
                .duration_since(std::time::UNIX_EPOCH)
                .map_err(|error| TaskulusError::Io(error.to_string()))?
                .as_secs_f64(),
        );
        if let Some(name) = entry.file_name().to_str() {
            mtimes.insert(name.to_string(), mtime);
        }
    }
    Ok(mtimes)
}

fn normalize_mtime(value: f64) -> f64 {
    (value * 1_000_000.0).round() / 1_000_000.0
}

/// Load cached index if the cache is valid.
pub fn load_cache_if_valid(
    cache_path: &Path,
    issues_directory: &Path,
) -> Result<Option<IssueIndex>, TaskulusError> {
    if !cache_path.exists() {
        return Ok(None);
    }
    let contents = std::fs::read_to_string(cache_path)
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    let payload: serde_json::Value =
        serde_json::from_str(&contents).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let file_mtimes: BTreeMap<String, f64> = serde_json::from_value(
        payload
            .get("file_mtimes")
            .cloned()
            .unwrap_or_else(|| serde_json::json!({})),
    )
    .map_err(|error| TaskulusError::Io(error.to_string()))?;
    let current_mtimes = collect_issue_file_mtimes(issues_directory)?;
    if file_mtimes != current_mtimes {
        return Ok(None);
    }
    let issues: Vec<IssueData> = serde_json::from_value(
        payload
            .get("issues")
            .cloned()
            .unwrap_or_else(|| serde_json::json!([])),
    )
    .map_err(|error| TaskulusError::Io(error.to_string()))?;
    let reverse_deps: BTreeMap<String, Vec<String>> = serde_json::from_value(
        payload
            .get("reverse_deps")
            .cloned()
            .unwrap_or_else(|| serde_json::json!({})),
    )
    .map_err(|error| TaskulusError::Io(error.to_string()))?;

    Ok(Some(build_index_from_cache(issues, reverse_deps)))
}

/// Write the index cache to disk.
pub fn write_cache(
    index: &IssueIndex,
    cache_path: &Path,
    file_mtimes: &BTreeMap<String, f64>,
) -> Result<(), TaskulusError> {
    let cache = IndexCache {
        version: 1,
        built_at: Utc::now(),
        file_mtimes: file_mtimes.clone(),
        issues: index.by_id.values().cloned().collect(),
        reverse_deps: index
            .reverse_dependencies
            .iter()
            .map(|(target, issues)| {
                (
                    target.clone(),
                    issues
                        .iter()
                        .map(|issue| issue.identifier.clone())
                        .collect(),
                )
            })
            .collect(),
    };
    let payload = serde_json::json!({
        "version": cache.version,
        "built_at": cache.built_at.to_rfc3339_opts(SecondsFormat::Secs, true),
        "file_mtimes": cache.file_mtimes,
        "issues": cache.issues,
        "reverse_deps": cache.reverse_deps,
    });
    if let Some(parent) = cache_path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| TaskulusError::Io(error.to_string()))?;
    }
    std::fs::write(
        cache_path,
        serde_json::to_string_pretty(&payload)
            .map_err(|error| TaskulusError::Io(error.to_string()))?,
    )
    .map_err(|error| TaskulusError::Io(error.to_string()))?;
    Ok(())
}

/// Rebuild an IssueIndex from cached data.
pub fn build_index_from_cache(
    issues: Vec<IssueData>,
    reverse_deps: BTreeMap<String, Vec<String>>,
) -> IssueIndex {
    let mut index = IssueIndex::new();
    for issue in issues {
        index.by_id.insert(issue.identifier.clone(), issue.clone());
        index
            .by_status
            .entry(issue.status.clone())
            .or_default()
            .push(issue.clone());
        index
            .by_type
            .entry(issue.issue_type.clone())
            .or_default()
            .push(issue.clone());
        if let Some(parent) = issue.parent.clone() {
            index
                .by_parent
                .entry(parent)
                .or_default()
                .push(issue.clone());
        }
        for label in &issue.labels {
            index
                .by_label
                .entry(label.clone())
                .or_default()
                .push(issue.clone());
        }
    }
    for (target, ids) in reverse_deps {
        let mut issues = Vec::new();
        for identifier in ids {
            if let Some(issue) = index.by_id.get(&identifier) {
                issues.push(issue.clone());
            }
        }
        index.reverse_dependencies.insert(target, issues);
    }
    index
}
