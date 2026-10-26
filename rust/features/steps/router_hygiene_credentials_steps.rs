//! Steps for router host hygiene and credential handling.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Mutex, OnceLock};

use cucumber::{given, then, when};
use kanbus::models::MutexApiConfiguration;
use kanbus::mutex_api;
use kanbus::router::{
    finish_router_package_resources, prune_stale_router_worktrees, redact_router_log,
    router_worktree_path, router_worktree_root,
};
use tempfile::TempDir;

use crate::step_definitions::initialization_steps::KanbusWorld;

const PLACEHOLDER_BEARER_TOKEN: &str = "placeholder-token";

#[derive(Default)]
struct HygieneFixture {
    repository: Option<TempDir>,
    output: String,
    redacted: String,
    mutex_configuration: Option<MutexApiConfiguration>,
    mutex_error: Option<String>,
}

fn fixture() -> &'static Mutex<HygieneFixture> {
    static FIXTURE: OnceLock<Mutex<HygieneFixture>> = OnceLock::new();
    FIXTURE.get_or_init(|| Mutex::new(HygieneFixture::default()))
}

fn git(root: &Path, arguments: &[&str]) -> String {
    let output = Command::new("git")
        .args(arguments)
        .current_dir(root)
        .output()
        .expect("run git");
    assert!(
        output.status.success(),
        "git {arguments:?} failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8_lossy(&output.stdout).trim().to_string()
}

fn repository_root(state: &HygieneFixture) -> PathBuf {
    fs::canonicalize(state.repository.as_ref().expect("repository").path())
        .expect("canonical repository path")
}

fn registered_worktrees(root: &Path) -> Vec<PathBuf> {
    git(root, &["worktree", "list", "--porcelain"])
        .lines()
        .filter_map(|line| line.strip_prefix("worktree "))
        .map(PathBuf::from)
        .collect()
}

fn package_has_registered_worktree(root: &Path, package: &str) -> bool {
    let prefix = format!("{package}-");
    registered_worktrees(root).iter().any(|path| {
        path.file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.starts_with(&prefix))
    })
}

fn opencode_data_directory_for(root: &Path, package: &str) -> PathBuf {
    let common = PathBuf::from(git(root, &["rev-parse", "--git-common-dir"]));
    let common = if common.is_absolute() {
        common
    } else {
        root.join(common)
    };
    common
        .join("kanbus-router-adapters")
        .join("opencode")
        .join(package)
}

#[given("a router test repository")]
fn given_router_test_repository(_world: &mut KanbusWorld) {
    let repository = TempDir::new().expect("temporary repository");
    let root = fs::canonicalize(repository.path()).expect("canonical path");
    git(&root, &["init", "--quiet"]);
    git(&root, &["config", "user.email", "hygiene@example.test"]);
    git(&root, &["config", "user.name", "Hygiene Test"]);
    fs::write(root.join("README.md"), "hygiene\n").expect("write file");
    git(&root, &["add", "README.md"]);
    git(&root, &["commit", "--quiet", "-m", "initial"]);
    *fixture().lock().expect("lock fixture") = HygieneFixture {
        repository: Some(repository),
        ..HygieneFixture::default()
    };
}

#[then(
    expr = "the router worktree for package {string} claim {string} should be inside the git common directory"
)]
fn then_worktree_inside_common_directory(_world: &mut KanbusWorld, package: String, claim: String) {
    let state = fixture().lock().expect("lock fixture");
    let root = repository_root(&state);
    let common = PathBuf::from(git(&root, &["rev-parse", "--git-common-dir"]));
    let common = fs::canonicalize(if common.is_absolute() {
        common
    } else {
        root.join(common)
    })
    .expect("canonical common directory");
    let path = router_worktree_path(&root, &package, &claim);
    assert!(
        path.starts_with(&common) || path.starts_with(root.join(".git")),
        "{} is outside {}",
        path.display(),
        common.display()
    );
}

#[given(expr = "a registered router worktree for package {string} claim {string}")]
fn given_registered_router_worktree(_world: &mut KanbusWorld, package: String, claim: String) {
    let state = fixture().lock().expect("lock fixture");
    let root = repository_root(&state);
    let path = router_worktree_path(&root, &package, &claim);
    fs::create_dir_all(path.parent().expect("worktree parent")).expect("create parent");
    git(
        &root,
        &[
            "worktree",
            "add",
            "--detach",
            &path.to_string_lossy(),
            "HEAD",
        ],
    );
}

#[given(expr = "an OpenCode data directory holding a credentials copy for package {string}")]
fn given_opencode_data_directory(_world: &mut KanbusWorld, package: String) {
    let state = fixture().lock().expect("lock fixture");
    let root = repository_root(&state);
    let credentials = opencode_data_directory_for(&root, &package).join("opencode");
    fs::create_dir_all(&credentials).expect("create credentials directory");
    fs::write(credentials.join("auth.json"), "{}\n").expect("write credentials copy");
}

