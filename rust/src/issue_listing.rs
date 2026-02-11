//! Issue listing utilities.

use std::path::Path;

use crate::cache::{collect_issue_file_mtimes, load_cache_if_valid, write_cache};
use crate::daemon_client::{is_daemon_enabled, request_index_list};
use crate::daemon_paths::get_index_cache_path;
use crate::error::TaskulusError;
use crate::file_io::load_project_directory;
use crate::index::build_index_from_directory;
use crate::models::IssueData;

/// List issues for the project.
///
/// # Arguments
/// * `root` - Repository root path.
///
/// # Errors
/// Returns `TaskulusError` when listing fails.
pub fn list_issues(root: &Path) -> Result<Vec<IssueData>, TaskulusError> {
    if is_daemon_enabled() {
        let payloads = request_index_list(root)?;
        return payloads
            .into_iter()
            .map(serde_json::from_value::<IssueData>)
            .map(|result| result.map_err(|error| TaskulusError::Io(error.to_string())))
            .collect();
    }
    list_issues_local(root)
}

fn list_issues_local(root: &Path) -> Result<Vec<IssueData>, TaskulusError> {
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    let cache_path = get_index_cache_path(root)?;
    if let Some(index) = load_cache_if_valid(&cache_path, &issues_dir)? {
        return Ok(index.by_id.values().cloned().collect());
    }
    let index = build_index_from_directory(&issues_dir)?;
    let mtimes = collect_issue_file_mtimes(&issues_dir)?;
    write_cache(&index, &cache_path, &mtimes)?;
    Ok(index.by_id.values().cloned().collect())
}
