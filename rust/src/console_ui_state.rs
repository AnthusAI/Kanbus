//! Console UI state: a server-side cache of the last URL route pushed to clients.
//!
//! The server tracks what state it has told browser clients to navigate to.
//! This is used by CLI query commands (`kbs console status`, `kbs console get focus`, etc.)
//! and is persisted to `.kanbus/.cache/console_state.json` across server restarts.

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::error::KanbusError;

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

/// Load `ConsoleUiState` from a JSON file.
///
/// Returns `Default::default()` if the file does not exist (not an error).
pub fn load_state(path: &Path) -> Result<ConsoleUiState, KanbusError> {
    if !path.exists() {
        return Ok(ConsoleUiState::default());
    }
    let json = std::fs::read_to_string(path).map_err(|e| KanbusError::Io(e.to_string()))?;
    serde_json::from_str(&json).map_err(|e| KanbusError::Io(e.to_string()))
}

/// Persist `ConsoleUiState` to a JSON file.
///
/// Creates parent directories if they do not exist.
pub fn save_state(path: &Path, state: &ConsoleUiState) -> Result<(), KanbusError> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| KanbusError::Io(e.to_string()))?;
    }
    let json = serde_json::to_string_pretty(state).map_err(|e| KanbusError::Io(e.to_string()))?;
    std::fs::write(path, json).map_err(|e| KanbusError::Io(e.to_string()))
}
