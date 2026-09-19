//! Console backend core helpers.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

use chrono::{SecondsFormat, Utc};
use serde::Serialize;

use crate::config::resolve_board_name;
use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{
    find_project_local_directory, get_configuration_path, resolve_labeled_projects,
};
use crate::migration::load_beads_issues;
use crate::models::{IssueData, ProjectConfiguration};
use crate::overlay::apply_overlay_to_issues;
use crate::right_now::{ensure_right_now_summaries, require_display_right_now_summary};

/// Default status filter for the console Now panel.
pub const DEFAULT_NOW_STATUS_FILTER: &str = "in_progress";

/// Status filter value that includes every issue in the Now panel.
pub const NOW_STATUS_FILTER_ALL: &str = "all";

/// Snapshot payload for the console.
#[derive(Debug, Clone, Serialize)]
pub struct ConsoleSnapshot {
    pub config: ProjectConfiguration,
    pub issues: Vec<IssueData>,
    pub updated_at: String,
}

/// File-backed store for console data.
#[derive(Debug, Clone)]
pub struct FileStore {
    root: PathBuf,
}

impl FileStore {
    /// Create a new file store rooted at the provided path.
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    /// Resolve a tenant root under a shared base directory.
    pub fn resolve_tenant_root(base: &Path, account: &str, project: &str) -> PathBuf {
        base.join(account).join(project)
    }

    /// Return the file store root path.
    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Load the project configuration for this store.
    pub fn load_config(&self) -> Result<ProjectConfiguration, KanbusError> {
        let configuration_path = get_configuration_path(self.root())?;
        load_project_configuration(&configuration_path)
    }

    /// Load issues for this store using the provided configuration.
    pub fn load_issues(
        &self,
        configuration: &ProjectConfiguration,
    ) -> Result<Vec<IssueData>, KanbusError> {
        if !configuration.virtual_projects.is_empty() {
            return self.load_issues_with_virtual_projects();
        }
        if configuration.beads_compatibility {
            load_beads_issues(self.root())
        } else {
            let project_dir = self.root().join(&configuration.project_directory);
            load_console_issues(&project_dir)
        }
    }

    /// Load issues from all virtual projects.
    fn load_issues_with_virtual_projects(&self) -> Result<Vec<IssueData>, KanbusError> {
        let configuration = self.load_config()?;
        let labeled = resolve_labeled_projects(self.root())?;
        let mut all_issues = Vec::new();
        for project in &labeled {
            let issues_dir = project.project_dir.join("issues");
            if issues_dir.is_dir() {
                let mut shared = load_issues_from_dir(&issues_dir)?;
                for issue in &mut shared {
                    tag_custom(issue, "project_label", &project.label);
                    tag_custom(issue, "source", "shared");
                }
                let mut shared = apply_overlay_to_issues(
                    &project.project_dir,
                    shared,
                    &configuration.overlay,
                    Some(project.label.as_str()),
                )?;
                all_issues.append(&mut shared);

                if let Some(local_dir) = find_project_local_directory(&project.project_dir) {
                    let local_issues_dir = local_dir.join("issues");
                    if local_issues_dir.is_dir() {
                        let mut local = load_issues_from_dir(&local_issues_dir)?;
                        for issue in &mut local {
                            tag_custom(issue, "project_label", &project.label);
                            tag_custom(issue, "source", "local");
                        }
                        all_issues.append(&mut local);
                    }
                }
            } else if let Some(repo_root) = project.project_dir.parent() {
                let beads_path = repo_root.join(".beads").join("issues.jsonl");
                if beads_path.exists() {
                    let mut issues = load_beads_issues(repo_root)?;
                    for issue in &mut issues {
                        tag_custom(issue, "project_label", &project.label);
                        tag_custom(issue, "source", "shared");
                    }
                    all_issues.append(&mut issues);
                }
            }
        }
        Ok(all_issues)
    }

