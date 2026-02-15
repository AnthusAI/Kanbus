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
