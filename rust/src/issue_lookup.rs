//! Issue lookup helpers for project directories.

use std::fs;
use std::path::{Path, PathBuf};

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{
    find_project_local_directory, get_configuration_path, resolve_labeled_projects,
};
use crate::ids::issue_identifier_matches;
use crate::issue_files::{issue_path_for_identifier, read_issue_from_file};
use crate::models::IssueData;
use crate::overlay::{load_overlay_issue, load_tombstone, resolve_issue_with_overlay};
use crate::project::discover_project_directories;
use chrono::{DateTime, Duration, Utc};

/// Issue lookup result.
#[derive(Debug)]
pub struct IssueLookupResult {
    pub issue: IssueData,
    pub issue_path: PathBuf,
    pub project_dir: PathBuf,
}

/// Load an issue by identifier from a project directory.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `identifier` - Issue identifier (full or abbreviated).
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if the issue cannot be found.
pub fn load_issue_from_project(
    root: &Path,
    identifier: &str,
) -> Result<IssueLookupResult, KanbusError> {
    let project_dirs = discover_project_directories(root)?;
    if project_dirs.is_empty() {
        return Err(KanbusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }
    let root_configuration = load_root_configuration(root);
    let project_labels: std::collections::BTreeMap<PathBuf, String> =
        resolve_labeled_projects(root)
            .unwrap_or_default()
            .into_iter()
            .map(|project| (project.project_dir, project.label))
            .collect();
    let overlay_configs: std::collections::BTreeMap<PathBuf, crate::models::OverlayConfig> =
        project_dirs
            .iter()
            .map(|project_dir| {
                (
                    project_dir.clone(),
                    overlay_config_for_project(project_dir, root_configuration.as_ref()),
                )
            })
            .collect();

    let mut all_matches: Vec<(String, PathBuf, PathBuf)> = Vec::new();

    for project_dir in &project_dirs {
        let overlay_config = overlay_configs
            .get(project_dir)
            .cloned()
            .unwrap_or_else(disabled_overlay_config);
        // If the base issue file is missing but a live tombstone exists, surface that explicitly.
        // This matters for realtime demos and for explaining "why not found" when overlay is enabled.
        if overlay_config.enabled {
            if let Some(tombstone) = load_tombstone(project_dir, identifier)? {
                if !tombstone_expired(&tombstone.ts, tombstone.ttl_s) {
                    return Err(KanbusError::IssueOperation(format!(
                        "deleted (overlay tombstone): {identifier}"
                    )));
                }
            }
        }
        for issues_dir in search_directories(project_dir) {
            let issue_path = issue_path_for_identifier(&issues_dir, identifier);
            if issue_path.exists() {
                let issue = read_issue_from_file(&issue_path)?;
                if issues_dir == project_dir.join("issues") {
                    let overlay_issue = load_overlay_issue(project_dir, &issue.identifier)?;
                    let tombstone = load_tombstone(project_dir, &issue.identifier)?;
                    let resolved = resolve_issue_with_overlay(
                        project_dir,
                        Some(issue),
                        overlay_issue,
                        tombstone,
                        &overlay_config,
                        project_labels.get(project_dir).map(|value| value.as_str()),
                    )?;
                    if let Some(issue) = resolved {
                        return Ok(IssueLookupResult {
                            issue,
                            issue_path,
                            project_dir: project_dir.clone(),
                        });
                    }
                    continue;
                }
                return Ok(IssueLookupResult {
                    issue,
                    issue_path,
                    project_dir: project_dir.clone(),
                });
            }

            if let Ok(matches) = find_matching_issues(&issues_dir, identifier) {
                for (full_id, path) in matches {
                    all_matches.push((full_id, path, project_dir.clone()));
                }
            }
        }

        if let Some(overlay_issue) = load_overlay_issue(project_dir, identifier)? {
            let tombstone = load_tombstone(project_dir, identifier)?;
            let resolved = resolve_issue_with_overlay(
                project_dir,
                None,
                Some(overlay_issue),
                tombstone,
                &overlay_config,
                project_labels.get(project_dir).map(|value| value.as_str()),
            )?;
            if let Some(issue) = resolved {
                return Ok(IssueLookupResult {
                    issue,
                    issue_path: project_dir
                        .join(".overlay")
                        .join("issues")
                        .join(format!("{identifier}.json")),
                    project_dir: project_dir.clone(),
                });
            }
            if overlay_config.enabled {
                // Overlay existed, but was suppressed (typically by a tombstone). Surface that.
                if load_tombstone(project_dir, identifier)?.is_some() {
                    return Err(KanbusError::IssueOperation(format!(
                        "deleted (overlay tombstone): {identifier}"
                    )));
                }
            }
        }
    }

    match all_matches.len() {
        0 => Err(KanbusError::IssueOperation("not found".to_string())),
        1 => {
            let (_full_id, issue_path, project_dir) = all_matches.into_iter().next().unwrap();
            let issue = read_issue_from_file(&issue_path)?;
            Ok(IssueLookupResult {
                issue,
                issue_path,
                project_dir,
            })
        }
        _ => {
            let ids: Vec<String> = all_matches.into_iter().map(|(id, _, _)| id).collect();
            Err(KanbusError::IssueOperation(format!(
                "ambiguous identifier, matches: {}",
                ids.join(", ")
            )))
        }
    }
}

fn tombstone_expired(ts: &str, ttl_s: u64) -> bool {
    if ttl_s == 0 {
        return false;
    }
    let parsed: Option<DateTime<Utc>> = DateTime::parse_from_rfc3339(ts)
        .ok()
        .map(|dt| dt.with_timezone(&Utc));
    let Some(parsed) = parsed else {
        return false;
    };
    parsed + Duration::seconds(ttl_s as i64) < Utc::now()
}

/// Return issue directories to search for a given project directory.
fn search_directories(project_dir: &Path) -> Vec<PathBuf> {
    let mut dirs = vec![project_dir.join("issues")];
    if let Some(local_dir) = find_project_local_directory(project_dir) {
        dirs.push(local_dir.join("issues"));
    }
    dirs
}

/// Find issues that match an abbreviated identifier.
///
/// # Arguments
/// * `issues_dir` - Path to issues directory.
/// * `identifier` - Abbreviated identifier to match.
///
/// # Returns
/// Vector of (full_id, path) tuples for matching issues.
///
/// # Errors
/// Returns `KanbusError` if directory cannot be read.
fn find_matching_issues(
    issues_dir: &Path,
    identifier: &str,
) -> Result<Vec<(String, PathBuf)>, KanbusError> {
    let mut matches = Vec::new();

    if !issues_dir.is_dir() {
        return Ok(matches);
    }

    let entries = fs::read_dir(issues_dir).map_err(|error| {
        KanbusError::IssueOperation(format!("cannot read issues directory: {error}"))
    })?;

    for entry in entries {
        let entry = entry.map_err(|error| {
            KanbusError::IssueOperation(format!("cannot read directory entry: {error}"))
        })?;

        let path = entry.path();
        if !path.is_file() || path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }

        let file_stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");

        if issue_identifier_matches(identifier, file_stem) {
            matches.push((file_stem.to_string(), path));
        }
    }

    Ok(matches)
}

