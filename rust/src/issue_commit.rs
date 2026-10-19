//! Commit board state (issues and events) to git.

use std::path::Path;
use std::process::Command;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::{
    canonicalize_path, ensure_git_repository, get_configuration_path, load_project_directory,
};

const COMMIT_MESSAGE: &str = "chore(kanbus): commit board state";

/// Ephemeral git identity flags for `kbs commit` subprocess invocations.
///
/// Passed as `-c user.email=kanbus@localhost` and `-c user.name=Kanbus` per
/// commit call. These are not written to `.git/config`, so agent worktrees can
/// commit board state without depending on the caller's git identity.
const GIT_COMMIT_NAME: &str = "Kanbus";
const GIT_COMMIT_EMAIL: &str = "kanbus@localhost";

/// Result of a board state commit operation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IssueCommitResult {
    /// Whether a new commit was created.
    pub committed: bool,
    /// Whether the events directory was part of the commit scope.
    pub includes_events: bool,
}

/// Stage and commit board state changes.
///
/// `project/issues/` is always staged. `project/events/` is staged as well, in
/// the same commit, unless the configuration sets `events: false`.
/// Git author identity uses ephemeral `-c` flags (see `GIT_COMMIT_EMAIL` and
/// `GIT_COMMIT_NAME`); nothing is persisted to `git config`.
///
/// # Errors
/// Returns `KanbusError` if the commit operation fails.
pub fn commit_project_issues(root: &Path) -> Result<IssueCommitResult, KanbusError> {
    ensure_git_repository(root)?;
    let project_dir = load_project_directory(root)?;
    let issues_dir = project_dir.join("issues");
    if !issues_dir.is_dir() {
        return Err(KanbusError::Initialization(
            "project not initialized".to_string(),
        ));
    }

    let configuration = load_project_configuration(&get_configuration_path(root)?)?;
    let root_path = canonicalize_path(root).unwrap_or_else(|_| root.to_path_buf());
    let relative_to_root = |directory: &Path| -> Result<String, KanbusError> {
        Ok(directory
            .strip_prefix(&root_path)
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .to_string_lossy()
            .replace('\\', "/"))
    };
    let mut committed_paths = vec![relative_to_root(&issues_dir)?];
    let events_dir = project_dir.join("events");
    let includes_events = configuration.events && events_dir.is_dir();
    if includes_events {
        committed_paths.push(relative_to_root(&events_dir)?);
    }

    let add_output = Command::new("git")
        .args(["add", "--"])
        .args(&committed_paths)
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !add_output.status.success() {
        let message = String::from_utf8_lossy(&add_output.stderr)
            .trim()
            .to_string();
        let fallback = String::from_utf8_lossy(&add_output.stdout)
            .trim()
            .to_string();
        return Err(KanbusError::IssueOperation(if message.is_empty() {
            if fallback.is_empty() {
                "git add failed".to_string()
            } else {
                fallback
            }
        } else {
            message
        }));
    }

    let staged_output = Command::new("git")
        .args(["diff", "--cached", "--quiet", "--"])
        .args(&committed_paths)
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if staged_output.status.success() {
        return Ok(IssueCommitResult {
            committed: false,
            includes_events,
        });
    }

    let commit_output = Command::new("git")
        .args([
            "-c",
            &format!("user.email={GIT_COMMIT_EMAIL}"),
            "-c",
            &format!("user.name={GIT_COMMIT_NAME}"),
            "commit",
            "-m",
            COMMIT_MESSAGE,
            "--",
        ])
        .args(&committed_paths)
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !commit_output.status.success() {
        let message = String::from_utf8_lossy(&commit_output.stderr)
            .trim()
            .to_string();
        let fallback = String::from_utf8_lossy(&commit_output.stdout)
            .trim()
            .to_string();
        return Err(KanbusError::IssueOperation(if message.is_empty() {
            if fallback.is_empty() {
                "git commit failed".to_string()
            } else {
                fallback
            }
        } else {
            message
        }));
    }

    Ok(IssueCommitResult {
        committed: true,
        includes_events,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;
    use tempfile::TempDir;

    fn init_repo_with_project(temp_dir: &TempDir) -> std::path::PathBuf {
        let root = temp_dir.path().to_path_buf();
        Command::new("git")
            .args(["init"])
            .current_dir(&root)
            .output()
            .expect("git init");
        Command::new("git")
            .args(["config", "user.email", "test@example.com"])
            .current_dir(&root)
            .output()
            .expect("git config email");
        Command::new("git")
            .args(["config", "user.name", "Test User"])
            .current_dir(&root)
            .output()
            .expect("git config name");
        let issues_dir = root.join("project/issues");
        std::fs::create_dir_all(&issues_dir).expect("create issues");
        std::fs::write(issues_dir.join(".gitkeep"), "").expect("write gitkeep");
        Command::new("git")
            .args(["add", "project/issues"])
            .current_dir(&root)
            .output()
            .expect("git add");
        Command::new("git")
            .args(["commit", "-m", "initial"])
            .current_dir(&root)
            .output()
            .expect("git commit");
        std::fs::write(root.join(".kanbus.yml"), "project_key: kanbus\n").expect("write config");
        root
    }

    #[test]
    fn commit_project_issues_is_idempotent_when_clean() {
        let temp_dir = TempDir::new().expect("tempdir");
        let root = init_repo_with_project(&temp_dir);
        let result = commit_project_issues(&root).expect("commit");
        assert!(!result.committed);
    }

    #[test]
    fn commit_project_issues_creates_commit_for_issue_changes() {
        let temp_dir = TempDir::new().expect("tempdir");
        let root = init_repo_with_project(&temp_dir);
        std::fs::write(
            root.join("project/issues/kanbus-test.json"),
            r#"{"identifier":"kanbus-test","title":"Test"}"#,
        )
        .expect("write issue");
        let result = commit_project_issues(&root).expect("commit");
        assert!(result.committed);
    }

    fn write_issue_and_event(root: &std::path::Path) {
        std::fs::create_dir_all(root.join("project/events")).expect("create events");
        std::fs::write(
            root.join("project/issues/kanbus-test.json"),
            r#"{"identifier":"kanbus-test","title":"Test"}"#,
        )
        .expect("write issue");
        std::fs::write(
            root.join("project/events/event-1.json"),
            r#"{"event_id":"event-1"}"#,
        )
        .expect("write event");
    }

    fn committed_paths_of_head(root: &std::path::Path) -> Vec<String> {
        let committed_files = Command::new("git")
            .args(["show", "--name-only", "--pretty=format:", "HEAD"])
            .current_dir(root)
            .output()
            .expect("committed files");
        assert!(committed_files.status.success());
        String::from_utf8_lossy(&committed_files.stdout)
            .lines()
            .filter(|path| !path.is_empty())
            .map(str::to_string)
            .collect()
    }

    #[test]
    fn commit_project_issues_commits_events_with_issues_by_default() {
        let temp_dir = TempDir::new().expect("tempdir");
        let root = init_repo_with_project(&temp_dir);
        write_issue_and_event(&root);

        let result = commit_project_issues(&root).expect("commit");
        assert!(result.committed);
        assert!(result.includes_events);

        let committed_paths = committed_paths_of_head(&root);
        assert!(committed_paths.contains(&"project/issues/kanbus-test.json".to_string()));
        assert!(committed_paths.contains(&"project/events/event-1.json".to_string()));
        let status = Command::new("git")
            .args(["status", "--porcelain", "--", "project"])
            .current_dir(&root)
            .output()
            .expect("status");
        assert!(String::from_utf8_lossy(&status.stdout).trim().is_empty());
    }

    #[test]
    fn commit_project_issues_leaves_events_out_when_events_are_disabled() {
        let temp_dir = TempDir::new().expect("tempdir");
        let root = init_repo_with_project(&temp_dir);
        std::fs::write(
            root.join(".kanbus.yml"),
            "project_key: kanbus\nevents: false\n",
        )
        .expect("write config");
        write_issue_and_event(&root);

        let result = commit_project_issues(&root).expect("commit");
        assert!(result.committed);
        assert!(!result.includes_events);

        for path in committed_paths_of_head(&root) {
            assert!(
                path.starts_with("project/issues/"),
                "unexpected commit path: {path}"
            );
        }
        assert!(root.join("project/events/event-1.json").is_file());
    }
}
