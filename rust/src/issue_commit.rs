//! Commit project/issues to git.

use std::path::Path;
use std::process::Command;

use crate::error::KanbusError;
use crate::file_io::{canonicalize_path, ensure_git_repository, load_project_directory};

const COMMIT_MESSAGE: &str = "chore(kanbus): commit board state (issues)";

/// Ephemeral git identity flags for `kbs commit` subprocess invocations.
///
/// Passed as `-c user.email=kanbus@localhost` and `-c user.name=Kanbus` per
/// commit call. These are not written to `.git/config`, so agent worktrees can
/// commit board state without depending on the caller's git identity.
const GIT_COMMIT_NAME: &str = "Kanbus";
const GIT_COMMIT_EMAIL: &str = "kanbus@localhost";

/// Result of a project/issues commit operation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IssueCommitResult {
    /// Whether a new commit was created.
    pub committed: bool,
}

/// Stage and commit project/issues changes.
///
/// Only `project/issues/` is staged. `project/events/` is never included.
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

    let root_path = canonicalize_path(root).unwrap_or_else(|_| root.to_path_buf());
    let issues_path = issues_dir
        .strip_prefix(&root_path)
        .map_err(|error| KanbusError::Io(error.to_string()))?
        .to_string_lossy()
        .replace('\\', "/");

    let add_output = Command::new("git")
        .args(["add", "--", &issues_path])
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
        .args(["diff", "--cached", "--quiet", "--", &issues_path])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if staged_output.status.success() {
        return Ok(IssueCommitResult { committed: false });
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
            &issues_path,
        ])
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

    Ok(IssueCommitResult { committed: true })
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

    #[test]
    fn commit_project_issues_does_not_stage_events() {
        let temp_dir = TempDir::new().expect("tempdir");
        let root = init_repo_with_project(&temp_dir);
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

        let result = commit_project_issues(&root).expect("commit");
        assert!(result.committed);

        let issues_status = Command::new("git")
            .args(["status", "--porcelain", "--", "project/issues"])
            .current_dir(&root)
            .output()
            .expect("issues status");
        assert!(issues_status.status.success());
        assert!(String::from_utf8_lossy(&issues_status.stdout)
            .trim()
            .is_empty());

        let staged_events = Command::new("git")
            .args(["diff", "--cached", "--name-only", "--", "project/events"])
            .current_dir(&root)
            .output()
            .expect("staged events");
        assert!(staged_events.status.success());
        assert!(String::from_utf8_lossy(&staged_events.stdout)
            .trim()
            .is_empty());

        let committed_files = Command::new("git")
            .args(["show", "--name-only", "--pretty=format:", "HEAD"])
            .current_dir(&root)
            .output()
            .expect("committed files");
        assert!(committed_files.status.success());
        for path in String::from_utf8_lossy(&committed_files.stdout).lines() {
            if path.is_empty() {
                continue;
            }
            assert!(
                path.starts_with("project/issues/"),
                "unexpected commit path: {path}"
            );
        }
        assert!(root.join("project/events/event-1.json").is_file());
    }
}
