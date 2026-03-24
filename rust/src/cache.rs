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
    use std::collections::BTreeMap;

    use crate::models::{DependencyLink, IssueComment};

    fn issue(id: &str, status: &str, issue_type: &str, labels: &[&str]) -> IssueData {
        IssueData {
            identifier: id.to_string(),
            title: format!("Issue {id}"),
            description: String::new(),
            issue_type: issue_type.to_string(),
            status: status.to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: labels.iter().map(|label| (*label).to_string()).collect(),
            dependencies: Vec::<DependencyLink>::new(),
            comments: Vec::<IssueComment>::new(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            closed_at: None,
            custom: BTreeMap::new(),
        }
    }

    #[test]
    fn collect_issue_file_mtimes_ignores_non_json_and_errors_on_missing_dir() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues dir");
        std::fs::write(issues_dir.join("kanbus-1.json"), "{}").expect("write issue file");
        std::fs::write(issues_dir.join("README.md"), "ignored").expect("write non-json file");

        let mtimes = collect_issue_file_mtimes(&issues_dir).expect("mtimes");
        assert_eq!(mtimes.len(), 1);
        assert!(mtimes.contains_key("kanbus-1.json"));

        let missing = temp.path().join("missing");
        let error = collect_issue_file_mtimes(&missing).expect_err("missing should fail");
        assert!(matches!(error, KanbusError::Io(_)));
    }

    #[test]
    fn load_cache_if_valid_handles_missing_invalid_and_stale_cache() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues dir");
        let issue_path = issues_dir.join("kanbus-1.json");
        std::fs::write(&issue_path, "{}").expect("write issue placeholder");
        let cache_path = temp.path().join(".cache").join("index.json");

        let missing = load_cache_if_valid(&cache_path, &issues_dir).expect("missing cache");
        assert!(missing.is_none());

        std::fs::create_dir_all(cache_path.parent().expect("cache parent"))
            .expect("create cache dir");
        std::fs::write(&cache_path, "{bad json").expect("write bad cache");
        let invalid = load_cache_if_valid(&cache_path, &issues_dir).expect_err("invalid cache");
        assert!(matches!(invalid, KanbusError::Io(_)));

        let stale_payload = serde_json::json!({
            "file_mtimes": {"kanbus-1.json": 0.0},
            "issues": [],
            "reverse_deps": {},
        });
        std::fs::write(
            &cache_path,
            serde_json::to_string_pretty(&stale_payload).expect("serialize stale payload"),
        )
        .expect("write stale cache");
        let stale = load_cache_if_valid(&cache_path, &issues_dir).expect("stale result");
        assert!(stale.is_none());
    }

    #[test]
    fn write_cache_and_load_cache_if_valid_round_trip() {
        let temp = tempfile::tempdir().expect("tempdir");
        let issues_dir = temp.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues dir");

        let cached_issue = issue("kanbus-1", "open", "task", &["alpha", "beta"]);
        let issue_payload = serde_json::to_string_pretty(&cached_issue).expect("serialize issue");
        std::fs::write(issues_dir.join("kanbus-1.json"), issue_payload).expect("write issue");

        let mut index = IssueIndex::new();
        let shared = Arc::new(cached_issue.clone());
        index
            .by_id
            .insert(cached_issue.identifier.clone(), Arc::clone(&shared));
        index
            .reverse_dependencies
            .insert("kanbus-target".to_string(), vec![Arc::clone(&shared)]);

        let file_mtimes = collect_issue_file_mtimes(&issues_dir).expect("collect mtimes");
        let cache_path = temp.path().join(".cache").join("index.json");
        write_cache(&index, &cache_path, &file_mtimes).expect("write cache");
        assert!(cache_path.exists());

        let loaded = load_cache_if_valid(&cache_path, &issues_dir)
            .expect("load cache")
            .expect("cache should be valid");
        assert_eq!(loaded.by_id.len(), 1);
        assert!(loaded.by_id.contains_key("kanbus-1"));
        assert!(loaded.reverse_dependencies.contains_key("kanbus-target"));
    }

    #[test]
    fn build_index_from_cache_skips_unknown_reverse_dependency_ids() {
        let issues = vec![issue("kanbus-1", "open", "task", &["x"])];
        let reverse_deps = BTreeMap::from([(
            "kanbus-target".to_string(),
            vec!["kanbus-1".to_string(), "kanbus-missing".to_string()],
        )]);
        let index = build_index_from_cache(issues, reverse_deps);
        let deps = index
            .reverse_dependencies
            .get("kanbus-target")
            .expect("reverse deps entry");
        assert_eq!(deps.len(), 1);
        assert_eq!(deps[0].identifier, "kanbus-1");
    }
}
