use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use chrono::{DateTime, TimeZone, Utc};
use cucumber::given;

use kanbus::config::default_project_configuration;
use kanbus::ids::format_issue_key;
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

const DEDUP_IDENTIFIER: &str = "kanbus-dedup";
const DEDUP_TITLE: &str = "Deduped work";
const DEDUP_EDITED_TITLE: &str = "Deduped work (edited in worktree)";
const TIE_IDENTIFIER: &str = "kanbus-tie";
const TIE_ALPHA_TITLE: &str = "Tie copy alpha";
const TIE_ZETA_TITLE: &str = "Tie copy zeta";
const ONE_IDENTIFIER: &str = "kanbus-one";
const TWO_IDENTIFIER: &str = "kanbus-two";

fn git(arguments: &[&str], cwd: &Path) {
    let output = Command::new("git")
        .args(arguments)
        .current_dir(cwd)
        .output()
        .expect("git command failed");
    assert!(
        output.status.success(),
        "git {arguments:?} failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

fn init_git_repo(repo: &Path) {
    let output = Command::new("git")
        .args(["init"])
        .current_dir(repo)
        .output()
        .expect("git init failed");
    assert!(output.status.success(), "git init failed");
}

fn build_issue(identifier: &str, title: &str, updated_at: DateTime<Utc>) -> IssueData {
    let created_at = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at,
        updated_at,
        closed_at: None,
        agent: None,
        right_now_summary: None,
        right_now_updated_at: None,
        custom: std::collections::BTreeMap::new(),
    }
}

fn write_issue(project_dir: &Path, issue: &IssueData) {
    let issues_dir = project_dir.join("issues");
    fs::create_dir_all(&issues_dir).expect("create issues dir");
    let issue_path = issues_dir.join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn read_issue(project_dir: &Path, identifier: &str) -> IssueData {
    let issue_path = project_dir.join("issues").join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue file");
    serde_json::from_str(&contents).expect("parse issue file")
}

fn write_default_config(repo_root: &Path) {
    let configuration = default_project_configuration();
    let payload = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(repo_root.join(".kanbus.yml"), payload).expect("write config");
}

fn commit_all(repo: &Path) {
    git(&["add", "-A"], repo);
    git(
        &[
            "-c",
            "user.name=Kanbus Spec",
            "-c",
            "user.email=spec@kanbus.local",
            "commit",
            "-m",
            "fixture",
        ],
        repo,
    );
}

fn add_worktree(workspace: &Path, repo: &Path, name: &str) -> PathBuf {
    let worktree = workspace.join(name);
    git(
        &["worktree", "add", worktree.to_str().expect("utf8 path")],
        repo,
    );
    worktree
}

fn base_updated_at() -> DateTime<Utc> {
    Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap()
}

fn edited_updated_at() -> DateTime<Utc> {
    Utc.with_ymd_and_hms(2026, 2, 12, 0, 0, 0).unwrap()
}

fn create_workspace(world: &mut KanbusWorld) -> PathBuf {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let workspace = temp_dir.path().join("workspace");
    fs::create_dir_all(&workspace).expect("create workspace");
    world.temp_dir = Some(temp_dir);
    workspace
}

#[given(
    "a workspace root containing a repository with a committed Kanbus project and two linked git worktrees"
)]
fn given_workspace_repo_with_two_worktrees(world: &mut KanbusWorld) {
    let workspace = create_workspace(world);
    let repo = create_repo(&workspace, "repo");
    write_issue(
        &repo.join("project"),
        &build_issue(DEDUP_IDENTIFIER, DEDUP_TITLE, base_updated_at()),
    );
    write_default_config(&repo);
    commit_all(&repo);
    add_worktree(&workspace, &repo, "repo-wt1");
    add_worktree(&workspace, &repo, "repo-wt2");
    world.working_directory = Some(workspace);
}

fn create_repo(workspace: &Path, name: &str) -> PathBuf {
    let repo = workspace.join(name);
    fs::create_dir_all(&repo).expect("create repo dir");
    init_git_repo(&repo);
    repo
}

#[given("the copy in one worktree was changed most recently")]
fn given_worktree_copy_changed_most_recently(world: &mut KanbusWorld) {
    let workspace = world
        .temp_dir
        .as_ref()
        .expect("tempdir")
        .path()
        .to_path_buf();
    let worktree = workspace.join("repo-wt2");
    let issue = read_issue(&worktree.join("project"), DEDUP_IDENTIFIER);
    let edited = IssueData {
        title: DEDUP_EDITED_TITLE.to_string(),
        updated_at: edited_updated_at(),
        ..issue
    };
    write_issue(&worktree.join("project"), &edited);
}