    /// Build a snapshot payload for this store.
    pub fn build_snapshot(&self) -> Result<ConsoleSnapshot, KanbusError> {
        let mut configuration = self.load_config()?;
        configuration.name = Some(resolve_board_name(
            configuration.name.as_deref(),
            self.root(),
            &configuration.project_key,
        ));
        let mut issues = self.load_issues(&configuration)?;
        issues.sort_by(|left, right| left.identifier.cmp(&right.identifier));
        let updated_at = Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true);
        Ok(ConsoleSnapshot {
            config: configuration,
            issues,
            updated_at,
        })
    }

    /// Backfill right-now summaries for every issue in the default Now display set.
    ///
    /// The display set mirrors the console tree view with the default in-progress
    /// status filter, including ancestors and descendants pulled into the feed.
    /// Generation is fail-closed: missing or mock summaries surface as errors.
    ///
    /// # Errors
    ///
    /// Returns `KanbusError` when configuration, issue loading, or JIT generation fails.
    pub fn ensure_right_now_summaries(&self) -> Result<(), KanbusError> {
        let configuration = self.load_config()?;
        let issues = self.load_issues(&configuration)?;
        let display_identifiers =
            collect_now_tree_issue_identifiers(&issues, DEFAULT_NOW_STATUS_FILTER);
        ensure_right_now_summaries(self.root(), &display_identifiers, true)?;
        let refreshed_issues = self.load_issues(&configuration)?;
        let issues_by_identifier: HashMap<String, &IssueData> = refreshed_issues
            .iter()
            .map(|issue| (issue.identifier.clone(), issue))
            .collect();
        for identifier in &display_identifiers {
            let issue = issues_by_identifier.get(identifier).ok_or_else(|| {
                KanbusError::IssueOperation(format!("issue not found after JIT: {identifier}"))
            })?;
            require_display_right_now_summary(issue)?;
        }
        Ok(())
    }

    /// Build the JSON payload for a snapshot.
    pub fn build_snapshot_payload(&self) -> Result<String, KanbusError> {
        let snapshot = self.build_snapshot()?;
        serde_json::to_string(&snapshot).map_err(|error| KanbusError::Io(error.to_string()))
    }
}

/// Collect issue identifiers for the console Now tree display set.
///
/// # Arguments
///
/// * `all_issues` - Every issue available to the console.
/// * `status_filter` - Status key to match, or [`NOW_STATUS_FILTER_ALL`].
///
/// # Returns
///
/// Identifiers for matching issues plus ancestors and descendants shown in tree mode.
pub fn collect_now_tree_issue_identifiers(
    all_issues: &[IssueData],
    status_filter: &str,
) -> Vec<String> {
    let matching_issues: Vec<&IssueData> = if status_filter == NOW_STATUS_FILTER_ALL {
        all_issues.iter().collect()
    } else {
        all_issues
            .iter()
            .filter(|issue| issue.status == status_filter)
            .collect()
    };

    if matching_issues.is_empty() || matching_issues.len() == all_issues.len() {
        return matching_issues
            .iter()
            .map(|issue| issue.identifier.clone())
            .collect();
    }

    let issues_by_identifier: HashMap<String, &IssueData> = all_issues
        .iter()
        .map(|issue| (issue.identifier.clone(), issue))
        .collect();
    let mut children_by_parent: HashMap<String, Vec<String>> = HashMap::new();
    for issue in all_issues {
        if let Some(parent) = &issue.parent {
            children_by_parent
                .entry(parent.clone())
                .or_default()
                .push(issue.identifier.clone());
        }
    }

    let mut included = HashSet::new();
    let mut pending: Vec<String> = matching_issues
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect();
    while let Some(identifier) = pending.pop() {
        if !included.insert(identifier.clone()) {
            continue;
        }
        if let Some(children) = children_by_parent.get(&identifier) {
            pending.extend(children.iter().cloned());
        }
        if let Some(issue) = issues_by_identifier.get(&identifier) {
            if let Some(parent) = &issue.parent {
                pending.push(parent.clone());
            }
        }
    }

    all_issues
        .iter()
        .filter(|issue| included.contains(&issue.identifier))
        .map(|issue| issue.identifier.clone())
        .collect()
}

