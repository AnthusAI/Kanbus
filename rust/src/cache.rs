//! Index cache utilities for Kanbus.

use std::collections::BTreeMap;
use std::path::Path;
use std::sync::Arc;

use chrono::{DateTime, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};

use crate::error::KanbusError;
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
) -> Result<BTreeMap<String, f64>, KanbusError> {
    let mut mtimes = BTreeMap::new();
    let entries =
        std::fs::read_dir(issues_directory).map_err(|error| KanbusError::Io(error.to_string()))?;
    for entry in entries {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let mtime = mtime_from_entry(&entry)?;
        if let Some(name) = entry.file_name().to_str() {
            mtimes.insert(name.to_string(), mtime);
        }
    }
    Ok(mtimes)
}

fn mtime_from_entry(entry: &std::fs::DirEntry) -> Result<f64, KanbusError> {
    let metadata = entry
        .metadata()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let modified = metadata
        .modified()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let duration = modified
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(normalize_mtime(duration.as_secs_f64()))
}

fn normalize_mtime(value: f64) -> f64 {
    (value * 1_000_000.0).round() / 1_000_000.0
}

/// Load cached index if the cache is valid.
pub fn load_cache_if_valid(
    cache_path: &Path,
    issues_directory: &Path,
) -> Result<Option<IssueIndex>, KanbusError> {
    if !cache_path.exists() {
        return Ok(None);
    }
    let contents =
        std::fs::read_to_string(cache_path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let payload: serde_json::Value =
        serde_json::from_str(&contents).map_err(|error| KanbusError::Io(error.to_string()))?;
    let file_mtimes: BTreeMap<String, f64> = serde_json::from_value(
        payload
            .get("file_mtimes")
            .cloned()
            .unwrap_or_else(|| serde_json::json!({})),
    )
    .map_err(|error| KanbusError::Io(error.to_string()))?;
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
    .map_err(|error| KanbusError::Io(error.to_string()))?;
    let reverse_deps: BTreeMap<String, Vec<String>> = serde_json::from_value(
        payload
            .get("reverse_deps")
            .cloned()
            .unwrap_or_else(|| serde_json::json!({})),
    )
    .map_err(|error| KanbusError::Io(error.to_string()))?;

    Ok(Some(build_index_from_cache(issues, reverse_deps)))
}

/// Write the index cache to disk.
pub fn write_cache(
    index: &IssueIndex,
    cache_path: &Path,
    file_mtimes: &BTreeMap<String, f64>,
) -> Result<(), KanbusError> {
    let cache = IndexCache {
        version: 1,
        built_at: Utc::now(),
        file_mtimes: file_mtimes.clone(),
        issues: index
            .by_id
            .values()
            .map(|issue| issue.as_ref().clone())
            .collect(),
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
        std::fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    std::fs::write(
        cache_path,
        serde_json::to_string_pretty(&payload)
            .map_err(|error| KanbusError::Io(error.to_string()))?,
    )
    .map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(())
}

/// Rebuild an IssueIndex from cached data.
pub fn build_index_from_cache(
    issues: Vec<IssueData>,
    reverse_deps: BTreeMap<String, Vec<String>>,
) -> IssueIndex {
    let mut index = IssueIndex::new();
    for issue in issues {
        let shared = Arc::new(issue);
        index
            .by_id
            .insert(shared.identifier.clone(), Arc::clone(&shared));
        index
            .by_status
            .entry(shared.status.clone())
            .or_default()
            .push(Arc::clone(&shared));
        index
            .by_type
            .entry(shared.issue_type.clone())
            .or_default()
            .push(Arc::clone(&shared));
        if let Some(parent) = shared.parent.clone() {
            index
                .by_parent
                .entry(parent)
                .or_default()
                .push(Arc::clone(&shared));
        }
        for label in &shared.labels {
            index
                .by_label
                .entry(label.clone())
                .or_default()
                .push(Arc::clone(&shared));
        }
    }
    for (target, ids) in reverse_deps {
        let mut issues = Vec::new();
        for identifier in ids {
            if let Some(issue) = index.by_id.get(&identifier) {
                issues.push(Arc::clone(issue));
            }
        }
        index.reverse_dependencies.insert(target, issues);
    }
    index
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use tempfile::tempdir;

    fn sample_issue(identifier: &str) -> IssueData {
        IssueData {
            identifier: identifier.to_string(),
            title: "Title".to_string(),
            description: "Desc".to_string(),
            issue_type: "task".to_string(),
            status: "open".to_string(),
            priority: 1,
            assignee: None,
            creator: None,
            parent: None,
            labels: vec!["label".to_string()],
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    fn sample_index(issue: IssueData) -> IssueIndex {
        let mut index = IssueIndex::new();
        let shared = Arc::new(issue);
        index
            .by_id
            .insert(shared.identifier.clone(), Arc::clone(&shared));
        index
            .by_status
            .entry(shared.status.clone())
            .or_default()
            .push(Arc::clone(&shared));
        index
            .by_type
            .entry(shared.issue_type.clone())
            .or_default()
            .push(Arc::clone(&shared));
        for label in &shared.labels {
            index
                .by_label
                .entry(label.clone())
                .or_default()
                .push(Arc::clone(&shared));
        }
        index
    }

    #[test]
    fn collect_issue_file_mtimes_skips_non_json() {
        let temp = tempdir().unwrap();
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).unwrap();
        std::fs::write(issues_dir.join("one.json"), "{}").unwrap();
        std::fs::write(issues_dir.join("note.txt"), "skip").unwrap();
        let mtimes = collect_issue_file_mtimes(&issues_dir).unwrap();
        assert_eq!(mtimes.len(), 1);
        assert!(mtimes.contains_key("one.json"));
    }

    #[test]
    fn load_cache_if_valid_round_trips() {
        let temp = tempdir().unwrap();
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).unwrap();
        std::fs::write(issues_dir.join("issue.json"), "{}").unwrap();
        let mtimes = collect_issue_file_mtimes(&issues_dir).unwrap();

        let cache_path = temp.path().join("cache").join("index.json");
        let issue = sample_issue("kanbus-abc123");
        let index = sample_index(issue);
        write_cache(&index, &cache_path, &mtimes).unwrap();

        let loaded = load_cache_if_valid(&cache_path, &issues_dir).unwrap();
        let loaded = loaded.expect("expected cache hit");
        assert!(loaded.by_id.contains_key("kanbus-abc123"));
    }

    #[test]
    fn load_cache_if_valid_returns_none_on_mtime_change() {
        let temp = tempdir().unwrap();
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).unwrap();
        let issue_path = issues_dir.join("issue.json");
        std::fs::write(&issue_path, "{}").unwrap();
        let mtimes = collect_issue_file_mtimes(&issues_dir).unwrap();

        let cache_path = temp.path().join("cache").join("index.json");
        let issue = sample_issue("kanbus-abc123");
        let index = sample_index(issue);
        write_cache(&index, &cache_path, &mtimes).unwrap();

        std::fs::write(&issue_path, "{\"updated\": true}").unwrap();
        let loaded = load_cache_if_valid(&cache_path, &issues_dir).unwrap();
        assert!(loaded.is_none());
    }
}
