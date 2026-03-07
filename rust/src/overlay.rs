//! Overlay cache helpers for speculative realtime updates.

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{get_configuration_path, resolve_labeled_projects};
use crate::issue_files::read_issue_from_file;
use crate::models::{IssueData, OverlayConfig};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OverlayIssueRecord {
    pub overlay_ts: String,
    #[serde(default)]
    pub overlay_event_id: Option<String>,
    pub issue: IssueData,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OverlayTombstone {
    pub op: String,
    pub project: String,
    pub id: String,
    #[serde(default)]
    pub event_id: Option<String>,
    pub ts: String,
    pub ttl_s: u64,
}

pub fn overlay_root(project_dir: &Path) -> PathBuf {
    project_dir.join(".overlay")
}

pub fn overlay_issue_path(project_dir: &Path, issue_id: &str) -> PathBuf {
    overlay_root(project_dir)
        .join("issues")
        .join(format!("{issue_id}.json"))
}

pub fn overlay_tombstone_path(project_dir: &Path, issue_id: &str) -> PathBuf {
    overlay_root(project_dir)
        .join("tombstones")
        .join(format!("{issue_id}.json"))
}

pub fn write_overlay_issue(
    project_dir: &Path,
    issue: &IssueData,
    overlay_ts: &str,
    overlay_event_id: Option<String>,
) -> Result<(), KanbusError> {
    let payload = OverlayIssueRecord {
        overlay_ts: overlay_ts.to_string(),
        overlay_event_id,
        issue: issue.clone(),
    };
    let path = overlay_issue_path(project_dir, &issue.identifier);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    let contents = serde_json::to_string_pretty(&payload)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::write(path, contents).map_err(|error| KanbusError::Io(error.to_string()))
}

pub fn write_tombstone(
    project_dir: &Path,
    tombstone: &OverlayTombstone,
) -> Result<(), KanbusError> {
    let path = overlay_tombstone_path(project_dir, &tombstone.id);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    let contents = serde_json::to_string_pretty(&tombstone)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::write(path, contents).map_err(|error| KanbusError::Io(error.to_string()))
}

pub fn load_overlay_issue(
    project_dir: &Path,
    issue_id: &str,
) -> Result<Option<OverlayIssueRecord>, KanbusError> {
    let path = overlay_issue_path(project_dir, issue_id);
    if !path.exists() {
        return Ok(None);
    }
    let contents = fs::read_to_string(&path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let record: OverlayIssueRecord =
        serde_json::from_str(&contents).map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(Some(record))
}

pub fn load_tombstone(
    project_dir: &Path,
    issue_id: &str,
) -> Result<Option<OverlayTombstone>, KanbusError> {
    let path = overlay_tombstone_path(project_dir, issue_id);
    if !path.exists() {
        return Ok(None);
    }
    let contents = fs::read_to_string(&path).map_err(|error| KanbusError::Io(error.to_string()))?;
    let record: OverlayTombstone =
        serde_json::from_str(&contents).map_err(|error| KanbusError::Io(error.to_string()))?;
    Ok(Some(record))
}

pub fn resolve_issue_with_overlay(
    project_dir: &Path,
    base_issue: Option<IssueData>,
    overlay_issue: Option<OverlayIssueRecord>,
    tombstone: Option<OverlayTombstone>,
    config: &OverlayConfig,
    project_label: Option<&str>,
) -> Result<Option<IssueData>, KanbusError> {
    if !config.enabled {
        return Ok(base_issue);
    }
    let now = Utc::now();
    let base_updated = base_issue.as_ref().map(|issue| issue.updated_at);
    let base_event_id = base_issue.as_ref().and_then(extract_event_id);

    if let Some(tombstone_record) = tombstone {
        if is_expired(&tombstone_record.ts, tombstone_record.ttl_s, now) {
            let _ = fs::remove_file(overlay_tombstone_path(project_dir, &tombstone_record.id));
        } else if tombstone_newer_than_base(&tombstone_record.ts, base_updated) {
            return Ok(None);
        }
    }

    if let Some(overlay_record) = overlay_issue {
        if is_expired(&overlay_record.overlay_ts, config.ttl_s, now) {
            let _ = fs::remove_file(overlay_issue_path(
                project_dir,
                &overlay_record.issue.identifier,
            ));
        } else if let Some(base_time) = base_updated {
            if overlay_is_newer(
                &overlay_record.overlay_ts,
                base_time,
                overlay_record.overlay_event_id.as_deref(),
                base_event_id.as_deref(),
            ) {
                return Ok(Some(tag_issue(overlay_record.issue, project_label)));
            }
            let _ = fs::remove_file(overlay_issue_path(
                project_dir,
                &overlay_record.issue.identifier,
            ));
        } else {
            return Ok(Some(tag_issue(overlay_record.issue, project_label)));
        }
    }

    Ok(base_issue.map(|issue| tag_issue(issue, project_label)))
}

pub fn apply_overlay_to_issues(
    project_dir: &Path,
    issues: Vec<IssueData>,
    config: &OverlayConfig,
    project_label: Option<&str>,
) -> Result<Vec<IssueData>, KanbusError> {
    if !config.enabled {
        return Ok(issues);
    }
    let mut results = Vec::new();
    let mut base_ids = BTreeMap::new();
    for issue in &issues {
        base_ids.insert(issue.identifier.clone(), true);
    }

    for issue in issues {
        if issue.custom.get("source") == Some(&Value::String("local".to_string())) {
            results.push(issue);
            continue;
        }
        let overlay_issue = load_overlay_issue(project_dir, &issue.identifier)?;
        let tombstone = load_tombstone(project_dir, &issue.identifier)?;
        let resolved = resolve_issue_with_overlay(
            project_dir,
            Some(issue),
            overlay_issue,
            tombstone,
            config,
            project_label,
        )?;
        if let Some(issue) = resolved {
            results.push(issue);
        }
    }

    let overlay_dir = overlay_root(project_dir).join("issues");
    if overlay_dir.exists() {
        for entry in
            fs::read_dir(&overlay_dir).map_err(|error| KanbusError::Io(error.to_string()))?
        {
            let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
            let path = entry.path();
            if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
                continue;
            }
            let issue_id = path
                .file_stem()
                .and_then(|name| name.to_str())
                .unwrap_or("");
            if base_ids.contains_key(issue_id) {
                continue;
            }
            let overlay_issue = load_overlay_issue(project_dir, issue_id)?;
            if overlay_issue.is_none() {
                continue;
            }
            let tombstone = load_tombstone(project_dir, issue_id)?;
            let resolved = resolve_issue_with_overlay(
                project_dir,
                None,
                overlay_issue,
                tombstone,
                config,
                project_label,
            )?;
            if let Some(issue) = resolved {
                results.push(issue);
            }
        }
    }

    results.sort_by(|left, right| left.identifier.cmp(&right.identifier));
    Ok(results)
}

pub fn gc_overlay(project_dir: &Path, config: &OverlayConfig) -> Result<(), KanbusError> {
    if !config.enabled {
        return Ok(());
    }
    let now = Utc::now();
    let issues_dir = overlay_root(project_dir).join("issues");
    if issues_dir.exists() {
        for entry in
            fs::read_dir(&issues_dir).map_err(|error| KanbusError::Io(error.to_string()))?
        {
            let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
            let path = entry.path();
            if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
                continue;
            }
            let issue_id = path
                .file_stem()
                .and_then(|name| name.to_str())
                .unwrap_or("");
            let overlay_issue = load_overlay_issue(project_dir, issue_id)?;
            if let Some(record) = overlay_issue {
                let base_path = project_dir.join("issues").join(format!("{issue_id}.json"));
                let base_issue = if base_path.exists() {
                    read_issue_from_file(&base_path).ok()
                } else {
                    None
                };
                if is_expired(&record.overlay_ts, config.ttl_s, now) {
                    let _ = fs::remove_file(path);
                } else if let Some(base_issue) = base_issue {
                    if !overlay_is_newer(
                        &record.overlay_ts,
                        base_issue.updated_at,
                        record.overlay_event_id.as_deref(),
                        extract_event_id(&base_issue).as_deref(),
                    ) {
                        let _ = fs::remove_file(path);
                    }
                }
            } else {
                let _ = fs::remove_file(path);
            }
        }
    }

    let tombstones_dir = overlay_root(project_dir).join("tombstones");
    if tombstones_dir.exists() {
        for entry in
            fs::read_dir(&tombstones_dir).map_err(|error| KanbusError::Io(error.to_string()))?
        {
            let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
            let path = entry.path();
            if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
                continue;
            }
            let issue_id = path
                .file_stem()
                .and_then(|name| name.to_str())
                .unwrap_or("");
            let tombstone = load_tombstone(project_dir, issue_id)?;
            if let Some(record) = tombstone {
                let base_path = project_dir.join("issues").join(format!("{issue_id}.json"));
                let base_issue = if base_path.exists() {
                    read_issue_from_file(&base_path).ok()
                } else {
                    None
                };
                if is_expired(&record.ts, record.ttl_s, now) {
                    let _ = fs::remove_file(path);
                } else if let Some(base_issue) = base_issue {
                    if base_newer_than_tombstone(base_issue.updated_at, &record.ts) {
                        let _ = fs::remove_file(path);
                    }
                }
            } else {
                let _ = fs::remove_file(path);
            }
        }
    }

    Ok(())
}

