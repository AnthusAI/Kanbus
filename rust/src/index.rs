//! In-memory index building for Taskulus issues.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use crate::error::TaskulusError;
use crate::models::IssueData;

/// In-memory lookup tables for issues.
#[derive(Debug, Clone)]
pub struct IssueIndex {
    pub by_id: BTreeMap<String, IssueData>,
    pub by_status: BTreeMap<String, Vec<IssueData>>,
    pub by_type: BTreeMap<String, Vec<IssueData>>,
    pub by_parent: BTreeMap<String, Vec<IssueData>>,
    pub by_label: BTreeMap<String, Vec<IssueData>>,
    pub reverse_dependencies: BTreeMap<String, Vec<IssueData>>,
}

impl IssueIndex {
    pub(crate) fn new() -> Self {
        Self {
            by_id: BTreeMap::new(),
            by_status: BTreeMap::new(),
            by_type: BTreeMap::new(),
            by_parent: BTreeMap::new(),
            by_label: BTreeMap::new(),
            reverse_dependencies: BTreeMap::new(),
        }
    }
}

/// Build an IssueIndex by scanning issue files in a directory.
///
/// # Arguments
/// * `issues_directory` - Directory containing issue JSON files.
///
/// # Errors
/// Returns `TaskulusError::Io` if file reads or JSON parsing fails.
pub fn build_index_from_directory(issues_directory: &Path) -> Result<IssueIndex, TaskulusError> {
    let mut index = IssueIndex::new();
    let mut entries: Vec<_> = fs::read_dir(issues_directory)
        .map_err(|error| TaskulusError::Io(error.to_string()))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| TaskulusError::Io(error.to_string()))?;
    entries.sort_by_key(|entry| entry.file_name());

    for entry in entries {
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let contents =
            fs::read_to_string(&path).map_err(|error| TaskulusError::Io(error.to_string()))?;
        let issue: IssueData = serde_json::from_str(&contents)
            .map_err(|error| TaskulusError::Io(error.to_string()))?;

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
        for dependency in &issue.dependencies {
            if dependency.dependency_type == "blocked-by" {
                index
                    .reverse_dependencies
                    .entry(dependency.target.clone())
                    .or_default()
                    .push(issue.clone());
            }
        }
    }

    Ok(index)
}
