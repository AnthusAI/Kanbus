use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then};

use kanbus::file_io::load_project_directory;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

#[then("project/issues should be committed to git")]
fn then_project_issues_committed_to_git(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let cwd = cwd.canonicalize().unwrap_or_else(|_| cwd.clone());
    let project_dir = load_project_dir(world);
    let issues_path = project_dir.join("issues");
    let issues_path = issues_path.canonicalize().unwrap_or(issues_path);
    let relative_issues_path = issues_path
        .strip_prefix(&cwd)
        .expect("issues path under repo root")
        .to_string_lossy()
        .replace('\\', "/");

    let output = Command::new("git")
        .args(["status", "--porcelain", "--", &relative_issues_path])
        .current_dir(&cwd)
        .output()
        .expect("git status");

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.trim().is_empty(), "{stdout}");
}

#[then("the events directory should be committed to git")]
fn then_project_events_committed_to_git(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let cwd = cwd.canonicalize().unwrap_or_else(|_| cwd.clone());
    let project_dir = load_project_dir(world);
    let events_path = project_dir.join("events");
    let events_path = events_path.canonicalize().unwrap_or(events_path);
    let relative_events_path = events_path
        .strip_prefix(&cwd)
        .expect("events path under repo root")
        .to_string_lossy()
        .replace('\\', "/");

    let output = Command::new("git")
        .args(["status", "--porcelain", "--", &relative_events_path])
        .current_dir(&cwd)
        .output()
        .expect("git status");

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.trim().is_empty(), "{stdout}");
}

#[then(expr = "the last commit message should be {string}")]
fn then_last_commit_message_should_be(world: &mut KanbusWorld, expected: String) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let output = Command::new("git")
        .args(["log", "-1", "--pretty=%s"])
        .current_dir(cwd)
        .output()
        .expect("git log");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(String::from_utf8_lossy(&output.stdout).trim(), expected);
}

fn event_files_under_project_events(world: &KanbusWorld) -> Vec<PathBuf> {
    let events_dir = load_project_dir(world).join("events");
    if !events_dir.is_dir() {
        return Vec::new();
    }
    let mut paths: Vec<PathBuf> = std::fs::read_dir(&events_dir)
        .expect("read events directory")
        .map(|entry| entry.expect("events entry").path())
        .filter(|path| {
            let extension = path.extension().and_then(|value| value.to_str());
            let hidden = path
                .file_name()
                .and_then(|value| value.to_str())
                .is_some_and(|name| name.starts_with('.'));
            matches!(extension, Some("json") | Some("jsonl")) && !hidden
        })
        .collect();
    paths.sort();
    paths
}

#[then("the events directory should contain event files")]
fn then_project_events_contain_event_files(world: &mut KanbusWorld) {
    assert!(
        !event_files_under_project_events(world).is_empty(),
        "expected event files"
    );
}

#[then("the events directory should contain no event files")]
fn then_project_events_contain_no_event_files(world: &mut KanbusWorld) {
    let event_files = event_files_under_project_events(world);
    assert!(
        event_files.is_empty(),
        "unexpected event files: {event_files:?}"
    );
}

#[given(expr = "the repository .gitignore contains {string}")]
fn given_repository_gitignore_contains(world: &mut KanbusWorld, rule: String) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let gitignore_path = cwd.join(".gitignore");
    let existing = std::fs::read_to_string(&gitignore_path).unwrap_or_default();
    let separator = if existing.is_empty() || existing.ends_with('\n') {
        ""
    } else {
        "\n"
    };
    std::fs::write(&gitignore_path, format!("{existing}{separator}{rule}\n"))
        .expect("write gitignore");
}