pub fn gc_overlay_for_projects(
    root: &Path,
    project_label: Option<String>,
    all_projects: bool,
) -> Result<usize, KanbusError> {
    if project_label.is_some() && all_projects {
        return Err(KanbusError::IssueOperation(
            "cannot combine --project with --all".to_string(),
        ));
    }
    let configuration = load_project_configuration(&get_configuration_path(root)?)?;
    let labeled = resolve_labeled_projects(root)?;
    if labeled.is_empty() {
        return Ok(0);
    }
    let selected = if all_projects {
        labeled
    } else {
        let label = project_label.unwrap_or_else(|| configuration.project_key.clone());
        let selected: Vec<_> = labeled
            .into_iter()
            .filter(|project| project.label == label)
            .collect();
        if selected.is_empty() {
            return Err(KanbusError::IssueOperation(format!(
                "unknown project label: {label}"
            )));
        }
        selected
    };
    for project in &selected {
        gc_overlay(&project.project_dir, &configuration.overlay)?;
    }
    Ok(selected.len())
}

pub fn install_overlay_hooks(root: &Path) -> Result<(), KanbusError> {
    let hooks_dir = resolve_git_hooks_dir(root)?;
    fs::create_dir_all(&hooks_dir).map_err(|error| KanbusError::Io(error.to_string()))?;
    let hook_block = overlay_hook_block();
    for hook in ["post-merge", "post-checkout", "post-rewrite"] {
        let path = hooks_dir.join(hook);
        let contents = if path.exists() {
            let existing =
                fs::read_to_string(&path).map_err(|error| KanbusError::Io(error.to_string()))?;
            if existing.contains("Kanbus overlay cache GC") {
                continue;
            }
            format!("{}\n\n{}", existing.trim_end(), hook_block)
        } else {
            format!("#!/bin/sh\n{}", hook_block)
        };
        fs::write(&path, format!("{contents}\n"))
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        ensure_executable(&path)?;
    }
    Ok(())
}