/// Resolve issues by full or short identifier.
///
/// Short identifiers are `{project_key}-{prefix}` where `prefix` is up to 6
/// characters from the UUID segment after the dash.
pub fn find_issue_matches<'a>(
    issues: &'a [IssueData],
    identifier: &str,
    project_key: &str,
) -> Vec<&'a IssueData> {
    let mut matches = Vec::new();
    for issue in issues {
        if issue.identifier == identifier {
            matches.push(issue);
            continue;
        }
        if short_id_matches(identifier, project_key, &issue.identifier) {
            matches.push(issue);
        }
    }
    matches
}

fn short_id_matches(candidate: &str, project_key: &str, full_id: &str) -> bool {
    if !candidate.starts_with(project_key) {
        return false;
    }
    let mut parts = candidate.splitn(2, '-');
    let prefix_key = parts.next().unwrap_or("");
    let prefix = parts.next().unwrap_or("");
    if prefix_key != project_key {
        return false;
    }
    if prefix.is_empty() || prefix.len() > 6 {
        return false;
    }
    let mut full_parts = full_id.splitn(2, '-');
    let full_key = full_parts.next().unwrap_or("");
    let full_suffix = full_parts.next().unwrap_or("");
    if full_key != project_key {
        return false;
    }
    full_suffix.starts_with(prefix)
}

