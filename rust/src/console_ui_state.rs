//! Console UI state: a server-side cache of the last URL route pushed to clients.
//!
//! The server tracks what state it has told browser clients to navigate to.
//! This is used by CLI query commands (`kbs console status`, `kbs console get focus`, etc.)
//! and is persisted to `.kanbus/.cache/console_state.json` across server restarts.

use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::error::KanbusError;

const STATE_FILE_NAME: &str = "console_state.json";

/// Cached record of the last URL route pushed to console clients.
///
/// All fields are `Option` — `None` means the server has not pushed that piece
/// of state since startup (or since the last persist).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ConsoleUiState {
    /// ID of the currently focused issue, if any.
    pub focused_issue_id: Option<String>,
    /// ID of a specific comment to scroll to within the focused issue, if any.
    pub focused_comment_id: Option<String>,
    /// Current view mode: "initiatives", "epics", or "issues".
    pub view_mode: Option<String>,
    /// Active search query, if any.
    pub search_query: Option<String>,
}

fn resolve_state_path(root: &Path) -> Result<PathBuf, KanbusError> {
    let fallback = root.join(".kanbus").join(".cache").join(STATE_FILE_NAME);
    let candidate = crate::daemon_paths::get_console_state_path(root).unwrap_or(fallback);

    let canonical_root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let absolute = if candidate.is_absolute() {
        candidate
    } else {
        canonical_root.join(candidate)
    };

    if absolute
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(KanbusError::IssueOperation(
            "invalid console state path".to_string(),
        ));
    }
    if absolute.file_name().and_then(|name| name.to_str()) != Some(STATE_FILE_NAME) {
        return Err(KanbusError::IssueOperation(
            "invalid console state file name".to_string(),
        ));
    }
    if !absolute.starts_with(&canonical_root) {
        return Err(KanbusError::IssueOperation(
            "console state path must remain inside project root".to_string(),
        ));
    }

    Ok(absolute)
}

/// Resolve the persisted UI state path for a project root.
pub fn state_path(root: &Path) -> Result<PathBuf, KanbusError> {
    resolve_state_path(root)
}

/// Load `ConsoleUiState` from a JSON file.
///
/// Returns `Default::default()` if the file does not exist (not an error).
pub fn load_state(root: &Path) -> Result<ConsoleUiState, KanbusError> {
    let path = resolve_state_path(root)?;
    if !path.exists() {
        return Ok(ConsoleUiState::default());
    }
    let json = std::fs::read_to_string(&path).map_err(|e| KanbusError::Io(e.to_string()))?;
    serde_json::from_str(&json).map_err(|e| KanbusError::Io(e.to_string()))
}

/// Persist `ConsoleUiState` to a JSON file.
///
/// Creates parent directories if they do not exist.
pub fn save_state(root: &Path, state: &ConsoleUiState) -> Result<(), KanbusError> {
    let path = resolve_state_path(root)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| KanbusError::Io(e.to_string()))?;
    }
    let json = serde_json::to_string_pretty(state).map_err(|e| KanbusError::Io(e.to_string()))?;
    std::fs::write(&path, json).map_err(|e| KanbusError::Io(e.to_string()))
}