#[given(expr = "the directory of the router worktree for package {string} was deleted")]
fn given_worktree_directory_deleted(_world: &mut KanbusWorld, package: String) {
    let state = fixture().lock().expect("lock fixture");
    let root = repository_root(&state);
    let prefix = format!("{package}-");
    for path in registered_worktrees(&root) {
        let matches = path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.starts_with(&prefix));
        if matches {
            fs::remove_dir_all(path).expect("delete worktree directory");
        }
    }
}

#[when(expr = "the router finishes package {string} with a terminal outcome")]
fn when_router_finishes_package(_world: &mut KanbusWorld, package: String) {
    let state = fixture().lock().expect("lock fixture");
    finish_router_package_resources(&repository_root(&state), &package);
}

#[when("the router prunes stale worktrees")]
fn when_router_prunes_stale_worktrees(_world: &mut KanbusWorld) {
    let state = fixture().lock().expect("lock fixture");
    prune_stale_router_worktrees(&repository_root(&state));
}

#[then(expr = "no router worktree should remain registered for package {string}")]
fn then_no_worktree_remains(_world: &mut KanbusWorld, package: String) {
    let state = fixture().lock().expect("lock fixture");
    let root = repository_root(&state);
    assert!(!package_has_registered_worktree(&root, &package));
    let prefix = format!("{package}-");
    let leftover = fs::read_dir(router_worktree_root(&root))
        .map(|entries| {
            entries.flatten().any(|entry| {
                entry
                    .file_name()
                    .to_str()
                    .is_some_and(|name| name.starts_with(&prefix))
            })
        })
        .unwrap_or(false);
    assert!(!leftover, "a worktree directory is left behind");
}

#[then(expr = "a router worktree should remain registered for package {string}")]
fn then_worktree_remains(_world: &mut KanbusWorld, package: String) {
    let state = fixture().lock().expect("lock fixture");
    assert!(package_has_registered_worktree(
        &repository_root(&state),
        &package
    ));
}

#[then(expr = "no OpenCode data directory should remain for package {string}")]
fn then_no_opencode_data_remains(_world: &mut KanbusWorld, package: String) {
    let state = fixture().lock().expect("lock fixture");
    let directory = opencode_data_directory_for(&repository_root(&state), &package);
    assert!(!directory.exists(), "{} still exists", directory.display());
}

#[given(
    regex = r#"^agent output with a (?P<family>.+) credential assembled from "(?P<prefix>[^"]*)" and "(?P<body>[^"]*)" joined by (?P<joiner>\w+) between two text lines$"#
)]
fn assemble_agent_output(
    _world: &mut KanbusWorld,
    family: String,
    prefix: String,
    body: String,
    joiner: String,
) {
    let _ = family;
    let separator = if joiner == "space" { " " } else { "" };
    fixture().lock().expect("lock fixture").output =
        format!("first line\n{prefix}{separator}{body}\nlast line");
}

#[when("the agent output is redacted for persistence")]
fn when_agent_output_is_redacted(_world: &mut KanbusWorld) {
    let mut state = fixture().lock().expect("lock fixture");
    state.redacted = redact_router_log(&state.output);
}

#[then(expr = "the redacted output should have {int} lines")]
fn then_redacted_output_line_count(_world: &mut KanbusWorld, count: usize) {
    let state = fixture().lock().expect("lock fixture");
    assert_eq!(
        state.redacted.split('\n').count(),
        count,
        "{}",
        state.redacted
    );
}

#[then(expr = "the redacted output should not contain {string}")]
fn then_redacted_output_lacks(_world: &mut KanbusWorld, text: String) {
    let state = fixture().lock().expect("lock fixture");
    assert!(!state.redacted.contains(&text), "{}", state.redacted);
}

#[then(expr = "the redacted output should contain {string}")]
fn then_redacted_output_contains(_world: &mut KanbusWorld, text: String) {
    let state = fixture().lock().expect("lock fixture");
    assert!(state.redacted.contains(&text), "{}", state.redacted);
}

#[given(expr = "a mutex API client configuration with endpoint {string} and a bearer token")]
fn given_mutex_client_configuration(_world: &mut KanbusWorld, endpoint: String) {
    fixture().lock().expect("lock fixture").mutex_configuration = Some(MutexApiConfiguration {
        endpoint: Some(endpoint),
        bearer_token: Some(PLACEHOLDER_BEARER_TOKEN.to_string()),
    });
}

#[when("the mutex API client acquires a lease")]
fn when_mutex_client_acquires_lease(_world: &mut KanbusWorld) {
    let mut state = fixture().lock().expect("lock fixture");
    let configuration = state
        .mutex_configuration
        .clone()
        .expect("mutex configuration");
    state.mutex_error = std::thread::spawn(move || {
        mutex_api::acquire(
            &configuration,
            "router:issue:kbs-hygiene",
            "hygiene",
            "claim-hygiene",
            1,
            60,
        )
        .err()
        .map(|error| error.to_string())
    })
    .join()
    .expect("mutex client thread");
}

#[then(expr = "the mutex API client error should be {string}")]
fn then_mutex_client_error(_world: &mut KanbusWorld, message: String) {
    let state = fixture().lock().expect("lock fixture");
    assert_eq!(state.mutex_error.as_deref(), Some(message.as_str()));
}