fn load_issues_from_dir(issues_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let mut issues = Vec::new();
    for entry in fs::read_dir(issues_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
        let entry = entry.map_err(|error| KanbusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let bytes = fs::read(&path)
            .map_err(|_error| KanbusError::IssueOperation("issue file is invalid".to_string()))?;
        let issue: IssueData = serde_json::from_slice(&bytes)
            .map_err(|_error| KanbusError::IssueOperation("issue file is invalid".to_string()))?;
        issues.push(issue);
    }
    Ok(issues)
}

fn load_console_issues(project_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let issues_dir = project_dir.join("issues");
    if !issues_dir.exists() || !issues_dir.is_dir() {
        return Err(KanbusError::IssueOperation(
            "project/issues directory not found".to_string(),
        ));
    }

    let mut issues = load_issues_from_dir(&issues_dir)?;
    for issue in &mut issues {
        tag_custom(issue, "source", "shared");
    }

    let configuration_path = get_configuration_path(project_dir)?;
    let configuration = load_project_configuration(&configuration_path)?;
    issues = apply_overlay_to_issues(
        project_dir,
        issues,
        &configuration.overlay,
        Some(configuration.project_key.as_str()),
    )?;

    if let Some(local_dir) = find_project_local_directory(project_dir) {
        let local_issues_dir = local_dir.join("issues");
        if local_issues_dir.is_dir() {
            let mut local_issues = load_issues_from_dir(&local_issues_dir)?;
            for issue in &mut local_issues {
                tag_custom(issue, "source", "local");
            }
            issues.extend(local_issues);
        }
    }

    Ok(issues)
}

fn tag_custom(issue: &mut IssueData, key: &str, value: &str) {
    issue.custom.insert(
        key.to_string(),
        serde_json::Value::String(value.to_string()),
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{TimeZone, Utc};
    use tempfile::TempDir;

    fn issue(identifier: &str) -> IssueData {
        let timestamp = Utc.with_ymd_and_hms(2026, 3, 6, 0, 0, 0).unwrap();
        IssueData {
            identifier: identifier.to_string(),
            title: format!("Issue {identifier}"),
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

    fn write_base_config(root: &Path) {
        std::fs::write(root.join(".kanbus.yml"), "project_key: kanbus\n").expect("write config");
    }

    #[test]
    fn find_issue_matches_exact_and_short_identifier() {
        let issues = vec![issue("kanbus-abcdef"), issue("kanbus-zzzzzz")];

        let exact = find_issue_matches(&issues, "kanbus-abcdef", "kanbus");
        assert_eq!(exact.len(), 1);
        assert_eq!(exact[0].identifier, "kanbus-abcdef");

        let short = find_issue_matches(&issues, "kanbus-abc", "kanbus");
        assert_eq!(short.len(), 1);
        assert_eq!(short[0].identifier, "kanbus-abcdef");
    }

    #[test]
    fn short_id_match_rejects_invalid_candidates() {
        assert!(!short_id_matches("alpha-abc", "kanbus", "kanbus-abcdef"));
        assert!(!short_id_matches("kanbus-", "kanbus", "kanbus-abcdef"));
        assert!(!short_id_matches(
            "kanbus-abcdefg",
            "kanbus",
            "kanbus-abcdef"
        ));
    }

    #[test]
    fn load_issues_from_dir_reads_only_json_files() {
        let temp_dir = TempDir::new().expect("tempdir");
        let issues_dir = temp_dir.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues");

        let first = issue("kanbus-111111");
        let second = issue("kanbus-222222");
        std::fs::write(
            issues_dir.join("kanbus-111111.json"),
            serde_json::to_vec(&first).expect("serialize first"),
        )
        .expect("write first");
        std::fs::write(
            issues_dir.join("kanbus-222222.json"),
            serde_json::to_vec(&second).expect("serialize second"),
        )
        .expect("write second");
        std::fs::write(issues_dir.join("notes.txt"), "skip").expect("write note");

        let issues = load_issues_from_dir(&issues_dir).expect("load issues");
        let identifiers = issues
            .into_iter()
            .map(|item| item.identifier)
            .collect::<Vec<_>>();
        assert_eq!(identifiers.len(), 2);
        assert!(identifiers.contains(&"kanbus-111111".to_string()));
        assert!(identifiers.contains(&"kanbus-222222".to_string()));
    }

    #[test]
    fn load_issues_from_dir_rejects_invalid_json_payload() {
        let temp_dir = TempDir::new().expect("tempdir");
        let issues_dir = temp_dir.path().join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues");
        std::fs::write(issues_dir.join("broken.json"), "{bad json").expect("write broken");

        let result = load_issues_from_dir(&issues_dir);
        match result {
            Err(KanbusError::IssueOperation(message)) => {
                assert_eq!(message, "issue file is invalid")
            }
            other => panic!("expected invalid issue file error, got {other:?}"),
        }
    }

    #[test]
    fn load_console_issues_rejects_missing_project_issues_directory() {
        let temp_dir = TempDir::new().expect("tempdir");
        let project_dir = temp_dir.path().join("project");
        std::fs::create_dir_all(&project_dir).expect("create project dir");
        write_base_config(temp_dir.path());

        let result = load_console_issues(&project_dir);
        match result {
            Err(KanbusError::IssueOperation(message)) => {
                assert_eq!(message, "project/issues directory not found")
            }
            other => panic!("expected missing issues error, got {other:?}"),
        }
    }

    #[test]
    fn load_console_issues_tags_shared_and_local_issue_sources() {
        let temp_dir = TempDir::new().expect("tempdir");
        write_base_config(temp_dir.path());
        let project_dir = temp_dir.path().join("project");
        let shared_dir = project_dir.join("issues");
        let local_dir = temp_dir.path().join("project-local").join("issues");
        std::fs::create_dir_all(&shared_dir).expect("create shared dir");
        std::fs::create_dir_all(&local_dir).expect("create local dir");

        std::fs::write(
            shared_dir.join("kanbus-shared.json"),
            serde_json::to_vec(&issue("kanbus-shared")).expect("serialize shared"),
        )
        .expect("write shared issue");
        std::fs::write(
            local_dir.join("kanbus-local.json"),
            serde_json::to_vec(&issue("kanbus-local")).expect("serialize local"),
        )
        .expect("write local issue");

        let issues = load_console_issues(&project_dir).expect("load issues");
        let by_id = issues
            .into_iter()
            .map(|issue| (issue.identifier.clone(), issue))
            .collect::<std::collections::BTreeMap<_, _>>();

        assert_eq!(
            by_id
                .get("kanbus-shared")
                .and_then(|item| item.custom.get("source"))
                .and_then(|value| value.as_str()),
            Some("shared")
        );
        assert_eq!(
            by_id
                .get("kanbus-local")
                .and_then(|item| item.custom.get("source"))
                .and_then(|value| value.as_str()),
            Some("local")
        );
    }

    #[test]
    fn file_store_build_snapshot_payload_sorts_issue_identifiers() {
        let temp_dir = TempDir::new().expect("tempdir");
        write_base_config(temp_dir.path());
        let issues_dir = temp_dir.path().join("project").join("issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues");
        std::fs::write(
            issues_dir.join("kanbus-b.json"),
            serde_json::to_vec(&issue("kanbus-b")).expect("serialize b"),
        )
        .expect("write b");
        std::fs::write(
            issues_dir.join("kanbus-a.json"),
            serde_json::to_vec(&issue("kanbus-a")).expect("serialize a"),
        )
        .expect("write a");

        let store = FileStore::new(temp_dir.path());
        let payload = store.build_snapshot_payload().expect("snapshot payload");
        let json: serde_json::Value =
            serde_json::from_str(&payload).expect("parse snapshot payload");
        let ids = json["issues"]
            .as_array()
            .expect("issues array")
            .iter()
            .filter_map(|item| item.get("id").and_then(|value| value.as_str()))
            .collect::<Vec<_>>();
        assert_eq!(ids, vec!["kanbus-a", "kanbus-b"]);
    }

    #[test]
    fn resolve_tenant_root_builds_expected_path() {
        let base = Path::new("/tmp/kanbus");
        let path = FileStore::resolve_tenant_root(base, "anthus", "project");
        assert!(path.ends_with("kanbus/anthus/project"));
    }

    #[test]
    fn collect_now_tree_issue_identifiers_includes_tree_relatives() {
        let parent = IssueData {
            identifier: "kanbus-parent".to_string(),
            parent: None,
            status: "open".to_string(),
            ..issue("kanbus-parent")
        };
        let child = IssueData {
            identifier: "kanbus-child".to_string(),
            parent: Some("kanbus-parent".to_string()),
            status: "in_progress".to_string(),
            ..issue("kanbus-child")
        };
        let unrelated = IssueData {
            identifier: "kanbus-other".to_string(),
            status: "open".to_string(),
            ..issue("kanbus-other")
        };
        let all_issues = vec![parent, child, unrelated];
        let identifiers =
            collect_now_tree_issue_identifiers(&all_issues, DEFAULT_NOW_STATUS_FILTER);
        assert_eq!(
            identifiers,
            vec!["kanbus-parent".to_string(), "kanbus-child".to_string()]
        );
    }

    #[test]
    fn collect_now_tree_issue_identifiers_returns_all_when_filter_matches_every_issue() {
        let first = IssueData {
            status: "in_progress".to_string(),
            ..issue("kanbus-a")
        };
        let second = IssueData {
            status: "in_progress".to_string(),
            ..issue("kanbus-b")
        };
        let all_issues = vec![first, second];
        let identifiers =
            collect_now_tree_issue_identifiers(&all_issues, DEFAULT_NOW_STATUS_FILTER);
        assert_eq!(
            identifiers,
            vec!["kanbus-a".to_string(), "kanbus-b".to_string()]
        );
    }
}
