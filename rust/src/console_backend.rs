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
use crate::right_now::DEFAULT_RIGHT_NOW_STATUS;

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

    /// Backfill right-now summaries for active issues and their ancestors.
    ///
    /// Every descendant in an active association tree is generated so a later
    /// tree expansion cannot reveal an unresolved summary placeholder.
    ///
    /// # Errors
    ///
    /// Returns `KanbusError` when configuration or issue loading fails.
    pub fn ensure_right_now_summaries(&self) -> Result<(), KanbusError> {
        let configuration = self.load_config()?;
        let issues = self.load_issues(&configuration)?;
        let (roots, selected_identifiers) = active_right_now_tree(&issues);
        crate::right_now::ensure_right_now_summary_subtrees(
            self.root(),
            &roots,
            &selected_identifiers,
        );
        Ok(())
    }

    /// Build the JSON payload for a snapshot.
    pub fn build_snapshot_payload(&self) -> Result<String, KanbusError> {
        let snapshot = self.build_snapshot()?;
        serde_json::to_string(&snapshot).map_err(|error| KanbusError::Io(error.to_string()))
    }
}

/// Return the roots and complete visible set for trees containing active work.
///
/// The right-now summary walk proceeds from parents to selected children, so the
/// selected set must include the whole association tree. A user can expand
/// any branch in the Now UI without another backend request, so descendants
/// must be ready before the snapshot is returned.
pub(crate) fn active_right_now_tree(issues: &[IssueData]) -> (Vec<String>, HashSet<String>) {
    let parents: HashMap<&str, Option<&str>> = issues
        .iter()
        .map(|issue| (issue.identifier.as_str(), issue.parent.as_deref()))
        .collect();
    let mut selected_identifiers = HashSet::new();
    let mut children_by_parent: HashMap<&str, Vec<&str>> = HashMap::new();
    for issue in issues {
        if let Some(parent) = issue.parent.as_deref() {
            children_by_parent
                .entry(parent)
                .or_default()
                .push(issue.identifier.as_str());
        }
    }

    for issue in issues
        .iter()
        .filter(|issue| issue.status == DEFAULT_RIGHT_NOW_STATUS)
    {
        let mut current = issue.identifier.as_str();
        let mut visited = HashSet::new();
        while visited.insert(current) {
            selected_identifiers.insert(current.to_string());
            match parents.get(current).and_then(|parent| *parent) {
                Some(parent) if parents.contains_key(parent) => current = parent,
                _ => break,
            }
        }
    }

    // The console's Now tree expands each selected ancestor downward. Mirror
    // that visibility rule here so discovery, open, or closed descendants do
    // not remain permanently on the loading placeholder.
    let mut pending: Vec<String> = selected_identifiers.iter().cloned().collect();
    while let Some(identifier) = pending.pop() {
        for child in children_by_parent
            .get(identifier.as_str())
            .into_iter()
            .flatten()
        {
            if selected_identifiers.insert((*child).to_string()) {
                pending.push((*child).to_string());
            }
        }
    }

    let mut roots: Vec<String> = selected_identifiers
        .iter()
        .filter(|identifier| {
            !parents
                .get(identifier.as_str())
                .and_then(|parent| *parent)
                .is_some_and(|parent| selected_identifiers.contains(parent))
        })
        .cloned()
        .collect();
    // A malformed cyclic hierarchy has no natural root. Run each selected
    // issue in that case so JIT summary generation still makes progress.
    if roots.is_empty() && !selected_identifiers.is_empty() {
        roots.extend(selected_identifiers.iter().cloned());
    }
    roots.sort();
    (roots, selected_identifiers)
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
    use serial_test::serial;
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
    fn active_right_now_tree_includes_every_visible_card_and_uses_topmost_root() {
        let epic = issue("kanbus-epic");
        let mut parent = issue("kanbus-parent");
        parent.parent = Some(epic.identifier.clone());
        let mut active = issue("kanbus-active");
        active.status = DEFAULT_RIGHT_NOW_STATUS.to_string();
        active.parent = Some(parent.identifier.clone());
        let mut discovery = issue("kanbus-discovery");
        discovery.status = "discovery".to_string();
        discovery.parent = Some(parent.identifier.clone());
        let mut discovery_child = issue("kanbus-discovery-child");
        discovery_child.status = "discovery".to_string();
        discovery_child.parent = Some(discovery.identifier.clone());
        let unrelated = issue("kanbus-unrelated");

        let (roots, selected) =
            active_right_now_tree(&[epic, parent, active, discovery, discovery_child, unrelated]);

        assert_eq!(roots, vec!["kanbus-epic"]);
        assert_eq!(
            selected,
            std::collections::HashSet::from([
                "kanbus-epic".to_string(),
                "kanbus-parent".to_string(),
                "kanbus-active".to_string(),
                "kanbus-discovery".to_string(),
                "kanbus-discovery-child".to_string(),
            ])
        );
    }

    #[test]
    fn active_right_now_tree_includes_descendants_that_may_be_expanded() {
        let root = issue("kanbus-root");
        let mut active = issue("kanbus-active");
        active.status = DEFAULT_RIGHT_NOW_STATUS.to_string();
        active.parent = Some(root.identifier.clone());
        let mut discovery = issue("kanbus-discovery");
        discovery.status = "open".to_string();
        discovery.parent = Some(root.identifier.clone());

        let (roots, selected) = active_right_now_tree(&[root, active, discovery]);

        assert_eq!(roots, vec!["kanbus-root"]);
        assert_eq!(
            selected,
            std::collections::HashSet::from([
                "kanbus-root".to_string(),
                "kanbus-active".to_string(),
                "kanbus-discovery".to_string(),
            ])
        );
    }

    #[test]
    #[serial]
    fn file_store_backfills_active_issue_ancestors() {
        let previous_mock = std::env::var("KANBUS_TEST_AI_MOCK").ok();
        std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
        let temp_dir = TempDir::new().expect("tempdir");
        std::fs::write(
            temp_dir.path().join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\nai:\n  provider: litellm\n  model: gpt-4o-mini\nright_now:\n  enabled: true\n  default_tree_expanded: true\n",
        )
        .expect("write config");
        let issues_dir = temp_dir.path().join("project/issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues");

        let epic = issue("kanbus-epic");
        let mut parent = issue("kanbus-parent");
        parent.parent = Some(epic.identifier.clone());
        let mut active = issue("kanbus-active");
        active.status = DEFAULT_RIGHT_NOW_STATUS.to_string();
        active.parent = Some(parent.identifier.clone());
        let mut discovery = issue("kanbus-discovery");
        discovery.status = "discovery".to_string();
        discovery.parent = Some(parent.identifier.clone());
        for issue in [epic, parent, active, discovery] {
            std::fs::write(
                issues_dir.join(format!("{}.json", issue.identifier)),
                serde_json::to_vec(&issue).expect("serialize issue"),
            )
            .expect("write issue");
        }

        let store = FileStore::new(temp_dir.path());
        store
            .ensure_right_now_summaries()
            .expect("backfill summaries");
        let refreshed = store
            .load_issues(&store.load_config().expect("load config"))
            .expect("load refreshed issues");
        for identifier in [
            "kanbus-epic",
            "kanbus-parent",
            "kanbus-active",
            "kanbus-discovery",
        ] {
            let summary = refreshed
                .iter()
                .find(|issue| issue.identifier == identifier)
                .and_then(|issue| issue.right_now_summary.as_deref());
            assert_eq!(
                summary,
                Some(format!("Mock right-now summary for {identifier}.").as_str())
            );
        }

        match previous_mock {
            Some(value) => std::env::set_var("KANBUS_TEST_AI_MOCK", value),
            None => std::env::remove_var("KANBUS_TEST_AI_MOCK"),
        }
    }

    #[test]
    #[serial]
    fn file_store_backfills_visible_cards_in_virtual_projects() {
        let previous_mock = std::env::var("KANBUS_TEST_AI_MOCK").ok();
        std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
        let temp_dir = TempDir::new().expect("tempdir");
        std::fs::write(
            temp_dir.path().join(".kanbus.yml"),
            "project_key: workspace\nproject_directory: primary/project\nvirtual_projects:\n  virtual:\n    path: virtual/project\nai:\n  provider: litellm\n  model: gpt-4o-mini\nright_now:\n  enabled: true\n  default_tree_expanded: true\n",
        )
        .expect("write workspace config");
        std::fs::create_dir_all(temp_dir.path().join("primary/project/issues"))
            .expect("create primary issues directory");
        let issues_dir = temp_dir.path().join("virtual/project/issues");
        std::fs::create_dir_all(&issues_dir).expect("create virtual issues");

        let parent = issue("virtual-parent");
        let mut active = issue("virtual-active");
        active.status = DEFAULT_RIGHT_NOW_STATUS.to_string();
        active.parent = Some(parent.identifier.clone());
        let mut discovery = issue("virtual-discovery");
        discovery.status = "open".to_string();
        discovery.parent = Some(parent.identifier.clone());
        for issue in [parent, active, discovery] {
            std::fs::write(
                issues_dir.join(format!("{}.json", issue.identifier)),
                serde_json::to_vec(&issue).expect("serialize issue"),
            )
            .expect("write virtual issue");
        }

        let store = FileStore::new(temp_dir.path());
        store
            .ensure_right_now_summaries()
            .expect("backfill virtual summaries");
        let refreshed = store
            .load_issues(&store.load_config().expect("load config"))
            .expect("load refreshed issues");
        for identifier in ["virtual-parent", "virtual-active", "virtual-discovery"] {
            assert_eq!(
                refreshed
                    .iter()
                    .find(|issue| issue.identifier == identifier)
                    .and_then(|issue| issue.right_now_summary.as_deref()),
                Some(format!("Mock right-now summary for {identifier}.").as_str())
            );
        }

        match previous_mock {
            Some(value) => std::env::set_var("KANBUS_TEST_AI_MOCK", value),
            None => std::env::remove_var("KANBUS_TEST_AI_MOCK"),
        }
    }

    #[test]
    #[serial]
    fn file_store_backfills_expandable_active_tree_by_default() {
        let previous_mock = std::env::var("KANBUS_TEST_AI_MOCK").ok();
        std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
        let temp_dir = TempDir::new().expect("tempdir");
        std::fs::write(
            temp_dir.path().join(".kanbus.yml"),
            "project_key: kanbus\nproject_directory: project\nai:\n  provider: litellm\n  model: gpt-4o-mini\nright_now:\n  enabled: true\n  default_tree_expanded: false\n",
        )
        .expect("write config");
        let issues_dir = temp_dir.path().join("project/issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues");

        let root = issue("kanbus-root");
        let mut active = issue("kanbus-active");
        active.status = DEFAULT_RIGHT_NOW_STATUS.to_string();
        active.parent = Some(root.identifier.clone());
        let mut hidden_discovery = issue("kanbus-hidden-discovery");
        hidden_discovery.status = "open".to_string();
        hidden_discovery.parent = Some(root.identifier.clone());
        for issue in [root, active, hidden_discovery] {
            std::fs::write(
                issues_dir.join(format!("{}.json", issue.identifier)),
                serde_json::to_vec(&issue).expect("serialize issue"),
            )
            .expect("write issue");
        }

        let store = FileStore::new(temp_dir.path());
        store
            .ensure_right_now_summaries()
            .expect("backfill active tree");
        let refreshed = store
            .load_issues(&store.load_config().expect("load config"))
            .expect("load refreshed issues");
        assert_eq!(
            refreshed
                .iter()
                .find(|issue| issue.identifier == "kanbus-root")
                .and_then(|issue| issue.right_now_summary.as_deref()),
            Some("Mock right-now summary for kanbus-root.")
        );
        for identifier in ["kanbus-active", "kanbus-hidden-discovery"] {
            assert_eq!(
                refreshed
                    .iter()
                    .find(|issue| issue.identifier == identifier)
                    .and_then(|issue| issue.right_now_summary.as_deref()),
                Some(format!("Mock right-now summary for {identifier}.").as_str())
            );
        }

        match previous_mock {
            Some(value) => std::env::set_var("KANBUS_TEST_AI_MOCK", value),
            None => std::env::remove_var("KANBUS_TEST_AI_MOCK"),
        }
    }

    #[test]
    fn resolve_tenant_root_builds_expected_path() {
        let base = Path::new("/tmp/kanbus");
        let path = FileStore::resolve_tenant_root(base, "anthus", "project");
        assert!(path.ends_with("kanbus/anthus/project"));
    }
}
