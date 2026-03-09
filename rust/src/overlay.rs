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
    #[serde(default)]
    pub overrides: Option<BTreeMap<String, Value>>,
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
        overrides: None,
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

#[derive(Debug, Clone, Default)]
pub struct OverlayReconcileStats {
    pub projects: usize,
    pub issues_scanned: usize,
    pub issues_updated: usize,
    pub issues_removed: usize,
    pub fields_pruned: usize,
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
                if let (Some(base_issue), Some(overrides)) =
                    (base_issue.as_ref(), overlay_record.overrides.as_ref())
                {
                    if let Ok(merged) = apply_overrides(base_issue, overrides) {
                        return Ok(Some(tag_issue(merged, project_label)));
                    }
                }
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

pub fn reconcile_overlay(
    project_dir: &Path,
    config: &OverlayConfig,
    prune: bool,
    dry_run: bool,
) -> Result<OverlayReconcileStats, KanbusError> {
    let mut stats = OverlayReconcileStats::default();
    if !config.enabled {
        return Ok(stats);
    }
    let issues_dir = overlay_root(project_dir).join("issues");
    if !issues_dir.exists() {
        return Ok(stats);
    }
    for entry in fs::read_dir(&issues_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let issue_id = path
            .file_stem()
            .and_then(|name| name.to_str())
            .unwrap_or("");
        let mut record = match load_overlay_issue(project_dir, issue_id)? {
            Some(record) => record,
            None => {
                if !dry_run {
                    let _ = fs::remove_file(path);
                }
                continue;
            }
        };
        let base_path = project_dir.join("issues").join(format!("{issue_id}.json"));
        if !base_path.exists() {
            continue;
        }
        let base_issue = match read_issue_from_file(&base_path) {
            Ok(issue) => issue,
            Err(_) => continue,
        };
        stats.issues_scanned += 1;

        let mut overrides = match record.overrides.clone() {
            Some(existing) => existing,
            None => diff_issue_fields(&base_issue, &record.issue)?,
        };
        if prune {
            let before = overrides.len();
            let base_values = issue_to_map(&base_issue)?;
            overrides.retain(|key, value| match base_values.get(key) {
                Some(base_value) => base_value != value,
                None => true,
            });
            stats.fields_pruned += before.saturating_sub(overrides.len());
        }

        if overrides.is_empty() {
            stats.issues_removed += 1;
            if !dry_run {
                let _ = fs::remove_file(path);
            }
            continue;
        }

        let merged_issue = apply_overrides(&base_issue, &overrides)?;
        let needs_write = issue_to_map(&record.issue)? != issue_to_map(&merged_issue)?
            || record.overrides.as_ref() != Some(&overrides);
        if needs_write {
            stats.issues_updated += 1;
            if !dry_run {
                record.issue = merged_issue;
                record.overrides = Some(overrides);
                let contents = serde_json::to_string_pretty(&record)
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
                fs::write(path, contents).map_err(|error| KanbusError::Io(error.to_string()))?;
            }
        }
    }
    Ok(stats)
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

pub fn reconcile_overlay_for_projects(
    root: &Path,
    project_label: Option<String>,
    all_projects: bool,
    prune: bool,
    dry_run: bool,
) -> Result<OverlayReconcileStats, KanbusError> {
    if project_label.is_some() && all_projects {
        return Err(KanbusError::IssueOperation(
            "cannot combine --project with --all".to_string(),
        ));
    }
    let configuration = load_project_configuration(&get_configuration_path(root)?)?;
    let labeled = resolve_labeled_projects(root)?;
    if labeled.is_empty() {
        return Ok(OverlayReconcileStats::default());
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
    let mut aggregate = OverlayReconcileStats {
        projects: selected.len(),
        ..OverlayReconcileStats::default()
    };
    for project in &selected {
        let stats =
            reconcile_overlay(&project.project_dir, &configuration.overlay, prune, dry_run)?;
        aggregate.issues_scanned += stats.issues_scanned;
        aggregate.issues_updated += stats.issues_updated;
        aggregate.issues_removed += stats.issues_removed;
        aggregate.fields_pruned += stats.fields_pruned;
    }
    Ok(aggregate)
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
            if existing.contains("Kanbus overlay cache maintenance")
                || existing.contains("Kanbus overlay cache GC")
            {
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
    let resolved = if path.is_absolute() {
        path
    } else {
        root.join(path)
    };
    if resolved == Path::new("/dev/null") {
        return Err(KanbusError::IssueOperation(
            "git hooks are disabled (core.hooksPath=/dev/null); run `git config --unset core.hooksPath` to enable hook installation".to_string(),
        ));
    }
    if resolved.exists() && !resolved.is_dir() {
        return Err(KanbusError::IssueOperation(format!(
            "git hooks path is not a directory: {}",
            resolved.display()
        )));
    }
    Ok(resolved)
}

fn overlay_hook_block() -> String {
    [
        "# Kanbus overlay cache maintenance",
        "if command -v kanbus >/dev/null 2>&1; then",
        "  kanbus overlay reconcile --all --prune >/dev/null 2>&1 || true",
        "  kanbus overlay gc --all >/dev/null 2>&1 || true",
        "elif command -v kbs >/dev/null 2>&1; then",
        "  kbs overlay reconcile --all --prune >/dev/null 2>&1 || true",
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

fn issue_to_map(issue: &IssueData) -> Result<BTreeMap<String, Value>, KanbusError> {
    let value = serde_json::to_value(issue).map_err(|error| KanbusError::Io(error.to_string()))?;
    let object = value
        .as_object()
        .ok_or_else(|| KanbusError::Io("issue serialization is not an object".to_string()))?;
    Ok(object
        .iter()
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect())
}

fn issue_from_map(map: &BTreeMap<String, Value>) -> Result<IssueData, KanbusError> {
    serde_json::from_value(Value::Object(
        map.iter()
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect(),
    ))
    .map_err(|error| KanbusError::Io(error.to_string()))
}

fn apply_overrides(
    base_issue: &IssueData,
    overrides: &BTreeMap<String, Value>,
) -> Result<IssueData, KanbusError> {
    let mut merged = issue_to_map(base_issue)?;
    for (key, value) in overrides {
        merged.insert(key.clone(), value.clone());
    }
    issue_from_map(&merged)
}

fn diff_issue_fields(
    base_issue: &IssueData,
    overlay_issue: &IssueData,
) -> Result<BTreeMap<String, Value>, KanbusError> {
    let base = issue_to_map(base_issue)?;
    let overlay = issue_to_map(overlay_issue)?;
    let mut diff = BTreeMap::new();
    for (key, value) in overlay {
        if base.get(&key) != Some(&value) {
            diff.insert(key, value);
        }
    }
    Ok(diff)
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{Duration, TimeZone, Utc};
    use std::collections::BTreeMap;
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
            overrides: None,
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

    #[test]
    fn reconcile_prunes_converged_fields() {
        let now = Utc::now();
        let base_issue = issue("kanbus-3", now);
        let mut overlay_issue = base_issue.clone();
        overlay_issue.priority = 1;
        let temp_dir = TempDir::new().expect("tempdir");
        let project_dir = temp_dir.path();
        let issues_dir = project_dir.join("issues");
        fs::create_dir_all(&issues_dir).expect("issues dir");
        let issue_path = issues_dir.join("kanbus-3.json");
        fs::write(
            &issue_path,
            serde_json::to_vec(&base_issue).expect("serialize"),
        )
        .expect("write issue");

        let record = OverlayIssueRecord {
            overlay_ts: now.to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
            overlay_event_id: Some("evt-1".to_string()),
            overrides: Some(BTreeMap::from([
                ("title".to_string(), Value::String(base_issue.title.clone())),
                (
                    "priority".to_string(),
                    Value::Number(serde_json::Number::from(1)),
                ),
            ])),
            issue: overlay_issue,
        };
        let overlay_path = overlay_issue_path(project_dir, "kanbus-3");
        fs::create_dir_all(overlay_path.parent().expect("parent")).expect("overlay dir");
        fs::write(
            &overlay_path,
            serde_json::to_string_pretty(&record).expect("serialize record"),
        )
        .expect("write overlay");

        let stats = reconcile_overlay(
            project_dir,
            &OverlayConfig {
                enabled: true,
                ttl_s: 86_400,
            },
            true,
            false,
        )
        .expect("reconcile");
        assert_eq!(stats.issues_scanned, 1);
        assert_eq!(stats.issues_updated, 1);
        assert_eq!(stats.fields_pruned, 1);
        let payload = fs::read_to_string(&overlay_path).expect("read overlay");
        let updated: OverlayIssueRecord = serde_json::from_str(&payload).expect("parse overlay");
        let overrides = updated.overrides.expect("overrides");
        assert_eq!(overrides.len(), 1);
        assert!(overrides.contains_key("priority"));
        assert_eq!(updated.issue.priority, 1);
    }

    #[test]
    fn reconcile_removes_empty_override_entry() {
        let now = Utc::now();
        let base_issue = issue("kanbus-4", now);
        let temp_dir = TempDir::new().expect("tempdir");
        let project_dir = temp_dir.path();
        let issues_dir = project_dir.join("issues");
        fs::create_dir_all(&issues_dir).expect("issues dir");
        let issue_path = issues_dir.join("kanbus-4.json");
        fs::write(
            &issue_path,
            serde_json::to_vec(&base_issue).expect("serialize"),
        )
        .expect("write issue");

        let record = OverlayIssueRecord {
            overlay_ts: now.to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
            overlay_event_id: Some("evt-2".to_string()),
            overrides: Some(BTreeMap::from([(
                "title".to_string(),
                Value::String(base_issue.title.clone()),
            )])),
            issue: base_issue.clone(),
        };
        let overlay_path = overlay_issue_path(project_dir, "kanbus-4");
        fs::create_dir_all(overlay_path.parent().expect("parent")).expect("overlay dir");
        fs::write(
            &overlay_path,
            serde_json::to_string_pretty(&record).expect("serialize record"),
        )
        .expect("write overlay");

        let stats = reconcile_overlay(
            project_dir,
            &OverlayConfig {
                enabled: true,
                ttl_s: 86_400,
            },
            true,
            false,
        )
        .expect("reconcile");
        assert_eq!(stats.issues_removed, 1);
        assert!(!overlay_path.exists());
    }

    #[test]
    fn resolve_uses_override_fields_when_present() {
        let now = Utc::now();
        let mut base_issue = issue("kanbus-5", now);
        base_issue.title = "Canonical".to_string();
        let mut overlay_issue = base_issue.clone();
        overlay_issue.title = "Stale snapshot title".to_string();
        overlay_issue.priority = 1;
        let record = OverlayIssueRecord {
            overlay_ts: (now + Duration::seconds(10))
                .to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
            overlay_event_id: Some("evt-3".to_string()),
            overrides: Some(BTreeMap::from([(
                "priority".to_string(),
                Value::Number(serde_json::Number::from(1)),
            )])),
            issue: overlay_issue,
        };
        let temp_dir = TempDir::new().expect("tempdir");
        let resolved = resolve_issue_with_overlay(
            temp_dir.path(),
            Some(base_issue),
            Some(record),
            None,
            &OverlayConfig {
                enabled: true,
                ttl_s: 86_400,
            },
            None,
        )
        .expect("resolve")
        .expect("resolved issue");
        assert_eq!(resolved.title, "Canonical");
        assert_eq!(resolved.priority, 1);
    }

    #[test]
    fn parse_ts_and_expiry_helpers_handle_invalid_timestamps() {
        let now = Utc::now();
        assert!(parse_ts("not-a-timestamp").is_none());
        assert!(!is_expired("not-a-timestamp", 60, now));
    }

    #[test]
    fn overlay_hook_block_contains_expected_commands() {
        let block = overlay_hook_block();
        assert!(block.contains("kanbus overlay reconcile --all --prune"));
        assert!(block.contains("kbs overlay gc --all"));
    }

    #[test]
    fn overlay_paths_and_tombstone_round_trip() {
        let temp_dir = TempDir::new().expect("tempdir");
        let project_dir = temp_dir.path();
        assert_eq!(overlay_root(project_dir), project_dir.join(".overlay"));
        assert_eq!(
            overlay_issue_path(project_dir, "kanbus-9"),
            project_dir
                .join(".overlay")
                .join("issues")
                .join("kanbus-9.json")
        );
        assert_eq!(
            overlay_tombstone_path(project_dir, "kanbus-9"),
            project_dir
                .join(".overlay")
                .join("tombstones")
                .join("kanbus-9.json")
        );

        let tombstone = OverlayTombstone {
            op: "delete".to_string(),
            project: "alpha".to_string(),
            id: "kanbus-9".to_string(),
            event_id: Some("evt-9".to_string()),
            ts: Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
            ttl_s: 60,
        };
        write_tombstone(project_dir, &tombstone).expect("write tombstone");
        let loaded = load_tombstone(project_dir, "kanbus-9")
            .expect("load tombstone")
            .expect("tombstone");
        assert_eq!(loaded.id, "kanbus-9");
        assert_eq!(loaded.project, "alpha");
    }

    #[test]
    fn resolve_issue_with_overlay_handles_disabled_and_tombstone_paths() {
        let now = Utc::now();
        let base_issue = issue("kanbus-10", now);
        let temp_dir = TempDir::new().expect("tempdir");
        let project_dir = temp_dir.path();

        let disabled = resolve_issue_with_overlay(
            project_dir,
            Some(base_issue.clone()),
            None,
            None,
            &OverlayConfig {
                enabled: false,
                ttl_s: 60,
            },
            Some("alpha"),
        )
        .expect("disabled resolve")
        .expect("issue");
        assert_eq!(disabled.identifier, "kanbus-10");
        assert!(disabled.custom.get("project_label").is_none());

        let tombstone = OverlayTombstone {
            op: "delete".to_string(),
            project: "alpha".to_string(),
            id: "kanbus-10".to_string(),
            event_id: Some("evt-10".to_string()),
            ts: (now + Duration::seconds(1)).to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
            ttl_s: 60,
        };
        let deleted = resolve_issue_with_overlay(
            project_dir,
            Some(base_issue),
            None,
            Some(tombstone),
            &OverlayConfig {
                enabled: true,
                ttl_s: 60,
            },
            Some("alpha"),
        )
        .expect("tombstone resolve");
        assert!(deleted.is_none());
    }

    #[test]
    fn apply_overlay_to_issues_keeps_local_source_and_tags_shared() {
        let now = Utc::now();
        let mut local_issue = issue("kanbus-local", now);
        local_issue
            .custom
            .insert("source".to_string(), Value::String("local".to_string()));
        let shared_issue = issue("kanbus-shared", now);
        let temp_dir = TempDir::new().expect("tempdir");
        let resolved = apply_overlay_to_issues(
            temp_dir.path(),
            vec![local_issue.clone(), shared_issue],
            &OverlayConfig {
                enabled: true,
                ttl_s: 60,
            },
            Some("alpha"),
        )
        .expect("apply");
        let by_id: BTreeMap<_, _> = resolved
            .into_iter()
            .map(|issue| (issue.identifier.clone(), issue))
            .collect();
        assert_eq!(
            by_id
                .get("kanbus-local")
                .and_then(|issue| issue.custom.get("source")),
            Some(&Value::String("local".to_string()))
        );
        assert_eq!(
            by_id
                .get("kanbus-shared")
                .and_then(|issue| issue.custom.get("project_label")),
            Some(&Value::String("alpha".to_string()))
        );
    }

    #[test]
    fn timestamp_order_helpers_cover_edge_cases() {
        let now = Utc::now();
        let earlier = (now - Duration::seconds(1)).to_rfc3339();
        let equal = now.to_rfc3339();
        let later = (now + Duration::seconds(1)).to_rfc3339();
        assert!(overlay_is_newer(&later, now, None, None));
        assert!(!overlay_is_newer(&earlier, now, None, None));
        assert!(overlay_is_newer(&equal, now, Some("evt-b"), Some("evt-a")));
        assert!(tombstone_newer_than_base(&equal, Some(now)));
        assert!(tombstone_newer_than_base(&later, Some(now)));
        assert!(tombstone_newer_than_base(&later, None));
        assert!(base_newer_than_tombstone(now, &earlier));
        assert!(!base_newer_than_tombstone(now, &later));
    }

    #[test]
    fn reconcile_and_gc_return_early_when_overlay_disabled() {
        let temp_dir = TempDir::new().expect("tempdir");
        let config = OverlayConfig {
            enabled: false,
            ttl_s: 60,
        };
        let reconcile =
            reconcile_overlay(temp_dir.path(), &config, true, false).expect("reconcile");
        assert_eq!(reconcile.issues_scanned, 0);
        gc_overlay(temp_dir.path(), &config).expect("gc overlay");
    }

    #[test]
    fn resolve_git_hooks_dir_errors_outside_git_repo() {
        let temp_dir = TempDir::new().expect("tempdir");
        let error = resolve_git_hooks_dir(temp_dir.path()).expect_err("not git repo");
        assert!(error.to_string().contains("not a git repository"));
    }

    #[test]
    fn resolve_git_hooks_dir_rejects_dev_null_and_non_directory_paths() {
        let temp_dir = TempDir::new().expect("tempdir");
        Command::new("git")
            .arg("init")
            .current_dir(temp_dir.path())
            .output()
            .expect("git init");

        Command::new("git")
            .args(["config", "core.hooksPath", "/dev/null"])
            .current_dir(temp_dir.path())
            .output()
            .expect("set hooksPath /dev/null");
        let dev_null_error =
            resolve_git_hooks_dir(temp_dir.path()).expect_err("dev/null should be rejected");
        assert!(dev_null_error
            .to_string()
            .contains("git hooks are disabled"));

        let file_path = temp_dir.path().join("hooks-file");
        fs::write(&file_path, "not-a-directory").expect("write hooks file");
        Command::new("git")
            .args(["config", "core.hooksPath", "hooks-file"])
            .current_dir(temp_dir.path())
            .output()
            .expect("set hooksPath file");
        let file_error =
            resolve_git_hooks_dir(temp_dir.path()).expect_err("file path should be rejected");
        assert!(file_error
            .to_string()
            .contains("git hooks path is not a directory"));
    }

    #[test]
    fn install_overlay_hooks_creates_and_appends_once() {
        let temp_dir = TempDir::new().expect("tempdir");
        Command::new("git")
            .arg("init")
            .current_dir(temp_dir.path())
            .output()
            .expect("git init");

        install_overlay_hooks(temp_dir.path()).expect("install hooks");
        let hooks_dir = temp_dir.path().join(".git").join("hooks");
        for hook in ["post-merge", "post-checkout", "post-rewrite"] {
            let path = hooks_dir.join(hook);
            let contents = fs::read_to_string(&path).expect("read hook");
            assert!(contents.contains("Kanbus overlay cache maintenance"));
        }

        let post_merge = hooks_dir.join("post-merge");
        fs::write(&post_merge, "#!/bin/sh\necho existing\n").expect("seed post-merge");
        install_overlay_hooks(temp_dir.path()).expect("append hooks");
        let once = fs::read_to_string(&post_merge).expect("read once");
        assert!(once.contains("echo existing"));
        assert_eq!(once.matches("Kanbus overlay cache maintenance").count(), 1);

        install_overlay_hooks(temp_dir.path()).expect("idempotent install");
        let twice = fs::read_to_string(&post_merge).expect("read twice");
        assert_eq!(twice.matches("Kanbus overlay cache maintenance").count(), 1);
    }

    #[test]
    fn project_overlay_commands_reject_conflicting_filters() {
        let temp_dir = TempDir::new().expect("tempdir");
        let gc = gc_overlay_for_projects(temp_dir.path(), Some("alpha".to_string()), true)
            .expect_err("gc should reject --project with --all");
        assert!(gc
            .to_string()
            .contains("cannot combine --project with --all"));

        let reconcile = reconcile_overlay_for_projects(
            temp_dir.path(),
            Some("alpha".to_string()),
            true,
            true,
            false,
        )
        .expect_err("reconcile should reject --project with --all");
        assert!(reconcile
            .to_string()
            .contains("cannot combine --project with --all"));
    }

    #[test]
    fn tag_issue_and_event_id_helpers_preserve_existing_source() {
        let now = Utc::now();
        let mut shared = issue("kanbus-tag", now);
        let tagged = tag_issue(shared.clone(), Some("alpha"));
        assert_eq!(
            tagged.custom.get("source"),
            Some(&Value::String("shared".to_string()))
        );
        assert_eq!(
            tagged.custom.get("project_label"),
            Some(&Value::String("alpha".to_string()))
        );

        shared
            .custom
            .insert("source".to_string(), Value::String("local".to_string()));
        shared.custom.insert(
            "last_event_id".to_string(),
            Value::String("evt-123".to_string()),
        );
        let tagged_local = tag_issue(shared.clone(), Some("beta"));
        assert_eq!(
            tagged_local.custom.get("source"),
            Some(&Value::String("local".to_string()))
        );
        assert_eq!(extract_event_id(&tagged_local), Some("evt-123".to_string()));
    }

    #[test]
    fn map_and_override_helpers_round_trip_and_diff() {
        let now = Utc::now();
        let base = issue("kanbus-map", now);
        let mut overlay = base.clone();
        overlay.priority = 1;
        overlay.title = "Changed".to_string();

        let diff = diff_issue_fields(&base, &overlay).expect("diff fields");
        assert!(diff.contains_key("priority"));
        assert!(diff.contains_key("title"));

        let merged = apply_overrides(&base, &diff).expect("apply overrides");
        assert_eq!(merged.priority, 1);
        assert_eq!(merged.title, "Changed");

        let map = issue_to_map(&merged).expect("issue to map");
        let restored = issue_from_map(&map).expect("map to issue");
        assert_eq!(restored.identifier, "kanbus-map");
        assert_eq!(restored.priority, 1);
    }
}
