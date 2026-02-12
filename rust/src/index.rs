//! In-memory index building for Taskulus issues.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;

use crate::error::TaskulusError;
use crate::models::IssueData;

fn read_issue_data(path: &Path) -> Result<IssueData, TaskulusError> {
    let contents = fs::read(path).map_err(|error| TaskulusError::Io(error.to_string()))?;
    serde_json::from_slice(&contents).map_err(|error| TaskulusError::Io(error.to_string()))
}

fn add_issue_to_index(index: &mut IssueIndex, issue: IssueData) {
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
    for dependency in &shared.dependencies {
        if dependency.dependency_type == "blocked-by" {
            index
                .reverse_dependencies
                .entry(dependency.target.clone())
                .or_default()
                .push(Arc::clone(&shared));
        }
    }
}

/// In-memory lookup tables for issues.
#[derive(Debug, Clone)]
pub struct IssueIndex {
    pub by_id: BTreeMap<String, Arc<IssueData>>,
    pub by_status: BTreeMap<String, Vec<Arc<IssueData>>>,
    pub by_type: BTreeMap<String, Vec<Arc<IssueData>>>,
    pub by_parent: BTreeMap<String, Vec<Arc<IssueData>>>,
    pub by_label: BTreeMap<String, Vec<Arc<IssueData>>>,
    pub reverse_dependencies: BTreeMap<String, Vec<Arc<IssueData>>>,
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
    let entries =
        fs::read_dir(issues_directory).map_err(|error| TaskulusError::Io(error.to_string()))?;
    let mut json_entries: Vec<PathBuf> = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|error| TaskulusError::Io(error.to_string()))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        json_entries.push(path);
    }
    json_entries.sort_by(|left, right| left.file_name().cmp(&right.file_name()));

    if json_entries.is_empty() {
        return Ok(index);
    }

    let worker_count = thread::available_parallelism()
        .map(|count| count.get())
        .unwrap_or(1)
        .min(json_entries.len());
    if worker_count <= 1 {
        for path in json_entries {
            let issue = read_issue_data(&path)?;
            add_issue_to_index(&mut index, issue);
        }
        return Ok(index);
    }

    let indexed_paths: Vec<(usize, PathBuf)> = json_entries
        .iter()
        .enumerate()
        .map(|(index, path)| (index, path.clone()))
        .collect();
    let chunk_size = indexed_paths.len().div_ceil(worker_count);
    let chunks: Vec<Vec<(usize, PathBuf)>> = indexed_paths
        .chunks(chunk_size)
        .map(|chunk| chunk.to_vec())
        .collect();

    let mut handles = Vec::with_capacity(chunks.len());
    for chunk_paths in chunks {
        handles.push(thread::spawn(move || {
            let mut batch: Vec<(usize, IssueData)> = Vec::with_capacity(chunk_paths.len());
            for (index, path) in chunk_paths {
                let issue = read_issue_data(&path)?;
                batch.push((index, issue));
            }
            Ok::<_, TaskulusError>(batch)
        }));
    }

    let mut ordered = vec![None; json_entries.len()];
    for handle in handles {
        let batch = handle
            .join()
            .map_err(|_| TaskulusError::Io("index thread panicked".to_string()))??;
        for (index, issue) in batch {
            ordered[index] = Some(issue);
        }
    }
    for issue in ordered.into_iter().flatten() {
        add_issue_to_index(&mut index, issue);
    }

    Ok(index)
}