#[given("a workspace root containing two Kanbus projects with distinct issues")]
fn given_workspace_two_projects_distinct_issues(world: &mut KanbusWorld) {
    let workspace = create_workspace(world);
    for (repo_name, identifier, title) in [
        ("proj-one", ONE_IDENTIFIER, "One project task"),
        ("proj-two", TWO_IDENTIFIER, "Two project task"),
    ] {
        let repo = create_repo(&workspace, repo_name);
        write_issue(
            &repo.join("project"),
            &build_issue(identifier, title, base_updated_at()),
        );
        write_default_config(&repo);
    }
    world.working_directory = Some(workspace);
}

#[given(
    "a workspace root containing a repository and a linked worktree with tied copies of the same issue"
)]
fn given_workspace_tied_copies(world: &mut KanbusWorld) {
    let workspace = create_workspace(world);
    let repo = create_repo(&workspace, "repo");
    write_issue(
        &repo.join("project"),
        &build_issue(TIE_IDENTIFIER, TIE_ALPHA_TITLE, base_updated_at()),
    );
    write_default_config(&repo);
    commit_all(&repo);
    let worktree = add_worktree(&workspace, &repo, "repo-wt");
    let issue = read_issue(&worktree.join("project"), TIE_IDENTIFIER);
    let tied = IssueData {
        title: TIE_ZETA_TITLE.to_string(),
        ..issue
    };
    write_issue(&worktree.join("project"), &tied);
    world.working_directory = Some(workspace);
}

#[given("a single Kanbus project with one issue and no duplicate copies")]
fn given_single_project_no_duplicates(world: &mut KanbusWorld) {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let repo = temp_dir.path().join("single-project");
    fs::create_dir_all(&repo).expect("create repo dir");
    init_git_repo(&repo);
    write_issue(
        &repo.join("project"),
        &build_issue(DEDUP_IDENTIFIER, DEDUP_TITLE, base_updated_at()),
    );
    write_default_config(&repo);
    world.temp_dir = Some(temp_dir);
    world.working_directory = Some(repo);
}

#[then("the issue appears exactly once")]
fn then_issue_appears_exactly_once(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let key = format_issue_key(DEDUP_IDENTIFIER, false);
    assert_eq!(
        stdout.matches(key.as_str()).count(),
        1,
        "expected {key} exactly once, got: {stdout}"
    );
}

#[then("the listed entry is the most recently changed version of the issue")]
fn then_listed_entry_is_most_recent(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(
        stdout.contains(DEDUP_EDITED_TITLE),
        "edited version missing: {stdout}"
    );
    assert!(
        !stdout.contains(DEDUP_TITLE),
        "stale version listed: {stdout}"
    );
}

#[then("each distinct issue appears exactly once")]
fn then_each_distinct_issue_appears_once(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    for identifier in [ONE_IDENTIFIER, TWO_IDENTIFIER] {
        let key = format_issue_key(identifier, false);
        assert_eq!(
            stdout.matches(key.as_str()).count(),
            1,
            "expected {key} exactly once, got: {stdout}"
        );
    }
}

#[then("the deterministic tie-break winner is listed")]
fn then_tie_break_winner_listed(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains(TIE_ZETA_TITLE), "zeta copy missing: {stdout}");
    assert!(
        !stdout.contains(TIE_ALPHA_TITLE),
        "alpha copy listed: {stdout}"
    );
}

#[then("the single-project listing shows the issue exactly once")]
fn then_single_project_listing_shows_issue_once(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let key = format_issue_key(DEDUP_IDENTIFIER, true);
    assert_eq!(
        stdout.matches(key.as_str()).count(),
        1,
        "expected {key} exactly once, got: {stdout}"
    );
}

#[then("no issue identity appears more than once")]
fn then_no_identity_appears_more_than_once(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_ref().expect("stdout");
    for identifier in [DEDUP_IDENTIFIER] {
        let key = format_issue_key(identifier, false);
        assert!(
            stdout.matches(key.as_str()).count() <= 1,
            "identity {key} duplicated: {stdout}"
        );
    }
}