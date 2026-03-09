//! Console UI state: a server-side cache of the last URL route pushed to clients.
//!
//! The server tracks what state it has told browser clients to navigate to.
//! This is used by CLI query commands (`kbs console status`, `kbs console get focus`, etc.)
//! and is persisted to `.kanbus/.cache/console_state.json` across server restarts.

use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use serde::{Deserialize, Serialize};

use crate::error::KanbusError;

const STATE_FILE_NAME: &str = "console_state.json";
static STATE_CACHE: OnceLock<Mutex<HashMap<PathBuf, ConsoleUiState>>> = OnceLock::new();

fn state_cache() -> &'static Mutex<HashMap<PathBuf, ConsoleUiState>> {
    STATE_CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

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
    let canonical_root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let absolute = canonical_root
        .join(".kanbus")
        .join(".cache")
        .join(STATE_FILE_NAME);

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
    if let Ok(guard) = state_cache().lock() {
        if let Some(state) = guard.get(&path) {
            return Ok(state.clone());
        }
    }
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
        std::fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    let json =
        serde_json::to_string_pretty(state).map_err(|error| KanbusError::Io(error.to_string()))?;
    std::fs::write(&path, json).map_err(|error| KanbusError::Io(error.to_string()))?;

    let mut guard = state_cache().lock().map_err(|_| {
        KanbusError::IssueOperation("console state cache lock poisoned".to_string())
    })?;
    guard.insert(path, state.clone());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_project_configuration;
    use tempfile::TempDir;

    fn setup_root(temp_dir: &TempDir) -> std::path::PathBuf {
        let root = temp_dir.path().join("repo");
        std::fs::create_dir_all(root.join("project").join("issues")).expect("create project");
        std::process::Command::new("git")
            .args(["init"])
            .current_dir(&root)
            .output()
            .expect("git init");
        let config = default_project_configuration();
        let payload = serde_yaml::to_string(&config).expect("serialize config");
        std::fs::write(root.join(".kanbus.yml"), payload).expect("write config");
        root
    }

    #[test]
    fn load_state_returns_default_when_missing() {
        let temp_dir = TempDir::new().expect("tempdir");
        let root = setup_root(&temp_dir);
        let state = load_state(&root).expect("load state");
        assert!(state.focused_issue_id.is_none());
        assert!(state.view_mode.is_none());
    }

    #[test]
    fn save_and_load_state_round_trip() {
        let temp_dir = TempDir::new().expect("tempdir");
        let root = setup_root(&temp_dir);
        let original = ConsoleUiState {
            focused_issue_id: Some("kanbus-123456".to_string()),
            focused_comment_id: Some("comment-1".to_string()),
            view_mode: Some("issues".to_string()),
            search_query: Some("auth".to_string()),
        };

        save_state(&root, &original).expect("save state");
        let loaded = load_state(&root).expect("load state");

        assert_eq!(loaded.focused_issue_id, original.focused_issue_id);
        assert_eq!(loaded.focused_comment_id, original.focused_comment_id);
        assert_eq!(loaded.view_mode, original.view_mode);
        assert_eq!(loaded.search_query, original.search_query);
    }

    #[test]
    fn state_path_is_scoped_inside_root() {
        let temp_dir = TempDir::new().expect("tempdir");
        let root = setup_root(&temp_dir);
        let path = state_path(&root).expect("state path");
        assert_eq!(
            path.file_name().and_then(|name| name.to_str()),
            Some("console_state.json")
        );
        assert!(!path
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir)));
    }
}
