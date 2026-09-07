//! Console snapshot helpers.

use std::path::Path;

use crate::console_backend::{ConsoleSnapshot, FileStore};
use crate::error::KanbusError;

/// Build a console snapshot for the given repository root.
///
/// # Arguments
///
/// * `root` - Repository root path.
///
/// # Errors
///
/// Returns `KanbusError` if snapshot creation fails.
pub fn build_console_snapshot(root: &Path) -> Result<ConsoleSnapshot, KanbusError> {
    FileStore::new(root).build_snapshot()
}

/// Backfill right-now summaries and return issues for the console Now view.
///
/// # Arguments
///
/// * `root` - Repository root path.
///
/// # Errors
///
/// Returns `KanbusError` when backfill or snapshot creation fails.
pub fn build_console_now_issues(root: &Path) -> Result<Vec<crate::models::IssueData>, KanbusError> {
    let store = FileStore::new(root);
    store.ensure_right_now_summaries()?;
    Ok(store.build_snapshot()?.issues)
}