fn load_root_configuration(root: &Path) -> Option<crate::models::ProjectConfiguration> {
    let config_path = get_configuration_path(root).ok()?;
    load_project_configuration(&config_path).ok()
}

fn disabled_overlay_config() -> crate::models::OverlayConfig {
    crate::models::OverlayConfig {
        enabled: false,
        ttl_s: crate::models::OverlayConfig::default().ttl_s,
    }
}

fn overlay_config_for_project(
    project_dir: &Path,
    root_configuration: Option<&crate::models::ProjectConfiguration>,
) -> crate::models::OverlayConfig {
    if let Some(configuration) = root_configuration {
        return configuration.overlay.clone();
    }
    let config_path = project_dir
        .parent()
        .unwrap_or_else(|| Path::new(""))
        .join(".kanbus.yml");
    if !config_path.is_file() {
        return disabled_overlay_config();
    }
    load_project_configuration(&config_path)
        .map(|configuration| configuration.overlay)
        .unwrap_or_else(|_| disabled_overlay_config())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;
    use std::fs::File;
    use std::io::Write;

    #[test]
    fn tombstone_expired_handles_zero_ttl_and_invalid_timestamp() {
        assert!(!tombstone_expired("not-a-ts", 30));
        assert!(!tombstone_expired("2026-03-09T00:00:00Z", 0));
    }

    #[test]
    fn tombstone_expired_detects_expired_and_live_tombstones() {
        assert!(tombstone_expired("2000-01-01T00:00:00Z", 1));
        assert!(!tombstone_expired("2999-01-01T00:00:00Z", 1));
    }

    #[test]
    fn search_directories_includes_project_local_when_present() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let workspace = tempdir.path();
        let project_dir = workspace.join("project");
        std::fs::create_dir_all(project_dir.join("issues")).expect("create issues");
        std::fs::create_dir_all(workspace.join("project-local").join("issues"))
            .expect("create local issues");

        let dirs = search_directories(&project_dir);
        assert!(dirs.iter().any(|path| path.ends_with("project/issues")));
        assert!(dirs
            .iter()
            .any(|path| path.ends_with("project-local/issues")));
    }

    #[test]
    fn find_matching_issues_filters_non_json_and_returns_abbrev_matches() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let issues_dir = tempdir.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues");
        std::fs::write(issues_dir.join("kanbus-abc1234.json"), "{}").expect("write json");
        std::fs::write(issues_dir.join("kanbus-def0000.json"), "{}").expect("write json");
        std::fs::write(issues_dir.join("README.txt"), "ignored").expect("write txt");

        let matches = find_matching_issues(&issues_dir, "kanbus-abc").expect("find matches");
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].0, "kanbus-abc1234");
        assert!(matches[0].1.ends_with("kanbus-abc1234.json"));
    }

    #[test]
    fn find_matching_issues_returns_empty_for_missing_directory() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let missing = tempdir.path().join("does-not-exist");
        let matches = find_matching_issues(&missing, "kanbus").expect("empty matches");
        assert!(matches.is_empty());
    }

    #[test]
    fn disabled_overlay_config_disables_overlay_with_default_ttl() {
        let config = disabled_overlay_config();
        assert!(!config.enabled);
        assert_eq!(config.ttl_s, crate::models::OverlayConfig::default().ttl_s);
    }

    #[test]
    fn overlay_config_for_project_prefers_root_configuration() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let mut root = default_project_configuration();
        root.overlay.enabled = true;
        root.overlay.ttl_s = 123;

        let config = overlay_config_for_project(tempdir.path(), Some(&root));
        assert!(config.enabled);
        assert_eq!(config.ttl_s, 123);
    }

    #[test]
    fn overlay_config_for_project_returns_disabled_without_project_config() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let project_dir = tempdir.path().join("project");
        std::fs::create_dir_all(&project_dir).expect("create project dir");

        let config = overlay_config_for_project(&project_dir, None);
        assert!(!config.enabled);
    }

    #[test]
    fn overlay_config_for_project_loads_overlay_from_workspace_config() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let workspace = tempdir.path();
        let project_dir = workspace.join("project");
        std::fs::create_dir_all(&project_dir).expect("create project dir");

        let mut config = default_project_configuration();
        config.overlay.enabled = true;
        config.overlay.ttl_s = 4321;
        let yaml = serde_yaml::to_string(&config).expect("serialize config");
        std::fs::write(workspace.join(".kanbus.yml"), yaml).expect("write config");

        let resolved = overlay_config_for_project(&project_dir, None);
        assert!(resolved.enabled);
        assert_eq!(resolved.ttl_s, 4321);
    }

    #[test]
    fn load_root_configuration_returns_none_when_lookup_fails() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let root = tempdir.path();
        // Not initialized workspace => no configuration path.
        assert!(load_root_configuration(root).is_none());
    }

    #[test]
    fn load_root_configuration_reads_configuration_when_present() {
        let tempdir = tempfile::tempdir().expect("tempdir");
        let root = tempdir.path();
        std::fs::create_dir_all(root.join("project").join("issues")).expect("create project");
        let mut config = default_project_configuration();
        config.project_key = "myproj".to_string();
        let yaml = serde_yaml::to_string(&config).expect("serialize config");
        let mut file = File::create(root.join(".kanbus.yml")).expect("create config");
        file.write_all(yaml.as_bytes()).expect("write config");

        let loaded = load_root_configuration(root).expect("load root config");
        assert_eq!(loaded.project_key, "myproj");
    }
}