fn resolve_git_hooks_dir(root: &Path) -> Result<PathBuf, KanbusError> {
    let output = Command::new("git")
        .args(["rev-parse", "--git-path", "hooks"])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !output.status.success() {
        return Err(KanbusError::IssueOperation(
            "not a git repository".to_string(),
        ));
    }
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let path = PathBuf::from(stdout);
    if path.is_absolute() {
        Ok(path)
    } else {
        Ok(root.join(path))
    }
}

fn overlay_hook_block() -> String {
    [
        "# Kanbus overlay cache GC",
        "if command -v kanbus >/dev/null 2>&1; then",
        "  kanbus overlay gc --all >/dev/null 2>&1 || true",
        "elif command -v kbs >/dev/null 2>&1; then",
        "  kbs overlay gc --all >/dev/null 2>&1 || true",
        "fi",
    ]
    .join("\n")
}

fn ensure_executable(path: &Path) -> Result<(), KanbusError> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let metadata = fs::metadata(path).map_err(|error| KanbusError::Io(error.to_string()))?;
        let mut permissions = metadata.permissions();
        let mode = permissions.mode();
        permissions.set_mode(mode | 0o111);
        fs::set_permissions(path, permissions)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    Ok(())
}

fn tag_issue(mut issue: IssueData, project_label: Option<&str>) -> IssueData {
    issue
        .custom
        .entry("source".to_string())
        .or_insert(Value::String("shared".to_string()));
    if let Some(label) = project_label {
        issue
            .custom
            .entry("project_label".to_string())
            .or_insert(Value::String(label.to_string()));
    }
    issue
}

fn parse_ts(timestamp: &str) -> Option<DateTime<Utc>> {
    if timestamp.is_empty() {
        return None;
    }
    DateTime::parse_from_rfc3339(timestamp)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
}

