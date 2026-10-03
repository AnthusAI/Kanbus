//! Issue listing utilities.

use std::io::ErrorKind;
use std::path::Path;

use crate::config_loader::load_project_configuration;
use crate::daemon_client::{is_daemon_config_schema_error, is_daemon_enabled, request_index_list};
use crate::error::KanbusError;
use crate::file_io::{
    canonicalize_path, discover_kanbus_projects, discover_project_directories,
    find_project_local_directory, get_configuration_path, resolve_labeled_projects,
};
use crate::models::{IssueData, ProjectConfiguration};
use crate::overlay::apply_overlay_to_issues;
use crate::queries::{filter_issues, search_issues, sort_issues};
use std::collections::{HashMap, HashSet};

/// List issues for the project.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `KanbusError` when listing fails.
#[allow(clippy::too_many_arguments)]
pub fn list_issues(
    root: &Path,
    status: Option<&str>,
    issue_type: Option<&str>,
    assignee: Option<&str>,
    label: Option<&str>,
    parent: Option<&str>,
    sort: Option<&str>,
    search: Option<&str>,
    project_filter: &[String],
    include_local: bool,
    local_only: bool,
) -> Result<Vec<IssueData>, KanbusError> {
    if local_only && !include_local {
        return Err(KanbusError::IssueOperation(
            "local-only conflicts with no-local".to_string(),
        ));
    }
    if !project_filter.is_empty() {
        return list_with_project_filter(
            root,
            project_filter,
            status,
            issue_type,
            assignee,
            label,
            parent,
            sort,
            search,
            include_local,
            local_only,
        );
    }
    let mut projects = Vec::new();
    discover_project_directories(root, &mut projects)?;
    let mut dotfile_projects = discover_kanbus_projects(root)?;
    projects.append(&mut dotfile_projects);
    let mut normalized = Vec::new();
    for path in projects {
        match canonicalize_path(&path) {
            Ok(canonical) => normalized.push(canonical),
            Err(_) => normalized.push(path),
        }
    }
    normalized.sort();
    normalized.dedup();
    let root_configuration = load_root_configuration(root);
    if let Some(configuration) = root_configuration.as_ref() {
        let base = get_configuration_path(root)?
            .parent()
            .unwrap_or_else(|| Path::new(""))
            .to_path_buf();
        normalized.retain(|project_path| {
            !crate::file_io::is_path_ignored(project_path, &base, &configuration.ignore_paths)
        });
    }
    let mut permission_error = None;
    normalized.retain(|path| {
        let issues_dir = path.join("issues");
        match std::fs::metadata(&issues_dir) {
            Ok(metadata) => metadata.is_dir(),
            Err(error) => {
                if error.kind() == ErrorKind::PermissionDenied {
                    permission_error = Some(error);
                }
                false
            }
        }
    });
    if let Some(error) = permission_error {
        return Err(KanbusError::Io(error.to_string()));
    }
    let projects = normalized;
    if projects.is_empty() {
        return Err(KanbusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }
    let project_labels: HashMap<std::path::PathBuf, String> = resolve_labeled_projects(root)
        .unwrap_or_default()
        .into_iter()
        .map(|project| (project.project_dir, project.label))
        .collect();

    if projects.len() > 1 {
        let overlay_configs = resolve_overlay_configs(&projects, root_configuration.as_ref());
        let issues = list_issues_across_projects(
            root,
            &projects,
            include_local,
            local_only,
            &overlay_configs,
            &project_labels,
        )?;
        return apply_query(
            issues, status, issue_type, assignee, label, parent, sort, search,
        );
    }

    let project_dir = projects[0].clone();
    let overlay_config = overlay_config_for_project(&project_dir, root_configuration.as_ref());

    if include_local || local_only {
        let local_dir = find_project_local_directory(&project_dir);
        if !local_only && is_daemon_enabled() {
            let mut issues = load_shared_issues_via_daemon_or_filesystem(root, &project_dir)?;
            issues = apply_overlay_to_issues(
                &project_dir,
                issues,
                &overlay_config,
                project_labels.get(&project_dir).map(|value| value.as_str()),
            )?;
            if let Some(local_dir) = local_dir {
                let local_issues_dir = local_dir.join("issues");
                if local_issues_dir.exists() {
                    issues.extend(load_issues_from_directory(&local_issues_dir)?);
                }
            }
            return apply_query(
                issues, status, issue_type, assignee, label, parent, sort, search,
            );
        }
        let issues = list_issues_with_local(
            &project_dir,
            local_dir.as_deref(),
            local_only,
            &overlay_config,
            project_labels.get(&project_dir).map(|value| value.as_str()),
        )?;
        return apply_query(
            issues, status, issue_type, assignee, label, parent, sort, search,
        );
    }
    if is_daemon_enabled() {
        let issues = load_shared_issues_via_daemon_or_filesystem(root, &project_dir)?;
        let issues = apply_overlay_to_issues(
            &project_dir,
            issues,
            &overlay_config,
            project_labels.get(&project_dir).map(|value| value.as_str()),
        )?;
        return apply_query(
            issues, status, issue_type, assignee, label, parent, sort, search,
        );
    }
    let issues = list_issues_local(&project_dir, &overlay_config, &project_labels)?;
    apply_query(
        issues, status, issue_type, assignee, label, parent, sort, search,
    )
}

#[allow(clippy::too_many_arguments)]
fn list_with_project_filter(
    root: &Path,
    project_filter: &[String],
    status: Option<&str>,
    issue_type: Option<&str>,
    assignee: Option<&str>,
    label: Option<&str>,
    parent: Option<&str>,
    sort: Option<&str>,
    search: Option<&str>,
    include_local: bool,
    local_only: bool,
) -> Result<Vec<IssueData>, KanbusError> {
    let labeled = resolve_labeled_projects(root)?;
    if labeled.is_empty() {
        return Err(KanbusError::IssueOperation(
            "project not initialized".to_string(),
        ));
    }
    let known: HashSet<&str> = labeled.iter().map(|p| p.label.as_str()).collect();
    for name in project_filter {
        if !known.contains(name.as_str()) {
            return Err(KanbusError::IssueOperation(format!(
                "unknown project: {name}"
            )));
        }
    }
    let allowed: HashSet<&str> = project_filter.iter().map(|s| s.as_str()).collect();
    let project_dirs: Vec<std::path::PathBuf> = labeled
        .into_iter()
        .filter(|p| allowed.contains(p.label.as_str()))
        .map(|p| p.project_dir)
        .collect();
    let configuration = load_project_configuration(&get_configuration_path(root)?)?;
    let overlay_configs = resolve_overlay_configs(&project_dirs, Some(&configuration));
    let project_labels: HashMap<std::path::PathBuf, String> = resolve_labeled_projects(root)?
        .into_iter()
        .map(|project| (project.project_dir, project.label))
        .collect();
    let issues = list_issues_across_projects(
        root,
        &project_dirs,
        include_local,
        local_only,
        &overlay_configs,
        &project_labels,
    )?;
    apply_query(
        issues, status, issue_type, assignee, label, parent, sort, search,
    )
}

fn load_shared_issues_via_daemon_or_filesystem(
    root: &Path,
    project_dir: &Path,
) -> Result<Vec<IssueData>, KanbusError> {
    match request_index_list(root) {
        Ok(payloads) => payloads
            .into_iter()
            .map(serde_json::from_value::<IssueData>)
            .map(|result| result.map_err(|error| KanbusError::Io(error.to_string())))
            .collect(),
        Err(KanbusError::IssueOperation(message)) if is_daemon_config_schema_error(&message) => {
            list_issues_for_project(project_dir)
        }
        Err(error) => Err(error),
    }
}

fn list_issues_local(
    project_dir: &Path,
    overlay_config: &crate::models::OverlayConfig,
    project_labels: &HashMap<std::path::PathBuf, String>,
) -> Result<Vec<IssueData>, KanbusError> {
    let issues = list_issues_for_project(project_dir)?;
    apply_overlay_to_issues(
        project_dir,
        issues,
        overlay_config,
        project_labels.get(project_dir).map(|value| value.as_str()),
    )
}

fn list_issues_for_project(project_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let issues_dir = project_dir.join("issues");
    if !issues_dir.is_dir() {
        return Err(KanbusError::IssueOperation(format!(
            "issues directory not found: {}. Run 'kanbus migrate' if you need to migrate from an older format.",
            issues_dir.display()
        )));
    }
    load_issues_from_directory(&issues_dir)
}

fn list_issues_with_local(
    project_dir: &Path,
    local_dir: Option<&Path>,
    local_only: bool,
    overlay_config: &crate::models::OverlayConfig,
    project_label: Option<&str>,
) -> Result<Vec<IssueData>, KanbusError> {
    if std::env::var("KANBUS_TEST_LOCAL_LISTING_ERROR").is_ok() {
        return Err(KanbusError::IssueOperation(
            "local listing failed".to_string(),
        ));
    }
    let shared_issues = list_issues_for_project(project_dir)?;
    let shared_issues =
        apply_overlay_to_issues(project_dir, shared_issues, overlay_config, project_label)?;
    let mut local_issues = Vec::new();
    if let Some(local_dir) = local_dir {
        let issues_dir = local_dir.join("issues");
        if issues_dir.exists() {
            local_issues = load_issues_from_directory(&issues_dir)?;
        }
    }
    if local_only {
        return Ok(local_issues);
    }
    Ok([shared_issues, local_issues].concat())
}

fn list_issues_across_projects(
    root: &Path,
    projects: &[std::path::PathBuf],
    include_local: bool,
    local_only: bool,
    overlay_configs: &HashMap<std::path::PathBuf, crate::models::OverlayConfig>,
    project_labels: &HashMap<std::path::PathBuf, String>,
) -> Result<Vec<IssueData>, KanbusError> {
    let mut collected: Vec<(IssueData, std::path::PathBuf)> = Vec::new();
    for project_dir in projects {
        let issues_dir = project_dir.join("issues");
        if !issues_dir.is_dir() {
            continue;
        }
        let local_dir = if include_local || local_only {
            find_project_local_directory(project_dir)
        } else {
            None
        };
        if local_only && local_dir.is_none() {
            continue;
        }
        let overlay_config = overlay_configs
            .get(project_dir)
            .cloned()
            .unwrap_or_else(disabled_overlay_config);
        let project_issues = list_issues_with_local(
            project_dir,
            local_dir.as_deref(),
            local_only,
            &overlay_config,
            project_labels.get(project_dir).map(|value| value.as_str()),
        )?;
        for issue in project_issues {
            collected.push((issue, project_dir.clone()));
        }
    }
    let mut issues = Vec::new();
    for (mut issue, project_dir) in deduplicate_issues_by_identity(collected) {
        tag_issue_project(&mut issue, root, &project_dir);
        issues.push(issue);
    }
    Ok(issues)
}

/// Collapse copies of the same issue identity across discovered projects.
///
/// The copy with the greatest `updated_at` wins; equal timestamps break the
/// tie on the lexicographically greater canonical serialized record. The
/// winning copy keeps the position of the first occurrence of the identity.
fn deduplicate_issues_by_identity(
    collected: Vec<(IssueData, std::path::PathBuf)>,
) -> Vec<(IssueData, std::path::PathBuf)> {
    let mut chosen: HashMap<String, (usize, IssueData, std::path::PathBuf)> =
        HashMap::new();
    for (position, (issue, project_dir)) in collected.into_iter().enumerate() {
        let Some((current_position, current_issue, _)) =
            chosen.get(&issue.identifier)
        else {
            chosen.insert(issue.identifier.clone(), (position, issue, project_dir));
            continue;
        };
        let current_position = *current_position;
        if is_more_recent(&issue, current_issue) {
            if let Some(entry) = chosen.get_mut(&issue.identifier) {
                *entry = (current_position, issue, project_dir);
            }
        }
    }
    let mut entries: Vec<(usize, IssueData, std::path::PathBuf)> =
        chosen.into_values().collect();
    entries.sort_by_key(|(position, _, _)| *position);
    entries
        .into_iter()
        .map(|(_, issue, project_dir)| (issue, project_dir))
        .collect()
}

fn is_more_recent(candidate: &IssueData, current: &IssueData) -> bool {
    if candidate.updated_at != current.updated_at {
        return candidate.updated_at > current.updated_at;
    }
    canonical_issue_record(candidate) > canonical_issue_record(current)
}

fn canonical_issue_record(issue: &IssueData) -> String {
    canonical_json(&serde_json::to_value(issue).expect("issue serializes to JSON"))
}

fn canonical_json(value: &serde_json::Value) -> String {
    use serde_json::Value;
    match value {
        Value::Object(map) => {
            let keys: std::collections::BTreeMap<&str, &Value> = map
                .iter()
                .map(|(key, item)| (key.as_str(), item))
                .collect();
            let rendered: Vec<String> = keys
                .into_iter()
                .map(|(key, item)| {
                    let encoded_key =
                        serde_json::to_string(key).expect("key serializes to JSON");
                    format!("{encoded_key}:{}", canonical_json(item))
                })
                .collect();
            format!("{{{}}}", rendered.join(","))
        }
        Value::Array(items) => {
            let rendered: Vec<String> = items.iter().map(canonical_json).collect();
            format!("[{}]", rendered.join(","))
        }
        other => other.to_string(),
    }
}

fn load_root_configuration(root: &Path) -> Option<ProjectConfiguration> {
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
    root_configuration: Option<&ProjectConfiguration>,
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

fn resolve_overlay_configs(
    project_dirs: &[std::path::PathBuf],
    root_configuration: Option<&ProjectConfiguration>,
) -> HashMap<std::path::PathBuf, crate::models::OverlayConfig> {
    project_dirs
        .iter()
        .map(|project_dir| {
            (
                project_dir.clone(),
                overlay_config_for_project(project_dir, root_configuration),
            )
        })
        .collect()
}

fn tag_issue_project(issue: &mut IssueData, root: &Path, project_dir: &Path) {
    let project_path = project_dir
        .strip_prefix(root)
        .map(|path| path.to_path_buf())
        .unwrap_or_else(|_| project_dir.to_path_buf());
    issue.custom.insert(
        "project_path".to_string(),
        serde_json::Value::String(project_path.to_string_lossy().to_string()),
    );
}

pub fn load_issues_from_directory(issues_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    crate::issue_files::read_issues_from_directory(issues_dir)
}

#[allow(clippy::too_many_arguments)]
fn apply_query(
    issues: Vec<IssueData>,
    status: Option<&str>,
    issue_type: Option<&str>,
    assignee: Option<&str>,
    label: Option<&str>,
    parent: Option<&str>,
    sort: Option<&str>,
    search: Option<&str>,
) -> Result<Vec<IssueData>, KanbusError> {
    let filtered = filter_issues(issues, status, issue_type, assignee, label, parent);
    let searched = search_issues(filtered, search);
    sort_issues(searched, sort)
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{TimeZone, Utc};
    use serial_test::serial;
    use std::env;
    use tempfile::TempDir;

    fn issue(identifier: &str, title: &str) -> IssueData {
        let timestamp = Utc.with_ymd_and_hms(2026, 3, 6, 0, 0, 0).unwrap();
        IssueData {
            identifier: identifier.to_string(),
            title: title.to_string(),
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
            created_at: timestamp,
            updated_at: timestamp,
            closed_at: None,
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: std::collections::BTreeMap::new(),
        }
    }

    #[test]
    fn load_issues_from_directory_sorts_identifiers() {
        let temp_dir = TempDir::new().expect("tempdir");
        let issues_dir = temp_dir.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues");

        let one = issue("kanbus-b", "B");
        let two = issue("kanbus-a", "A");
        std::fs::write(
            issues_dir.join("kanbus-b.json"),
            serde_json::to_vec(&one).expect("serialize one"),
        )
        .expect("write one");
        std::fs::write(
            issues_dir.join("kanbus-a.json"),
            serde_json::to_vec(&two).expect("serialize two"),
        )
        .expect("write two");
        std::fs::write(issues_dir.join("notes.txt"), "skip").expect("write note");

        let issues = load_issues_from_directory(&issues_dir).expect("load issues");
        let identifiers = issues
            .iter()
            .map(|item| item.identifier.clone())
            .collect::<Vec<_>>();
        assert_eq!(
            identifiers,
            vec!["kanbus-a".to_string(), "kanbus-b".to_string()]
        );
    }

    #[test]
    fn tag_issue_project_adds_project_path_custom_field() {
        let root = Path::new("/workspace");
        let project_dir = Path::new("/workspace/service/project");
        let mut data = issue("kanbus-1", "Tagged");

        tag_issue_project(&mut data, root, project_dir);

        assert_eq!(
            data.custom
                .get("project_path")
                .and_then(|value| value.as_str()),
            Some("service/project")
        );
    }

    #[test]
    fn apply_query_filters_by_status() {
        let issues = vec![issue("kanbus-1", "One"), issue("kanbus-2", "Two")];
        let mut closed = issues[1].clone();
        closed.status = "closed".to_string();

        let filtered = apply_query(
            vec![issues[0].clone(), closed],
            Some("open"),
            None,
            None,
            None,
            None,
            None,
            None,
        )
        .expect("apply query");

        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].identifier, "kanbus-1");
    }

    #[test]
    fn apply_query_filters_by_parent() {
        let mut child = issue("kanbus-child", "Child");
        child.parent = Some("kanbus-parent-123456".to_string());
        let sibling = issue("kanbus-other", "Other");

        let filtered = apply_query(
            vec![child, sibling],
            None,
            None,
            None,
            None,
            Some("kanbus-parent"),
            None,
            None,
        )
        .expect("apply query");

        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].identifier, "kanbus-child");
    }

    #[test]
    #[serial]
    fn list_issues_with_local_respects_local_only_and_combined_modes() {
        let temp_dir = TempDir::new().expect("tempdir");
        let project_dir = temp_dir.path().join("project");
        let local_dir = temp_dir.path().join("project-local");
        std::fs::create_dir_all(project_dir.join("issues")).expect("create shared issues");
        std::fs::create_dir_all(local_dir.join("issues")).expect("create local issues");

        let shared = issue("kanbus-shared", "Shared");
        let local = issue("kanbus-local", "Local");
        std::fs::write(
            project_dir.join("issues/kanbus-shared.json"),
            serde_json::to_vec(&shared).expect("serialize shared"),
        )
        .expect("write shared");
        std::fs::write(
            local_dir.join("issues/kanbus-local.json"),
            serde_json::to_vec(&local).expect("serialize local"),
        )
        .expect("write local");

        let overlay = disabled_overlay_config();
        let local_only = list_issues_with_local(
            &project_dir,
            Some(&local_dir),
            true,
            &overlay,
            Some("project"),
        )
        .expect("local only");
        assert_eq!(local_only.len(), 1);
        assert_eq!(local_only[0].identifier, "kanbus-local");

        let combined = list_issues_with_local(
            &project_dir,
            Some(&local_dir),
            false,
            &overlay,
            Some("project"),
        )
        .expect("combined");
        assert_eq!(combined.len(), 2);
        let ids = combined
            .into_iter()
            .map(|item| item.identifier)
            .collect::<Vec<_>>();
        assert!(ids.contains(&"kanbus-shared".to_string()));
        assert!(ids.contains(&"kanbus-local".to_string()));
    }

    #[test]
    #[serial]
    fn list_issues_with_local_uses_test_error_override() {
        let temp_dir = TempDir::new().expect("tempdir");
        let project_dir = temp_dir.path().join("project");
        std::fs::create_dir_all(project_dir.join("issues")).expect("create shared issues");

        env::set_var("KANBUS_TEST_LOCAL_LISTING_ERROR", "1");
        let result =
            list_issues_with_local(&project_dir, None, false, &disabled_overlay_config(), None);
        env::remove_var("KANBUS_TEST_LOCAL_LISTING_ERROR");

        match result {
            Err(KanbusError::IssueOperation(message)) => {
                assert_eq!(message, "local listing failed")
            }
            other => panic!("expected local listing error, got {other:?}"),
        }
    }

    #[test]
    fn apply_query_supports_search_and_sort() {
        let mut alpha = issue("kanbus-1", "Alpha title");
        let mut beta = issue("kanbus-2", "Beta title");
        alpha.priority = 3;
        beta.priority = 1;

        let queried = apply_query(
            vec![alpha, beta],
            None,
            None,
            None,
            None,
            None,
            Some("priority"),
            Some("beta"),
        )
        .expect("apply query with search/sort");
        assert_eq!(queried.len(), 1);
        assert_eq!(queried[0].identifier, "kanbus-2");
    }

    fn collected(
        entries: &[(IssueData, &str)],
    ) -> Vec<(IssueData, std::path::PathBuf)> {
        entries
            .iter()
            .map(|(issue, project_dir)| (issue.clone(), std::path::PathBuf::from(project_dir)))
            .collect()
    }

    fn issue_with_updated_at(
        identifier: &str,
        title: &str,
        updated_at: chrono::DateTime<Utc>,
    ) -> IssueData {
        let mut data = issue(identifier, title);
        data.updated_at = updated_at;
        data
    }

    #[test]
    fn deduplicate_issues_by_identity_keeps_most_recent_copy() {
        let stale = issue("kanbus-dup", "Stale copy");
        let fresh = issue_with_updated_at(
            "kanbus-dup",
            "Fresh copy",
            Utc.with_ymd_and_hms(2026, 3, 7, 0, 0, 0).unwrap(),
        );
        let distinct = issue("kanbus-other", "Other issue");

        let deduplicated = deduplicate_issues_by_identity(collected(&[
            (stale, "repo/project"),
            (fresh, "repo-wt/project"),
            (distinct, "other/project"),
        ]));

        assert_eq!(
            deduplicated
                .iter()
                .map(|(issue, _)| issue.identifier.clone())
                .collect::<Vec<_>>(),
            vec!["kanbus-dup".to_string(), "kanbus-other".to_string()]
        );
        assert_eq!(deduplicated[0].0.title, "Fresh copy");
        assert_eq!(
            deduplicated[0].0.updated_at,
            Utc.with_ymd_and_hms(2026, 3, 7, 0, 0, 0).unwrap()
        );
        assert_eq!(
            deduplicated[0].1,
            std::path::PathBuf::from("repo-wt/project")
        );
    }

    #[test]
    fn deduplicate_issues_by_identity_tie_breaks_on_canonical_record() {
        let alpha = issue("kanbus-tie", "Tie copy alpha");
        let zeta = issue("kanbus-tie", "Tie copy zeta");

        let forward = deduplicate_issues_by_identity(collected(&[
            (alpha.clone(), "a"),
            (zeta.clone(), "b"),
        ]));
        assert_eq!(forward[0].0.title, "Tie copy zeta");

        let reversed = deduplicate_issues_by_identity(collected(&[
            (zeta, "b"),
            (alpha, "a"),
        ]));
        assert_eq!(reversed[0].0.title, "Tie copy zeta");
    }

    #[test]
    fn deduplicate_issues_by_identity_keeps_distinct_issues() {
        let one = issue("kanbus-one", "One");
        let two = issue_with_updated_at(
            "kanbus-two",
            "Two",
            Utc.with_ymd_and_hms(2026, 3, 7, 0, 0, 0).unwrap(),
        );

        let deduplicated =
            deduplicate_issues_by_identity(collected(&[(one, "a"), (two, "b")]));

        assert_eq!(
            deduplicated
                .iter()
                .map(|(issue, _)| issue.identifier.clone())
                .collect::<Vec<_>>(),
            vec!["kanbus-one".to_string(), "kanbus-two".to_string()]
        );
    }

    #[test]
    fn deduplicate_issues_by_identity_keeps_first_occurrence_position() {
        let first = issue("kanbus-dup", "First");
        let second = issue_with_updated_at(
            "kanbus-dup",
            "Second",
            Utc.with_ymd_and_hms(2026, 3, 7, 0, 0, 0).unwrap(),
        );
        let tail = issue("kanbus-tail", "Tail");

        let deduplicated = deduplicate_issues_by_identity(collected(&[
            (first, "a"),
            (second, "b"),
            (tail, "c"),
        ]));

        assert_eq!(
            deduplicated
                .iter()
                .map(|(issue, _)| issue.title.clone())
                .collect::<Vec<_>>(),
            vec!["Second".to_string(), "Tail".to_string()]
        );
        assert_eq!(deduplicated[0].1, std::path::PathBuf::from("b"));
    }
}