fn is_expired(timestamp: &str, ttl_s: u64, now: DateTime<Utc>) -> bool {
    if ttl_s == 0 {
        return false;
    }
    let parsed = match parse_ts(timestamp) {
        Some(parsed) => parsed,
        None => return false,
    };
    parsed + Duration::seconds(ttl_s as i64) < now
}

fn overlay_is_newer(
    overlay_ts: &str,
    base_updated: DateTime<Utc>,
    overlay_event_id: Option<&str>,
    base_event_id: Option<&str>,
) -> bool {
    let parsed = match parse_ts(overlay_ts) {
        Some(parsed) => parsed,
        None => return false,
    };
    if parsed > base_updated {
        return true;
    }
    if parsed < base_updated {
        return false;
    }
    if let (Some(overlay_id), Some(base_id)) = (overlay_event_id, base_event_id) {
        return overlay_id > base_id;
    }
    true
}

fn tombstone_newer_than_base(tombstone_ts: &str, base_updated: Option<DateTime<Utc>>) -> bool {
    let parsed = match parse_ts(tombstone_ts) {
        Some(parsed) => parsed,
        None => return false,
    };
    if let Some(base_time) = base_updated {
        parsed >= base_time
    } else {
        true
    }
}

fn base_newer_than_tombstone(base_updated: DateTime<Utc>, tombstone_ts: &str) -> bool {
    let parsed = match parse_ts(tombstone_ts) {
        Some(parsed) => parsed,
        None => return true,
    };
    base_updated > parsed
}

fn extract_event_id(issue: &IssueData) -> Option<String> {
    match issue.custom.get("last_event_id") {
        Some(Value::String(value)) => Some(value.clone()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{Duration, TimeZone, Utc};
    use tempfile::TempDir;

    fn issue(identifier: &str, updated_at: DateTime<Utc>) -> IssueData {
        IssueData {
            identifier: identifier.to_string(),
            title: "Overlay test".to_string(),
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
            created_at: updated_at,
            updated_at,
            closed_at: None,
            custom: std::collections::BTreeMap::new(),
        }
    }

    #[test]
    fn resolve_issue_prefers_newer_overlay() {
        // Use relative times so the test is stable regardless of wall clock.
        let now = Utc::now();
        let base_time = now - Duration::hours(2);
        let overlay_time = now - Duration::hours(1);
        let base_issue = issue("kanbus-1", base_time);
        let overlay_issue = issue("kanbus-1", overlay_time);
        let overlay_record = OverlayIssueRecord {
            overlay_ts: overlay_time.to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
            overlay_event_id: None,
            issue: overlay_issue.clone(),
        };
        let temp_dir = TempDir::new().expect("tempdir");
        let result = resolve_issue_with_overlay(
            temp_dir.path(),
            Some(base_issue),
            Some(overlay_record),
            None,
            &OverlayConfig {
                enabled: true,
                ttl_s: 86_400,
            },
            None,
        )
        .expect("resolve");
        assert!(result.is_some());
        let resolved = result.unwrap();
        assert_eq!(resolved.identifier, overlay_issue.identifier);
        assert_eq!(resolved.updated_at, overlay_issue.updated_at);
    }

    #[test]
    fn gc_overlay_removes_stale_entry() {
        let base_time = Utc.with_ymd_and_hms(2026, 3, 6, 0, 0, 0).unwrap();
        let overlay_time = Utc.with_ymd_and_hms(2026, 3, 5, 23, 0, 0).unwrap();
        let base_issue = issue("kanbus-2", base_time);
        let overlay_issue = issue("kanbus-2", overlay_time);
        let temp_dir = TempDir::new().expect("tempdir");
        let project_dir = temp_dir.path();
        let issues_dir = project_dir.join("issues");
        fs::create_dir_all(&issues_dir).expect("issues dir");
        let issue_path = issues_dir.join("kanbus-2.json");
        fs::write(
            &issue_path,
            serde_json::to_vec(&base_issue).expect("serialize"),
        )
        .expect("write issue");
        write_overlay_issue(
            project_dir,
            &overlay_issue,
            &overlay_time.to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
            None,
        )
        .expect("write overlay");
        gc_overlay(
            project_dir,
            &OverlayConfig {
                enabled: true,
                ttl_s: 86_400,
            },
        )
        .expect("gc overlay");
        let overlay_path = overlay_issue_path(project_dir, "kanbus-2");
        assert!(!overlay_path.exists());
    }
}
