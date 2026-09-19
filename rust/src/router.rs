//! Deterministic Issue Router configuration, planning, and coordination.

use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use chrono::{DateTime, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::coordination::{
    append_hard_claim_event, append_hard_release_event, append_hard_renew_event,
    parse_duration_seconds, published_revision, run_coordination, CoordinationOperation,
};
use crate::error::KanbusError;
use crate::event_history::{events_dir_for_project, EventRecord, EventType};
use crate::file_io::{get_configuration_path, load_project_directory};
use crate::issue_files::{list_issue_identifiers, read_issue_from_file};
use crate::models::{
    IssueData, IssueRouterConfiguration, IssueRouterProviderConfiguration, ProjectConfiguration,
};
use crate::policy_context::{PolicyContext, PolicyOperation};
use crate::policy_evaluator::evaluate_policies;
use crate::policy_loader::load_policies;

const ROUTER_ROUTE_LABEL_PREFIXES: [&str; 2] = ["agent-class:", "agent-provider:"];
const ROUTER_GIT_TIMEOUT: Duration = Duration::from_secs(20);

/// A resolved package route used by the planner and worker scheduler.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct IssueRouterRoute {
    /// Route kind, either `class` or `provider`.
    pub kind: String,
    /// Class or explicitly pinned provider name from the issue label.
    pub name: String,
    /// Provider profile selected for the next attempt.
    pub provider_profile: String,
}

/// One package that can be started by the Issue Router.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct IssueRouterEligiblePackage {
    /// Identifier of the explicitly routed package root.
    pub issue_id: String,
    /// Resolved provider route.
    pub route: IssueRouterRoute,
    /// Sorted identifiers included in this package.
    pub package_issue_ids: Vec<String>,
    /// Instant at which the root entered its current pending period.
    pub pending_since: String,
    /// One-based adapter attempt number.
    pub attempt: u32,
}

/// One package that is waiting for a stable deferral reason to clear.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct IssueRouterDeferredPackage {
    /// Identifier of the package root.
    pub issue_id: String,
    /// Stable machine-readable reason the package is deferred.
    pub reason: String,
}

/// Deterministic plan returned by `router plan`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct IssueRouterPlan {
    /// Version of the public router-plan shape.
    pub version: u8,
    /// Whether router configuration enables scheduling.
    pub enabled: bool,
    /// Whether global durable router control state pauses scheduling.
    pub paused: bool,
    /// Ordered packages that can be started.
    pub eligible: Vec<IssueRouterEligiblePackage>,
    /// Pending or retrying packages blocked by policy or capacity.
    pub deferred: Vec<IssueRouterDeferredPackage>,
}

#[derive(Debug, Clone, Default)]
struct RouterEventState {
    paused: bool,
    holds: BTreeSet<String>,
    attempts: BTreeMap<String, u32>,
    retry_at: BTreeMap<String, DateTime<Utc>>,
    provider_profiles: BTreeMap<String, String>,
    requested_changes: BTreeSet<String>,
    checkpoints: BTreeMap<String, (String, u64)>,
    pull_requests: BTreeMap<String, (u64, String)>,
    cancelled: BTreeSet<String>,
}

#[derive(Debug, Clone)]
struct Candidate {
    issue: IssueData,
    route: Option<IssueRouterRoute>,
    package_issue_ids: Vec<String>,
    pending_since: DateTime<Utc>,
    attempt: u32,
    priority: u8,
}

/// A supported issue-router CLI operation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IssueRouterOperation {
    /// Display the deterministic scheduling plan.
    Plan { json: bool },
    /// Process at most one eligible package synchronously.
    RunOnce,
    /// Keep reconciling until a stop request is received.
    RunWatch,
    /// Display local scheduler and durable control state.
    Status,
    /// Stop watch-mode scheduling after the current package run.
    Stop,
    /// Pause global package scheduling.
    Pause,
    /// Resume global package scheduling.
    Resume,
    /// Hold one route kind from new scheduling.
    Hold {
        /// Class route to hold.
        class: Option<String>,
        /// Provider profile to hold.
        provider_profile: Option<String>,
    },
    /// Release one held route kind.
    Unhold {
        /// Class route to release.
        class: Option<String>,
        /// Provider profile to release.
        provider_profile: Option<String>,
    },
    /// Cancel an active package while retaining its last accepted checkpoint.
    Cancel {
        /// Package root issue identifier.
        issue_id: String,
    },
    /// Surface durable evidence for an orphaned or paused provider run.
    Recover {
        /// Package root issue identifier.
        issue_id: String,
    },
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
struct LocalRouterState {
    watch_pid: Option<u32>,
    scheduler_claim_id: Option<String>,
    scheduler_owner: Option<String>,
    scheduler_hard: bool,
    active_issue_id: Option<String>,
    active_claim_id: Option<String>,
    active_child_pid: Option<u32>,
    stop_requested: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterAgentResult {
    schema_version: u8,
    outcome: String,
    #[serde(default)]
    summary: String,
    #[serde(default)]
    issue_updates: Vec<RouterIssueUpdate>,
    #[serde(default)]
    issue_comments: Vec<RouterIssueComment>,
    checkpoint: Option<RouterCheckpoint>,
    #[serde(default)]
    artifacts: Vec<RouterArtifact>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterIssueUpdate {
    issue_id: String,
    status: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterIssueComment {
    issue_id: String,
    text: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterCheckpoint {
    #[serde(rename = "ref")]
    reference: String,
    revision: u64,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterArtifact {
    name: String,
    #[serde(rename = "ref")]
    reference: String,
}

#[derive(Debug, Clone)]
struct RouterClaim {
    issue_id: String,
    claim_id: String,
    revision: u64,
    resource: String,
    hard: bool,
    owner: String,
    resources: Vec<String>,
}

struct RouterLeaseRenewalGuard {
    stopped: Arc<AtomicBool>,
    failure: Arc<Mutex<Option<String>>>,
    worker: Option<thread::JoinHandle<()>>,
}

impl RouterLeaseRenewalGuard {
    fn start(
        interval: Duration,
        renew: impl Fn() -> Result<(), String> + Send + 'static,
    ) -> Result<Self, String> {
        // Refresh the earliest-acquired handle before any potentially slow
        // shared-state publication begins.
        renew()?;
        let stopped = Arc::new(AtomicBool::new(false));
        let failure = Arc::new(Mutex::new(None));
        let thread_stopped = Arc::clone(&stopped);
        let thread_failure = Arc::clone(&failure);
        let worker = thread::spawn(move || loop {
            thread::park_timeout(interval);
            if thread_stopped.load(Ordering::SeqCst) {
                break;
            }
            if let Err(error) = renew() {
                if let Ok(mut failure) = thread_failure.lock() {
                    *failure = Some(error);
                }
                break;
            }
        });
        Ok(Self {
            stopped,
            failure,
            worker: Some(worker),
        })
    }

    fn check(&self) -> Result<(), KanbusError> {
        let failure = self
            .failure
            .lock()
            .map_err(|_| KanbusError::IssueOperation("router lease renewer failed".into()))?;
        if let Some(error) = failure.as_ref() {
            return Err(KanbusError::IssueOperation(format!(
                "router hard lease renewal failed: {error}"
            )));
        }
        Ok(())
    }

    fn stop(&mut self) -> Result<(), KanbusError> {
        self.stopped.store(true, Ordering::SeqCst);
        if let Some(worker) = self.worker.take() {
            worker.thread().unpark();
            let _ = worker.join();
        }
        self.check()
    }
}

impl Drop for RouterLeaseRenewalGuard {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::SeqCst);
        if let Some(worker) = self.worker.take() {
            worker.thread().unpark();
            let _ = worker.join();
        }
    }
}

#[derive(Debug, Clone)]
struct PublishedRouterRef {
    reference: String,
    pushed_sha: String,
    previous_remote_sha: String,
    previous_local_sha: Option<String>,
    remote_published: bool,
}

fn serialized_event_type(event: &EventRecord) -> Option<String> {
    serde_json::to_value(&event.event_type)
        .ok()?
        .as_str()
        .map(ToOwned::to_owned)
}

fn is_shared_router_event(event: &EventRecord) -> bool {
    if matches!(&event.event_type, EventType::RouterControl) {
        return payload_text(event, "action") == Some("cancel");
    }
    serialized_event_type(event).is_some_and(|kind| kind.starts_with("router."))
        || (event.issue_id.starts_with("router:")
            && matches!(
                &event.event_type,
                EventType::CoordinationClaim
                    | EventType::CoordinationRenew
                    | EventType::CoordinationRelease
                    | EventType::CoordinationResultPublished
            ))
}

fn load_router_events(project_dir: &Path) -> Result<Vec<EventRecord>, KanbusError> {
    let events_dir = events_dir_for_project(project_dir);
    let mut events = Vec::new();
    if events_dir.exists() {
        let mut paths = fs::read_dir(events_dir)
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| {
                path.extension().and_then(|extension| extension.to_str()) == Some("json")
            })
            .collect::<Vec<_>>();
        paths.sort();
        for path in paths {
            let bytes = fs::read(path).map_err(|error| KanbusError::Io(error.to_string()))?;
            let Ok(event) = serde_json::from_slice::<EventRecord>(&bytes) else {
                continue;
            };
            let kind = serialized_event_type(&event).unwrap_or_default();
            if kind.starts_with("router.")
                || (event.issue_id.starts_with("router:")
                    && matches!(
                        &event.event_type,
                        EventType::CoordinationClaim
                            | EventType::CoordinationRenew
                            | EventType::CoordinationRelease
                    ))
            {
                events.push(event);
            }
        }
    }
    let root = repository_root(project_dir)?;
    for event in read_shared_router_events(&root)? {
        if !events
            .iter()
            .any(|existing| existing.event_id == event.event_id)
        {
            events.push(event);
        }
    }
    events.sort_by(|left, right| {
        left.occurred_at
            .cmp(&right.occurred_at)
            .then_with(|| left.event_id.cmp(&right.event_id))
    });
    Ok(events)
}

const ROUTER_STATE_BRANCH: &str = "kanbus/router-state";
fn configured_project_directory(root: &Path) -> Result<PathBuf, KanbusError> {
    let project_dir = load_project_directory(root)?;
    project_dir
        .strip_prefix(root)
        .map(Path::to_path_buf)
        .map_err(|_| {
            KanbusError::IssueOperation(
                "shared router state requires project_directory inside the repository".to_string(),
            )
        })
}

/// Resolve the enclosing Git repository root for an Issue Router command.
///
/// Router commands establish this boundary before loading Kanbus
/// configuration or shared state, so a caller may safely start from any
/// repository subdirectory.
pub fn resolve_router_root(path: &Path) -> Result<PathBuf, KanbusError> {
    let mut command = router_git_command();
    command
        .args(["rev-parse", "--show-toplevel"])
        .current_dir(path);
    let output = router_git_output(command).map_err(|_| {
        KanbusError::IssueOperation("issue router requires a Git repository".to_string())
    })?;
    if !output.status.success() {
        return Err(KanbusError::IssueOperation(
            "issue router requires a Git repository".to_string(),
        ));
    }
    let root = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if root.is_empty() {
        return Err(KanbusError::IssueOperation(
            "issue router requires a Git repository".to_string(),
        ));
    }
    let root = PathBuf::from(root);
    Ok(root.canonicalize().unwrap_or(root))
}

fn repository_root(path: &Path) -> Result<PathBuf, KanbusError> {
    resolve_router_root(path)
}

/// Construct Git commands used by coordination without allowing an invisible
/// credential prompt to wedge a worker before it has even started an agent.
fn router_git_command() -> Command {
    let mut command = Command::new("git");
    command
        .env("GIT_TERMINAL_PROMPT", "0")
        .env("GIT_ASKPASS", "/bin/false");
    command
}

/// Run a router Git command with bounded wait time so a remote transport stall
/// is reported as a recoverable router failure rather than wedging a worker.
fn router_git_output(command: Command) -> Result<Output, KanbusError> {
    router_git_output_with_timeout(command, ROUTER_GIT_TIMEOUT)
}

fn router_git_output_with_timeout(
    mut command: Command,
    timeout: Duration,
) -> Result<Output, KanbusError> {
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = command
        .spawn()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let deadline = Instant::now() + timeout;
    loop {
        if let Some(status) = child
            .try_wait()
            .map_err(|error| KanbusError::Io(error.to_string()))?
        {
            let mut stdout = Vec::new();
            if let Some(mut stream) = child.stdout.take() {
                stream
                    .read_to_end(&mut stdout)
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
            }
            let mut stderr = Vec::new();
            if let Some(mut stream) = child.stderr.take() {
                stream
                    .read_to_end(&mut stderr)
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
            }
            return Ok(Output {
                status,
                stdout,
                stderr,
            });
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err(KanbusError::IssueOperation(
                "router Git operation timed out".to_string(),
            ));
        }
        thread::sleep(Duration::from_millis(50));
    }
}

fn remote_router_state_ref(root: &Path, fetch: bool) -> Result<Option<String>, KanbusError> {
    let mut remote_command = router_git_command();
    remote_command
        .args(["remote", "get-url", "origin"])
        .current_dir(root);
    let remote = router_git_output(remote_command)?;
    if !remote.status.success() {
        return Ok(None);
    }
    let remote_branch = format!("refs/heads/{ROUTER_STATE_BRANCH}");
    let mut listed_command = router_git_command();
    listed_command
        .args(["ls-remote", "--heads", "origin", &remote_branch])
        .current_dir(root);
    let listed = router_git_output(listed_command)?;
    if !listed.status.success() {
        return Err(KanbusError::IssueOperation(
            "could not inspect shared router state".to_string(),
        ));
    }
    if listed.stdout.is_empty() {
        return Ok(None);
    }
    if fetch {
        let tracking_ref = format!("refs/remotes/origin/{ROUTER_STATE_BRANCH}");
        let refspec = format!("+{remote_branch}:{tracking_ref}");
        let mut fetch_command = router_git_command();
        fetch_command
            .args(["fetch", "--quiet", "origin", &refspec])
            .current_dir(root);
        let fetched = router_git_output(fetch_command)?;
        if !fetched.status.success() {
            return Err(KanbusError::IssueOperation(
                "could not fetch shared router state".to_string(),
            ));
        }
    }
    Ok(Some(format!("refs/remotes/origin/{ROUTER_STATE_BRANCH}")))
}

pub(crate) fn read_shared_router_events(root: &Path) -> Result<Vec<EventRecord>, KanbusError> {
    let Some(state_ref) = remote_router_state_ref(root, true)? else {
        return Ok(Vec::new());
    };
    read_router_state_ref_events(root, &state_ref)
}

fn read_router_state_ref_events(
    root: &Path,
    state_ref: &str,
) -> Result<Vec<EventRecord>, KanbusError> {
    let events_path = configured_project_directory(root)?.join("events");
    let events_path = events_path.to_string_lossy().to_string();
    let mut list_command = router_git_command();
    list_command
        .args([
            "ls-tree",
            "-r",
            "--name-only",
            state_ref,
            "--",
            &events_path,
        ])
        .current_dir(root);
    let listed = router_git_output(list_command)?;
    if !listed.status.success() {
        return Err(KanbusError::IssueOperation(
            "could not read shared router state".to_string(),
        ));
    }
    // A router-state branch can contain thousands of immutable records.  One
    // `git show` process per record made claim acquisition look like a hung
    // worker and prevented Codex from ever starting.  Ask Git for every blob
    // in one batch instead.
    let paths = String::from_utf8_lossy(&listed.stdout)
        .lines()
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let mut child = router_git_command()
        .args(["cat-file", "--batch"])
        .current_dir(root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if let Some(mut input) = child.stdin.take() {
        for path in &paths {
            input
                .write_all(format!("{state_ref}:{path}\n").as_bytes())
                .map_err(|error| KanbusError::Io(error.to_string()))?;
        }
    }
    let mut output = Vec::new();
    if let Some(mut stdout) = child.stdout.take() {
        stdout
            .read_to_end(&mut output)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    if !child
        .wait()
        .map_err(|error| KanbusError::Io(error.to_string()))?
        .success()
    {
        return Err(KanbusError::IssueOperation(
            "could not read shared router state".to_string(),
        ));
    }
    let mut events = Vec::new();
    let mut cursor = 0usize;
    while cursor < output.len() {
        let Some(header_end) = output[cursor..].iter().position(|byte| *byte == b'\n') else {
            break;
        };
        let header_end = cursor + header_end;
        let header = String::from_utf8_lossy(&output[cursor..header_end]);
        cursor = header_end + 1;
        let Some(size) = header
            .split_whitespace()
            .nth(2)
            .and_then(|value| value.parse::<usize>().ok())
        else {
            continue;
        };
        if cursor.saturating_add(size) > output.len() {
            break;
        }
        if let Ok(event) = serde_json::from_slice::<EventRecord>(&output[cursor..cursor + size]) {
            if is_shared_router_event(&event) {
                events.push(event);
            }
        }
        cursor += size;
        if output.get(cursor) == Some(&b'\n') {
            cursor += 1;
        }
    }
    events.sort_by(|left, right| {
        left.occurred_at
            .cmp(&right.occurred_at)
            .then_with(|| left.event_id.cmp(&right.event_id))
    });
    Ok(events)
}

fn related_claim_events(
    project_dir: &Path,
    event: &EventRecord,
) -> Result<Vec<EventRecord>, KanbusError> {
    if !matches!(&event.event_type, EventType::RouterAttempt)
        || payload_text(event, "action") != Some("started")
    {
        return Ok(Vec::new());
    }
    let Some(claim_id) = payload_text(event, "claim_id") else {
        return Ok(Vec::new());
    };
    let events_dir = events_dir_for_project(project_dir);
    if !events_dir.exists() {
        return Ok(Vec::new());
    }
    let mut related = Vec::new();
    for entry in fs::read_dir(events_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
        let path = entry
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .path();
        if path.extension().and_then(|extension| extension.to_str()) != Some("json") {
            continue;
        }
        let bytes = fs::read(path).map_err(|error| KanbusError::Io(error.to_string()))?;
        let Ok(candidate) = serde_json::from_slice::<EventRecord>(&bytes) else {
            continue;
        };
        if !matches!(
            &candidate.event_type,
            EventType::CoordinationClaim
                | EventType::CoordinationRenew
                | EventType::CoordinationRelease
        ) || payload_text(&candidate, "claim_id") != Some(claim_id)
            || !candidate.issue_id.starts_with("router:")
        {
            continue;
        }
        related.push(candidate);
    }
    related.sort_by(|left, right| {
        left.occurred_at
            .cmp(&right.occurred_at)
            .then_with(|| left.event_id.cmp(&right.event_id))
    });
    Ok(related)
}

/// Publish router-owned state to the dedicated shared state branch.
///
/// Only the configured project issue and event directories are staged from a
/// clean, hidden worktree. User checkout dirt is never added.
pub fn publish_shared_router_event(root: &Path, event: &EventRecord) -> Result<(), KanbusError> {
    // Pause/hold controls are intentionally local to this host. Cancellation is
    // package-scoped and remains shared so it can fence a running claim.
    if matches!(&event.event_type, EventType::RouterControl)
        && !matches!(payload_text(event, "action"), Some("cancel"))
    {
        return Ok(());
    }
    if remote_router_state_ref(root, false)?.is_none()
        && !Command::new("git")
            .args(["remote", "get-url", "origin"])
            .current_dir(root)
            .output()
            .is_ok_and(|output| output.status.success())
    {
        return Ok(());
    }
    for attempt in 0..5 {
        let state_ref = remote_router_state_ref(root, true)?;
        let expected_remote_tip = if state_ref.is_some() {
            let tracking_ref = format!("refs/remotes/origin/{ROUTER_STATE_BRANCH}");
            let sha = Command::new("git")
                .args(["rev-parse", &tracking_ref])
                .current_dir(root)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            String::from_utf8_lossy(&sha.stdout).trim().to_string()
        } else {
            String::new()
        };
        let base = if let Some(reference) = state_ref.as_deref() {
            let sha = Command::new("git")
                .args(["rev-parse", reference])
                .current_dir(root)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            String::from_utf8_lossy(&sha.stdout).trim().to_string()
        } else {
            let head = Command::new("git")
                .args(["rev-parse", "HEAD"])
                .current_dir(root)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            if !head.status.success() {
                return Err(KanbusError::IssueOperation(
                    "shared router state requires a committed Git base".to_string(),
                ));
            }
            String::from_utf8_lossy(&head.stdout).trim().to_string()
        };
        if let Some(reference) = state_ref.as_deref() {
            let shared_events = read_router_state_ref_events(root, reference)?;
            if shared_events
                .iter()
                .any(|existing| existing.event_id == event.event_id)
            {
                return Ok(());
            }
            validate_shared_result_publication(event, &shared_events)?;
            validate_started_event_claim(root, event, &shared_events)?;
        } else {
            validate_shared_result_publication(event, &[])?;
            validate_started_event_claim(root, event, &[])?;
        }
        let worktree = std::env::temp_dir().join(format!(
            ".kanbus-router-state-{}-{}",
            std::process::id(),
            Uuid::new_v4()
        ));
        let added = Command::new("git")
            .args(["worktree", "add", "--detach"])
            .arg(&worktree)
            .arg(&base)
            .current_dir(root)
            .output()
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        if !added.status.success() {
            return Err(KanbusError::IssueOperation(
                "could not create hidden router-state worktree".to_string(),
            ));
        }
        let update = (|| {
            let source_head = Command::new("git")
                .args(["rev-parse", "HEAD"])
                .current_dir(root)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            if !source_head.status.success() {
                return Err(KanbusError::IssueOperation(
                    "could not resolve current source revision".to_string(),
                ));
            }
            let source_head = String::from_utf8_lossy(&source_head.stdout)
                .trim()
                .to_string();
            let merge = Command::new("git")
                .args([
                    "-c",
                    "user.name=Kanbus Issue Router",
                    "-c",
                    "user.email=kanbus-router@localhost",
                    "merge",
                    // The router-state ref is derived state.  A normal board
                    // commit is authoritative when both touch an issue (for
                    // example, a human accepts review while the router is
                    // recording a recovery event).  Taking the incoming
                    // source version lets us apply the new router event below
                    // instead of stranding the package on a Git conflict.
                    "-X",
                    "theirs",
                    "--no-edit",
                    &source_head,
                ])
                .current_dir(&worktree)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            if !merge.status.success() {
                let _ = Command::new("git")
                    .args(["merge", "--abort"])
                    .current_dir(&worktree)
                    .output();
                return Err(KanbusError::IssueOperation(
                    "router state reconciliation conflicted; no package was started".to_string(),
                ));
            }
            apply_shared_router_event_status(&worktree, event)?;
            let project_directory = configured_project_directory(root)?;
            let mut events_to_write = related_claim_events(&load_project_directory(root)?, event)?;
            events_to_write.push(event.clone());
            for shared_event in events_to_write {
                let filename = crate::event_history::event_filename(
                    &shared_event.occurred_at,
                    &shared_event.event_id,
                );
                let destination = worktree
                    .join(&project_directory)
                    .join("events")
                    .join(filename);
                if destination.exists() {
                    continue;
                }
                fs::create_dir_all(destination.parent().expect("router event parent"))
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
                let bytes = serde_json::to_vec_pretty(&shared_event)
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
                fs::write(destination, bytes)
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
            }
            let issue_path = project_directory.join("issues");
            let event_directory = project_directory.join("events");
            let add_issues = Command::new("git")
                .arg("add")
                .arg("--")
                .arg(issue_path)
                .current_dir(&worktree)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            if !add_issues.status.success() {
                return Err(KanbusError::IssueOperation(
                    "could not stage shared router state".to_string(),
                ));
            }
            // Project event history is intentionally ignored in user checkouts;
            // force-add only the router's configured event directory in this
            // clean hidden worktree so peer planners can reduce the same log.
            let add_events = Command::new("git")
                .args(["add", "-f", "--"])
                .arg(event_directory)
                .current_dir(&worktree)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            if !add_events.status.success() {
                return Err(KanbusError::IssueOperation(
                    "could not stage shared router state".to_string(),
                ));
            }
            let commit = Command::new("git")
                .args([
                    "-c",
                    "user.name=Kanbus Issue Router",
                    "-c",
                    "user.email=kanbus-router@localhost",
                    "commit",
                    "--allow-empty",
                    "-m",
                    &format!("[router-state] {}", event.event_id),
                ])
                .current_dir(&worktree)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            if !commit.status.success() {
                return Err(KanbusError::IssueOperation(
                    "could not commit shared router state".to_string(),
                ));
            }
            let remote_ref = format!("refs/heads/{ROUTER_STATE_BRANCH}");
            let lease = format!("--force-with-lease={remote_ref}:{expected_remote_tip}");
            let push_ref = format!("HEAD:{remote_ref}");
            let push = Command::new("git")
                .args(["push", &lease, "origin", &push_ref])
                .current_dir(&worktree)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            if push.status.success() {
                return Ok(true);
            }
            let current = Command::new("git")
                .args(["ls-remote", "--heads", "origin", &remote_ref])
                .current_dir(root)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            let current_sha = String::from_utf8_lossy(&current.stdout)
                .split_whitespace()
                .next()
                .unwrap_or("")
                .to_string();
            if current_sha != expected_remote_tip {
                return Ok(false);
            }
            Err(KanbusError::IssueOperation(
                "could not publish shared router state".to_string(),
            ))
        })();
        let _ = Command::new("git")
            .args(["worktree", "remove", "--force"])
            .arg(&worktree)
            .current_dir(root)
            .output();
        match update {
            Ok(true) => return Ok(()),
            Ok(false) if attempt < 4 => continue,
            Ok(false) => break,
            Err(error) => return Err(error),
        }
    }
    Err(KanbusError::IssueOperation(
        "shared router state changed repeatedly; retry the operation".to_string(),
    ))
}

fn validate_started_event_claim(
    root: &Path,
    event: &EventRecord,
    shared_events: &[EventRecord],
) -> Result<(), KanbusError> {
    if !matches!(&event.event_type, EventType::RouterAttempt)
        || payload_text(event, "action") != Some("started")
    {
        return Ok(());
    }
    let Some(issue_id) = event.issue_id.strip_prefix("router:") else {
        return Ok(());
    };
    let Some(claim_id) = payload_text(event, "claim_id") else {
        return Err(KanbusError::IssueOperation(
            "router start event omitted claim id".to_string(),
        ));
    };
    let project_dir = load_project_directory(root)?;
    let events_dir = events_dir_for_project(&project_dir);
    let mut coordination_events = shared_events
        .iter()
        .filter(|candidate| candidate.issue_id == format!("router:issue:{issue_id}"))
        .filter(|candidate| {
            matches!(
                &candidate.event_type,
                EventType::CoordinationClaim
                    | EventType::CoordinationRenew
                    | EventType::CoordinationRelease
            )
        })
        .cloned()
        .collect::<Vec<_>>();
    if events_dir.exists() {
        for entry in fs::read_dir(events_dir).map_err(|error| KanbusError::Io(error.to_string()))? {
            let path = entry
                .map_err(|error| KanbusError::Io(error.to_string()))?
                .path();
            if path.extension().and_then(|extension| extension.to_str()) != Some("json") {
                continue;
            }
            let bytes = fs::read(path).map_err(|error| KanbusError::Io(error.to_string()))?;
            let Ok(candidate) = serde_json::from_slice::<EventRecord>(&bytes) else {
                continue;
            };
            if candidate.issue_id == format!("router:issue:{issue_id}")
                && matches!(
                    &candidate.event_type,
                    EventType::CoordinationClaim
                        | EventType::CoordinationRenew
                        | EventType::CoordinationRelease
                )
                && !coordination_events
                    .iter()
                    .any(|existing| existing.event_id == candidate.event_id)
            {
                coordination_events.push(candidate);
            }
        }
    }
    let current =
        crate::coordination::reduce_coordination_events(&coordination_events, router_now());
    if !current.is_active()
        || current.claim_id.as_deref() != Some(claim_id)
        || current.owner.as_deref() != Some(event.actor_id.as_str())
    {
        return Err(KanbusError::IssueOperation(format!(
            "router package {issue_id} does not own the current live issue claim"
        )));
    }
    let configuration_path = get_configuration_path(root)?;
    let configuration = crate::config_loader::load_project_configuration(&configuration_path)?;
    let resource = format!("router:issue:{issue_id}");
    let revision = event.payload.get("revision").and_then(Value::as_u64);
    let hard_required = configuration
        .coordination
        .providers
        .first()
        .is_some_and(|provider| provider == "mutex_api");
    if hard_required {
        let lease = crate::mutex_api::inspect(&configuration.coordination.mutex_api, &resource)
            .map_err(|_| hard_mutex_unavailable())?;
        let current = lease.is_some_and(|lease| {
            lease.owner == event.actor_id
                && lease.claim_id == claim_id
                && Some(lease.revision) == revision
        });
        if !current {
            return Err(KanbusError::IssueOperation(format!(
                "router package {issue_id} does not own the current live issue claim"
            )));
        }
    } else if configuration
        .coordination
        .providers
        .iter()
        .any(|provider| provider == "mqtt")
    {
        let inspection = crate::coordination::run_coordination(
            root,
            CoordinationOperation::Inspect {
                resource: resource.clone(),
            },
        )?;
        if !coordination_output_claim_matches(&inspection, &event.actor_id, claim_id) {
            return Err(KanbusError::IssueOperation(format!(
                "router package {issue_id} does not own the current MQTT issue claim"
            )));
        }
    }
    Ok(())
}

fn validate_shared_result_publication(
    event: &EventRecord,
    shared_events: &[EventRecord],
) -> Result<(), KanbusError> {
    if !matches!(&event.event_type, EventType::CoordinationResultPublished) {
        return Ok(());
    }
    let revision = event.payload.get("revision").and_then(Value::as_u64);
    let artifact = payload_text(event, "artifact");
    let Some(revision) = revision else {
        return Err(KanbusError::IssueOperation(
            "published result revision must be a positive integer".to_string(),
        ));
    };
    let existing = shared_events
        .iter()
        .filter(|candidate| candidate.issue_id == event.issue_id)
        .filter(|candidate| {
            matches!(
                &candidate.event_type,
                EventType::CoordinationResultPublished
            )
        })
        .collect::<Vec<_>>();
    let Some(current) = existing
        .iter()
        .filter_map(|candidate| candidate.payload.get("revision").and_then(Value::as_u64))
        .max()
    else {
        return Ok(());
    };
    if revision < current {
        return Err(KanbusError::IssueOperation(format!(
            "stale revision {revision}; published revision is {current}"
        )));
    }
    if revision == current {
        if existing.iter().any(|candidate| {
            candidate.payload.get("revision").and_then(Value::as_u64) == Some(revision)
                && payload_text(candidate, "artifact") == artifact
        }) {
            return Ok(());
        }
        return Err(KanbusError::IssueOperation(format!(
            "revision {revision} already published with a different artifact"
        )));
    }
    Ok(())
}

fn apply_shared_router_event_status(
    worktree: &Path,
    event: &EventRecord,
) -> Result<(), KanbusError> {
    let Some(issue_id) = event.issue_id.strip_prefix("router:") else {
        return Ok(());
    };
    let configuration_path = get_configuration_path(worktree)?;
    let configuration = crate::config_loader::load_project_configuration(&configuration_path)?;
    let Some(router) = configuration.router.as_ref() else {
        return Ok(());
    };
    let mut transitions = Vec::<(String, String)>::new();
    let status = match &event.event_type {
        EventType::RouterAttempt if payload_text(event, "action") == Some("started") => {
            Some(&router.workflow.active)
        }
        EventType::RouterResult => match payload_text(event, "outcome") {
            Some("completed") => Some(&router.workflow.review),
            Some("blocked") | Some("cancelled") => Some(&router.workflow.blocked),
            _ => None,
        },
        EventType::RouterForge => match payload_text(event, "action") {
            Some("requested_changes" | "check_run_failure" | "checks_failed") => {
                Some(&router.workflow.active)
            }
            Some("opened" | "synchronize" | "approved" | "check_run_success" | "checks_passed") => {
                Some(&router.workflow.review)
            }
            Some("closed")
                if event.payload.get("merged").and_then(Value::as_bool) == Some(false) =>
            {
                Some(&router.workflow.blocked)
            }
            Some("closed")
                if event.payload.get("merged").and_then(Value::as_bool) == Some(true)
                    && event.payload.get("approved").and_then(Value::as_bool) == Some(true) =>
            {
                router.workflow.terminal.first()
            }
            _ => None,
        },
        _ => None,
    };
    if let Some(status) = status {
        transitions.push((issue_id.to_string(), status.clone()));
    }
    if matches!(&event.event_type, EventType::RouterResult) {
        if let Some(updates) = event.payload.get("issue_updates").and_then(Value::as_array) {
            for update in updates {
                if let (Some(id), Some(status)) = (
                    update.get("issue_id").and_then(Value::as_str),
                    update.get("status").and_then(Value::as_str),
                ) {
                    transitions.push((id.to_string(), status.to_string()));
                }
            }
        }
    }
    if transitions.is_empty() {
        return Ok(());
    }
    for (transition_issue_id, status) in transitions {
        apply_shared_issue_status(worktree, &configuration, &transition_issue_id, &status)?;
    }
    Ok(())
}

fn apply_shared_issue_status(
    worktree: &Path,
    configuration: &ProjectConfiguration,
    issue_id: &str,
    status: &str,
) -> Result<(), KanbusError> {
    let issue_path = worktree
        .join(&configuration.project_directory)
        .join("issues")
        .join(format!("{issue_id}.json"));
    if !issue_path.exists() {
        return Ok(());
    }
    let issue = read_issue_from_file(&issue_path)?;
    for next_status in
        router_status_transition_path(configuration, &issue.issue_type, &issue.status, status)?
    {
        crate::issue_update::update_issue(
            worktree,
            issue_id,
            None,
            None,
            Some(&next_status),
            None,
            None,
            false,
            true,
            &[],
            &[],
            None,
            None,
            None,
        )?;
    }
    Ok(())
}

/// Resolve a router lifecycle target through the issue's configured workflow.
///
/// Router events may be replayed after a Git-only refresh, when the canonical
/// card is still Open but the durable stream already records completion.  Do
/// not bypass workflow validation with an invalid Open -> Review shortcut.
fn router_status_transition_path(
    configuration: &ProjectConfiguration,
    issue_type: &str,
    current_status: &str,
    target_status: &str,
) -> Result<Vec<String>, KanbusError> {
    if current_status == target_status {
        return Ok(Vec::new());
    }
    let workflow = crate::workflows::get_workflow_for_issue_type(configuration, issue_type)?;
    let mut queue = VecDeque::from([(current_status.to_string(), Vec::<String>::new())]);
    let mut visited = BTreeSet::from([current_status.to_string()]);
    while let Some((status, path)) = queue.pop_front() {
        for next_status in workflow.get(&status).into_iter().flatten() {
            if !visited.insert(next_status.clone()) {
                continue;
            }
            let mut next_path = path.clone();
            next_path.push(next_status.clone());
            if next_status == target_status {
                return Ok(next_path);
            }
            queue.push_back((next_status.clone(), next_path));
        }
    }
    Err(KanbusError::IssueOperation(format!(
        "router cannot transition package from {current_status} to {target_status} through the configured workflow"
    )))
}

fn parse_timestamp(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|value| value.with_timezone(&Utc))
}

fn router_now() -> DateTime<Utc> {
    #[cfg(debug_assertions)]
    if let Ok(value) = std::env::var("KANBUS_TEST_COORDINATION_NOW") {
        if let Some(timestamp) = parse_timestamp(&value) {
            return timestamp;
        }
    }
    Utc::now()
}

fn payload_text<'a>(event: &'a EventRecord, key: &str) -> Option<&'a str> {
    event.payload.get(key).and_then(Value::as_str)
}

/// A Review slot is occupied only by work a human can actually inspect.
fn has_preserved_review_conversation(events: &[EventRecord], issue_id: &str) -> bool {
    events
        .iter()
        .filter(|event| event.issue_id == format!("router:{issue_id}"))
        .filter(|event| matches!(&event.event_type, EventType::RouterConversation))
        .max_by(|left, right| {
            left.occurred_at
                .cmp(&right.occurred_at)
                .then_with(|| left.event_id.cmp(&right.event_id))
        })
        .is_some_and(|event| payload_text(event, "lifecycle") == Some("review"))
}

fn reduce_router_events(events: &[EventRecord]) -> RouterEventState {
    let mut state = RouterEventState::default();
    for event in events {
        let issue_key = event
            .issue_id
            .strip_prefix("router:")
            .unwrap_or(&event.issue_id)
            .to_string();
        match &event.event_type {
            EventType::RouterControl => match payload_text(event, "action") {
                Some("pause") => state.paused = true,
                Some("resume") => state.paused = false,
                Some("hold") => {
                    if let Some(route) = payload_text(event, "route") {
                        state.holds.insert(route.to_string());
                    }
                }
                Some("unhold") => {
                    if let Some(route) = payload_text(event, "route") {
                        state.holds.remove(route);
                    }
                }
                Some("cancel") => {
                    state.cancelled.insert(issue_key.clone());
                }
                Some("requested_changes") => {
                    state.requested_changes.insert(issue_key.clone());
                }
                _ => {}
            },
            EventType::RouterAttempt => {
                let attempt_value = if payload_text(event, "action") == Some("retryable_failure") {
                    event.payload.get("next_attempt").and_then(Value::as_u64)
                } else {
                    event.payload.get("attempt").and_then(Value::as_u64)
                };
                if let Some(attempt) = attempt_value {
                    if let Ok(attempt) = u32::try_from(attempt) {
                        state.attempts.insert(issue_key.clone(), attempt.max(1));
                    }
                }
                if let Some(profile) = payload_text(event, "provider_profile") {
                    state
                        .provider_profiles
                        .insert(issue_key.clone(), profile.to_string());
                }
                if payload_text(event, "action") == Some("retryable_failure") {
                    if let Some(retry_at) =
                        payload_text(event, "retry_at").and_then(parse_timestamp)
                    {
                        state.retry_at.insert(issue_key.clone(), retry_at);
                    }
                } else if payload_text(event, "action") == Some("started") {
                    state.retry_at.remove(&issue_key);
                }
                if let (Some(reference), Some(revision)) = (
                    payload_text(event, "checkpoint_ref"),
                    event
                        .payload
                        .get("checkpoint_revision")
                        .and_then(Value::as_u64),
                ) {
                    state
                        .checkpoints
                        .insert(issue_key.clone(), (reference.to_string(), revision));
                }
            }
            EventType::RouterResult => {
                if event.payload.get("outcome").and_then(Value::as_str) == Some("completed") {
                    state.retry_at.remove(&issue_key);
                }
            }
            EventType::RouterForge => match payload_text(event, "action") {
                Some("requested_changes") => {
                    state.requested_changes.insert(issue_key.clone());
                }
                Some("approved") | Some("merged") | Some("closed") => {
                    state.requested_changes.remove(&issue_key);
                }
                Some("opened") | Some("synchronize") => {
                    if let (Some(number), Some(head_sha)) = (
                        event.payload.get("number").and_then(Value::as_u64),
                        payload_text(event, "head_sha"),
                    ) {
                        state
                            .pull_requests
                            .insert(issue_key.clone(), (number, head_sha.to_string()));
                    }
                }
                _ => {}
            },
            _ => {}
        }
    }
    state
}

fn apply_router_status_overlay(
    issues: &mut [IssueData],
    router_events: &[EventRecord],
    router: &IssueRouterConfiguration,
    issue_events: &[EventRecord],
) {
    let mut approvals = BTreeMap::<String, String>::new();
    for event in router_events {
        if matches!(&event.event_type, EventType::RouterForge)
            && payload_text(event, "action") == Some("approved")
        {
            if let Some(head) = payload_text(event, "head_sha") {
                approvals.insert(
                    event.issue_id.trim_start_matches("router:").to_string(),
                    head.to_string(),
                );
            }
        }
    }
    for issue in &mut *issues {
        let route_marker = format!("router:{}", issue.identifier);
        let latest_router = router_events
            .iter()
            .filter(|event| event.issue_id == route_marker)
            .filter(|event| {
                matches!(
                    &event.event_type,
                    EventType::RouterAttempt
                        | EventType::RouterResult
                        | EventType::RouterForge
                        | EventType::RouterConversation
                )
            })
            .max_by(|left, right| {
                left.occurred_at
                    .cmp(&right.occurred_at)
                    .then_with(|| left.event_id.cmp(&right.event_id))
            });
        let Some(event) = latest_router else {
            continue;
        };
        // A human terminal decision in the canonical issue record is final.
        // Router projections are advisory and must never resurrect closed work.
        if router.workflow.terminal.contains(&issue.status) {
            continue;
        }
        // The card itself is canonical.  An event can remain in the shared
        // history after a human (or the router) has already updated the card;
        // never let that older projection resurrect stale work in the planner.
        if parse_timestamp(&event.occurred_at)
            .is_some_and(|occurred_at| issue.updated_at > occurred_at)
        {
            continue;
        }
        let last_board_transition = issue_events
            .iter()
            .filter(|candidate| candidate.issue_id == issue.identifier)
            .filter(|candidate| matches!(&candidate.event_type, EventType::StateTransition))
            .max_by(|left, right| {
                left.occurred_at
                    .cmp(&right.occurred_at)
                    .then_with(|| left.event_id.cmp(&right.event_id))
            });
        if last_board_transition
            .is_some_and(|transition| transition.occurred_at >= event.occurred_at)
        {
            continue;
        }
        let status = match &event.event_type {
            EventType::RouterAttempt
                if matches!(
                    payload_text(event, "action"),
                    Some("started" | "retryable_failure")
                ) =>
            {
                // A retry is not a terminal agent decision: the package stays
                // active while the backoff clock prevents another start.
                Some(router.workflow.active.as_str())
            }
            EventType::RouterResult => match payload_text(event, "outcome") {
                Some("completed") => Some(router.workflow.review.as_str()),
                Some("blocked") | Some("cancelled") => Some(router.workflow.blocked.as_str()),
                _ => None,
            },
            EventType::RouterForge => match payload_text(event, "action") {
                Some("requested_changes" | "check_run_failure" | "checks_failed") => {
                    Some(router.workflow.active.as_str())
                }
                Some("opened")
                | Some("synchronize")
                | Some("approved")
                | Some("check_run_success")
                | Some("checks_passed") => Some(router.workflow.review.as_str()),
                Some("closed") => {
                    let merged = event
                        .payload
                        .get("merged")
                        .and_then(Value::as_bool)
                        .unwrap_or(false);
                    if !merged {
                        Some(router.workflow.blocked.as_str())
                    } else {
                        let head = payload_text(event, "head_sha").unwrap_or_default();
                        let event_approved = event
                            .payload
                            .get("approved")
                            .and_then(Value::as_bool)
                            .unwrap_or(false);
                        if event_approved
                            || approvals
                                .get(&issue.identifier)
                                .is_some_and(|approved| approved == head)
                        {
                            router.workflow.terminal.first().map(String::as_str)
                        } else {
                            Some(router.workflow.review.as_str())
                        }
                    }
                }
                _ => None,
            },
            // Conversation events are the durable source of an agent run's
            // lifecycle.  They must participate in the projection: otherwise
            // a prior `router.attempt started` can incorrectly overwrite a
            // newer agent turn that has already been handed to Review.
            EventType::RouterConversation => match payload_text(event, "lifecycle") {
                Some("in_progress") => Some(router.workflow.active.as_str()),
                Some("blocked") => Some(router.workflow.blocked.as_str()),
                Some("review") => Some(router.workflow.review.as_str()),
                _ => None,
            },
            _ => None,
        };
        if let Some(status) = status {
            issue.status = status.to_string();
        }
    }
    for event in router_events {
        if !matches!(&event.event_type, EventType::RouterResult) {
            continue;
        }
        let Some(updates) = event.payload.get("issue_updates").and_then(Value::as_array) else {
            continue;
        };
        for update in updates {
            let (Some(issue_id), Some(status)) = (
                update.get("issue_id").and_then(Value::as_str),
                update.get("status").and_then(Value::as_str),
            ) else {
                continue;
            };
            let Some(issue) = issues.iter_mut().find(|issue| issue.identifier == issue_id) else {
                continue;
            };
            if router.workflow.terminal.contains(&issue.status) {
                continue;
            }
            let later_board_transition = issue_events
                .iter()
                .filter(|candidate| candidate.issue_id == issue.identifier)
                .filter(|candidate| matches!(&candidate.event_type, EventType::StateTransition))
                .max_by(|left, right| {
                    left.occurred_at
                        .cmp(&right.occurred_at)
                        .then_with(|| left.event_id.cmp(&right.event_id))
                });
            if later_board_transition
                .is_none_or(|transition| transition.occurred_at < event.occurred_at)
            {
                issue.status = status.to_string();
            }
        }
    }
}

/// Return the effective issue status after reducing router events and shared
/// router-state publication, without mutating the caller's checkout.
pub fn effective_issue_router_status(root: &Path, issue_id: &str) -> Result<String, KanbusError> {
    let configuration =
        crate::config_loader::load_project_configuration(&get_configuration_path(root)?)?;
    let router = configuration
        .router
        .as_ref()
        .ok_or_else(|| KanbusError::Configuration("issue router is not configured".to_string()))?;
    let project_dir = load_project_directory(root)?;
    let mut issues = load_project_issues(&project_dir)?;
    let issue_events = issue_event_history(&project_dir)?;
    let router_events = load_router_events(&project_dir)?;
    apply_router_status_overlay(&mut issues, &router_events, router, &issue_events);
    issues
        .into_iter()
        .find(|issue| issue.identifier == issue_id)
        .map(|issue| issue.status)
        .ok_or_else(|| KanbusError::IssueOperation(format!("issue {issue_id} not found")))
}

fn issue_route_labels(issue: &IssueData) -> Vec<(&'static str, String)> {
    issue
        .labels
        .iter()
        .filter_map(|label| {
            ROUTER_ROUTE_LABEL_PREFIXES.iter().find_map(|prefix| {
                label
                    .strip_prefix(prefix)
                    .map(|name| (*prefix, name.to_string()))
            })
        })
        .collect()
}

fn has_route_marker(issue: &IssueData) -> bool {
    issue.labels.iter().any(|label| {
        ROUTER_ROUTE_LABEL_PREFIXES
            .iter()
            .any(|prefix| label.starts_with(prefix))
    })
}

fn configured_provider<'a>(
    configuration: &'a IssueRouterConfiguration,
    profile: &str,
) -> Option<&'a IssueRouterProviderConfiguration> {
    configuration.providers.get(profile)
}

fn route_for_issue(
    issue: &IssueData,
    configuration: &IssueRouterConfiguration,
    state: &RouterEventState,
    provider_wip: &BTreeMap<String, usize>,
    _class_wip: &BTreeMap<String, usize>,
) -> Result<IssueRouterRoute, String> {
    let labels = issue_route_labels(issue);
    if labels.len() != 1 {
        return Err("invalid_route".to_string());
    }
    let (kind, name) = &labels[0];
    let previous_profile = state.provider_profiles.get(&issue.identifier);
    if *kind == "agent-provider:" {
        if configured_provider(configuration, name).is_none() {
            return Err("invalid_route".to_string());
        }
        return Ok(IssueRouterRoute {
            kind: "provider".to_string(),
            name: name.clone(),
            provider_profile: name.clone(),
        });
    }
    let Some(class) = configuration.classes.get(name) else {
        return Err("invalid_route".to_string());
    };
    select_class_profile(name, class, configuration, previous_profile, provider_wip)
}

fn select_class_profile(
    class_name: &str,
    class: &crate::models::IssueRouterClassConfiguration,
    configuration: &IssueRouterConfiguration,
    previous_profile: Option<&String>,
    provider_wip: &BTreeMap<String, usize>,
) -> Result<IssueRouterRoute, String> {
    if let Some(profile) = previous_profile {
        if class.providers.contains(profile)
            && configuration
                .limits
                .provider_wip
                .get(profile)
                .is_none_or(|limit| provider_wip.get(profile).copied().unwrap_or_default() < *limit)
        {
            return Ok(IssueRouterRoute {
                kind: "class".to_string(),
                name: class_name.to_string(),
                provider_profile: profile.clone(),
            });
        }
    }
    for profile in &class.providers {
        if configured_provider(configuration, profile).is_none() {
            return Err("invalid_route".to_string());
        }
        if configuration
            .limits
            .provider_wip
            .get(profile)
            .is_none_or(|limit| provider_wip.get(profile).copied().unwrap_or_default() < *limit)
        {
            return Ok(IssueRouterRoute {
                kind: "class".to_string(),
                name: class_name.to_string(),
                provider_profile: profile.clone(),
            });
        }
    }
    class
        .providers
        .first()
        .map(|profile| IssueRouterRoute {
            kind: "class".to_string(),
            name: class_name.to_string(),
            provider_profile: profile.clone(),
        })
        .ok_or_else(|| "invalid_route".to_string())
}

fn is_pending_status(issue: &IssueData, configuration: &IssueRouterConfiguration) -> bool {
    issue.status == configuration.workflow.pending
}

fn is_active_status(issue: &IssueData, configuration: &IssueRouterConfiguration) -> bool {
    issue.status == configuration.workflow.active
}

fn is_wip_status(issue: &IssueData, configuration: &IssueRouterConfiguration) -> bool {
    issue.status == configuration.workflow.active
        || issue.status == configuration.workflow.review
        || issue.status == configuration.workflow.blocked
}

fn is_terminal_status(issue: &IssueData, configuration: &IssueRouterConfiguration) -> bool {
    configuration.workflow.terminal.contains(&issue.status)
}

fn package_issue_ids(root: &IssueData, issues: &[IssueData]) -> Vec<String> {
    let by_id = issues
        .iter()
        .map(|issue| (issue.identifier.as_str(), issue))
        .collect::<HashMap<_, _>>();
    let mut members = Vec::new();
    for issue in issues {
        if issue.identifier == root.identifier {
            members.push(issue.identifier.clone());
            continue;
        }
        if has_route_marker(issue) {
            continue;
        }
        let mut parent = issue.parent.as_deref();
        let mut belongs = false;
        let mut nested_route = false;
        while let Some(parent_id) = parent {
            if parent_id == root.identifier {
                belongs = true;
                break;
            }
            let Some(parent_issue) = by_id.get(parent_id) else {
                break;
            };
            if has_route_marker(parent_issue) {
                nested_route = true;
                break;
            }
            parent = parent_issue.parent.as_deref();
        }
        if belongs && !nested_route {
            members.push(issue.identifier.clone());
        }
    }
    members.sort();
    members
}

fn pending_since(issue: &IssueData, events: &[EventRecord], pending_status: &str) -> DateTime<Utc> {
    events
        .iter()
        .filter(|event| event.issue_id == issue.identifier)
        .filter(|event| matches!(&event.event_type, EventType::StateTransition))
        .filter(|event| payload_text(event, "to_status") == Some(pending_status))
        .filter_map(|event| parse_timestamp(&event.occurred_at))
        .next_back()
        .unwrap_or(issue.created_at)
}

fn issue_event_history(project_dir: &Path) -> Result<Vec<EventRecord>, KanbusError> {
    let events_dir = events_dir_for_project(project_dir);
    let mut paths = if events_dir.exists() {
        fs::read_dir(events_dir)
            .map_err(|error| KanbusError::Io(error.to_string()))?
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .filter(|path| {
                path.extension().and_then(|extension| extension.to_str()) == Some("json")
            })
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };
    paths.sort();
    let mut events = Vec::new();
    for path in paths {
        let bytes = fs::read(path).map_err(|error| KanbusError::Io(error.to_string()))?;
        if let Ok(event) = serde_json::from_slice::<EventRecord>(&bytes) {
            events.push(event);
        }
    }
    let root = repository_root(project_dir)?;
    for event in read_shared_router_events(&root)? {
        if !events
            .iter()
            .any(|existing| existing.event_id == event.event_id)
        {
            events.push(event);
        }
    }
    events.sort_by(|left, right| {
        left.occurred_at
            .cmp(&right.occurred_at)
            .then_with(|| left.event_id.cmp(&right.event_id))
    });
    Ok(events)
}

fn has_live_router_claim(events: &[EventRecord], issue_id: &str, now: DateTime<Utc>) -> bool {
    let resource = format!("router:issue:{issue_id}");
    let resource_events = events
        .iter()
        .filter(|event| event.issue_id == resource)
        .filter(|event| {
            matches!(
                &event.event_type,
                EventType::CoordinationClaim
                    | EventType::CoordinationRenew
                    | EventType::CoordinationRelease
            )
        })
        .cloned()
        .collect::<Vec<_>>();
    crate::coordination::reduce_coordination_events(&resource_events, now).is_active()
}

fn load_project_issues(project_dir: &Path) -> Result<Vec<IssueData>, KanbusError> {
    let issues_dir = project_dir.join("issues");
    let mut identifiers = list_issue_identifiers(&issues_dir)?
        .into_iter()
        .collect::<Vec<_>>();
    identifiers.sort();
    identifiers
        .iter()
        .map(|identifier| read_issue_from_file(&issues_dir.join(format!("{identifier}.json"))))
        .collect()
}

fn policy_rejects(
    issue: &IssueData,
    all_issues: &[IssueData],
    configuration: &ProjectConfiguration,
    policies: &[(String, gherkin::Feature)],
) -> bool {
    let context = PolicyContext {
        current_issue: Some(issue.clone()),
        proposed_issue: issue.clone(),
        transition: None,
        operation: PolicyOperation::Ready,
        project_configuration: configuration.clone(),
        all_issues: all_issues.to_vec(),
    };
    evaluate_policies(&context, policies).is_err()
}

fn issue_dependency_blocked(
    issue: &IssueData,
    issues_by_id: &HashMap<&str, &IssueData>,
    configuration: &IssueRouterConfiguration,
) -> bool {
    issue.dependencies.iter().any(|dependency| {
        if dependency.dependency_type != "blocked-by" {
            return false;
        }
        issues_by_id
            .get(dependency.target.as_str())
            .is_none_or(|dependency_issue| !is_terminal_status(dependency_issue, configuration))
    })
}

fn format_timestamp(timestamp: DateTime<Utc>) -> String {
    timestamp.to_rfc3339_opts(SecondsFormat::Secs, true)
}

fn candidate_status_priority(
    issue: &IssueData,
    configuration: &IssueRouterConfiguration,
) -> Option<u8> {
    if is_active_status(issue, configuration) {
        Some(0)
    } else if is_pending_status(issue, configuration) {
        Some(2)
    } else {
        None
    }
}

/// Validate typed Issue Router configuration and return deterministic errors.
///
/// # Arguments
/// * `configuration` - Loaded project configuration.
///
/// # Returns
/// Validation errors prefixed with their router configuration path.
pub fn validate_issue_router_configuration(configuration: &ProjectConfiguration) -> Vec<String> {
    let Some(router) = configuration.router.as_ref() else {
        return Vec::new();
    };
    let mut errors = Vec::new();
    for (role, status) in [
        ("pending", router.workflow.pending.as_str()),
        ("active", router.workflow.active.as_str()),
        ("review", router.workflow.review.as_str()),
        ("blocked", router.workflow.blocked.as_str()),
    ] {
        if !configuration
            .statuses
            .iter()
            .any(|entry| entry.key == status)
        {
            errors.push(format!(
                "router.workflow.{role} references undefined status \"{status}\""
            ));
        }
    }
    for status in &router.workflow.terminal {
        if !configuration
            .statuses
            .iter()
            .any(|entry| entry.key == *status)
        {
            errors.push(format!(
                "router.workflow.terminal references undefined status \"{status}\""
            ));
        }
    }
    let mut role_names = BTreeSet::new();
    for status in [
        &router.workflow.pending,
        &router.workflow.active,
        &router.workflow.review,
        &router.workflow.blocked,
    ]
    .into_iter()
    .chain(router.workflow.terminal.iter())
    {
        if !role_names.insert(status) {
            errors.push("router.workflow roles must use distinct statuses".to_string());
            break;
        }
    }
    if router.workflow.terminal.is_empty() {
        errors.push("router.workflow.terminal must be a nonempty list".to_string());
    }
    if router.limits.project_wip == 0 {
        errors.push("router.limits.project_wip must be a positive integer".to_string());
    }
    if router.limits.review_wip == 0 {
        errors.push("router.limits.review_wip must be a positive integer".to_string());
    }
    if router.limits.review_wip > router.limits.project_wip {
        errors.push("router.limits.review_wip must not exceed project_wip".to_string());
    }
    for (name, limit) in &router.limits.class_wip {
        if *limit == 0 {
            errors.push(format!(
                "router.limits.class_wip.{name} must be a positive integer"
            ));
        }
        if !router.classes.contains_key(name) {
            errors.push(format!(
                "router.limits.class_wip.{name} references undefined class"
            ));
        }
    }
    for (name, limit) in &router.limits.provider_wip {
        if *limit == 0 {
            errors.push(format!(
                "router.limits.provider_wip.{name} must be a positive integer"
            ));
        }
        if !router.providers.contains_key(name) {
            errors.push(format!(
                "router.limits.provider_wip.{name} references undefined provider profile"
            ));
        }
    }
    if router.providers.is_empty() {
        errors.push("router.providers must not be empty".to_string());
    }
    for (profile, provider) in &router.providers {
        if provider.adapter != "codex" {
            errors.push(format!("router.providers.{profile}.adapter must be codex"));
        }
        if provider.command.trim().is_empty() {
            errors.push(format!(
                "router.providers.{profile}.command must not be empty"
            ));
        }
    }
    for (class_name, class) in &router.classes {
        if class.providers.is_empty() {
            errors.push(format!(
                "router.classes.{class_name}.providers must be a nonempty list"
            ));
        }
        for profile in &class.providers {
            if !router.providers.contains_key(profile) {
                errors.push(format!(
                    "router.classes.{class_name}.providers references undefined provider profile \"{profile}\""
                ));
                break;
            }
        }
    }
    if router.retries.max_attempts == 0 {
        errors.push("router.retries.max_attempts must be a positive integer".to_string());
    }
    if crate::coordination::parse_duration_seconds(&router.watch_interval).is_err() {
        errors.push("router.watch_interval must be a positive duration".to_string());
    }
    if let Some(forge) = router.forge.as_ref() {
        if forge.provider != "github" {
            errors.push("router.forge.provider must be github".to_string());
        }
        let parts = forge.repository.split('/').collect::<Vec<_>>();
        if parts.len() != 2 || parts.iter().any(|part| part.trim().is_empty()) {
            errors.push("router.forge.repository must use owner/repository format".to_string());
        }
        if forge.base_branch.trim().is_empty() {
            errors.push("router.forge.base_branch must not be empty".to_string());
        }
        if forge.token_env.is_empty()
            || !forge
                .token_env
                .chars()
                .enumerate()
                .all(|(index, character)| {
                    if index == 0 {
                        character == '_' || character.is_ascii_alphabetic()
                    } else {
                        character == '_' || character.is_ascii_alphanumeric()
                    }
                })
        {
            errors.push(
                "router.forge.token_env must be a valid environment variable name".to_string(),
            );
        }
        if !reqwest::Url::parse(&forge.api_url)
            .is_ok_and(|url| matches!(url.scheme(), "http" | "https") && url.host_str().is_some())
        {
            errors.push("router.forge.api_url must be an absolute http(s) URL".to_string());
        }
    }
    errors
}

/// Initialize the configured forge client with only its selected credential
/// variable. This also supports deterministic CLI integration tests without
/// mutating the process environment.
pub fn validate_router_forge_credentials(
    root: &Path,
    environment: &BTreeMap<String, String>,
) -> Result<String, KanbusError> {
    let (_, router, _) = load_issue_router(root)?;
    let forge = router
        .forge
        .as_ref()
        .ok_or_else(|| KanbusError::Configuration("router.forge is required".to_string()))?;
    let token = environment
        .get(&forge.token_env)
        .cloned()
        .or_else(|| std::env::var(&forge.token_env).ok())
        .ok_or_else(|| {
            KanbusError::IssueOperation(format!(
                "GitHub token environment variable {} is not set",
                forge.token_env
            ))
        })?;
    // reqwest's blocking client owns a Tokio runtime. Build and drop it on a
    // dedicated thread because this API is also called by async test runners.
    let token_env = forge.token_env.clone();
    let selected = std::thread::spawn(move || {
        GitHubForge::from_router_with_token(&router, token).map(|_| token_env)
    })
    .join()
    .map_err(|_| {
        KanbusError::IssueOperation("forge client initialization panicked".to_string())
    })??;
    Ok(selected)
}

/// Apply one normalized GitHub check-run observation to its current router PR.
///
/// The event is accepted only when its repository, PR number, head SHA, and
/// router ownership match the immutable event history. Failed/non-successful
/// checks requeue the package through the canonical issue mutation API.
pub fn record_router_check_run_event(
    root: &Path,
    event_id: &str,
    number: u64,
    head_sha: &str,
    conclusion: &str,
) -> Result<bool, KanbusError> {
    if event_id.is_empty()
        || number == 0
        || head_sha.is_empty()
        || !matches!(
            conclusion,
            "success" | "failure" | "cancelled" | "timed_out" | "action_required"
        )
    {
        return Err(KanbusError::IssueOperation(
            "invalid GitHub check-run event".to_string(),
        ));
    }
    let (_, router, project_dir) = load_issue_router(root)?;
    let forge = router
        .forge
        .as_ref()
        .ok_or_else(|| KanbusError::IssueOperation("router.forge is required".to_string()))?;
    let events = load_router_events(&project_dir)?;
    if events.iter().any(|event| {
        event.issue_id.starts_with("router:")
            && matches!(&event.event_type, EventType::RouterForge)
            && payload_text(event, "forge_event_id") == Some(event_id)
    }) {
        return Ok(false);
    }
    let owner = events.iter().rev().find(|event| {
        event.issue_id.starts_with("router:")
            && matches!(&event.event_type, EventType::RouterForge)
            && matches!(
                payload_text(event, "action"),
                Some("opened" | "synchronize" | "requested_changes" | "approved")
            )
            && event.payload.get("number").and_then(Value::as_u64) == Some(number)
            && payload_text(event, "head_sha") == Some(head_sha)
            && payload_text(event, "repository").is_none_or(|repo| repo == forge.repository)
    });
    let Some(owner) = owner else {
        return Err(KanbusError::IssueOperation(format!(
            "GitHub pull request {number} is not owned by the Issue Router"
        )));
    };
    let issue_id = owner.issue_id.trim_start_matches("router:");
    let failed = conclusion != "success";
    append_router_event(
        &project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterForge,
        json!({
            "action": if failed { "check_run_failure" } else { "check_run_success" },
            "repository": forge.repository,
            "number": number,
            "head_sha": head_sha,
            "conclusion": conclusion,
            "forge_event_id": event_id,
        }),
    )?;
    Ok(true)
}

/// Apply one normalized GitHub pull-request observation to its routed package.
pub fn record_router_pull_request_event(root: &Path, payload: &Value) -> Result<bool, KanbusError> {
    let schema_version = payload
        .get("schema_version")
        .and_then(Value::as_u64)
        .unwrap_or_default();
    let event_id = payload
        .get("event_id")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let kind = payload
        .get("kind")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let action = payload
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let repository = payload
        .get("repository")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let number = payload
        .get("number")
        .and_then(Value::as_u64)
        .unwrap_or_default();
    let head_sha = payload
        .get("head_sha")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let merged = payload
        .get("merged")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if schema_version != 1
        || payload.get("merged").and_then(Value::as_bool).is_none()
        || event_id.is_empty()
        || kind != "pull_request"
        || number == 0
        || head_sha.is_empty()
        || !matches!(
            action,
            "opened" | "synchronize" | "requested_changes" | "approved" | "closed"
        )
    {
        return Err(KanbusError::IssueOperation(
            "invalid GitHub pull request event".to_string(),
        ));
    }
    let (_, router, project_dir) = load_issue_router(root)?;
    let forge = router
        .forge
        .as_ref()
        .ok_or_else(|| KanbusError::IssueOperation("router.forge is required".to_string()))?;
    if repository != forge.repository {
        return Err(KanbusError::IssueOperation(format!(
            "GitHub event repository \"{repository}\" does not match configured repository \"{}\"",
            forge.repository
        )));
    }
    let events = load_router_events(&project_dir)?;
    if events.iter().any(|event| {
        event.issue_id.starts_with("router:")
            && matches!(&event.event_type, EventType::RouterForge)
            && payload_text(event, "forge_event_id") == Some(event_id)
    }) {
        return Ok(false);
    }
    let owner = events.iter().rev().find(|event| {
        event.issue_id.starts_with("router:")
            && matches!(&event.event_type, EventType::RouterForge)
            && matches!(
                payload_text(event, "action"),
                Some("opened" | "synchronize" | "requested_changes" | "approved" | "closed")
            )
            && event.payload.get("number").and_then(Value::as_u64) == Some(number)
            && payload_text(event, "repository").is_none_or(|repo| repo == repository)
    });
    let Some(owner) = owner else {
        return Err(KanbusError::IssueOperation(format!(
            "GitHub pull request {number} is not owned by the Issue Router"
        )));
    };
    let current_head = payload_text(owner, "head_sha").unwrap_or_default();
    if action != "synchronize" && current_head != head_sha {
        return Err(KanbusError::IssueOperation(format!(
            "GitHub pull request {number} head does not match the current router publication"
        )));
    }
    let issue_id = owner.issue_id.trim_start_matches("router:").to_string();
    let approved = events.iter().any(|event| {
        event.issue_id == format!("router:{issue_id}")
            && matches!(&event.event_type, EventType::RouterForge)
            && payload_text(event, "action") == Some("approved")
            && payload_text(event, "head_sha") == Some(head_sha)
    });
    if action == "closed" && merged && !approved {
        append_router_event(
            &project_dir,
            &format!("router:{issue_id}"),
            EventType::RouterForge,
            json!({
                "action": "merged_unapproved",
                "number": number,
                "head_sha": head_sha,
                "diagnostic": "merged pull request has no approval for its current head",
                "forge_event_id": event_id,
            }),
        )?;
    }
    append_router_event(
        &project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterForge,
        json!({
            "action": action,
            "repository": repository,
            "number": number,
            "head_sha": head_sha,
            "merged": merged,
            "approved": approved,
            "forge_event_id": event_id,
        }),
    )?;
    Ok(true)
}

/// Build a stable router plan from the configured board and immutable events.
///
/// # Arguments
/// * `root` - Repository root containing the project configuration.
///
/// # Errors
/// Returns `KanbusError` when configuration or project state cannot be loaded.
pub fn build_issue_router_plan(root: &Path) -> Result<IssueRouterPlan, KanbusError> {
    let configuration_path = get_configuration_path(root)?;
    let project_configuration =
        crate::config_loader::load_project_configuration(&configuration_path)?;
    let router = project_configuration
        .router
        .as_ref()
        .ok_or_else(|| KanbusError::Configuration("issue router is not configured".to_string()))?;
    if !router.enabled {
        return Err(KanbusError::Configuration(
            "issue router is disabled".to_string(),
        ));
    }
    let project_dir = load_project_directory(root)?;
    let mut issues = load_project_issues(&project_dir)?;
    let events = issue_event_history(&project_dir)?;
    let router_events = load_router_events(&project_dir)?;
    apply_router_status_overlay(&mut issues, &router_events, router, &events);
    let state = reduce_router_events(&router_events);
    let policies = load_policies(&project_dir.join("policies"))?;
    let issues_by_id = issues
        .iter()
        .map(|issue| (issue.identifier.as_str(), issue))
        .collect::<HashMap<_, _>>();
    let mut routed_package_wip = Vec::new();
    for issue in &issues {
        if !is_wip_status(issue, router) || !has_route_marker(issue) {
            continue;
        }
        if let Ok(route) =
            route_for_issue(issue, router, &state, &BTreeMap::new(), &BTreeMap::new())
        {
            routed_package_wip.push((issue.identifier.clone(), route));
        }
    }
    let all_project_wip = routed_package_wip.len();
    let all_project_review = routed_package_wip
        .iter()
        .filter(|(issue_id, _)| {
            issues
                .iter()
                .find(|issue| issue.identifier == *issue_id)
                .is_some_and(|issue| issue.status == router.workflow.review)
                && has_preserved_review_conversation(&router_events, issue_id)
        })
        .count();
    let mut class_wip = BTreeMap::<String, usize>::new();
    let mut provider_wip = BTreeMap::<String, usize>::new();
    for (issue_id, route) in &routed_package_wip {
        if route.kind == "class" {
            *class_wip.entry(route.name.clone()).or_default() += 1;
        }
        let assigned_profile = state
            .provider_profiles
            .get(issue_id)
            .unwrap_or(&route.provider_profile);
        *provider_wip.entry(assigned_profile.clone()).or_default() += 1;
    }

    let mut candidates = Vec::new();
    let planning_now = router_now();
    for issue in &issues {
        let Some(priority) = candidate_status_priority(issue, router) else {
            continue;
        };
        // A live durable claim means another worker owns this package. It is
        // intentionally omitted from eligible/deferred output until release
        // or expiry; stale active work remains recoverable once ownership ends.
        if has_live_router_claim(&events, &issue.identifier, planning_now) {
            continue;
        }
        let has_parent_route = issue.parent.as_deref().is_some_and(|parent_id| {
            let mut current = Some(parent_id);
            while let Some(identifier) = current {
                let Some(parent) = issues_by_id.get(identifier) else {
                    return false;
                };
                if has_route_marker(parent) {
                    return true;
                }
                current = parent.parent.as_deref();
            }
            false
        });
        if has_parent_route && !has_route_marker(issue) {
            continue;
        }
        let package_ids = package_issue_ids(issue, &issues);
        let pending_since = pending_since(issue, &events, &router.workflow.pending);
        let attempt = state.attempts.get(&issue.identifier).copied().unwrap_or(1);
        candidates.push(Candidate {
            issue: issue.clone(),
            route: None,
            package_issue_ids: package_ids,
            pending_since,
            attempt,
            priority: if state.requested_changes.contains(&issue.identifier) {
                1
            } else {
                priority
            },
        });
    }
    candidates.sort_by(|left, right| {
        left.priority
            .cmp(&right.priority)
            .then_with(|| left.pending_since.cmp(&right.pending_since))
            .then_with(|| left.issue.created_at.cmp(&right.issue.created_at))
            .then_with(|| left.issue.identifier.cmp(&right.issue.identifier))
    });

    let now = Utc::now();
    let mut eligible = Vec::new();
    let mut deferred = Vec::new();
    for mut candidate in candidates {
        let mut reason = if state.paused {
            Some("paused".to_string())
        } else {
            None
        };
        if reason.is_none() {
            match route_for_issue(&candidate.issue, router, &state, &provider_wip, &class_wip) {
                Ok(route) => candidate.route = Some(route),
                Err(route_reason) => reason = Some(route_reason),
            }
        }
        if reason.is_none() {
            let route = candidate.route.as_ref().expect("route assigned");
            if route_is_held(route, &state) {
                reason = Some("held".to_string());
            }
        }
        if reason.is_none() && issue_dependency_blocked(&candidate.issue, &issues_by_id, router) {
            reason = Some("dependency_blocked".to_string());
        }
        if reason.is_none()
            && policy_rejects(&candidate.issue, &issues, &project_configuration, &policies)
        {
            reason = Some("policy_rejected".to_string());
        }
        if reason.is_none()
            && state
                .retry_at
                .get(&candidate.issue.identifier)
                .is_some_and(|retry_at| *retry_at > now)
        {
            reason = Some("retry_backoff".to_string());
        }
        let pending = is_pending_status(&candidate.issue, router);
        if reason.is_none() && pending && all_project_wip >= router.limits.project_wip {
            reason = Some("project_wip_limit".to_string());
        }
        if reason.is_none() && pending && all_project_review >= router.limits.review_wip {
            reason = Some("review_wip_limit".to_string());
        }
        if reason.is_none() && pending {
            if let Some(route) = candidate.route.as_ref() {
                if route.kind == "class"
                    && router
                        .limits
                        .class_wip
                        .get(&route.name)
                        .is_some_and(|limit| {
                            class_wip.get(&route.name).copied().unwrap_or_default() >= *limit
                        })
                {
                    reason = Some("class_wip_limit".to_string());
                }
            }
        }
        if reason.is_none() && pending {
            if let Some(route) = candidate.route.as_ref() {
                if router
                    .limits
                    .provider_wip
                    .get(&route.provider_profile)
                    .is_some_and(|limit| {
                        provider_wip
                            .get(&route.provider_profile)
                            .copied()
                            .unwrap_or_default()
                            >= *limit
                    })
                {
                    reason = Some("provider_wip_limit".to_string());
                }
            }
        }
        if let Some(reason) = reason {
            deferred.push(IssueRouterDeferredPackage {
                issue_id: candidate.issue.identifier,
                reason,
            });
            continue;
        }
        let route = candidate.route.take().expect("route assigned");
        eligible.push(IssueRouterEligiblePackage {
            issue_id: candidate.issue.identifier,
            route,
            package_issue_ids: candidate.package_issue_ids,
            pending_since: format_timestamp(candidate.pending_since),
            attempt: candidate.attempt,
        });
    }
    Ok(IssueRouterPlan {
        version: 1,
        enabled: router.enabled,
        paused: state.paused,
        eligible,
        deferred,
    })
}

/// Serialize a plan as deterministic JSON or human-readable text.
///
/// # Arguments
/// * `plan` - Plan to display.
/// * `json` - Whether to use the stable JSON contract.
///
/// # Returns
/// A trailing-newline output string.
pub fn format_issue_router_plan(plan: &IssueRouterPlan, json: bool) -> String {
    if json {
        return format!(
            "{}\n",
            serde_json::to_string_pretty(plan).expect("router plan serialization")
        );
    }
    let mut output = String::from("Eligible:\n");
    if plan.eligible.is_empty() {
        output.push_str("  none\n");
    } else {
        for package in &plan.eligible {
            output.push_str(&format!(
                "  {} route={}:{} provider={} package={} pending_since={} attempt={}\n",
                package.issue_id,
                package.route.kind,
                package.route.name,
                package.route.provider_profile,
                package.package_issue_ids.join(","),
                package.pending_since,
                package.attempt
            ));
        }
    }
    output.push_str("Deferred:\n");
    if plan.deferred.is_empty() {
        output.push_str("  none\n");
    } else {
        for package in &plan.deferred {
            output.push_str(&format!(
                "  {} reason={}\n",
                package.issue_id, package.reason
            ));
        }
    }
    output.push_str(&format!(
        "Summary: eligible={} deferred={} paused={}\n",
        plan.eligible.len(),
        plan.deferred.len(),
        plan.paused
    ));
    output
}

/// Return the configured router and project directory, with user-facing failures.
///
/// # Arguments
/// * `root` - Repository root containing `.kanbus.yml`.
///
/// # Errors
/// Returns configuration or project-loading errors.
pub fn load_issue_router(
    root: &Path,
) -> Result<
    (
        ProjectConfiguration,
        IssueRouterConfiguration,
        std::path::PathBuf,
    ),
    KanbusError,
> {
    let configuration_path = get_configuration_path(root)?;
    let configuration = crate::config_loader::load_project_configuration(&configuration_path)?;
    let router = configuration
        .router
        .clone()
        .ok_or_else(|| KanbusError::Configuration("issue router is not configured".to_string()))?;
    if !router.enabled {
        return Err(KanbusError::Configuration(
            "issue router is disabled".to_string(),
        ));
    }
    let project_dir = load_project_directory(root)?;
    Ok((configuration, router, project_dir))
}

/// Execute the configured adapter for an explicitly identified package claim.
///
/// This narrow entry point is shared by the router itself and contract fixtures
/// that need to inspect the exact adapter request without creating a scheduler
/// claim through the public CLI. It still uses the production worktree, prompt,
/// child-process, and result-parsing path.
///
/// # Arguments
/// * `root` - Repository root containing the Kanbus configuration.
/// * `issue_id` - Routed package root.
/// * `package_issue_ids` - Explicit, already-resolved package membership.
/// * `provider_profile` - Configured provider profile to invoke.
/// * `claim_id` - Claim identifier included in the adapter prompt.
/// * `revision` - Logical revision included in the adapter prompt.
///
/// # Errors
/// Returns configuration, worktree, process, or adapter-result failures.
pub fn execute_issue_router_adapter_for_claim(
    root: &Path,
    issue_id: &str,
    package_issue_ids: &[String],
    provider_profile: &str,
    claim_id: &str,
    revision: u64,
) -> Result<(), KanbusError> {
    let (configuration, router, project_dir) = load_issue_router(root)?;
    let profile = router.providers.get(provider_profile).ok_or_else(|| {
        KanbusError::Configuration(format!(
            "router provider profile {provider_profile:?} is not configured"
        ))
    })?;
    let checkpoint = reduce_router_events(&load_router_events(&project_dir)?)
        .checkpoints
        .get(issue_id)
        .cloned();
    let resource = format!("router:issue:{issue_id}");
    let claim = RouterClaim {
        issue_id: issue_id.to_string(),
        claim_id: claim_id.to_string(),
        revision,
        resource: resource.clone(),
        hard: false,
        owner: crate::users::get_current_user(),
        resources: vec![resource],
    };
    let result = execute_router_adapter(
        root,
        &project_dir,
        &configuration,
        profile,
        issue_id,
        package_issue_ids,
        &claim,
        checkpoint,
        None,
    )
    .map(|_| ());
    let cleanup = clear_active_router_state(root);
    match (result, cleanup) {
        (Ok(()), Ok(())) => Ok(()),
        (Err(error), Ok(())) | (Ok(()), Err(error)) => Err(error),
        (Err(error), Err(cleanup_error)) => Err(KanbusError::IssueOperation(format!(
            "{error}; additionally could not clear adapter state: {cleanup_error}"
        ))),
    }
}

/// Validate that a package claim and logical revision are still current.
pub fn validate_issue_router_claim(
    root: &Path,
    issue_id: &str,
    claim_id: &str,
    revision: u64,
) -> Result<(), KanbusError> {
    let (configuration, _, project_dir) = load_issue_router(root)?;
    let claim = RouterClaim {
        issue_id: issue_id.to_string(),
        claim_id: claim_id.to_string(),
        revision,
        resource: format!("router:issue:{issue_id}"),
        hard: false,
        owner: crate::users::get_current_user(),
        resources: Vec::new(),
    };
    let events = load_router_events(&project_dir)?;
    let current = latest_started_router_event(&events, issue_id);
    let Some(current) = current else {
        return Err(stale_claim_error(&claim, None, None));
    };
    let current_claim = payload_text(current, "claim_id");
    let current_revision = current.payload.get("revision").and_then(Value::as_u64);
    if current_claim != Some(claim_id) {
        return Err(stale_claim_error(&claim, current_claim, current_revision));
    }
    if current_revision != Some(revision) {
        return Err(KanbusError::IssueOperation(format!(
            "stale router revision {revision} for package {issue_id}; current revision is {}",
            current_revision.unwrap_or_default()
        )));
    }
    assert_current_router_claim(&project_dir, &configuration, &claim)
}

/// Validate and persist a completed, blocked, or retryable package result.
///
/// The function is used by the scheduler and by callers that already have an
/// adapter result. All claim and package checks happen before any checkpoint,
/// artifact, or issue mutation is published.
#[allow(clippy::too_many_arguments)]
pub fn publish_issue_router_result_for_claim(
    root: &Path,
    issue_id: &str,
    package_issue_ids: &[String],
    claim_id: &str,
    revision: u64,
    outcome: &str,
    summary: &str,
    issue_updates: &[(String, String)],
    checkpoint: Option<(&str, u64)>,
    artifacts: &[(String, String)],
) -> Result<(), KanbusError> {
    let (_, router, project_dir) = load_issue_router(root)?;
    validate_issue_router_claim(root, issue_id, claim_id, revision)?;
    if !["completed", "blocked", "retryable_failure"].contains(&outcome) {
        return Err(KanbusError::IssueOperation(format!(
            "invalid Codex router outcome \"{outcome}\""
        )));
    }
    validate_router_issue_updates(&router, issue_id, package_issue_ids, issue_updates)?;
    if let Some((_, checkpoint_revision)) = checkpoint {
        if checkpoint_revision != revision {
            let current = published_revision(
                &project_dir,
                &format!("router:package:{issue_id}:checkpoint"),
            )?
            .unwrap_or(revision);
            return Err(KanbusError::IssueOperation(format!(
                "stale router revision {checkpoint_revision} for package {issue_id}; current revision is {current}"
            )));
        }
    }

    if outcome == "completed" {
        if let Some((reference, checkpoint_revision)) = checkpoint {
            crate::coordination::publish_coordination_result(
                &project_dir,
                &format!("router:package:{issue_id}:checkpoint"),
                checkpoint_revision,
                reference,
            )?;
            append_router_event(
                &project_dir,
                &format!("router:{issue_id}"),
                EventType::RouterAttempt,
                json!({
                    "action":"checkpoint_accepted",
                    "claim_id":claim_id,
                    "revision":revision,
                    "checkpoint_ref":reference,
                    "checkpoint_revision":checkpoint_revision
                }),
            )?;
        }
        for (name, reference) in artifacts {
            crate::coordination::publish_coordination_result(
                &project_dir,
                &format!("router:package:{issue_id}:artifact:{name}"),
                revision,
                reference,
            )?;
        }
    }
    append_router_event(
        &project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterResult,
        json!({
            "outcome":outcome,
            "summary":summary,
            "claim_id":claim_id,
            "revision":revision,
            "checkpoint_ref":checkpoint.map(|(reference, _)| reference),
            "checkpoint_revision":checkpoint.map(|(_, revision)| revision),
            "artifacts":artifacts.iter().map(|(name, reference)| json!({"name":name,"ref":reference})).collect::<Vec<_>>(),
            "issue_updates":issue_updates.iter().map(|(updated_issue_id, status)| json!({"issue_id":updated_issue_id,"status":status})).collect::<Vec<_>>(),
        }),
    )?;
    Ok(())
}

/// Record non-empty structured progress for a current package claim.
/// Empty heartbeats are intentionally ignored and do not renew claim freshness.
pub fn record_issue_router_progress(
    root: &Path,
    issue_id: &str,
    claim_id: &str,
    revision: u64,
    summary: Option<&str>,
) -> Result<(), KanbusError> {
    validate_issue_router_claim(root, issue_id, claim_id, revision)?;
    let Some(summary) = summary.map(str::trim).filter(|summary| !summary.is_empty()) else {
        return Ok(());
    };
    let project_dir = load_project_directory(root)?;
    append_router_event(
        &project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterAttempt,
        json!({"action":"progress","claim_id":claim_id,"revision":revision,"summary":summary}),
    )?;
    Ok(())
}

/// Record an accepted checkpoint for a current package claim.
pub fn accept_issue_router_checkpoint(
    root: &Path,
    issue_id: &str,
    claim_id: &str,
    revision: u64,
    reference: &str,
) -> Result<(), KanbusError> {
    validate_issue_router_claim(root, issue_id, claim_id, revision)?;
    let project_dir = load_project_directory(root)?;
    crate::coordination::publish_coordination_result(
        &project_dir,
        &format!("router:package:{issue_id}:checkpoint"),
        revision,
        reference,
    )?;
    append_router_event(
        &project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterAttempt,
        json!({
            "action":"checkpoint_accepted",
            "claim_id":claim_id,
            "revision":revision,
            "checkpoint_ref":reference,
            "checkpoint_revision":revision
        }),
    )?;
    Ok(())
}

/// Return whole hours since the latest meaningful progress for a claim.
pub fn issue_router_claim_staleness_hours(
    root: &Path,
    issue_id: &str,
    claim_id: &str,
) -> Result<u64, KanbusError> {
    let project_dir = load_project_directory(root)?;
    let events = load_router_events(&project_dir)?;
    let last_progress = events
        .iter()
        .filter(|event| {
            event.issue_id == format!("router:{issue_id}")
                && matches!(&event.event_type, EventType::RouterAttempt)
                && payload_text(event, "claim_id") == Some(claim_id)
                && matches!(
                    payload_text(event, "action"),
                    Some("started" | "progress" | "checkpoint_accepted")
                )
        })
        .filter_map(|event| DateTime::parse_from_rfc3339(&event.occurred_at).ok())
        .max()
        .map(|timestamp| timestamp.with_timezone(&Utc))
        .ok_or_else(|| {
            KanbusError::IssueOperation("router claim has no progress history".into())
        })?;
    Ok(Utc::now()
        .signed_duration_since(last_progress)
        .num_hours()
        .max(0) as u64)
}

fn validate_router_issue_updates(
    router: &IssueRouterConfiguration,
    package_id: &str,
    package_issue_ids: &[String],
    issue_updates: &[(String, String)],
) -> Result<(), KanbusError> {
    for (updated_issue_id, status) in issue_updates {
        if !package_issue_ids.contains(updated_issue_id) {
            return Err(KanbusError::IssueOperation(format!(
                "issue {updated_issue_id} is outside router package {package_id}"
            )));
        }
        if ![
            router.workflow.pending.as_str(),
            router.workflow.active.as_str(),
            router.workflow.review.as_str(),
            router.workflow.blocked.as_str(),
        ]
        .contains(&status.as_str())
        {
            return Err(KanbusError::IssueOperation(format!(
                "router result cannot transition package {updated_issue_id} from {} to {status}",
                router.workflow.active
            )));
        }
    }
    Ok(())
}

fn validate_router_issue_comments(
    package_id: &str,
    package_issue_ids: &[String],
    comments: &[RouterIssueComment],
) -> Result<(), KanbusError> {
    for comment in comments {
        if !package_issue_ids.contains(&comment.issue_id) {
            return Err(KanbusError::IssueOperation(format!(
                "issue {} is outside router package {package_id}",
                comment.issue_id
            )));
        }
        if comment.text.trim().is_empty() {
            return Err(KanbusError::IssueOperation(
                "router issue comment text must not be blank".to_string(),
            ));
        }
    }
    Ok(())
}

fn apply_router_issue_comments(
    root: &Path,
    package_id: &str,
    package_issue_ids: &[String],
    comments: &[RouterIssueComment],
) -> Result<(), KanbusError> {
    validate_router_issue_comments(package_id, package_issue_ids, comments)?;
    for comment in comments {
        crate::issue_comment::add_comment(
            root,
            &comment.issue_id,
            "Kanbus Issue Router",
            &comment.text,
            None,
        )?;
    }
    Ok(())
}

/// Render the mandatory, issue-visible review record for a completed agent turn.
///
/// Agent-provided `issue_comments` are optional supplemental notes. They must
/// never be the only route by which a completed turn becomes visible: a model
/// can legitimately omit them while still returning a useful summary. This
/// record is published after the branch, checkpoint, and draft PR exist and
/// before the router transitions the package to Review.
fn completed_router_review_comment(
    summary: &str,
    pull: &PullRequestInfo,
    checkpoint_ref: &str,
    artifacts: &[RouterArtifact],
) -> String {
    let summary = if summary.trim().is_empty() {
        "The agent completed a turn. Review the preserved branch and draft pull request."
    } else {
        summary.trim()
    };
    let mut comment = format!(
        "## Agent turn complete\n\n{summary}\n\n- Draft PR: {}\n- Branch: `{}`\n- Checkpoint: `{}`",
        pull.url, pull.branch, checkpoint_ref
    );
    if !artifacts.is_empty() {
        comment.push_str("\n- Artifacts:");
        for artifact in artifacts {
            comment.push_str(&format!(
                "\n  - `{}`: `{}`",
                artifact.name, artifact.reference
            ));
        }
    }
    comment
}

/// Return the default provider profile selected by the first configured class.
///
/// # Arguments
/// * `router` - Loaded router configuration.
///
/// # Returns
/// The first provider profile of the first class, when one is configured.
pub fn default_provider_profile(router: &IssueRouterConfiguration) -> Option<&str> {
    router
        .classes
        .values()
        .find_map(|class| class.providers.first().map(String::as_str))
        .or_else(|| router.providers.keys().next().map(String::as_str))
}

/// Wait for a valid peer MQTT coordination notification, if MQTT is configured.
/// Returns immediately on an unavailable broker so watch mode can retain its
/// durable Git polling interval.
pub fn wait_for_issue_router_notification(root: &Path, timeout: Duration) -> bool {
    let Ok((configuration, _, project_dir)) = load_issue_router(root) else {
        return false;
    };
    if !configuration
        .coordination
        .providers
        .iter()
        .any(|provider| provider == "mqtt")
    {
        return false;
    }
    crate::gossip::wait_for_coordination_gossip_notification(
        root,
        &project_dir,
        timeout,
        configuration.overlay.ttl_s,
    )
}

/// Return whether a published revision is behind the current router revision.
///
/// # Arguments
/// * `project_dir` - Project event directory parent.
/// * `resource` - Logical task resource.
/// * `revision` - Logical task revision to validate.
///
/// # Errors
/// Returns an event-store error when publication history cannot be read.
pub fn is_current_router_revision(
    project_dir: &Path,
    resource: &str,
    revision: u64,
) -> Result<bool, KanbusError> {
    Ok(published_revision(project_dir, resource)?.is_none_or(|published| published <= revision))
}

fn router_state_path(root: &Path) -> Result<PathBuf, KanbusError> {
    let output = Command::new("git")
        .args(["rev-parse", "--git-path", "kanbus/router-state.json"])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !output.status.success() {
        return Err(KanbusError::IssueOperation(
            "issue router requires a Git repository".to_string(),
        ));
    }
    let path = PathBuf::from(String::from_utf8_lossy(&output.stdout).trim());
    Ok(if path.is_absolute() {
        path
    } else {
        root.join(path)
    })
}

fn read_local_router_state(root: &Path) -> Result<LocalRouterState, KanbusError> {
    let path = router_state_path(root)?;
    if !path.exists() {
        return Ok(LocalRouterState::default());
    }
    let bytes = fs::read(path).map_err(|error| KanbusError::Io(error.to_string()))?;
    serde_json::from_slice(&bytes).map_err(|error| KanbusError::Io(error.to_string()))
}

fn write_local_router_state(root: &Path, state: &LocalRouterState) -> Result<(), KanbusError> {
    let path = router_state_path(root)?;
    let parent = path
        .parent()
        .ok_or_else(|| KanbusError::Io("router state directory unavailable".to_string()))?;
    fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
    let temp_path = parent.join(format!(".router-state-{}.tmp", Uuid::new_v4()));
    let bytes =
        serde_json::to_vec_pretty(state).map_err(|error| KanbusError::Io(error.to_string()))?;
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp_path)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    file.write_all(&bytes)
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    file.flush()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    fs::rename(&temp_path, &path).map_err(|error| {
        let _ = fs::remove_file(&temp_path);
        KanbusError::Io(error.to_string())
    })
}

fn process_is_running(pid: u32) -> bool {
    Command::new("kill")
        .args(["-0", &pid.to_string()])
        .status()
        .is_ok_and(|status| status.success())
}

fn append_router_event(
    project_dir: &Path,
    issue_id: &str,
    event_type: EventType,
    payload: Value,
) -> Result<EventRecord, KanbusError> {
    let event = EventRecord::new(
        issue_id,
        event_type,
        crate::users::get_current_user(),
        payload,
        crate::event_history::now_timestamp(),
    );
    crate::event_history::write_events_batch(
        &events_dir_for_project(project_dir),
        std::slice::from_ref(&event),
    )?;
    let root = repository_root(project_dir)?;
    publish_shared_router_event(&root, &event)?;
    Ok(event)
}

fn selected_hold_route(
    class: Option<String>,
    provider_profile: Option<String>,
    router: &IssueRouterConfiguration,
) -> Result<String, KanbusError> {
    match (class, provider_profile) {
        (Some(class), None) if router.classes.contains_key(&class) => Ok(format!("class:{class}")),
        (None, Some(profile)) if router.providers.contains_key(&profile) => {
            Ok(format!("provider-profile:{profile}"))
        }
        (Some(class), None) => Err(KanbusError::CommandFailure {
            exit_code: 2,
            message: format!("error: unknown class \"{class}\""),
        }),
        (None, Some(profile)) => Err(KanbusError::CommandFailure {
            exit_code: 2,
            message: format!("error: unknown provider profile \"{profile}\""),
        }),
        _ => Err(KanbusError::CommandFailure {
            exit_code: 2,
            message: "error: select exactly one of --class or --provider-profile".to_string(),
        }),
    }
}

fn route_is_held(route: &IssueRouterRoute, state: &RouterEventState) -> bool {
    state.holds.contains(&format!("class:{}", route.name))
        || state
            .holds
            .contains(&format!("provider-profile:{}", route.provider_profile))
}

fn router_status_output(root: &Path, project_dir: &Path) -> Result<String, KanbusError> {
    let local = read_local_router_state(root)?;
    let state = reduce_router_events(&load_router_events(project_dir)?);
    let running = local.watch_pid.is_some_and(process_is_running);
    let active_runs = usize::from(
        local.active_issue_id.is_some()
            && (running || local.active_child_pid.is_some_and(process_is_running)),
    );
    let held_routes = if state.holds.is_empty() {
        "none".to_string()
    } else {
        state
            .holds
            .iter()
            .map(|route| {
                let (kind, name) = route.split_once(':').unwrap_or(("", route));
                format!("{kind}:{name}")
            })
            .collect::<Vec<_>>()
            .join(",")
    };
    Ok(format!(
        "Issue Router: {}\nScheduling: {}\nActive runs: {active_runs}\nHeld routes: {held_routes}\n",
        if running { "running" } else { "stopped" },
        if state.paused { "paused" } else { "active" }
    ))
}

fn router_control_event(
    project_dir: &Path,
    issue_id: &str,
    action: &str,
    route: Option<&str>,
) -> Result<(), KanbusError> {
    let mut payload = json!({"action": action});
    if let Some(route) = route {
        payload["route"] = json!(route);
    }
    let event_issue_id = if action == "cancel" {
        format!("router:{issue_id}")
    } else {
        issue_id.to_string()
    };
    append_router_event(
        project_dir,
        &event_issue_id,
        EventType::RouterControl,
        payload,
    )?;
    Ok(())
}

fn router_cancel_control_event(
    project_dir: &Path,
    issue_id: &str,
    claim_id: &str,
    revision: u64,
) -> Result<(), KanbusError> {
    append_router_event(
        project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterControl,
        json!({"action": "cancel", "claim_id": claim_id, "revision": revision}),
    )?;
    Ok(())
}

fn cancel_router_package(
    root: &Path,
    router: &IssueRouterConfiguration,
    project_dir: &Path,
    issue_id: &str,
) -> Result<String, KanbusError> {
    let mut local = read_local_router_state(root)?;
    if local.active_issue_id.as_deref() != Some(issue_id) {
        return Err(KanbusError::CommandFailure {
            exit_code: 1,
            message: format!("error: no active router run for package \"{issue_id}\""),
        });
    }
    let claim_id = local
        .active_claim_id
        .clone()
        .ok_or_else(|| KanbusError::CommandFailure {
            exit_code: 1,
            message: format!("error: no active router run for package \"{issue_id}\""),
        })?;
    let events = load_router_events(project_dir)?;
    let started = events
        .iter()
        .rev()
        .find(|event| {
            event.issue_id == format!("router:{issue_id}")
                && matches!(&event.event_type, EventType::RouterAttempt)
                && payload_text(event, "action") == Some("started")
                && payload_text(event, "claim_id") == Some(claim_id.as_str())
        })
        .ok_or_else(|| KanbusError::CommandFailure {
            exit_code: 1,
            message: format!("error: no active router run for package \"{issue_id}\""),
        })?;
    let revision = started
        .payload
        .get("revision")
        .and_then(Value::as_u64)
        .unwrap_or(1);
    let owner = started.actor_id.clone();
    let configuration_path = get_configuration_path(root)?;
    let configuration = crate::config_loader::load_project_configuration(&configuration_path)?;
    let resource = format!("router:issue:{issue_id}");
    let hard = configuration
        .coordination
        .providers
        .first()
        .is_some_and(|provider| provider == "mutex_api");
    let claim = RouterClaim {
        issue_id: issue_id.to_string(),
        claim_id: claim_id.clone(),
        revision,
        resource,
        hard,
        owner,
        resources: Vec::new(),
    };
    assert_current_router_claim(project_dir, &configuration, &claim)?;
    router_cancel_control_event(project_dir, issue_id, &claim_id, revision)?;
    if let Some(pid) = local.active_child_pid {
        let _ = Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .status();
    }
    let _ = router;
    let checkpoint = reduce_router_events(&load_router_events(project_dir)?)
        .checkpoints
        .get(issue_id)
        .map(|(reference, _)| reference.clone());
    append_router_event(
        project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterResult,
        json!({"outcome": "cancelled", "claim_id": claim_id, "revision": revision, "checkpoint_ref": checkpoint}),
    )?;
    local.active_issue_id = None;
    local.active_claim_id = None;
    local.active_child_pid = None;
    write_local_router_state(root, &local)?;
    Ok(format!(
        "Cancelled router package {issue_id}; checkpoint {} preserved.\n",
        checkpoint.unwrap_or_else(|| "none".to_string())
    ))
}

fn wrap_router_error(error: KanbusError) -> KanbusError {
    match error {
        KanbusError::CommandFailure { .. } | KanbusError::CommandFailureWithOutput { .. } => error,
        KanbusError::Configuration(message) if message == "issue router is not configured" => {
            KanbusError::CommandFailure {
                exit_code: 2,
                message: "error: issue router is not configured".to_string(),
            }
        }
        KanbusError::Configuration(message) => KanbusError::CommandFailure {
            exit_code: 1,
            message: format!("error: {message}"),
        },
        KanbusError::IssueOperation(message) => KanbusError::CommandFailure {
            exit_code: 1,
            message: if message.starts_with("error:") {
                message
            } else {
                format!("error: {message}")
            },
        },
        other => other,
    }
}

/// Execute one public Issue Router command.
///
/// # Arguments
/// * `root` - Repository root containing the Kanbus project.
/// * `operation` - Requested router operation.
///
/// # Errors
/// Returns configuration, coordination, adapter, forge, or event-store failures.
pub fn execute_issue_router_operation(
    root: &Path,
    operation: IssueRouterOperation,
) -> Result<String, KanbusError> {
    execute_issue_router_operation_inner(root, operation).map_err(wrap_router_error)
}

fn execute_issue_router_operation_inner(
    root: &Path,
    operation: IssueRouterOperation,
) -> Result<String, KanbusError> {
    if let IssueRouterOperation::Stop = operation {
        let mut local = read_local_router_state(root)?;
        if !local.watch_pid.is_some_and(process_is_running) {
            local.watch_pid = None;
            local.active_issue_id = None;
            local.stop_requested = false;
            write_local_router_state(root, &local)?;
            return Ok("Issue Router is not running.\n".to_string());
        }
        local.stop_requested = true;
        write_local_router_state(root, &local)?;
        return Ok("Issue Router stop requested.\n".to_string());
    }
    let (configuration, router, project_dir) = load_issue_router(root)?;
    match operation {
        IssueRouterOperation::Plan { json } => {
            let plan = build_issue_router_plan(root)?;
            Ok(format_issue_router_plan(&plan, json))
        }
        IssueRouterOperation::RunOnce => run_issue_router_once(root, &router, &project_dir),
        IssueRouterOperation::RunWatch => run_issue_router_watch(root, &router, &project_dir),
        IssueRouterOperation::Status => router_status_output(root, &project_dir),
        IssueRouterOperation::Stop => unreachable!(),
        IssueRouterOperation::Pause => {
            router_control_event(&project_dir, "router:global", "pause", None)?;
            Ok("Issue Router paused.\n".to_string())
        }
        IssueRouterOperation::Resume => {
            router_control_event(&project_dir, "router:global", "resume", None)?;
            Ok("Issue Router resumed.\n".to_string())
        }
        IssueRouterOperation::Hold {
            class,
            provider_profile,
        } => {
            let route = selected_hold_route(class, provider_profile, &router)?;
            router_control_event(&project_dir, "router:global", "hold", Some(&route))?;
            Ok(format!("Held route {route}.\n"))
        }
        IssueRouterOperation::Unhold {
            class,
            provider_profile,
        } => {
            let route = selected_hold_route(class, provider_profile, &router)?;
            router_control_event(&project_dir, "router:global", "unhold", Some(&route))?;
            Ok(format!("Released hold for route {route}.\n"))
        }
        IssueRouterOperation::Cancel { issue_id } => {
            cancel_router_package(root, &router, &project_dir, &issue_id)
        }
        IssueRouterOperation::Recover { issue_id } => {
            recover_router_package(root, &configuration, &router, &project_dir, &issue_id)
        }
    }
}

fn recover_router_package(
    root: &Path,
    configuration: &ProjectConfiguration,
    router: &IssueRouterConfiguration,
    project_dir: &Path,
    issue_id: &str,
) -> Result<String, KanbusError> {
    let events = load_router_events(project_dir)?;
    let latest = events
        .iter()
        .filter(|event| event.issue_id == format!("router:{issue_id}"))
        .filter(|event| matches!(&event.event_type, EventType::RouterConversation))
        .max_by_key(|event| (&event.occurred_at, &event.event_id))
        .ok_or_else(|| {
            KanbusError::IssueOperation(format!(
                "no recoverable agent run for package \"{issue_id}\""
            ))
        })?;
    let provider = payload_text(latest, "provider").unwrap_or("unknown");
    let lifecycle = payload_text(latest, "lifecycle").unwrap_or("unknown");
    let branch = payload_text(latest, "branch").unwrap_or("none");
    append_router_event(
        project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterConversation,
        json!({
            "action":"recovered", "provider":provider, "lifecycle":lifecycle,
            "claim_id":payload_text(latest, "claim_id").unwrap_or("recovered"),
            "revision":latest.payload.get("revision").and_then(Value::as_u64).unwrap_or(1),
            "session_id":payload_text(latest, "session_id"), "branch":branch,
            "worktree":payload_text(latest, "worktree"),
        }),
    )?;
    let target_status = match lifecycle {
        "review" => Some(router.workflow.review.as_str()),
        "blocked" => Some(router.workflow.blocked.as_str()),
        _ => None,
    };
    if let Some(status) = target_status {
        // Recovering a completed or paused turn must put the actual board card
        // where the human can act on it, not merely emit hidden router state.
        apply_shared_issue_status(root, configuration, issue_id, status)?;
    }
    Ok(format!(
        "Recovered {issue_id}: provider={provider} lifecycle={lifecycle} branch={branch}\n"
    ))
}

fn run_issue_router_once(
    root: &Path,
    router: &IssueRouterConfiguration,
    project_dir: &Path,
) -> Result<String, KanbusError> {
    let configuration_path = get_configuration_path(root)?;
    let configuration = crate::config_loader::load_project_configuration(&configuration_path)?;
    let plan = build_issue_router_plan(root)?;
    let Some(package) = plan.eligible.first() else {
        return Ok(format!(
            "Issue Router run completed: started=0 completed=0 review=0 failed=0 deferred={}\n",
            plan.deferred.len()
        ));
    };
    let deferred_after_start = plan
        .deferred
        .len()
        .saturating_add(plan.eligible.len().saturating_sub(1));
    if router.forge.is_none() {
        return Err(KanbusError::Configuration(
            "router.forge is required to publish completed package work".to_string(),
        ));
    }
    let forge_client = GitHubForge::from_router(router)?;
    let profile = router
        .providers
        .get(&package.route.provider_profile)
        .ok_or_else(|| KanbusError::Configuration("router provider profile disappeared".into()))?;
    let issue = load_project_issues(project_dir)?
        .into_iter()
        .find(|issue| issue.identifier == package.issue_id)
        .ok_or_else(|| KanbusError::IssueOperation("routed issue not found".into()))?;
    let revision = next_router_revision(project_dir, &issue.identifier)?;
    let owner = crate::users::get_current_user();
    let claim_id = Uuid::new_v4().to_string();
    let (claims, resources, hard, mut lease_renewer) = acquire_router_claims(
        root,
        project_dir,
        &configuration,
        router,
        &package.issue_id,
        &package.route,
        &claim_id,
        revision,
        &owner,
    )?;
    if !claims {
        return Ok(format!(
            "Issue Router run completed: started=0 completed=0 review=0 failed=0 deferred={}\n",
            plan.deferred.len() + plan.eligible.len()
        ));
    }
    let claim = RouterClaim {
        issue_id: package.issue_id.clone(),
        claim_id: claim_id.clone(),
        revision,
        resource: format!("router:issue:{}", package.issue_id),
        hard,
        owner: owner.clone(),
        resources,
    };
    let active_state = reduce_router_events(&load_router_events(project_dir)?);
    let checkpoint = active_state.checkpoints.get(&package.issue_id).cloned();
    let mut started_payload = json!({
        "action": "started",
        "attempt": package.attempt,
        "claim_id": claim_id,
        "revision": revision,
        "provider_profile": package.route.provider_profile,
        "package_issue_ids": package.package_issue_ids,
    });
    if let Some((checkpoint_ref, checkpoint_revision)) = checkpoint.as_ref() {
        started_payload["checkpoint_ref"] = json!(checkpoint_ref);
        started_payload["checkpoint_revision"] = json!(checkpoint_revision);
    }
    let started_event = EventRecord::new(
        format!("router:{}", package.issue_id),
        EventType::RouterAttempt,
        crate::users::get_current_user(),
        started_payload,
        crate::event_history::now_timestamp(),
    );
    // Publish through the shared-ref compare-and-retry path before recording the
    // local start. It rejects a competing live claim after refreshing the branch.
    let start_result = (|| {
        if let Some(renewer) = lease_renewer.as_ref() {
            renewer.check()?;
        }
        publish_shared_router_event(root, &started_event)?;
        if let Some(renewer) = lease_renewer.as_ref() {
            renewer.check()?;
        }
        crate::event_history::write_events_batch(
            &events_dir_for_project(project_dir),
            std::slice::from_ref(&started_event),
        )?;
        assert_current_router_claim(project_dir, &configuration, &claim)?;
        set_active_router_state(root, &package.issue_id, &claim_id, None)
    })();
    if let Err(error) = start_result {
        if let Some(renewer) = lease_renewer.as_mut() {
            let _ = renewer.stop();
        }
        release_router_claims(root, &configuration, project_dir, &claim)?;
        return Err(error);
    }

    let run_result = execute_router_adapter(
        root,
        project_dir,
        &configuration,
        profile,
        &package.issue_id,
        &package.package_issue_ids,
        &claim,
        checkpoint,
        lease_renewer.as_ref(),
    );
    let result = match run_result {
        Ok(result) => result,
        Err(error) => {
            let renewer_stop = lease_renewer
                .as_mut()
                .map_or(Ok(()), RouterLeaseRenewalGuard::stop);
            let cleanup = release_then_clear(
                || release_router_claims(root, &configuration, project_dir, &claim),
                || clear_active_router_state(root),
            );
            return Err(preserve_router_error_after_adapter_failure(
                error,
                renewer_stop,
                cleanup,
            ));
        }
    };

    let processing = (|| -> Result<(usize, usize, usize, Option<String>), KanbusError> {
        if let Some(renewer) = lease_renewer.as_ref() {
            renewer.check()?;
        }
        // Reject a cancellation that arrived after the child exited but before
        // any result/checkpoint/forge publication is accepted.
        assert_current_router_claim(project_dir, &configuration, &claim)?;
        let mut completed = 0;
        let mut review = 0;
        let mut failed = 0;
        let mut outcome_error = None;
        match result.outcome.as_str() {
            "completed" => {
                let requested_updates = result
                    .issue_updates
                    .iter()
                    .map(|update| (update.issue_id.clone(), update.status.clone()))
                    .collect::<Vec<_>>();
                validate_router_issue_updates(
                    router,
                    &package.issue_id,
                    &package.package_issue_ids,
                    &requested_updates,
                )?;
                validate_router_issue_comments(
                    &package.issue_id,
                    &package.package_issue_ids,
                    &result.issue_comments,
                )?;
                let (proposed_checkpoint_ref, proposed_checkpoint_revision) = result
                    .checkpoint
                    .as_ref()
                    .map(|checkpoint| (checkpoint.reference.clone(), checkpoint.revision))
                    .unwrap_or_else(|| {
                        (
                            format!("refs/kanbus/router/checkpoints/{}", package.issue_id),
                            revision,
                        )
                    });
                if proposed_checkpoint_revision != revision {
                    return Err(KanbusError::IssueOperation(format!(
                        "stale router revision {proposed_checkpoint_revision} for package {}; current revision is {revision}",
                        package.issue_id
                    )));
                }
                for artifact in &result.artifacts {
                    assert_current_router_claim(project_dir, &configuration, &claim)?;
                    crate::coordination::publish_coordination_result(
                        project_dir,
                        &format!(
                            "router:package:{}:artifact:{}",
                            package.issue_id, artifact.name
                        ),
                        revision,
                        &artifact.reference,
                    )?;
                }
                let worktree = latest_router_worktree(root, &claim_id)?;
                let prior_pr = reduce_router_events(&load_router_events(project_dir)?)
                    .pull_requests
                    .get(&package.issue_id)
                    .map(|(number, _)| *number)
                    .map(|number| forge_client.get_pull_request(number))
                    .transpose()?;
                let branch = prior_pr
                    .as_ref()
                    .map(|pull| pull.branch.clone())
                    .unwrap_or_else(|| format!("codex/router/{}/r{}", package.issue_id, revision));
                let published_branch = publish_router_branch(
                    root,
                    project_dir,
                    &configuration,
                    router,
                    &claim,
                    &worktree,
                    &package.issue_id,
                    &branch,
                    revision,
                )?;
                let checkpoint_commit = published_branch.pushed_sha.clone();
                let published_checkpoint_ref = publish_router_checkpoint_ref(
                    root,
                    project_dir,
                    &configuration,
                    &claim,
                    &proposed_checkpoint_ref,
                    &checkpoint_commit,
                )?;
                assert_current_router_claim(project_dir, &configuration, &claim)?;
                let existing_pr = prior_pr.is_some();
                let pull = if let Some(existing) = prior_pr {
                    forge_client.get_pull_request(existing.number)?
                } else {
                    forge_client.create_pull_request(&package.issue_id, &issue.title, &branch)?
                };
                // GitHub cannot atomically bind PR creation to our claim lease. Fence
                // immediately after the API response and before recording acceptance;
                // the remote PR may be briefly visible if the lease expired in flight.
                record_router_pull_response(
                    project_dir,
                    &configuration,
                    &claim,
                    &package.issue_id,
                    &router.forge.as_ref().expect("validated forge").repository,
                    &branch,
                    existing_pr,
                    &pull,
                    &[&published_branch, &published_checkpoint_ref],
                )?;
                assert_current_router_claim(project_dir, &configuration, &claim)?;
                apply_router_issue_comments(
                    root,
                    &package.issue_id,
                    &package.package_issue_ids,
                    &result.issue_comments,
                )?;
                assert_current_router_claim(project_dir, &configuration, &claim)?;
                let review_comment = completed_router_review_comment(
                    &result.summary,
                    &pull,
                    &published_checkpoint_ref.reference,
                    &result.artifacts,
                );
                crate::issue_comment::add_comment(
                    root,
                    &package.issue_id,
                    "Kanbus Issue Router",
                    &review_comment,
                    None,
                )?;
                assert_current_router_claim(project_dir, &configuration, &claim)?;
                let accepted_checkpoint = RouterCheckpoint {
                    reference: proposed_checkpoint_ref,
                    revision: proposed_checkpoint_revision,
                };
                let (checkpoint_ref, checkpoint_revision) = publish_router_checkpoint(
                    project_dir,
                    &configuration,
                    &claim,
                    Some(&accepted_checkpoint),
                    &package.issue_id,
                )?;
                append_router_event(
                    project_dir,
                    &format!("router:{}", package.issue_id),
                    EventType::RouterResult,
                    json!({
                        "outcome": "completed",
                        "summary": result.summary,
                        "claim_id": claim_id,
                        "revision": revision,
                        "checkpoint_ref": checkpoint_ref,
                        "checkpoint_revision": checkpoint_revision,
                        "artifacts": result.artifacts.iter().map(|artifact| json!({"name": artifact.name, "ref": artifact.reference})).collect::<Vec<_>>(),
                        "issue_updates": result.issue_updates.iter().map(|update| json!({"issue_id":update.issue_id,"status":update.status})).collect::<Vec<_>>(),
                    }),
                )?;
                completed = 1;
                review = 1;
            }
            "blocked" => {
                assert_current_router_claim(project_dir, &configuration, &claim)?;
                // A paused agent must be able to speak directly to the person
                // reviewing the issue.  Preserve any agent-supplied comments,
                // then publish its exact question as a canonical issue comment
                // before the RouterResult event moves the card to Blocked.
                apply_router_issue_comments(
                    root,
                    &package.issue_id,
                    &package.package_issue_ids,
                    &result.issue_comments,
                )?;
                assert_current_router_claim(project_dir, &configuration, &claim)?;
                crate::issue_comment::add_comment(
                    root,
                    &package.issue_id,
                    "Kanbus Issue Router",
                    if result.summary.trim().is_empty() {
                        "The agent is awaiting a human reply."
                    } else {
                        &result.summary
                    },
                    None,
                )?;
                assert_current_router_claim(project_dir, &configuration, &claim)?;
                append_router_event(
                    project_dir,
                    &format!("router:{}", package.issue_id),
                    EventType::RouterResult,
                    json!({"outcome": "blocked", "summary": result.summary, "claim_id": claim_id, "revision": revision}),
                )?;
                failed = 1;
            }
            "retryable_failure" => {
                assert_current_router_claim(project_dir, &configuration, &claim)?;
                failed = 1;
                let retry_at =
                    Utc::now() + chrono::Duration::seconds(retry_delay_seconds(package.attempt));
                append_router_event(
                    project_dir,
                    &format!("router:{}", package.issue_id),
                    EventType::RouterAttempt,
                    json!({
                        "action": "retryable_failure",
                        "attempt": package.attempt,
                        "next_attempt": package.attempt + 1,
                        "retry_at": retry_at.to_rfc3339_opts(SecondsFormat::Secs, true),
                        "claim_id": claim_id,
                        "revision": revision,
                        "diagnostic": result.summary,
                    }),
                )?;
                if package.attempt >= router.retries.max_attempts {
                    assert_current_router_claim(project_dir, &configuration, &claim)?;
                    append_router_event(
                        project_dir,
                        &format!("router:{}", package.issue_id),
                        EventType::RouterResult,
                        json!({"outcome": "blocked", "diagnostic": "maximum retry attempts reached", "claim_id": claim_id, "revision": revision}),
                    )?;
                    outcome_error = Some("maximum retry attempts reached".to_string());
                } else {
                    outcome_error = Some(
                        if result.summary == "Codex router adapter returned invalid JSON" {
                            result.summary.clone()
                        } else {
                            format!("retryable failure: {}", result.summary)
                        },
                    );
                }
            }
            outcome => {
                return Err(KanbusError::IssueOperation(format!(
                    "invalid Codex router outcome \"{outcome}\""
                )));
            }
        }
        Ok((completed, review, failed, outcome_error))
    })();
    let (completed, review, failed, outcome_error) = match processing {
        Ok(result) => result,
        Err(error) => {
            if let Some(renewer) = lease_renewer.as_mut() {
                let renew_result = renewer.stop();
                if let Err(renew_error) = renew_result {
                    eprintln!("warning: {renew_error}");
                }
            }
            release_then_clear(
                || release_router_claims(root, &configuration, project_dir, &claim),
                || clear_active_router_state(root),
            )?;
            return Err(error);
        }
    };
    if let Some(renewer) = lease_renewer.as_mut() {
        if let Err(error) = renewer.stop() {
            release_then_clear(
                || release_router_claims(root, &configuration, project_dir, &claim),
                || clear_active_router_state(root),
            )?;
            return Err(error);
        }
    }
    release_then_clear(
        || release_router_claims(root, &configuration, project_dir, &claim),
        || clear_active_router_state(root),
    )?;
    let output = format!(
        "Issue Router run completed: started=1 completed={completed} review={review} failed={failed} deferred={}\n",
        deferred_after_start
    );
    if let Some(error) = outcome_error {
        return Err(KanbusError::CommandFailureWithOutput {
            exit_code: 1,
            stdout: output,
            stderr: format!("error: {error}"),
        });
    }
    Ok(output)
}

fn run_issue_router_watch(
    root: &Path,
    router: &IssueRouterConfiguration,
    project_dir: &Path,
) -> Result<String, KanbusError> {
    if router.forge.is_none() {
        return Err(KanbusError::Configuration(
            "router.forge is required for watch mode".to_string(),
        ));
    }
    let configuration =
        crate::config_loader::load_project_configuration(&get_configuration_path(root)?)?;
    let interval =
        parse_duration_seconds(&router.watch_interval).map_err(KanbusError::Configuration)?;
    let forge = GitHubForge::from_router(router)?;
    let mut local = read_local_router_state(root)?;
    if local.watch_pid.is_some_and(process_is_running) {
        return Err(KanbusError::IssueOperation(
            "Issue Router is already running".to_string(),
        ));
    }
    let scheduler_claim_id = Uuid::new_v4().to_string();
    let scheduler_owner = crate::users::get_current_user();
    let scheduler_resource = "router:scheduler";
    let scheduler_hard = configuration
        .coordination
        .providers
        .first()
        .is_some_and(|provider| provider == "mutex_api");
    if scheduler_hard {
        if !crate::mutex_api::is_configured(&configuration.coordination.mutex_api) {
            return Err(hard_mutex_unavailable());
        }
        let ttl = parse_duration_seconds(&configuration.coordination.default_lease_ttl)
            .map_err(KanbusError::Configuration)?;
        let contention = parse_duration_seconds(&configuration.coordination.contention_window)
            .map_err(KanbusError::Configuration)?;
        let lease = crate::mutex_api::acquire(
            &configuration.coordination.mutex_api,
            scheduler_resource,
            &scheduler_owner,
            &scheduler_claim_id,
            1,
            ttl,
        )
        .map_err(|error| match error {
            crate::mutex_api::MutexApiError::Unavailable(_) => hard_mutex_unavailable(),
            crate::mutex_api::MutexApiError::Rejected { status: 409, .. } => {
                KanbusError::IssueOperation("Issue Router is already running".to_string())
            }
            other => KanbusError::IssueOperation(other.to_string()),
        })?;
        append_hard_claim_event(project_dir, scheduler_resource, &lease, contention, ttl)?;
    } else {
        run_coordination(
            root,
            CoordinationOperation::Claim {
                resource: scheduler_resource.to_string(),
                owner: scheduler_owner.clone(),
                claim_id: scheduler_claim_id.clone(),
                revision: 1,
            },
        )?;
    }
    local.watch_pid = Some(std::process::id());
    local.scheduler_claim_id = Some(scheduler_claim_id.clone());
    local.scheduler_owner = Some(scheduler_owner.clone());
    local.scheduler_hard = scheduler_hard;
    local.stop_requested = false;
    write_local_router_state(root, &local)?;
    let mut next_poll = Instant::now();
    let scheduler_renewal = Duration::from_secs(
        parse_duration_seconds(&configuration.coordination.default_lease_ttl)
            .unwrap_or(900)
            .saturating_div(3)
            .max(1),
    );
    let mut next_scheduler_renew = Instant::now() + scheduler_renewal;
    let mut output = String::new();
    loop {
        local = read_local_router_state(root)?;
        if local.stop_requested {
            break;
        }
        if Instant::now() >= next_scheduler_renew {
            if let Err(error) = renew_watch_scheduler(root, project_dir, &configuration) {
                release_watch_scheduler_claim(root, project_dir, &configuration)?;
                clear_watch_router_state(root)?;
                return Err(error);
            }
            next_scheduler_renew = Instant::now() + scheduler_renewal;
        }
        let mut run_cycle = false;
        if Instant::now() >= next_poll {
            if let Err(error) =
                reconcile_github_pull_requests(root, project_dir, router, &forge, &configuration)
            {
                release_watch_scheduler_claim(root, project_dir, &configuration)?;
                clear_watch_router_state(root)?;
                return Err(error);
            }
            next_poll = Instant::now() + Duration::from_secs(interval);
            run_cycle = true;
        }
        if run_cycle {
            match run_issue_router_once(root, router, project_dir) {
                Ok(summary) => output = summary,
                Err(KanbusError::CommandFailure { message, .. }) => output = message,
                Err(KanbusError::CommandFailureWithOutput { stdout, .. }) => output = stdout,
                Err(error) => {
                    release_watch_scheduler_claim(root, project_dir, &configuration)?;
                    clear_watch_router_state(root)?;
                    return Err(error);
                }
            }
        }
        let now = Instant::now();
        let until_poll = next_poll.saturating_duration_since(now);
        let until_renewal = next_scheduler_renew.saturating_duration_since(now);
        let wait = until_poll.min(until_renewal).min(Duration::from_secs(1));
        if wait.is_zero() {
            continue;
        }
        if configuration
            .coordination
            .providers
            .iter()
            .any(|provider| provider == "mqtt")
        {
            let wait_started = Instant::now();
            let notified = crate::gossip::wait_for_coordination_gossip_notification(
                root,
                project_dir,
                wait,
                configuration.overlay.ttl_s,
            );
            if notified {
                next_poll = Instant::now();
            } else if let Some(remaining) = wait.checked_sub(wait_started.elapsed()) {
                thread::sleep(remaining);
            }
        } else {
            thread::sleep(wait);
        }
    }
    release_then_clear(
        || release_watch_scheduler_claim(root, project_dir, &configuration),
        || clear_watch_router_state(root),
    )?;
    Ok(output)
}

pub fn retry_delay_seconds(attempt: u32) -> i64 {
    let exponent = attempt.saturating_sub(1).min(5);
    (30_i64.saturating_mul(1_i64 << exponent)).min(900)
}

fn next_router_revision(project_dir: &Path, issue_id: &str) -> Result<u64, KanbusError> {
    let events = load_router_events(project_dir)?;
    let checkpoint_revision = reduce_router_events(&events)
        .checkpoints
        .get(issue_id)
        .map(|(_, revision)| *revision)
        .unwrap_or_default();
    let latest_claim_revision = events
        .iter()
        .filter(|event| event.issue_id == format!("router:{issue_id}"))
        .filter(|event| matches!(&event.event_type, EventType::RouterAttempt))
        .filter_map(|event| event.payload.get("revision").and_then(Value::as_u64))
        .max()
        .unwrap_or_default();
    Ok(published_revision(
        project_dir,
        &format!("router:package:{issue_id}:checkpoint"),
    )?
    .unwrap_or_default()
    .max(checkpoint_revision)
    .max(latest_claim_revision)
    .saturating_add(1)
    .max(1))
}

#[allow(clippy::too_many_arguments)]
fn acquire_router_claims(
    root: &Path,
    project_dir: &Path,
    configuration: &ProjectConfiguration,
    router: &IssueRouterConfiguration,
    issue_id: &str,
    route: &IssueRouterRoute,
    claim_id: &str,
    revision: u64,
    owner: &str,
) -> Result<(bool, Vec<String>, bool, Option<RouterLeaseRenewalGuard>), KanbusError> {
    let coordination = &configuration.coordination;
    let hard_required = coordination
        .providers
        .first()
        .is_some_and(|provider| provider == "mutex_api");
    if hard_required && !crate::mutex_api::is_configured(&coordination.mutex_api) {
        return Err(hard_mutex_unavailable());
    }
    if hard_required {
        let ttl = parse_duration_seconds(&coordination.default_lease_ttl)
            .map_err(KanbusError::Configuration)?;
        let contention = parse_duration_seconds(&coordination.contention_window)
            .map_err(KanbusError::Configuration)?;
        let occupancy = hard_capacity_occupancy(project_dir, router)?;
        let mut acquired = Vec::new();
        match acquire_hard_resource(
            coordination,
            project_dir,
            &mut acquired,
            None,
            &format!("router:issue:{issue_id}"),
            owner,
            claim_id,
            revision,
            ttl,
            contention,
        ) {
            Ok(true) => {}
            Ok(false) => return Ok((false, Vec::new(), true, None)),
            Err(error) => {
                let cleanup =
                    release_hard_resources(coordination, project_dir, &acquired, owner, claim_id);
                return Err(combine_hard_acquisition_error(error, cleanup));
            }
        }
        let renewal_resources = Arc::new(Mutex::new(acquired.clone()));
        let renewal_configuration = configuration.clone();
        let renewal_resource_set = Arc::clone(&renewal_resources);
        let renewal_claim_id = claim_id.to_string();
        let renewal_owner = owner.to_string();
        let interval = Duration::from_secs(ttl.saturating_div(3).max(1));
        let mut lease_renewer = match RouterLeaseRenewalGuard::start(interval, move || {
            let resources = renewal_resource_set
                .lock()
                .map_err(|_| "router lease renewal resource list is unavailable".to_string())?
                .clone();
            renew_hard_resource_set(
                &renewal_configuration,
                &resources,
                &renewal_owner,
                &renewal_claim_id,
                revision,
            )
            .map_err(|error| error.to_string())
        }) {
            Ok(renewer) => renewer,
            Err(error) => {
                let cleanup =
                    release_hard_resources(coordination, project_dir, &acquired, owner, claim_id);
                return Err(combine_hard_acquisition_error(
                    KanbusError::IssueOperation(format!(
                        "router hard lease renewal failed: {error}"
                    )),
                    cleanup,
                ));
            }
        };
        let acquisition_result = (|| -> Result<bool, KanbusError> {
            if !acquire_capacity_slot(
                coordination,
                project_dir,
                &mut acquired,
                "project",
                "project".to_string(),
                router.limits.project_wip,
                occupancy.project,
                Some(&renewal_resources),
                revision,
                owner,
                claim_id,
                ttl,
                contention,
            )? {
                return Ok(false);
            }
            if route.kind == "class" {
                if let Some(limit) = router.limits.class_wip.get(&route.name) {
                    if !acquire_capacity_slot(
                        coordination,
                        project_dir,
                        &mut acquired,
                        "class",
                        route.name.clone(),
                        *limit,
                        occupancy
                            .classes
                            .get(&route.name)
                            .copied()
                            .unwrap_or_default(),
                        Some(&renewal_resources),
                        revision,
                        owner,
                        claim_id,
                        ttl,
                        contention,
                    )? {
                        return Ok(false);
                    }
                }
            }
            if let Some(limit) = router.limits.provider_wip.get(&route.provider_profile) {
                if !acquire_capacity_slot(
                    coordination,
                    project_dir,
                    &mut acquired,
                    "provider-profile",
                    route.provider_profile.clone(),
                    *limit,
                    occupancy
                        .providers
                        .get(&route.provider_profile)
                        .copied()
                        .unwrap_or_default(),
                    Some(&renewal_resources),
                    revision,
                    owner,
                    claim_id,
                    ttl,
                    contention,
                )? {
                    return Ok(false);
                }
            }
            Ok(true)
        })();
        match acquisition_result {
            Ok(true) => {}
            Ok(false) => {
                let failures = stop_and_release_hard_resources(
                    &mut lease_renewer,
                    coordination,
                    project_dir,
                    &acquired,
                    owner,
                    claim_id,
                );
                if !failures.is_empty() {
                    return Err(KanbusError::IssueOperation(format!(
                        "router hard capacity acquisition cleanup failed: {}",
                        failures.join("; ")
                    )));
                }
                return Ok((false, Vec::new(), true, None));
            }
            Err(error) => {
                let failures = stop_and_release_hard_resources(
                    &mut lease_renewer,
                    coordination,
                    project_dir,
                    &acquired,
                    owner,
                    claim_id,
                );
                return Err(if failures.is_empty() {
                    error
                } else {
                    KanbusError::IssueOperation(format!(
                        "{error}; router hard capacity acquisition cleanup failed: {}",
                        failures.join("; ")
                    ))
                });
            }
        }
        return Ok((true, acquired, true, Some(lease_renewer)));
    }
    let mut resources = Vec::new();
    let issue_resource = format!("router:issue:{issue_id}");
    let issue_claim = run_coordination(
        root,
        CoordinationOperation::Claim {
            resource: issue_resource.clone(),
            owner: owner.to_string(),
            claim_id: claim_id.to_string(),
            revision,
        },
    )?;
    // A Git lease is deliberately soft.  A different candidate may win the
    // deterministic inspection window, but this worker's immutable claim is
    // still valid evidence and may proceed; later claim fencing prevents it
    // from publishing a stale result.  Treating a non-winning inspection as
    // "no start" silently defeated the single-worker path whenever historic
    // shared state was briefly ahead of the local checkout.
    let _ = issue_claim;
    resources.push(issue_resource);

    let mut capacity_specs = vec![("project", String::new(), router.limits.project_wip)];
    if let Some(limit) = router.limits.provider_wip.get(&route.provider_profile) {
        capacity_specs.push(("provider-profile", route.provider_profile.clone(), *limit));
    }
    if route.kind == "class" {
        if let Some(limit) = router.limits.class_wip.get(&route.name) {
            capacity_specs.push(("class", route.name.clone(), *limit));
        }
    }
    for (kind, name, limit) in capacity_specs {
        let mut claimed_slot = false;
        for slot in 0..limit {
            let resource = if name.is_empty() {
                format!("router:capacity:{kind}:{slot}")
            } else {
                format!("router:capacity:{kind}:{name}:{slot}")
            };
            let output = run_coordination(
                root,
                CoordinationOperation::Claim {
                    resource: resource.clone(),
                    owner: owner.to_string(),
                    claim_id: claim_id.to_string(),
                    revision,
                },
            )?;
            if coordination_output_claim_matches(&output, owner, claim_id) {
                resources.push(resource);
                claimed_slot = true;
                break;
            }
        }
        if !claimed_slot {
            let failures = release_soft_router_resources(root, &resources, owner, claim_id);
            release_failures_result(failures)?;
            return Ok((false, Vec::new(), false, None));
        }
    }
    Ok((!resources.is_empty(), resources, false, None))
}

fn update_renewal_resource_set(
    resources: &Arc<Mutex<Vec<String>>>,
    acquired: &[String],
) -> Result<(), KanbusError> {
    *resources.lock().map_err(|_| {
        KanbusError::IssueOperation("router lease renewal resource list is unavailable".into())
    })? = acquired.to_vec();
    Ok(())
}

fn stop_and_release_hard_resources(
    renewer: &mut RouterLeaseRenewalGuard,
    coordination: &crate::models::CoordinationConfiguration,
    project_dir: &Path,
    resources: &[String],
    owner: &str,
    claim_id: &str,
) -> Vec<String> {
    let mut failures = Vec::new();
    if let Err(error) = renewer.stop() {
        failures.push(error.to_string());
    }
    if let Err(error) =
        release_hard_resources(coordination, project_dir, resources, owner, claim_id)
    {
        failures.push(error.to_string());
    }
    failures
}

fn combine_hard_acquisition_error(
    original: KanbusError,
    cleanup: Result<(), KanbusError>,
) -> KanbusError {
    match cleanup {
        Ok(()) => original,
        Err(cleanup_error) => KanbusError::IssueOperation(format!(
            "{original}; router hard claim cleanup failed: {cleanup_error}"
        )),
    }
}

#[allow(clippy::too_many_arguments)]
fn acquire_capacity_slot(
    coordination: &crate::models::CoordinationConfiguration,
    project_dir: &Path,
    acquired: &mut Vec<String>,
    kind: &str,
    name: String,
    limit: usize,
    occupied: usize,
    renewal_resources: Option<&Arc<Mutex<Vec<String>>>>,
    revision: u64,
    owner: &str,
    claim_id: &str,
    ttl: u64,
    contention: u64,
) -> Result<bool, KanbusError> {
    for slot in available_capacity_slots(occupied, limit) {
        let resource = format!("router:capacity:{kind}:{name}:{slot}");
        if acquire_hard_resource(
            coordination,
            project_dir,
            acquired,
            renewal_resources,
            &resource,
            owner,
            claim_id,
            revision,
            ttl,
            contention,
        )? {
            return Ok(true);
        }
    }
    Ok(false)
}

struct CapacityOccupancy {
    project: usize,
    classes: BTreeMap<String, usize>,
    providers: BTreeMap<String, usize>,
}

fn hard_capacity_occupancy(
    project_dir: &Path,
    router: &IssueRouterConfiguration,
) -> Result<CapacityOccupancy, KanbusError> {
    let issues = load_project_issues(project_dir)?;
    let events = load_router_events(project_dir)?;
    let state = reduce_router_events(&events);
    let mut class_occupied = BTreeMap::<String, usize>::new();
    let mut provider_occupied = BTreeMap::<String, usize>::new();
    let mut project_occupied = 0usize;
    for issue in &issues {
        if !is_wip_status(issue, router) {
            continue;
        }
        let routes = issue_route_labels(issue);
        if routes.len() != 1 {
            continue;
        }
        let (kind, name) = &routes[0];
        let profile = if *kind == "agent-provider:" {
            if !router.providers.contains_key(name) {
                continue;
            }
            name.clone()
        } else if *kind == "agent-class:" {
            let Some(class) = router.classes.get(name) else {
                continue;
            };
            *class_occupied.entry(name.clone()).or_default() += 1;
            state
                .provider_profiles
                .get(&issue.identifier)
                .filter(|profile| class.providers.contains(profile))
                .cloned()
                .or_else(|| class.providers.first().cloned())
                .unwrap_or_default()
        } else {
            continue;
        };
        project_occupied += 1;
        if !profile.is_empty() && router.providers.contains_key(&profile) {
            *provider_occupied.entry(profile).or_default() += 1;
        }
    }
    Ok(CapacityOccupancy {
        project: project_occupied,
        classes: class_occupied,
        providers: provider_occupied,
    })
}

fn available_capacity_slots(occupied: usize, limit: usize) -> std::ops::Range<usize> {
    occupied.min(limit)..limit
}

#[allow(clippy::too_many_arguments)]
fn acquire_hard_resource(
    coordination: &crate::models::CoordinationConfiguration,
    project_dir: &Path,
    acquired: &mut Vec<String>,
    renewal_resources: Option<&Arc<Mutex<Vec<String>>>>,
    resource: &str,
    owner: &str,
    claim_id: &str,
    revision: u64,
    ttl: u64,
    contention: u64,
) -> Result<bool, KanbusError> {
    match crate::mutex_api::acquire(
        &coordination.mutex_api,
        resource,
        owner,
        claim_id,
        revision,
        ttl,
    ) {
        Ok(lease) => {
            acquired.push(resource.to_string());
            if let Some(renewal_resources) = renewal_resources {
                update_renewal_resource_set(renewal_resources, acquired)?;
            }
            append_hard_claim_event(project_dir, resource, &lease, contention, ttl)?;
            Ok(true)
        }
        Err(crate::mutex_api::MutexApiError::Unavailable(_)) => Err(hard_mutex_unavailable()),
        Err(crate::mutex_api::MutexApiError::Rejected { status: 409, .. }) => Ok(false),
        Err(error) => Err(KanbusError::IssueOperation(error.to_string())),
    }
}

fn release_hard_resources(
    coordination: &crate::models::CoordinationConfiguration,
    project_dir: &Path,
    resources: &[String],
    owner: &str,
    claim_id: &str,
) -> Result<(), KanbusError> {
    let failures = release_resources_in_reverse(resources, |resource| {
        crate::mutex_api::release(&coordination.mutex_api, resource, owner, claim_id)
            .map_err(|error| error.to_string())?;
        append_hard_release_event(project_dir, resource, owner, claim_id)
            .map_err(|error| error.to_string())
    });
    release_failures_result(failures)
}

fn release_router_claims(
    root: &Path,
    configuration: &ProjectConfiguration,
    project_dir: &Path,
    claim: &RouterClaim,
) -> Result<(), KanbusError> {
    let failures = release_resources_in_reverse(&claim.resources, |resource| {
        if claim.hard {
            crate::mutex_api::release(
                &configuration.coordination.mutex_api,
                resource,
                &claim.owner,
                &claim.claim_id,
            )
            .map_err(|error| error.to_string())?;
            append_hard_release_event(project_dir, resource, &claim.owner, &claim.claim_id)
                .map_err(|error| error.to_string())
        } else {
            release_soft_router_resource(root, resource, &claim.owner, &claim.claim_id)
        }
    });
    release_failures_result(failures)
}

fn release_soft_router_resources(
    root: &Path,
    resources: &[String],
    owner: &str,
    claim_id: &str,
) -> Vec<String> {
    release_resources_in_reverse(resources, |resource| {
        release_soft_router_resource(root, resource, owner, claim_id)
    })
}

fn release_soft_router_resource(
    root: &Path,
    resource: &str,
    owner: &str,
    claim_id: &str,
) -> Result<(), String> {
    let inspect = || {
        run_coordination(
            root,
            CoordinationOperation::Inspect {
                resource: resource.to_string(),
            },
        )
        .map_err(|error| error.to_string())
    };
    if !coordination_output_claim_matches(&inspect()?, owner, claim_id) {
        return Ok(());
    }
    match run_coordination(
        root,
        CoordinationOperation::Release {
            resource: resource.to_string(),
            owner: owner.to_string(),
            claim_id: claim_id.to_string(),
        },
    ) {
        Ok(_) => Ok(()),
        Err(error) if error.to_string().contains("lease owner mismatch") => {
            // The lease may have changed between Inspect and Release. Treat
            // that as a lost handle only when a fresh inspection confirms we
            // no longer own it; otherwise preserve the real release failure.
            if !coordination_output_claim_matches(&inspect()?, owner, claim_id) {
                Ok(())
            } else {
                Err(error.to_string())
            }
        }
        Err(error) => Err(error.to_string()),
    }
}

fn coordination_output_claim_matches(output: &str, owner: &str, claim_id: &str) -> bool {
    let fields = output
        .lines()
        .filter_map(|line| line.split_once(": "))
        .collect::<BTreeMap<_, _>>();
    fields.get("state") == Some(&"active soft ownership")
        && fields.get("owner") == Some(&owner)
        && fields.get("claim_id") == Some(&claim_id)
}

fn release_resources_in_reverse<T: std::fmt::Display>(
    resources: &[T],
    mut release: impl FnMut(&T) -> Result<(), String>,
) -> Vec<String> {
    let mut failures = Vec::new();
    for resource in resources.iter().rev() {
        if let Err(error) = release(resource) {
            failures.push(format!("{resource}: {error}"));
        }
    }
    failures
}

fn release_failures_result(failures: Vec<String>) -> Result<(), KanbusError> {
    match failures.as_slice() {
        [] => Ok(()),
        [error] => Err(KanbusError::IssueOperation(error.clone())),
        _ => Err(KanbusError::IssueOperation(format!(
            "multiple coordination releases failed: {}",
            failures.join("; ")
        ))),
    }
}

fn release_then_clear(
    release: impl FnOnce() -> Result<(), KanbusError>,
    clear: impl FnOnce() -> Result<(), KanbusError>,
) -> Result<(), KanbusError> {
    release()?;
    clear()
}

fn preserve_router_error_after_adapter_failure(
    original: KanbusError,
    renewer_stop: Result<(), KanbusError>,
    cleanup: Result<(), KanbusError>,
) -> KanbusError {
    let mut additional_errors = Vec::new();
    if let Err(stop_error) = renewer_stop {
        additional_errors.push(format!("lease renewer shutdown failed: {stop_error}"));
    }
    if let Err(cleanup_error) = cleanup {
        additional_errors.push(format!("router cleanup failed: {cleanup_error}"));
    }
    if additional_errors.is_empty() {
        original
    } else {
        KanbusError::IssueOperation(format!(
            "{original}; additionally {}",
            additional_errors.join("; additionally ")
        ))
    }
}

fn hard_mutex_unavailable() -> KanbusError {
    KanbusError::CommandFailure {
        exit_code: 1,
        message: "error: hard router coordination requires Mutex API; provider mutex_api is unavailable; no package was started".to_string(),
    }
}

fn latest_started_router_event<'a>(
    events: &'a [EventRecord],
    issue_id: &str,
) -> Option<&'a EventRecord> {
    events
        .iter()
        .filter(|event| {
            event.issue_id == format!("router:{issue_id}")
                && matches!(&event.event_type, EventType::RouterAttempt)
                && payload_text(event, "action") == Some("started")
        })
        .max_by(|left, right| {
            left.payload
                .get("revision")
                .and_then(Value::as_u64)
                .cmp(&right.payload.get("revision").and_then(Value::as_u64))
                .then_with(|| left.occurred_at.cmp(&right.occurred_at))
                .then_with(|| left.event_id.cmp(&right.event_id))
        })
}

fn assert_current_router_claim(
    project_dir: &Path,
    configuration: &ProjectConfiguration,
    claim: &RouterClaim,
) -> Result<(), KanbusError> {
    let events = load_router_events(project_dir)?;
    let current = latest_started_router_event(&events, &claim.issue_id);
    let Some(current) = current else {
        return Err(stale_claim_error(claim, None, None));
    };
    let current_claim = payload_text(current, "claim_id");
    let current_revision = current.payload.get("revision").and_then(Value::as_u64);
    if current_claim != Some(claim.claim_id.as_str()) || current_revision != Some(claim.revision) {
        return Err(stale_claim_error(claim, current_claim, current_revision));
    }
    if router_cancel_requested(project_dir, &claim.issue_id) {
        return Err(KanbusError::IssueOperation(format!(
            "router package {} cancelled",
            claim.issue_id
        )));
    }
    if !is_current_router_revision(
        project_dir,
        &format!("router:package:{}:checkpoint", claim.issue_id),
        claim.revision,
    )? {
        return Err(KanbusError::IssueOperation(format!(
            "stale router revision {} for package {}; current revision is {}",
            claim.revision,
            claim.issue_id,
            published_revision(
                project_dir,
                &format!("router:package:{}:checkpoint", claim.issue_id)
            )?
            .unwrap_or_default()
        )));
    }
    if claim.hard {
        let lease =
            crate::mutex_api::inspect(&configuration.coordination.mutex_api, &claim.resource)
                .map_err(|_| hard_mutex_unavailable())?;
        let current = lease.is_some_and(|lease| {
            lease.owner == claim.owner
                && lease.claim_id == claim.claim_id
                && lease.revision == claim.revision
        });
        if !current {
            return Err(stale_claim_error(claim, None, None));
        }
    }
    Ok(())
}

fn renew_router_claims(
    root: &Path,
    project_dir: &Path,
    configuration: &ProjectConfiguration,
    claim: &RouterClaim,
) -> Result<(), KanbusError> {
    let ttl_seconds = parse_duration_seconds(&configuration.coordination.default_lease_ttl)
        .map_err(KanbusError::Configuration)?;
    if claim.hard {
        for resource in &claim.resources {
            let current =
                crate::mutex_api::inspect(&configuration.coordination.mutex_api, resource)
                    .map_err(|_| hard_mutex_unavailable())?
                    .filter(|lease| {
                        lease.owner == claim.owner
                            && lease.claim_id == claim.claim_id
                            && lease.revision == claim.revision
                    })
                    .ok_or_else(|| stale_claim_error(claim, None, None))?;
            let seconds = router_renewal_extension_seconds(
                Some(current.expires_at),
                router_now(),
                ttl_seconds,
            );
            if seconds == 0 {
                continue;
            }
            let lease = crate::mutex_api::renew(
                &configuration.coordination.mutex_api,
                resource,
                &claim.owner,
                &claim.claim_id,
                seconds,
            )
            .map_err(|_| hard_mutex_unavailable())?;
            append_hard_renew_event(project_dir, resource, &lease)?;
        }
    } else {
        for resource in &claim.resources {
            renew_soft_router_resource(
                root,
                project_dir,
                resource,
                &claim.owner,
                &claim.claim_id,
                ttl_seconds,
            )?;
        }
    }
    let local = read_local_router_state(root)?;
    if let (Some(scheduler_claim), Some(scheduler_owner)) =
        (local.scheduler_claim_id, local.scheduler_owner)
    {
        if local.scheduler_hard {
            let current = crate::mutex_api::inspect(
                &configuration.coordination.mutex_api,
                "router:scheduler",
            )
            .map_err(|_| hard_mutex_unavailable())?
            .filter(|lease| lease.owner == scheduler_owner && lease.claim_id == scheduler_claim)
            .ok_or_else(|| {
                KanbusError::IssueOperation(
                    "stale router scheduler claim; Mutex API lease is no longer current"
                        .to_string(),
                )
            })?;
            let seconds = router_renewal_extension_seconds(
                Some(current.expires_at),
                router_now(),
                ttl_seconds,
            );
            if seconds == 0 {
                return assert_current_router_claim(project_dir, configuration, claim);
            }
            let lease = crate::mutex_api::renew(
                &configuration.coordination.mutex_api,
                "router:scheduler",
                &scheduler_owner,
                &scheduler_claim,
                seconds,
            )
            .map_err(|_| hard_mutex_unavailable())?;
            append_hard_renew_event(project_dir, "router:scheduler", &lease)?;
        } else {
            renew_soft_router_resource(
                root,
                project_dir,
                "router:scheduler",
                &scheduler_owner,
                &scheduler_claim,
                ttl_seconds,
            )?;
        }
    }
    assert_current_router_claim(project_dir, configuration, claim)
}

fn renew_hard_resource_set(
    configuration: &ProjectConfiguration,
    resources: &[String],
    owner: &str,
    claim_id: &str,
    revision: u64,
) -> Result<(), KanbusError> {
    let ttl_seconds = parse_duration_seconds(&configuration.coordination.default_lease_ttl)
        .map_err(KanbusError::Configuration)?;
    for resource in resources {
        let current = crate::mutex_api::inspect(&configuration.coordination.mutex_api, resource)
            .map_err(|_| hard_mutex_unavailable())?
            .filter(|lease| {
                lease.owner == owner && lease.claim_id == claim_id && lease.revision == revision
            })
            .ok_or_else(|| {
                KanbusError::IssueOperation(format!(
                    "stale router hard claim {claim_id} at revision {revision} for resource {resource}"
                ))
            })?;
        let seconds =
            router_renewal_extension_seconds(Some(current.expires_at), router_now(), ttl_seconds);
        if seconds == 0 {
            continue;
        }
        crate::mutex_api::renew(
            &configuration.coordination.mutex_api,
            resource,
            owner,
            claim_id,
            seconds,
        )
        .map_err(|_| hard_mutex_unavailable())?;
        // Match the Python lease keeper: background renewals update only the
        // authoritative API and never race a concurrent shared-state Git write.
    }
    Ok(())
}

fn soft_lease_renewal_extension(
    project_dir: &Path,
    resource: &str,
    owner: &str,
    claim_id: &str,
    ttl_seconds: u64,
) -> Result<u64, KanbusError> {
    let now = router_now();
    let lease = current_soft_router_lease(project_dir, resource, now)?;
    if lease.owner.as_deref() != Some(owner) || lease.claim_id.as_deref() != Some(claim_id) {
        return Ok(0);
    }
    Ok(router_renewal_extension_seconds(
        lease.expires_at,
        now,
        ttl_seconds,
    ))
}

fn current_soft_router_lease(
    project_dir: &Path,
    resource: &str,
    now: DateTime<Utc>,
) -> Result<crate::coordination::CoordinationLease, KanbusError> {
    let events = load_router_events(project_dir)?
        .into_iter()
        .filter(|event| event.issue_id == resource)
        .filter(|event| {
            matches!(
                &event.event_type,
                EventType::CoordinationClaim
                    | EventType::CoordinationRenew
                    | EventType::CoordinationRelease
            )
        })
        .collect::<Vec<_>>();
    Ok(crate::coordination::reduce_coordination_events(
        &events, now,
    ))
}

fn renew_soft_router_resource(
    root: &Path,
    project_dir: &Path,
    resource: &str,
    owner: &str,
    claim_id: &str,
    ttl_seconds: u64,
) -> Result<(), KanbusError> {
    let seconds =
        soft_lease_renewal_extension(project_dir, resource, owner, claim_id, ttl_seconds)?;
    if seconds == 0 {
        return Ok(());
    }
    match run_coordination(
        root,
        CoordinationOperation::Renew {
            resource: resource.to_string(),
            owner: owner.to_string(),
            claim_id: claim_id.to_string(),
            extend: Some(format!("{seconds}s")),
        },
    ) {
        Ok(_) => Ok(()),
        Err(error) if error.to_string().contains("lease owner mismatch") => {
            let lease = current_soft_router_lease(project_dir, resource, router_now())?;
            if lease.owner.as_deref() != Some(owner) || lease.claim_id.as_deref() != Some(claim_id)
            {
                Ok(())
            } else {
                Err(error)
            }
        }
        Err(error) => Err(error),
    }
}

fn router_renewal_extension_seconds(
    current_expiry: Option<DateTime<Utc>>,
    now: DateTime<Utc>,
    ttl_seconds: u64,
) -> u64 {
    crate::coordination::lease_renewal_extension_seconds(current_expiry, now, ttl_seconds)
}

fn stale_claim_error(
    claim: &RouterClaim,
    current_claim: Option<&str>,
    revision: Option<u64>,
) -> KanbusError {
    KanbusError::IssueOperation(format!(
        "stale router claim {} for package {}; current claim is {} at revision {}",
        claim.claim_id,
        claim.issue_id,
        current_claim.unwrap_or("none"),
        revision.unwrap_or_default()
    ))
}

#[allow(clippy::too_many_arguments)]
fn execute_router_adapter(
    root: &Path,
    project_dir: &Path,
    configuration: &ProjectConfiguration,
    profile: &crate::models::IssueRouterProviderConfiguration,
    issue_id: &str,
    package_issue_ids: &[String],
    claim: &RouterClaim,
    checkpoint: Option<(String, u64)>,
    external_renewer: Option<&RouterLeaseRenewalGuard>,
) -> Result<RouterAgentResult, KanbusError> {
    let worktree = create_router_worktree(root, issue_id, claim, checkpoint.as_ref())?;
    append_router_event(
        project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterConversation,
        json!({
            "action":"started", "provider":"codex", "lifecycle":"in_progress",
            "claim_id":claim.claim_id, "revision":claim.revision,
            "worktree":worktree, "branch":format!("codex/router/{issue_id}/r{}", claim.revision),
        }),
    )?;
    set_active_router_state(root, issue_id, &claim.claim_id, None)?;
    let prompt = format!(
        "Complete Kanbus package {issue_id} in this isolated worktree. Only update issue IDs in this package: {}. Current claim {} has logical revision {}. Latest accepted checkpoint: {}. Return one JSON object with keys schema_version, outcome, summary, issue_updates, issue_comments, checkpoint, and artifacts. Put requested comments in issue_comments as {{issue_id, text}}; do not edit project issue files directly. Allowed outcomes are completed, blocked, and retryable_failure.",
        package_issue_ids.join(", "),
        claim.claim_id,
        claim.revision,
        checkpoint
            .as_ref()
            .map(|(reference, revision)| format!(
                "{{\"ref\":\"{reference}\",\"revision\":{revision}}}"
            ))
            .unwrap_or_else(|| "null".to_string())
    );
    let mut command = Command::new(&profile.command);
    command
        .args(&profile.args)
        .arg("exec")
        .arg("--json")
        .arg("--cd")
        .arg(&worktree)
        .arg(prompt)
        .current_dir(&worktree)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command
        .spawn()
        .map_err(|_| KanbusError::IssueOperation("Codex router adapter failed".to_string()))?;
    set_active_router_state(root, issue_id, &claim.claim_id, Some(child.id()))?;
    let stdout_reader = child.stdout.take().map(|mut stream| {
        thread::spawn(move || {
            let mut output = String::new();
            let _ = stream.read_to_string(&mut output);
            output
        })
    });
    let stderr_reader = child.stderr.take().map(|mut stream| {
        thread::spawn(move || {
            let mut output = String::new();
            let _ = stream.read_to_string(&mut output);
            output
        })
    });
    let started = Instant::now();
    let renewal_seconds = parse_duration_seconds(&configuration.coordination.default_lease_ttl)
        .unwrap_or(900)
        .saturating_div(3)
        .max(1);
    let mut next_renewal = Instant::now() + Duration::from_secs(renewal_seconds);
    let output = loop {
        if let Some(renewer) = external_renewer {
            if let Err(error) = renewer.check() {
                let _ = child.kill();
                let _ = child.wait();
                return Err(error);
            }
        }
        if router_cancel_requested(project_dir, issue_id) {
            let _ = child.kill();
            let _ = child.wait();
            let _ = clear_active_router_state(root);
            let state = reduce_router_events(&load_router_events(project_dir)?);
            append_router_event(
                project_dir,
                &format!("router:{issue_id}"),
                EventType::RouterResult,
                json!({
                    "outcome": "cancelled",
                    "claim_id": claim.claim_id,
                    "revision": claim.revision,
                    "checkpoint_ref": state.checkpoints.get(issue_id).map(|(reference, _)| reference),
                }),
            )?;
            return Err(KanbusError::IssueOperation(format!(
                "router package {issue_id} cancelled"
            )));
        }
        if started.elapsed() > Duration::from_secs(3600) {
            let _ = child.kill();
            return Err(KanbusError::IssueOperation(
                "Codex router adapter failed".to_string(),
            ));
        }
        if Instant::now() >= next_renewal {
            let renew_result = if claim.hard && external_renewer.is_some() {
                Ok(())
            } else {
                renew_router_claims(root, project_dir, configuration, claim)
            };
            if let Err(error) = renew_result {
                let _ = child.kill();
                let _ = child.wait();
                return Err(error);
            }
            next_renewal = Instant::now() + Duration::from_secs(renewal_seconds);
        }
        if let Some(status) = child
            .try_wait()
            .map_err(|error| KanbusError::Io(error.to_string()))?
        {
            let stdout = stdout_reader
                .and_then(|reader| reader.join().ok())
                .unwrap_or_default();
            let stderr = stderr_reader
                .and_then(|reader| reader.join().ok())
                .unwrap_or_default();
            let session_id = codex_session_id(&stdout);
            append_router_event(
                project_dir,
                &format!("router:{issue_id}"),
                EventType::RouterConversation,
                json!({
                    "action":"agent_turn", "provider":"codex", "lifecycle":"review",
                    "claim_id":claim.claim_id, "revision":claim.revision,
                    "session_id":session_id, "worktree":worktree,
                    "branch":format!("codex/router/{issue_id}/r{}", claim.revision),
                    "log":redact_router_log(&format!("{stdout}\n{stderr}")),
                }),
            )?;
            if !status.success() {
                return Err(KanbusError::IssueOperation(
                    "Codex router adapter failed".to_string(),
                ));
            }
            break stdout;
        }
        thread::sleep(Duration::from_millis(100));
    };
    let result = parse_router_result(&output)?;
    if result.schema_version != 1 {
        return Err(KanbusError::IssueOperation(
            "Codex router adapter returned invalid result".to_string(),
        ));
    }
    if !["completed", "blocked", "retryable_failure"].contains(&result.outcome.as_str()) {
        return Err(KanbusError::IssueOperation(format!(
            "invalid Codex router outcome \"{}\"",
            result.outcome
        )));
    }
    if result.outcome == "blocked" {
        // The raw agent turn above is deliberately recorded before parsing so
        // malformed output is never discarded.  Once parsing establishes a
        // genuine agent pause, append the authoritative lifecycle overlay so
        // board status and recovery agree that a human reply is awaited.
        append_router_event(
            project_dir,
            &format!("router:{issue_id}"),
            EventType::RouterConversation,
            json!({
                "action":"awaiting_reply", "provider":"codex", "lifecycle":"blocked",
                "claim_id":claim.claim_id, "revision":claim.revision,
                "session_id":codex_session_id(&output), "worktree":worktree,
                "branch":format!("codex/router/{issue_id}/r{}", claim.revision),
            }),
        )?;
    }
    Ok(result)
}

fn codex_session_id(stdout: &str) -> Option<String> {
    for line in stdout.lines() {
        let Ok(value) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        for candidate in [
            value.get("thread_id"),
            value.get("session_id"),
            value.get("conversation_id"),
            value.pointer("/item/thread_id"),
            value.pointer("/item/session_id"),
            value.pointer("/payload/thread_id"),
            value.pointer("/payload/session_id"),
        ] {
            if let Some(id) = candidate
                .and_then(Value::as_str)
                .filter(|id| !id.is_empty())
            {
                return Some(id.to_string());
            }
        }
    }
    None
}

fn redact_router_log(value: &str) -> String {
    // Keep review evidence in Git without copying likely bearer or OpenAI keys.
    value
        .split_whitespace()
        .map(|word| {
            if word.starts_with("sk-") && word.len() > 12 {
                "[REDACTED]"
            } else {
                word
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn parse_router_result(stdout: &str) -> Result<RouterAgentResult, KanbusError> {
    let mut candidates = Vec::<Value>::new();
    if let Ok(value) = serde_json::from_str::<Value>(stdout.trim()) {
        if value.get("outcome").is_some() && value.get("schema_version").is_some() {
            candidates.push(value.clone());
        }
        for key in ["result", "structured_output"] {
            if let Some(item) = value.get(key) {
                if item.get("outcome").is_some() && item.get("schema_version").is_some() {
                    candidates.push(item.clone());
                }
            }
        }
    }
    for line in stdout.lines() {
        let Ok(value) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        if value.get("outcome").is_some() && value.get("schema_version").is_some() {
            candidates.push(value.clone());
        }
        for key in ["result", "structured_output"] {
            if let Some(item) = value.get(key) {
                if item.get("outcome").is_some() && item.get("schema_version").is_some() {
                    candidates.push(item.clone());
                }
            }
        }
        for item_path in ["/item", "/payload/item"] {
            let Some(item) = value.pointer(item_path) else {
                continue;
            };
            if let Some(text) = item.get("text").and_then(Value::as_str) {
                push_codex_result_text(text, &mut candidates);
            }
            if let Some(content) = item.get("content").and_then(Value::as_array) {
                for part in content {
                    if let Some(text) = part.get("text").and_then(Value::as_str) {
                        push_codex_result_text(text, &mut candidates);
                    }
                }
            }
        }
    }
    candidates
        .last()
        .cloned()
        .ok_or_else(|| {
            KanbusError::IssueOperation("Codex router adapter returned invalid JSON".to_string())
        })
        .and_then(|value| {
            serde_json::from_value(normalize_router_artifacts(value)).map_err(|_| {
                KanbusError::IssueOperation(
                    "Codex router adapter returned invalid result".to_string(),
                )
            })
        })
}

/// Normalize advisory artifact metadata without relaxing the result contract.
///
/// A completed agent turn may include a local `path` plus descriptive or
/// verification fields rather than the router's canonical named reference.
/// Artifacts do not authorize issue mutation, so retain canonical entries,
/// translate the known path form, and drop only entries that cannot be safely
/// represented. The rest of the result is still deserialized strictly.
fn normalize_router_artifacts(mut value: Value) -> Value {
    let Some(object) = value.as_object_mut() else {
        return value;
    };
    let Some(artifacts) = object.get("artifacts") else {
        return value;
    };
    let normalized = artifacts
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(normalize_router_artifact)
        .collect::<Vec<_>>();
    object.insert("artifacts".to_string(), Value::Array(normalized));
    value
}

fn normalize_router_artifact(item: &Value) -> Option<Value> {
    let object = item.as_object()?;
    let name = object.get("name").and_then(Value::as_str);
    let reference = object.get("ref").and_then(Value::as_str);
    if let (Some(name), Some(reference)) = (name, reference) {
        if !name.trim().is_empty() && !reference.trim().is_empty() {
            return Some(json!({"name": name, "ref": reference}));
        }
    }
    let path = object.get("path").and_then(Value::as_str)?.trim();
    let name = Path::new(path).file_name()?.to_str()?.trim();
    (!name.is_empty()).then(|| json!({"name": name, "ref": path}))
}

fn push_codex_result_text(text: &str, candidates: &mut Vec<Value>) {
    if let Ok(parsed) = serde_json::from_str::<Value>(text) {
        if parsed.get("outcome").is_some() && parsed.get("schema_version").is_some() {
            candidates.push(parsed);
        }
    }
}

fn router_cancel_requested(project_dir: &Path, issue_id: &str) -> bool {
    let Ok(events) = load_router_events(project_dir) else {
        return false;
    };
    let Some(start) = latest_started_router_event(&events, issue_id) else {
        return false;
    };
    let start_claim = payload_text(start, "claim_id");
    events.iter().any(|event| {
        event.issue_id == format!("router:{issue_id}")
            && matches!(&event.event_type, EventType::RouterControl)
            && payload_text(event, "action") == Some("cancel")
            && match payload_text(event, "claim_id") {
                Some(cancel_claim) => Some(cancel_claim) == start_claim,
                None => {
                    event.occurred_at > start.occurred_at
                        || (event.occurred_at == start.occurred_at
                            && event.event_id > start.event_id)
                }
            }
    })
}

fn set_active_router_state(
    root: &Path,
    issue_id: &str,
    claim_id: &str,
    child_pid: Option<u32>,
) -> Result<(), KanbusError> {
    let mut state = read_local_router_state(root)?;
    state.active_issue_id = Some(issue_id.to_string());
    state.active_claim_id = Some(claim_id.to_string());
    state.active_child_pid = child_pid;
    write_local_router_state(root, &state)
}

fn clear_active_router_state(root: &Path) -> Result<(), KanbusError> {
    let mut state = read_local_router_state(root)?;
    state.active_issue_id = None;
    state.active_claim_id = None;
    state.active_child_pid = None;
    write_local_router_state(root, &state)
}

fn clear_watch_router_state(root: &Path) -> Result<(), KanbusError> {
    let mut state = read_local_router_state(root)?;
    state.watch_pid = None;
    state.stop_requested = false;
    state.scheduler_claim_id = None;
    state.scheduler_owner = None;
    state.scheduler_hard = false;
    write_local_router_state(root, &state)
}

fn release_watch_scheduler_claim(
    root: &Path,
    project_dir: &Path,
    configuration: &ProjectConfiguration,
) -> Result<(), KanbusError> {
    let state = read_local_router_state(root)?;
    let (Some(claim_id), Some(owner)) = (state.scheduler_claim_id, state.scheduler_owner) else {
        return Ok(());
    };
    if state.scheduler_hard {
        crate::mutex_api::release(
            &configuration.coordination.mutex_api,
            "router:scheduler",
            &owner,
            &claim_id,
        )
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
        append_hard_release_event(project_dir, "router:scheduler", &owner, &claim_id)?;
    } else {
        release_soft_router_resource(root, "router:scheduler", &owner, &claim_id)
            .map_err(KanbusError::IssueOperation)?;
    }
    Ok(())
}

fn renew_watch_scheduler(
    root: &Path,
    project_dir: &Path,
    configuration: &ProjectConfiguration,
) -> Result<(), KanbusError> {
    let state = read_local_router_state(root)?;
    let (Some(claim_id), Some(owner)) = (state.scheduler_claim_id, state.scheduler_owner) else {
        return Ok(());
    };
    let ttl_seconds = parse_duration_seconds(&configuration.coordination.default_lease_ttl)
        .map_err(KanbusError::Configuration)?;
    if state.scheduler_hard {
        let current =
            crate::mutex_api::inspect(&configuration.coordination.mutex_api, "router:scheduler")
                .map_err(|_| hard_mutex_unavailable())?
                .filter(|lease| lease.owner == owner && lease.claim_id == claim_id)
                .ok_or_else(|| {
                    KanbusError::IssueOperation(
                        "stale router scheduler claim; Mutex API lease is no longer current"
                            .to_string(),
                    )
                })?;
        let seconds =
            router_renewal_extension_seconds(Some(current.expires_at), router_now(), ttl_seconds);
        if seconds == 0 {
            return Ok(());
        }
        let lease = crate::mutex_api::renew(
            &configuration.coordination.mutex_api,
            "router:scheduler",
            &owner,
            &claim_id,
            seconds,
        )
        .map_err(|_| hard_mutex_unavailable())?;
        append_hard_renew_event(project_dir, "router:scheduler", &lease)
    } else {
        renew_soft_router_resource(
            root,
            project_dir,
            "router:scheduler",
            &owner,
            &claim_id,
            ttl_seconds,
        )?;
        Ok(())
    }
}

fn latest_router_worktree(root: &Path, claim_id: &str) -> Result<PathBuf, KanbusError> {
    let state = read_local_router_state(root)?;
    let issue_id = state
        .active_issue_id
        .filter(|_| state.active_claim_id.as_deref() == Some(claim_id))
        .ok_or_else(|| {
            KanbusError::IssueOperation("router worktree claim is no longer active".to_string())
        })?;
    Ok(router_worktree_path(&issue_id, claim_id))
}

fn publish_router_checkpoint(
    project_dir: &Path,
    configuration: &ProjectConfiguration,
    claim: &RouterClaim,
    checkpoint: Option<&RouterCheckpoint>,
    issue_id: &str,
) -> Result<(String, u64), KanbusError> {
    assert_current_router_claim(project_dir, configuration, claim)?;
    let (reference, revision) = checkpoint
        .map(|checkpoint| (checkpoint.reference.clone(), checkpoint.revision))
        .unwrap_or_else(|| {
            (
                format!("refs/kanbus/router/checkpoints/{issue_id}"),
                claim.revision,
            )
        });
    if revision != claim.revision {
        return Err(KanbusError::IssueOperation(format!(
            "stale router revision {revision} for package {issue_id}; current revision is {}",
            claim.revision
        )));
    }
    crate::coordination::publish_coordination_result(
        project_dir,
        &format!("router:package:{issue_id}:checkpoint"),
        revision,
        &reference,
    )?;
    append_router_event(
        project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterAttempt,
        json!({"action": "checkpoint_accepted", "attempt": 1, "claim_id": claim.claim_id, "revision": revision, "checkpoint_ref": reference, "checkpoint_revision": revision}),
    )?;
    Ok((reference, revision))
}

fn create_router_worktree(
    root: &Path,
    issue_id: &str,
    claim: &RouterClaim,
    checkpoint: Option<&(String, u64)>,
) -> Result<PathBuf, KanbusError> {
    let worktree = router_worktree_path(issue_id, &claim.claim_id);
    if let Some(parent) = worktree.parent() {
        fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    let mut base = "HEAD".to_string();
    if let Some((reference, _)) = checkpoint {
        let local_ref = Command::new("git")
            .args(["rev-parse", "--verify", &format!("{reference}^{{commit}}")])
            .current_dir(root)
            .output()
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        if local_ref.status.success() {
            base = String::from_utf8_lossy(&local_ref.stdout)
                .trim()
                .to_string();
        } else {
            let remote = Command::new("git")
                .args(["remote", "get-url", "origin"])
                .current_dir(root)
                .output()
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            if remote.status.success() {
                let fetched = Command::new("git")
                    .args(["fetch", "--quiet", "origin", reference])
                    .current_dir(root)
                    .output()
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
                if fetched.status.success() {
                    let fetched_head = Command::new("git")
                        .args(["rev-parse", "--verify", "FETCH_HEAD^{commit}"])
                        .current_dir(root)
                        .output()
                        .map_err(|error| KanbusError::Io(error.to_string()))?;
                    if fetched_head.status.success() {
                        base = String::from_utf8_lossy(&fetched_head.stdout)
                            .trim()
                            .to_string();
                    }
                }
            }
        }
    }
    let output = Command::new("git")
        .args(["worktree", "add", "--detach"])
        .arg(&worktree)
        .arg(&base)
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !output.status.success() {
        return Err(KanbusError::IssueOperation(
            "could not create isolated router worktree".to_string(),
        ));
    }
    let branch = format!("codex/router/{issue_id}/r{}", claim.revision);
    let checkout = Command::new("git")
        .args(["checkout", "-b", &branch])
        .current_dir(&worktree)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !checkout.status.success() {
        return Err(KanbusError::IssueOperation(
            "could not create router publication branch".to_string(),
        ));
    }
    Ok(worktree)
}

fn router_worktree_path(issue_id: &str, claim_id: &str) -> PathBuf {
    std::env::temp_dir()
        .join("kanbus-router-worktrees")
        .join(format!("{}-{}", issue_id, claim_id))
}

#[derive(Debug)]
struct PullRequestInfo {
    number: u64,
    head_sha: String,
    url: String,
    branch: String,
}

struct GitHubForge {
    client: reqwest::blocking::Client,
    api_url: String,
    repository: String,
    base_branch: String,
    token: String,
}

impl GitHubForge {
    fn from_router(router: &IssueRouterConfiguration) -> Result<Self, KanbusError> {
        let forge = router
            .forge
            .as_ref()
            .ok_or_else(|| KanbusError::Configuration("router.forge is required".to_string()))?;
        let token = github_token_from_environment_or_gh(&forge.token_env)?;
        Self::from_router_with_token(router, token)
    }

    fn from_router_with_token(
        router: &IssueRouterConfiguration,
        token: String,
    ) -> Result<Self, KanbusError> {
        let forge = router
            .forge
            .as_ref()
            .ok_or_else(|| KanbusError::Configuration("router.forge is required".to_string()))?;
        let client = reqwest::blocking::Client::builder()
            .user_agent("kanbus-issue-router")
            .build()
            .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
        Ok(Self {
            client,
            api_url: forge.api_url.trim_end_matches('/').to_string(),
            repository: forge.repository.clone(),
            base_branch: forge.base_branch.clone(),
            token,
        })
    }

    fn create_pull_request(
        &self,
        issue_id: &str,
        title: &str,
        branch: &str,
    ) -> Result<PullRequestInfo, KanbusError> {
        let forge_url = format!("{}/repos/{}/pulls", self.api_url, self.repository);
        let response = self
            .client
            .post(forge_url)
            .bearer_auth(&self.token)
            .json(&json!({
                "title": format!("[{issue_id}] {title}"),
                "head": branch,
                "base": self.base_branch,
                "body": format!("Kanbus package: {issue_id}"),
                // Router output is never an automatic acceptance decision.
                // A draft makes every agent checkpoint reviewable before it can
                // be merged, including incomplete or uncertain work.
                "draft": true,
            }))
            .send()
            .map_err(|error| {
                KanbusError::IssueOperation(format!("GitHub pull request creation failed: {error}"))
            })?;
        if !response.status().is_success() {
            return Err(KanbusError::IssueOperation(format!(
                "GitHub pull request creation failed with status {}",
                response.status()
            )));
        }
        let payload: Value = response
            .json()
            .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
        Ok(PullRequestInfo {
            number: payload
                .get("number")
                .and_then(Value::as_u64)
                .ok_or_else(|| {
                    KanbusError::IssueOperation(
                        "GitHub response omitted pull request number".to_string(),
                    )
                })?,
            head_sha: payload
                .pointer("/head/sha")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            url: payload
                .get("html_url")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            branch: payload
                .pointer("/head/ref")
                .and_then(Value::as_str)
                .unwrap_or(branch)
                .to_string(),
        })
    }

    fn get_pull_request(&self, number: u64) -> Result<PullRequestInfo, KanbusError> {
        let response = self
            .client
            .get(format!(
                "{}/repos/{}/pulls/{number}",
                self.api_url, self.repository
            ))
            .bearer_auth(&self.token)
            .header("Accept", "application/vnd.github+json")
            .send()
            .map_err(|error| {
                KanbusError::IssueOperation(format!("GitHub pull request polling failed: {error}"))
            })?;
        if !response.status().is_success() {
            return Err(KanbusError::IssueOperation(format!(
                "GitHub pull request polling failed with status {}",
                response.status()
            )));
        }
        let payload: Value = response
            .json()
            .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
        Ok(PullRequestInfo {
            number,
            head_sha: payload
                .pointer("/head/sha")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            url: payload
                .get("html_url")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            branch: payload
                .pointer("/head/ref")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
        })
    }

    fn list_pull_requests(&self) -> Result<Vec<Value>, KanbusError> {
        let response = self
            .client
            .get(format!(
                "{}/repos/{}/pulls?state=all&per_page=100",
                self.api_url, self.repository
            ))
            .bearer_auth(&self.token)
            .header("Accept", "application/vnd.github+json")
            .send()
            .map_err(|error| {
                KanbusError::IssueOperation(format!("GitHub pull request polling failed: {error}"))
            })?;
        if !response.status().is_success() {
            return Err(KanbusError::IssueOperation(format!(
                "GitHub pull request polling failed with status {}",
                response.status()
            )));
        }
        response
            .json()
            .map_err(|error| KanbusError::IssueOperation(error.to_string()))
    }

    fn list_pull_request_reviews(&self, number: u64) -> Result<Vec<Value>, KanbusError> {
        let response = self
            .client
            .get(format!(
                "{}/repos/{}/pulls/{number}/reviews?per_page=100",
                self.api_url, self.repository
            ))
            .bearer_auth(&self.token)
            .header("Accept", "application/vnd.github+json")
            .send()
            .map_err(|error| {
                KanbusError::IssueOperation(format!("GitHub pull request polling failed: {error}"))
            })?;
        if !response.status().is_success() {
            return Err(KanbusError::IssueOperation(format!(
                "GitHub pull request polling failed with status {}",
                response.status()
            )));
        }
        response
            .json()
            .map_err(|error| KanbusError::IssueOperation(error.to_string()))
    }

    fn list_check_runs(&self, head_sha: &str) -> Result<Vec<Value>, KanbusError> {
        let response = self
            .client
            .get(format!(
                "{}/repos/{}/commits/{head_sha}/check-runs?per_page=100",
                self.api_url, self.repository
            ))
            .bearer_auth(&self.token)
            .header("Accept", "application/vnd.github+json")
            .send()
            .map_err(|error| {
                KanbusError::IssueOperation(format!("GitHub check-run polling failed: {error}"))
            })?;
        if !response.status().is_success() {
            return Err(KanbusError::IssueOperation(format!(
                "GitHub check-run polling failed with status {}",
                response.status()
            )));
        }
        let payload: Value = response
            .json()
            .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
        Ok(payload
            .get("check_runs")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default())
    }
}

/// Resolve a GitHub credential without making a user copy a credential out of
/// an already authenticated GitHub CLI.  The configured variable remains the
/// deterministic override for CI and non-interactive workers.
fn github_token_from_environment_or_gh(token_env: &str) -> Result<String, KanbusError> {
    if let Ok(token) = std::env::var(token_env) {
        if !token.trim().is_empty() {
            return Ok(token);
        }
    }
    let output = Command::new("gh")
        .args(["auth", "token"])
        .output()
        .map_err(|_| {
            KanbusError::IssueOperation(format!(
                "GitHub authentication is unavailable: set {token_env} or run gh auth login"
            ))
        })?;
    if output.status.success() {
        let token = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !token.is_empty() {
            return Ok(token);
        }
    }
    Err(KanbusError::IssueOperation(format!(
        "GitHub authentication is unavailable: set {token_env} or run gh auth login"
    )))
}

/// Reconcile GitHub's current PR/review state into immutable, normalized forge events.
/// Only PRs already recorded by the router are considered, and their number/head are
/// checked before an event is accepted.
fn reconcile_github_pull_requests(
    root: &Path,
    project_dir: &Path,
    router: &IssueRouterConfiguration,
    forge: &GitHubForge,
    configuration: &ProjectConfiguration,
) -> Result<(), KanbusError> {
    let events = load_router_events(project_dir)?;
    let state = reduce_router_events(&events);
    let pulls = forge.list_pull_requests()?;
    let mut known = state
        .pull_requests
        .iter()
        .map(|(issue, (number, head))| (issue.clone(), *number, head.clone()))
        .collect::<Vec<_>>();
    known.sort_by(|left, right| left.0.cmp(&right.0));
    for (issue_id, recorded_number, recorded_head) in known {
        let Some(pull) = pulls
            .iter()
            .find(|pull| pull.get("number").and_then(Value::as_u64) == Some(recorded_number))
        else {
            continue;
        };
        let head_sha = pull
            .pointer("/head/sha")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let repository = router
            .forge
            .as_ref()
            .expect("validated forge")
            .repository
            .as_str();
        let base_repository = pull.pointer("/base/repo/full_name").and_then(Value::as_str);
        if head_sha.is_empty() || base_repository.is_some_and(|name| name != repository) {
            continue;
        }
        let merged = pull.get("merged").and_then(Value::as_bool).unwrap_or(false);
        let closed = pull.get("state").and_then(Value::as_str) == Some("closed");
        let action = if merged || closed {
            Some("closed")
        } else if head_sha != recorded_head {
            Some("synchronize")
        } else {
            let reviews = forge.list_pull_request_reviews(recorded_number)?;
            reduce_pull_request_reviews(&reviews, head_sha)
        };
        if let Some(action) = action {
            let already_reduced = events.iter().any(|event| {
                event.issue_id == format!("router:{issue_id}")
                    && matches!(&event.event_type, EventType::RouterForge)
                    && payload_text(event, "action") == Some(action)
                    && payload_text(event, "head_sha") == Some(head_sha)
                    && (action != "closed"
                        || event.payload.get("merged").and_then(Value::as_bool) == Some(merged))
            });
            if !already_reduced {
                assert_current_watch_scheduler_claim(root, project_dir, configuration)?;
                let mut payload = json!({
                    "action": action,
                    "repository": router.forge.as_ref().expect("validated forge").repository,
                    "number": recorded_number,
                    "head_sha": head_sha,
                });
                if action == "closed" {
                    payload["merged"] = json!(merged);
                    payload["approved"] = json!(events.iter().any(|candidate| {
                        candidate.issue_id == format!("router:{issue_id}")
                            && matches!(&candidate.event_type, EventType::RouterForge)
                            && payload_text(candidate, "action") == Some("approved")
                            && payload_text(candidate, "head_sha") == Some(head_sha)
                    }));
                }
                append_router_event(
                    project_dir,
                    &format!("router:{issue_id}"),
                    EventType::RouterForge,
                    payload,
                )?;
            }
        }
        reconcile_github_check_runs(
            root,
            project_dir,
            forge,
            configuration,
            &issue_id,
            recorded_number,
            head_sha,
        )?;
    }
    Ok(())
}

fn reduce_pull_request_reviews<'a>(reviews: &'a [Value], head_sha: &str) -> Option<&'static str> {
    let mut latest_by_reviewer = BTreeMap::<String, (&'a Value, String, u64)>::new();
    for review in reviews {
        if review
            .get("commit_id")
            .and_then(Value::as_str)
            .is_some_and(|sha| sha != head_sha)
        {
            continue;
        }
        let reviewer = review
            .pointer("/user/login")
            .and_then(Value::as_str)
            .map(str::to_string)
            .or_else(|| {
                review
                    .pointer("/user/id")
                    .and_then(Value::as_u64)
                    .map(|id| format!("id:{id}"))
            });
        let Some(reviewer) = reviewer else {
            continue;
        };
        let submitted_at = review
            .get("submitted_at")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let id = review.get("id").and_then(Value::as_u64).unwrap_or_default();
        let should_replace =
            latest_by_reviewer
                .get(&reviewer)
                .is_none_or(|(_, previous_time, previous_id)| {
                    (&submitted_at, id) > (previous_time, *previous_id)
                });
        if should_replace {
            latest_by_reviewer.insert(reviewer, (review, submitted_at, id));
        }
    }
    let latest_states = latest_by_reviewer
        .values()
        .filter_map(|(review, _, _)| review.get("state").and_then(Value::as_str));
    let states = latest_states.collect::<Vec<_>>();
    if states.contains(&"CHANGES_REQUESTED") {
        Some("requested_changes")
    } else if states.contains(&"APPROVED") {
        Some("approved")
    } else {
        None
    }
}

#[allow(clippy::too_many_arguments)]
fn reconcile_github_check_runs(
    root: &Path,
    project_dir: &Path,
    forge: &GitHubForge,
    configuration: &ProjectConfiguration,
    issue_id: &str,
    number: u64,
    head_sha: &str,
) -> Result<(), KanbusError> {
    let mut latest_by_name = BTreeMap::<String, Value>::new();
    for check in forge.list_check_runs(head_sha)? {
        if check.get("status").and_then(Value::as_str) != Some("completed")
            || check
                .get("head_sha")
                .and_then(Value::as_str)
                .is_some_and(|sha| sha != head_sha)
            || !matches!(
                check.get("conclusion").and_then(Value::as_str),
                Some("success" | "failure" | "cancelled" | "timed_out" | "action_required")
            )
        {
            continue;
        }
        let name = check
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or("check")
            .to_string();
        let update_key = |value: &Value| {
            value
                .get("completed_at")
                .and_then(Value::as_str)
                .or_else(|| value.get("updated_at").and_then(Value::as_str))
                .unwrap_or_default()
                .to_string()
        };
        let replace = latest_by_name
            .get(&name)
            .is_none_or(|previous| update_key(&check) > update_key(previous));
        if replace {
            latest_by_name.insert(name, check);
        }
    }
    if latest_by_name.is_empty() {
        return Ok(());
    }
    let mut has_failure = false;
    for check in latest_by_name.values() {
        let conclusion = check
            .get("conclusion")
            .and_then(Value::as_str)
            .unwrap_or_default();
        has_failure |= conclusion != "success";
        let check_id = check.get("id").and_then(Value::as_u64).unwrap_or_default();
        let forge_event_id = format!("check-run:{check_id}:{head_sha}");
        if check_id == 0 {
            continue;
        }
        assert_current_watch_scheduler_claim(root, project_dir, configuration)?;
        crate::router::record_router_check_run_event(
            root,
            &forge_event_id,
            number,
            head_sha,
            conclusion,
        )?;
    }
    let action = if has_failure {
        "checks_failed"
    } else {
        "checks_passed"
    };
    let already_reduced = load_router_events(project_dir)?.iter().any(|event| {
        event.issue_id == format!("router:{issue_id}")
            && matches!(&event.event_type, EventType::RouterForge)
            && payload_text(event, "action") == Some(action)
            && payload_text(event, "head_sha") == Some(head_sha)
    });
    if !already_reduced {
        assert_current_watch_scheduler_claim(root, project_dir, configuration)?;
        append_router_event(
            project_dir,
            &format!("router:{issue_id}"),
            EventType::RouterForge,
            json!({"action": action, "number": number, "head_sha": head_sha}),
        )?;
    }
    Ok(())
}

fn assert_current_watch_scheduler_claim(
    root: &Path,
    project_dir: &Path,
    configuration: &ProjectConfiguration,
) -> Result<(), KanbusError> {
    let state = read_local_router_state(root)?;
    let (Some(claim_id), Some(owner)) = (state.scheduler_claim_id, state.scheduler_owner) else {
        return Err(KanbusError::IssueOperation(
            "stale router scheduler claim; no current local lease is recorded".to_string(),
        ));
    };
    if state.scheduler_hard {
        let lease =
            crate::mutex_api::inspect(&configuration.coordination.mutex_api, "router:scheduler")
                .map_err(|_| hard_mutex_unavailable())?;
        if !lease.is_some_and(|lease| lease.owner == owner && lease.claim_id == claim_id) {
            return Err(KanbusError::IssueOperation(
                "stale router scheduler claim; Mutex API lease is no longer current".to_string(),
            ));
        }
        return Ok(());
    }
    let events = load_router_events(project_dir)?;
    let scheduler_events = events
        .into_iter()
        .filter(|event| event.issue_id == "router:scheduler")
        .filter(|event| {
            matches!(
                &event.event_type,
                EventType::CoordinationClaim
                    | EventType::CoordinationRenew
                    | EventType::CoordinationRelease
            )
        })
        .collect::<Vec<_>>();
    let lease = crate::coordination::reduce_coordination_events(&scheduler_events, router_now());
    if !lease.is_active()
        || lease.owner.as_deref() != Some(owner.as_str())
        || lease.claim_id.as_deref() != Some(claim_id.as_str())
    {
        return Err(KanbusError::IssueOperation(
            "stale router scheduler claim; shared coordination lease is no longer current"
                .to_string(),
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn publish_router_branch(
    root: &Path,
    project_dir: &Path,
    configuration: &ProjectConfiguration,
    router: &IssueRouterConfiguration,
    claim: &RouterClaim,
    worktree: &Path,
    issue_id: &str,
    branch: &str,
    revision: u64,
) -> Result<PublishedRouterRef, KanbusError> {
    let project_relative = configured_project_directory(root)?;
    let excluded_issues = format!(":(exclude){}/issues", project_relative.display());
    let excluded_events = format!(":(exclude){}/events", project_relative.display());
    let add = Command::new("git")
        .args(["add", "-A", "--", ".", &excluded_issues, &excluded_events])
        .current_dir(worktree)
        .status()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !add.success() {
        return Err(KanbusError::IssueOperation(
            "could not stage router checkpoint".to_string(),
        ));
    }
    let commit = Command::new("git")
        .args([
            "-c",
            "user.name=Kanbus Issue Router",
            "-c",
            "user.email=kanbus-router@localhost",
            "commit",
            "--allow-empty",
            "-m",
            &format!("[router] {issue_id} revision {revision}"),
        ])
        .current_dir(worktree)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !commit.status.success() {
        return Err(KanbusError::IssueOperation(
            "could not commit router checkpoint".to_string(),
        ));
    }
    let remote = Command::new("git")
        .args(["remote", "get-url", "origin"])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let rev = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(worktree)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !rev.status.success() {
        return Err(KanbusError::IssueOperation(
            "could not resolve router checkpoint".to_string(),
        ));
    }
    let commit_sha = String::from_utf8_lossy(&rev.stdout).trim().to_string();
    if commit_sha.is_empty() {
        return Err(KanbusError::IssueOperation(
            "could not resolve router checkpoint".to_string(),
        ));
    }
    let remote_published = remote.status.success();
    let mut previous_remote_sha = String::new();
    if remote_published {
        assert_current_router_claim(project_dir, configuration, claim)?;
        let remote_ref = format!("refs/heads/{branch}");
        let existing = Command::new("git")
            .args(["ls-remote", "--heads", "origin", &remote_ref])
            .current_dir(root)
            .output()
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        if !existing.status.success() {
            return Err(KanbusError::IssueOperation(
                "could not inspect remote router branch".to_string(),
            ));
        }
        previous_remote_sha = String::from_utf8_lossy(&existing.stdout)
            .split_whitespace()
            .next()
            .unwrap_or("")
            .to_string();
        assert_current_router_claim(project_dir, configuration, claim)?;
        push_router_branch_with_fence(
            root,
            worktree,
            &remote_ref,
            &previous_remote_sha,
            &commit_sha,
            || assert_current_router_claim(project_dir, configuration, claim),
            || assert_current_router_claim(project_dir, configuration, claim),
        )?;
    }
    let _ = issue_id;
    let _ = router;
    let _ = revision;
    Ok(PublishedRouterRef {
        reference: format!("refs/heads/{branch}"),
        pushed_sha: commit_sha,
        previous_remote_sha,
        previous_local_sha: None,
        remote_published,
    })
}

fn push_router_branch_with_fence(
    root: &Path,
    worktree: &Path,
    remote_ref: &str,
    previous_remote_sha: &str,
    pushed_sha: &str,
    before_push: impl FnOnce() -> Result<(), KanbusError>,
    after_push: impl FnOnce() -> Result<(), KanbusError>,
) -> Result<(), KanbusError> {
    before_push()?;
    let lease = format!("--force-with-lease={remote_ref}:{previous_remote_sha}");
    let push_ref = format!("{pushed_sha}:{remote_ref}");
    let push = Command::new("git")
        .args(["push", &lease, "origin", &push_ref])
        .current_dir(worktree)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !push.status.success() {
        return Err(KanbusError::IssueOperation(
            "could not publish router branch".to_string(),
        ));
    }
    if let Err(error) = after_push() {
        return match rollback_router_branch_if_unchanged(
            root,
            remote_ref,
            pushed_sha,
            previous_remote_sha,
        ) {
            Ok(()) => Err(error),
            Err(rollback_error) => Err(KanbusError::IssueOperation(format!(
                "{error}; {rollback_error}"
            ))),
        };
    }
    Ok(())
}

/// Restore/delete a branch after a post-push fence failure only if it still points
/// at this run's pushed commit. If another writer advanced it, leave it untouched
/// and require inspection rather than clobbering their publication.
fn rollback_router_branch_if_unchanged(
    root: &Path,
    remote_ref: &str,
    pushed_sha: &str,
    previous_remote_sha: &str,
) -> Result<(), KanbusError> {
    rollback_remote_router_ref_if_unchanged(root, remote_ref, pushed_sha, previous_remote_sha)
}

fn rollback_remote_router_ref_if_unchanged(
    root: &Path,
    remote_ref: &str,
    pushed_sha: &str,
    previous_remote_sha: &str,
) -> Result<(), KanbusError> {
    let current = Command::new("git")
        .args(["ls-remote", "--refs", "origin", remote_ref])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !current.status.success() {
        return Err(KanbusError::IssueOperation(
            "router ref rollback could not inspect the remote; operator inspection may be required"
                .to_string(),
        ));
    }
    let current_sha = String::from_utf8_lossy(&current.stdout)
        .split_whitespace()
        .next()
        .unwrap_or("")
        .to_string();
    if current_sha != pushed_sha {
        return Err(KanbusError::IssueOperation(
            "router ref advanced after claim loss; rollback was skipped and operator inspection may be required"
                .to_string(),
        ));
    }
    let lease = format!("--force-with-lease={remote_ref}:{pushed_sha}");
    let rollback = if previous_remote_sha.is_empty() {
        Command::new("git")
            .args(["push", &lease, "origin", &format!(":{remote_ref}")])
            .current_dir(root)
            .output()
    } else {
        Command::new("git")
            .args([
                "push",
                &lease,
                "origin",
                &format!("{previous_remote_sha}:{remote_ref}"),
            ])
            .current_dir(root)
            .output()
    }
    .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !rollback.status.success() {
        return Err(KanbusError::IssueOperation(
            "router ref rollback lost its compare-and-swap race; operator inspection may be required"
                .to_string(),
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn record_router_pull_response(
    project_dir: &Path,
    configuration: &ProjectConfiguration,
    claim: &RouterClaim,
    issue_id: &str,
    repository: &str,
    branch: &str,
    existing_pr: bool,
    pull: &PullRequestInfo,
    published_refs: &[&PublishedRouterRef],
) -> Result<EventRecord, KanbusError> {
    if let Err(fence_error) = assert_current_router_claim(project_dir, configuration, claim) {
        return match rollback_published_router_refs(project_dir, published_refs) {
            Ok(()) => Err(fence_error),
            Err(rollback_error) => Err(KanbusError::IssueOperation(format!(
                "{fence_error}; {rollback_error}"
            ))),
        };
    }
    append_router_event(
        project_dir,
        &format!("router:{issue_id}"),
        EventType::RouterForge,
        json!({
            "action": if existing_pr { "synchronize" } else { "opened" },
            "repository": repository,
            "number": pull.number,
            "head_sha": pull.head_sha,
            "branch": branch,
            "url": pull.url,
        }),
    )
}

fn rollback_published_router_refs(
    root: &Path,
    published_refs: &[&PublishedRouterRef],
) -> Result<(), KanbusError> {
    let mut failures = Vec::new();
    for published in published_refs {
        if published.remote_published {
            if let Err(error) = rollback_remote_router_ref_if_unchanged(
                root,
                &published.reference,
                &published.pushed_sha,
                &published.previous_remote_sha,
            ) {
                failures.push(error.to_string());
            }
        }
        if let Some(previous_local_sha) = published.previous_local_sha.as_deref() {
            if let Err(error) = rollback_local_router_ref_if_unchanged(
                root,
                &published.reference,
                &published.pushed_sha,
                previous_local_sha,
            ) {
                failures.push(error.to_string());
            }
        }
    }
    if failures.is_empty() {
        Ok(())
    } else {
        Err(KanbusError::IssueOperation(failures.join("; ")))
    }
}

fn rollback_local_router_ref_if_unchanged(
    root: &Path,
    reference: &str,
    pushed_sha: &str,
    previous_local_sha: &str,
) -> Result<(), KanbusError> {
    let current = Command::new("git")
        .args(["show-ref", "--verify", "--hash", reference])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let current_sha = if current.status.success() {
        String::from_utf8_lossy(&current.stdout).trim().to_string()
    } else {
        String::new()
    };
    if current_sha != pushed_sha {
        return Err(KanbusError::IssueOperation(format!(
            "local router ref {reference} advanced after claim loss; rollback was skipped and operator inspection may be required"
        )));
    }
    let rollback = if previous_local_sha.is_empty() {
        Command::new("git")
            .args(["update-ref", "-d", reference, pushed_sha])
            .current_dir(root)
            .output()
    } else {
        Command::new("git")
            .args(["update-ref", reference, previous_local_sha, pushed_sha])
            .current_dir(root)
            .output()
    }
    .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !rollback.status.success() {
        return Err(KanbusError::IssueOperation(format!(
            "local router ref {reference} rollback lost its compare-and-swap race; operator inspection may be required"
        )));
    }
    Ok(())
}

fn publish_router_checkpoint_ref(
    root: &Path,
    project_dir: &Path,
    configuration: &ProjectConfiguration,
    claim: &RouterClaim,
    reference: &str,
    commit_sha: &str,
) -> Result<PublishedRouterRef, KanbusError> {
    if !reference.starts_with("refs/kanbus/router/") {
        return Err(KanbusError::IssueOperation(
            "router checkpoint ref is outside the Kanbus namespace".to_string(),
        ));
    }
    assert_current_router_claim(project_dir, configuration, claim)?;
    let remote = Command::new("git")
        .args(["remote", "get-url", "origin"])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let has_remote = remote.status.success();
    let previous_remote = if has_remote {
        let listed = Command::new("git")
            .args(["ls-remote", "--refs", "origin", reference])
            .current_dir(root)
            .output()
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        if !listed.status.success() {
            return Err(KanbusError::IssueOperation(
                "could not inspect remote router checkpoint".to_string(),
            ));
        }
        String::from_utf8_lossy(&listed.stdout)
            .split_whitespace()
            .next()
            .unwrap_or("")
            .to_string()
    } else {
        String::new()
    };
    let local = Command::new("git")
        .args(["show-ref", "--verify", "--hash", reference])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    let previous_local = if local.status.success() {
        String::from_utf8_lossy(&local.stdout).trim().to_string()
    } else {
        String::new()
    };
    let update = Command::new("git")
        .args(["update-ref", reference, commit_sha])
        .current_dir(root)
        .output()
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    if !update.status.success() {
        return Err(KanbusError::IssueOperation(
            "could not update router checkpoint ref".to_string(),
        ));
    }
    if has_remote {
        assert_current_router_claim(project_dir, configuration, claim)?;
        let lease = format!("--force-with-lease={reference}:{previous_remote}");
        let push = Command::new("git")
            .args([
                "push",
                &lease,
                "origin",
                &format!("{reference}:{reference}"),
            ])
            .current_dir(root)
            .output()
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        if !push.status.success() {
            if previous_local.is_empty() {
                let _ = Command::new("git")
                    .args(["update-ref", "-d", reference])
                    .current_dir(root)
                    .output();
            } else {
                let _ = Command::new("git")
                    .args(["update-ref", reference, &previous_local])
                    .current_dir(root)
                    .output();
            }
            return Err(KanbusError::IssueOperation(
                "could not publish router checkpoint ref".to_string(),
            ));
        }
        if let Err(error) = assert_current_router_claim(project_dir, configuration, claim) {
            let restore_local = if previous_local.is_empty() {
                Command::new("git")
                    .args(["update-ref", "-d", reference])
                    .current_dir(root)
                    .output()
            } else {
                Command::new("git")
                    .args(["update-ref", reference, &previous_local])
                    .current_dir(root)
                    .output()
            };
            let _ = restore_local;
            let rollback_lease = format!("--force-with-lease={reference}:{commit_sha}");
            let rollback = if previous_remote.is_empty() {
                Command::new("git")
                    .args(["push", &rollback_lease, "--delete", "origin", reference])
                    .current_dir(root)
                    .output()
            } else {
                Command::new("git")
                    .args([
                        "push",
                        &rollback_lease,
                        "origin",
                        &format!("{previous_remote}:{reference}"),
                    ])
                    .current_dir(root)
                    .output()
            };
            let _ = rollback;
            return Err(error);
        }
    }
    Ok(PublishedRouterRef {
        reference: reference.to_string(),
        pushed_sha: commit_sha.to_string(),
        previous_remote_sha: previous_remote,
        previous_local_sha: Some(previous_local),
        remote_published: has_remote,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Output;

    #[test]
    fn router_git_output_times_out_a_stalled_child() {
        let mut command = Command::new("sh");
        command.args(["-c", "sleep 1"]);
        let error = router_git_output_with_timeout(command, Duration::from_millis(10))
            .expect_err("stalled router Git child must time out");
        assert!(error.to_string().contains("router Git operation timed out"));
    }

    #[test]
    fn router_transition_path_uses_configured_intermediate_status() {
        let mut configuration = crate::config::default_project_configuration();
        configuration
            .workflows
            .get_mut("default")
            .expect("default workflow")
            .insert("in_progress".to_string(), vec!["review".to_string()]);

        assert_eq!(
            router_status_transition_path(&configuration, "task", "open", "review")
                .expect("legal workflow path"),
            vec!["in_progress".to_string(), "review".to_string()]
        );
    }

    #[test]
    fn hard_lease_renewer_runs_while_start_publication_is_delayed() {
        let renewals = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let renewal_counter = Arc::clone(&renewals);
        let mut guard = RouterLeaseRenewalGuard::start(Duration::from_millis(15), move || {
            renewal_counter.fetch_add(1, Ordering::SeqCst);
            Ok(())
        })
        .expect("initial hard-lease renewal succeeds");
        assert_eq!(
            renewals.load(Ordering::SeqCst),
            1,
            "first hard renewal must happen synchronously before delayed publication"
        );

        // Model a slow shared-state fetch/commit/push before the adapter starts.
        thread::sleep(Duration::from_millis(80));
        guard.check().expect("short-TTL renewer remains healthy");
        guard.stop().expect("stop cleanly");
        assert!(
            renewals.load(Ordering::SeqCst) >= 2,
            "hard lease renewals must continue during delayed start publication"
        );
    }

    #[test]
    fn hard_lease_renewer_starts_during_capacity_acquisition() {
        let resources = Arc::new(Mutex::new(vec!["router:issue:kbs-test".to_string()]));
        let renewed_resources = Arc::new(Mutex::new(Vec::<Vec<String>>::new()));
        let callback_resources = Arc::clone(&resources);
        let callback_log = Arc::clone(&renewed_resources);
        let mut guard = RouterLeaseRenewalGuard::start(Duration::from_millis(10), move || {
            let current = callback_resources.lock().expect("resource lock").clone();
            callback_log.lock().expect("renewal log").push(current);
            Ok(())
        })
        .expect("start renewer immediately after primary claim");

        // Capacity acquisition can include a full contention interval. The
        // primary issue lease must remain renewed while that acquisition runs.
        thread::sleep(Duration::from_millis(35));
        resources
            .lock()
            .expect("resource lock")
            .push("router:capacity:project:0".to_string());
        thread::sleep(Duration::from_millis(20));
        guard
            .check()
            .expect("renewer remains healthy during acquisition");
        guard.stop().expect("stop renewal guard");

        let observations = renewed_resources.lock().expect("renewal log");
        assert!(observations.len() >= 3, "renewals cover slow acquisition");
        assert!(observations
            .iter()
            .any(|observed| { observed == &["router:issue:kbs-test".to_string()] }));
        assert!(observations
            .iter()
            .any(|observed| { observed.contains(&"router:capacity:project:0".to_string()) }));
    }

    #[test]
    fn hard_capacity_claim_preserves_package_revision() {
        use std::io::{Read as _, Write as _};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock mutex API");
        let address = listener.local_addr().expect("mock address");
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept acquire request");
            let mut request = Vec::new();
            let mut buffer = [0_u8; 4096];
            let body_start = loop {
                let read = stream.read(&mut buffer).expect("read request");
                assert!(read > 0, "request connection remains open");
                request.extend_from_slice(&buffer[..read]);
                if let Some(position) = request.windows(4).position(|part| part == b"\r\n\r\n") {
                    break position + 4;
                }
            };
            let headers = String::from_utf8_lossy(&request[..body_start]);
            let content_length = headers
                .lines()
                .find_map(|line| {
                    let (name, value) = line.split_once(':')?;
                    name.eq_ignore_ascii_case("content-length")
                        .then(|| value.trim().parse::<usize>().ok())
                        .flatten()
                })
                .unwrap_or_default();
            while request.len() < body_start + content_length {
                let read = stream.read(&mut buffer).expect("read request body");
                assert!(read > 0, "request body is complete");
                request.extend_from_slice(&buffer[..read]);
            }
            let body: Value =
                serde_json::from_slice(&request[body_start..body_start + content_length])
                    .expect("parse acquire body");
            let now = Utc::now().timestamp();
            let response = json!({
                "resource": "router:capacity:project:project:0",
                "owner": body["owner"],
                "claim_id": body["claim_id"],
                "revision": body["revision"],
                "claimed_at": now,
                "expires_at": now + 300,
            });
            let response = serde_json::to_vec(&response).expect("serialize lease response");
            write!(
                stream,
                "HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                response.len()
            )
            .expect("write response headers");
            stream.write_all(&response).expect("write lease response");
            body
        });

        let temp = tempfile::tempdir().expect("temporary project");
        let configuration = crate::models::CoordinationConfiguration {
            mutex_api: crate::models::MutexApiConfiguration {
                endpoint: Some(format!("http://{address}")),
                bearer_token: Some("test-token".to_string()),
            },
            ..crate::models::CoordinationConfiguration::default()
        };
        let mut acquired = Vec::new();
        assert!(acquire_capacity_slot(
            &configuration,
            temp.path(),
            &mut acquired,
            "project",
            "project".to_string(),
            1,
            0,
            None,
            9,
            "worker",
            "claim-r9",
            300,
            0,
        )
        .expect("acquire capacity slot"));
        let request = server.join().expect("mock request");
        assert_eq!(request["revision"], 9);
        // acquire_capacity_slot persists directly under its project_dir.
        let events_dir = events_dir_for_project(temp.path());
        let event_path = fs::read_dir(events_dir)
            .expect("read hard lease audit")
            .next()
            .expect("one audit event")
            .expect("read audit entry")
            .path();
        let event: EventRecord =
            serde_json::from_slice(&fs::read(event_path).expect("read audit event"))
                .expect("parse audit event");
        assert_eq!(event.payload["revision"], 9);
    }

    #[test]
    fn hard_claim_is_tracked_before_audit_failure_and_cleanup_releases_the_api_lease() {
        use std::io::{Read as _, Write as _};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock mutex API");
        let address = listener.local_addr().expect("mock address");
        let server = thread::spawn(move || {
            let mut methods = Vec::new();
            for _ in 0..2 {
                let (mut stream, _) = listener.accept().expect("accept API request");
                let mut request = Vec::new();
                let mut buffer = [0_u8; 4096];
                let body_start = loop {
                    let read = stream.read(&mut buffer).expect("read request");
                    assert!(read > 0, "request connection remains open");
                    request.extend_from_slice(&buffer[..read]);
                    if let Some(position) = request.windows(4).position(|part| part == b"\r\n\r\n")
                    {
                        break position + 4;
                    }
                };
                let headers = String::from_utf8_lossy(&request[..body_start]);
                let method = headers
                    .lines()
                    .next()
                    .and_then(|line| line.split_whitespace().next())
                    .expect("HTTP method")
                    .to_string();
                let content_length = headers
                    .lines()
                    .find_map(|line| {
                        let (name, value) = line.split_once(':')?;
                        name.eq_ignore_ascii_case("content-length")
                            .then(|| value.trim().parse::<usize>().ok())
                            .flatten()
                    })
                    .unwrap_or_default();
                while request.len() < body_start + content_length {
                    let read = stream.read(&mut buffer).expect("read request body");
                    assert!(read > 0, "request body is complete");
                    request.extend_from_slice(&buffer[..read]);
                }
                if method == "POST" {
                    let now = Utc::now().timestamp();
                    let body = serde_json::to_vec(&json!({
                        "resource": "router:capacity:project:project:0",
                        "owner": "worker",
                        "claim_id": "claim-audit-failure",
                        "revision": 3,
                        "claimed_at": now,
                        "expires_at": now + 300,
                    }))
                    .expect("serialize acquired lease");
                    write!(
                        stream,
                        "HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                        body.len()
                    )
                    .expect("write acquire response headers");
                    stream.write_all(&body).expect("write acquire response");
                } else {
                    write!(
                        stream,
                        "HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                    .expect("write release response");
                }
                methods.push(method);
            }
            methods
        });

        let temp = tempfile::tempdir().expect("temporary directory");
        let project_file = temp.path().join("project-not-directory");
        fs::write(&project_file, "not a project directory").expect("make audit target invalid");
        let configuration = crate::models::CoordinationConfiguration {
            mutex_api: crate::models::MutexApiConfiguration {
                endpoint: Some(format!("http://{address}")),
                bearer_token: Some("test-token".to_string()),
            },
            ..crate::models::CoordinationConfiguration::default()
        };
        let resource = "router:capacity:project:project:0";
        let mut acquired = Vec::new();
        let error = acquire_hard_resource(
            &configuration,
            &project_file,
            &mut acquired,
            None,
            resource,
            "worker",
            "claim-audit-failure",
            3,
            300,
            1,
        )
        .expect_err("failed durable audit must not erase the granted API lease handle");
        assert!(error.to_string().contains("Not a directory"));
        assert_eq!(acquired, vec![resource]);

        let cleanup = release_hard_resources(
            &configuration,
            &project_file,
            &acquired,
            "worker",
            "claim-audit-failure",
        );
        assert!(cleanup.is_err(), "the failed release audit remains visible");
        assert_eq!(server.join().expect("mock server"), vec!["POST", "DELETE"]);
    }

    #[test]
    fn hard_capacity_api_error_stops_renewal_and_releases_prior_claims() {
        use std::io::{Read as _, Write as _};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock mutex API");
        let address = listener.local_addr().expect("mock address");
        let server = thread::spawn(move || {
            let mut requests = Vec::new();
            for _ in 0..5 {
                let (mut stream, _) = listener.accept().expect("accept API request");
                let mut request = Vec::new();
                let mut buffer = [0_u8; 4096];
                let body_start = loop {
                    let read = stream.read(&mut buffer).expect("read request");
                    assert!(read > 0, "request connection remains open");
                    request.extend_from_slice(&buffer[..read]);
                    if let Some(position) = request.windows(4).position(|part| part == b"\r\n\r\n")
                    {
                        break position + 4;
                    }
                };
                let headers = String::from_utf8_lossy(&request[..body_start]);
                let request_line = headers.lines().next().expect("request line");
                let method = request_line
                    .split_whitespace()
                    .next()
                    .expect("HTTP method")
                    .to_string();
                let path = request_line
                    .split_whitespace()
                    .nth(1)
                    .expect("request path")
                    .to_string();
                let content_length = headers
                    .lines()
                    .find_map(|line| {
                        let (name, value) = line.split_once(':')?;
                        name.eq_ignore_ascii_case("content-length")
                            .then(|| value.trim().parse::<usize>().ok())
                            .flatten()
                    })
                    .unwrap_or_default();
                while request.len() < body_start + content_length {
                    let read = stream.read(&mut buffer).expect("read request body");
                    assert!(read > 0, "request body is complete");
                    request.extend_from_slice(&buffer[..read]);
                }
                let (status, body) = match (method.as_str(), path.as_str()) {
                    ("POST", "/api/coordination/leases/router%3Aissue%3Akbs-hard-capacity") => {
                        let now = Utc::now().timestamp();
                        (
                            "201 Created",
                            serde_json::to_vec(&json!({
                                "resource": "router:issue:kbs-hard-capacity",
                                "owner": "worker",
                                "claim_id": "claim-capacity-error",
                                "revision": 4,
                                "claimed_at": now,
                                "expires_at": now + 300,
                            }))
                            .expect("serialize issue lease"),
                        )
                    }
                    ("PUT", "/api/coordination/leases/router%3Aissue%3Akbs-hard-capacity") => {
                        let now = Utc::now().timestamp();
                        (
                            "200 OK",
                            serde_json::to_vec(&json!({
                                "resource": "router:issue:kbs-hard-capacity",
                                "owner": "worker",
                                "claim_id": "claim-capacity-error",
                                "revision": 4,
                                "claimed_at": now - 1,
                                "expires_at": now + 300,
                            }))
                            .expect("serialize renewed issue lease"),
                        )
                    }
                    ("GET", "/api/coordination/leases/router%3Aissue%3Akbs-hard-capacity") => {
                        let now = Utc::now().timestamp();
                        (
                            "200 OK",
                            serde_json::to_vec(&json!({
                                "resource": "router:issue:kbs-hard-capacity",
                                "owner": "worker",
                                "claim_id": "claim-capacity-error",
                                "revision": 4,
                                "claimed_at": now - 1,
                                "expires_at": now + 300,
                            }))
                            .expect("serialize inspected issue lease"),
                        )
                    }
                    ("POST", _) => ("503 Service Unavailable", b"{}".to_vec()),
                    ("DELETE", "/api/coordination/leases/router%3Aissue%3Akbs-hard-capacity") => {
                        ("204 No Content", Vec::new())
                    }
                    unexpected => panic!("unexpected mutex API request: {unexpected:?}"),
                };
                write!(
                    stream,
                    "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                )
                .expect("write API response headers");
                stream.write_all(&body).expect("write API response");
                requests.push((method, path));
            }
            requests
        });

        let temp = tempfile::tempdir().expect("temporary repository");
        git_success(temp.path(), &["init", "-b", "main"]);
        git_success(temp.path(), &["config", "user.name", "Router Test"]);
        git_success(
            temp.path(),
            &["config", "user.email", "router-test@example.invalid"],
        );
        fs::write(
            temp.path().join("README.md"),
            "router hard acquisition test\n",
        )
        .expect("write repository fixture");
        git_success(temp.path(), &["add", "README.md"]);
        git_success(temp.path(), &["commit", "-m", "fixture base"]);
        let project_dir = temp.path().join("project");
        fs::create_dir_all(project_dir.join("issues")).expect("create issue directory");
        let mut configuration = crate::config::default_project_configuration();
        configuration.coordination.providers = vec![
            "mutex_api".to_string(),
            "mqtt".to_string(),
            "git".to_string(),
        ];
        configuration.coordination.default_lease_ttl = "300s".to_string();
        configuration.coordination.contention_window = "1s".to_string();
        configuration.coordination.mutex_api = crate::models::MutexApiConfiguration {
            endpoint: Some(format!("http://{address}")),
            bearer_token: Some("test-token".to_string()),
        };
        let router = IssueRouterConfiguration {
            enabled: true,
            workflow: crate::models::IssueRouterWorkflowConfiguration {
                pending: "open".to_string(),
                active: "in_progress".to_string(),
                review: "review".to_string(),
                blocked: "blocked".to_string(),
                terminal: vec!["closed".to_string()],
            },
            limits: crate::models::IssueRouterLimitsConfiguration {
                project_wip: 1,
                review_wip: 1,
                class_wip: BTreeMap::new(),
                provider_wip: BTreeMap::new(),
            },
            providers: BTreeMap::from([(
                "codex".to_string(),
                crate::models::IssueRouterProviderConfiguration {
                    adapter: "codex".to_string(),
                    command: "codex".to_string(),
                    args: Vec::new(),
                },
            )]),
            classes: BTreeMap::new(),
            retries: crate::models::IssueRouterRetryConfiguration { max_attempts: 3 },
            watch_interval: "30s".to_string(),
            forge: None,
        };
        let route = IssueRouterRoute {
            kind: "provider".to_string(),
            name: "codex".to_string(),
            provider_profile: "codex".to_string(),
        };

        let error = acquire_router_claims(
            temp.path(),
            &project_dir,
            &configuration,
            &router,
            "kbs-hard-capacity",
            &route,
            "claim-capacity-error",
            4,
            "worker",
        )
        .err()
        .expect("capacity API outage must fail closed");
        assert!(
            error
                .to_string()
                .contains("hard router coordination requires Mutex API"),
            "unexpected acquisition error: {error}"
        );
        assert_eq!(
            server.join().expect("mock mutex API"),
            vec![
                (
                    "POST".to_string(),
                    "/api/coordination/leases/router%3Aissue%3Akbs-hard-capacity".to_string()
                ),
                (
                    "GET".to_string(),
                    "/api/coordination/leases/router%3Aissue%3Akbs-hard-capacity".to_string()
                ),
                (
                    "PUT".to_string(),
                    "/api/coordination/leases/router%3Aissue%3Akbs-hard-capacity".to_string()
                ),
                (
                    "POST".to_string(),
                    "/api/coordination/leases/router%3Acapacity%3Aproject%3Aproject%3A0"
                        .to_string()
                ),
                (
                    "DELETE".to_string(),
                    "/api/coordination/leases/router%3Aissue%3Akbs-hard-capacity".to_string()
                ),
            ]
        );
    }

    fn event(
        issue_id: &str,
        event_type: EventType,
        payload: Value,
        occurred_at: &str,
    ) -> EventRecord {
        EventRecord::new(
            issue_id,
            event_type,
            "test-worker",
            payload,
            occurred_at.to_string(),
        )
    }

    #[test]
    fn latest_conversation_review_overrides_an_older_started_attempt() {
        let before_router_events = DateTime::parse_from_rfc3339("2026-09-18T22:00:00Z")
            .expect("valid timestamp")
            .with_timezone(&Utc);
        let mut issues = vec![IssueData {
            identifier: "kbs-review".to_string(),
            title: "Preserved agent work".to_string(),
            description: String::new(),
            issue_type: "task".to_string(),
            status: "in_progress".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: Utc::now(),
            updated_at: before_router_events,
            closed_at: None,
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: BTreeMap::new(),
        }];
        let router = IssueRouterConfiguration {
            enabled: true,
            workflow: crate::models::IssueRouterWorkflowConfiguration {
                pending: "open".to_string(),
                active: "in_progress".to_string(),
                review: "review".to_string(),
                blocked: "blocked".to_string(),
                terminal: vec!["closed".to_string()],
            },
            limits: crate::models::IssueRouterLimitsConfiguration {
                project_wip: 1,
                review_wip: 1,
                class_wip: BTreeMap::new(),
                provider_wip: BTreeMap::new(),
            },
            providers: BTreeMap::new(),
            classes: BTreeMap::new(),
            retries: crate::models::IssueRouterRetryConfiguration { max_attempts: 3 },
            watch_interval: "30s".to_string(),
            forge: None,
        };
        let started = event(
            "router:kbs-review",
            EventType::RouterAttempt,
            json!({"action":"started"}),
            "2026-09-18T23:00:00Z",
        );
        let review = event(
            "router:kbs-review",
            EventType::RouterConversation,
            json!({"action":"agent_turn", "lifecycle":"review"}),
            "2026-09-18T23:01:00Z",
        );

        apply_router_status_overlay(&mut issues, &[started.clone(), review], &router, &[]);

        assert_eq!(issues[0].status, "review");

        issues[0].updated_at = DateTime::parse_from_rfc3339("2026-09-18T23:02:00Z")
            .expect("valid timestamp")
            .with_timezone(&Utc);
        apply_router_status_overlay(&mut issues, &[started], &router, &[]);

        assert_eq!(
            issues[0].status, "review",
            "a later canonical board update must beat a stale router event"
        );
    }

    fn git_output(root: &Path, args: &[&str]) -> Output {
        Command::new("git")
            .args(args)
            .current_dir(root)
            .output()
            .expect("run Git fixture command")
    }

    fn git_success(root: &Path, args: &[&str]) -> String {
        let output = git_output(root, args);
        assert!(
            output.status.success(),
            "git {args:?} failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        String::from_utf8_lossy(&output.stdout).trim().to_string()
    }

    #[test]
    fn router_root_resolves_from_a_repository_subdirectory() {
        let temp = tempfile::tempdir().expect("router root temp dir");
        let root = temp.path().join("checkout");
        std::fs::create_dir_all(root.join("rust").join("src")).expect("create nested path");
        let initialized = Command::new("git")
            .args(["init", "--initial-branch=main"])
            .current_dir(&root)
            .output()
            .expect("initialize Git repository");
        assert!(initialized.status.success());

        let resolved = resolve_router_root(&root.join("rust").join("src"))
            .expect("resolve enclosing Git root");

        assert_eq!(
            resolved,
            root.canonicalize().expect("canonicalize fixture root")
        );
    }

    #[test]
    fn router_root_rejects_non_git_directories_with_actionable_diagnostic() {
        let temp = tempfile::tempdir().expect("router root temp dir");

        let error = resolve_router_root(temp.path()).expect_err("non-Git path must fail");

        assert!(matches!(
            error,
            KanbusError::IssueOperation(message)
                if message == "issue router requires a Git repository"
        ));
    }

    fn git_remote_fixture() -> (tempfile::TempDir, PathBuf, PathBuf, String) {
        let temp = tempfile::tempdir().expect("Git fixture temp dir");
        let root = temp.path().join("checkout");
        let remote = temp.path().join("remote.git");
        std::fs::create_dir_all(&root).expect("create checkout");
        let bare = Command::new("git")
            .args(["init", "--bare"])
            .arg(&remote)
            .output()
            .expect("initialize bare remote");
        assert!(bare.status.success());
        let initialized = Command::new("git")
            .args(["init", "-b", "main"])
            .current_dir(&root)
            .output()
            .expect("initialize source checkout");
        assert!(initialized.status.success());
        git_success(&root, &["config", "user.name", "Router Test"]);
        git_success(
            &root,
            &["config", "user.email", "router-test@example.invalid"],
        );
        std::fs::write(root.join("README.md"), "base\n").expect("write fixture file");
        git_success(&root, &["add", "README.md"]);
        git_success(&root, &["commit", "-m", "fixture base"]);
        git_success(
            &root,
            &[
                "remote",
                "add",
                "origin",
                remote.to_str().expect("remote path"),
            ],
        );
        let base_sha = git_success(&root, &["rev-parse", "HEAD"]);
        (temp, root, remote, base_sha)
    }

    fn remote_branch_sha(root: &Path, remote_ref: &str) -> String {
        let output = git_output(root, &["ls-remote", "--heads", "origin", remote_ref]);
        assert!(output.status.success());
        String::from_utf8_lossy(&output.stdout)
            .split_whitespace()
            .next()
            .unwrap_or("")
            .to_string()
    }

    fn remote_ref_sha(root: &Path, reference: &str) -> String {
        let output = git_output(root, &["ls-remote", "--refs", "origin", reference]);
        assert!(output.status.success());
        String::from_utf8_lossy(&output.stdout)
            .split_whitespace()
            .next()
            .unwrap_or("")
            .to_string()
    }

    #[test]
    fn canonical_router_events_reduce_under_bare_package_id_with_numeric_checkpoint() {
        let events = vec![
            event(
                "router:kbs-601",
                EventType::RouterAttempt,
                json!({"action":"started", "attempt":1, "claim_id":"claim-a", "revision":8, "provider_profile":"codex-default"}),
                "2026-09-17T10:00:00Z",
            ),
            event(
                "router:kbs-601",
                EventType::RouterAttempt,
                json!({"action":"checkpoint_accepted", "attempt":1, "claim_id":"claim-a", "revision":8, "checkpoint_ref":"refs/kanbus/checkpoint/kbs-601", "checkpoint_revision":8}),
                "2026-09-17T10:01:00Z",
            ),
            event(
                "router:kbs-601",
                EventType::RouterAttempt,
                json!({"action":"retryable_failure", "attempt":1, "next_attempt":2, "retry_at":"2026-09-17T10:02:00Z", "claim_id":"claim-a", "revision":8}),
                "2026-09-17T10:02:00Z",
            ),
            event(
                "router:kbs-601",
                EventType::RouterForge,
                json!({"action":"opened", "number":61, "head_sha":"abc601"}),
                "2026-09-17T10:03:00Z",
            ),
        ];

        let reduced = reduce_router_events(&events);
        assert_eq!(reduced.attempts.get("kbs-601"), Some(&2));
        assert_eq!(
            reduced.provider_profiles.get("kbs-601").map(String::as_str),
            Some("codex-default")
        );
        assert_eq!(
            reduced.checkpoints.get("kbs-601"),
            Some(&("refs/kanbus/checkpoint/kbs-601".to_string(), 8))
        );
        assert!(reduced.retry_at.contains_key("kbs-601"));
        assert_eq!(
            reduced.pull_requests.get("kbs-601"),
            Some(&(61, "abc601".to_string()))
        );
        assert!(!reduced.attempts.contains_key("router:kbs-601"));
    }

    #[test]
    fn canonical_router_result_keeps_claim_and_numeric_revision() {
        let result = event(
            "router:kbs-602",
            EventType::RouterResult,
            json!({"outcome":"completed", "claim_id":"claim-602", "revision":9, "checkpoint_ref":"refs/checkpoint/602", "checkpoint_revision":9, "artifacts":[{"name":"test-report", "ref":"refs/artifacts/report"}]}),
            "2026-09-17T10:00:00Z",
        );
        assert_eq!(payload_text(&result, "claim_id"), Some("claim-602"));
        assert_eq!(
            result.payload.get("revision").and_then(Value::as_u64),
            Some(9)
        );
        assert_eq!(
            result
                .payload
                .get("checkpoint_revision")
                .and_then(Value::as_u64),
            Some(9)
        );
    }

    #[test]
    fn current_router_claim_uses_logical_revision_before_event_id_for_timestamp_ties() {
        let mut revision_six = event(
            "router:kbs-607",
            EventType::RouterAttempt,
            json!({"action":"started", "claim_id":"claim-r6", "revision":6}),
            "2026-09-17T10:07:00.123456Z",
        );
        revision_six.event_id = "z-revision-six".to_string();
        let mut revision_seven = event(
            "router:kbs-607",
            EventType::RouterAttempt,
            json!({"action":"started", "claim_id":"claim-r7", "revision":7}),
            "2026-09-17T10:07:00.123456Z",
        );
        revision_seven.event_id = "a-revision-seven".to_string();

        let events = [revision_six, revision_seven];
        let current = latest_started_router_event(&events, "kbs-607")
            .expect("latest router start should exist");
        assert_eq!(payload_text(current, "claim_id"), Some("claim-r7"));
        assert_eq!(
            current.payload.get("revision").and_then(Value::as_u64),
            Some(7)
        );
    }

    #[test]
    fn stale_after_push_rolls_back_only_our_unchanged_router_branch() {
        let (_temp, root, _remote, base_sha) = git_remote_fixture();
        std::fs::write(root.join("README.md"), "candidate\n").expect("write candidate");
        git_success(&root, &["add", "README.md"]);
        git_success(&root, &["commit", "-m", "candidate"]);
        let candidate_sha = git_success(&root, &["rev-parse", "HEAD"]);

        let restore_ref = "refs/heads/router/restore";
        git_success(
            &root,
            &["push", "origin", &format!("{base_sha}:{restore_ref}")],
        );
        let stale = push_router_branch_with_fence(
            &root,
            &root,
            restore_ref,
            &base_sha,
            &candidate_sha,
            || Ok(()),
            || Err(KanbusError::IssueOperation("stale after push".to_string())),
        )
        .expect_err("stale branch push must fail");
        assert!(stale.to_string().contains("stale after push"));
        assert_eq!(remote_branch_sha(&root, restore_ref), base_sha);

        let delete_ref = "refs/heads/router/delete";
        let stale = push_router_branch_with_fence(
            &root,
            &root,
            delete_ref,
            "",
            &candidate_sha,
            || Ok(()),
            || Err(KanbusError::IssueOperation("stale after push".to_string())),
        )
        .expect_err("stale new branch push must fail");
        assert!(stale.to_string().contains("stale after push"));
        assert!(remote_branch_sha(&root, delete_ref).is_empty());

        let advanced_ref = "refs/heads/router/advanced";
        let stale = push_router_branch_with_fence(
            &root,
            &root,
            advanced_ref,
            "",
            &candidate_sha,
            || Ok(()),
            || {
                std::fs::write(root.join("README.md"), "advanced by another writer\n")
                    .expect("write concurrent candidate");
                git_success(&root, &["add", "README.md"]);
                git_success(&root, &["commit", "-m", "advanced concurrently"]);
                let advanced_sha = git_success(&root, &["rev-parse", "HEAD"]);
                git_success(
                    &root,
                    &["push", "origin", &format!("{advanced_sha}:{advanced_ref}")],
                );
                Err(KanbusError::IssueOperation("stale after push".to_string()))
            },
        )
        .expect_err("stale push with a concurrently advanced ref must report inspection");
        assert!(stale
            .to_string()
            .contains("operator inspection may be required"));
        let advanced_sha = git_success(&root, &["rev-parse", "HEAD"]);
        assert_eq!(remote_branch_sha(&root, advanced_ref), advanced_sha);
    }

    #[test]
    fn stale_after_pull_response_records_no_forge_event_or_status_change() {
        let temp = tempfile::tempdir().expect("router project temp dir");
        let root = temp.path();
        crate::file_io::initialize_project(root, false).expect("initialize router project");
        let initialized = Command::new("git")
            .args(["init", "-b", "main"])
            .current_dir(root)
            .output()
            .expect("initialize test repository");
        assert!(initialized.status.success());
        git_success(root, &["config", "user.name", "Router Test"]);
        git_success(
            root,
            &["config", "user.email", "router-test@example.invalid"],
        );
        git_success(root, &["add", "-A"]);
        git_success(root, &["commit", "-m", "fixture base"]);

        let project_dir = crate::file_io::load_project_directory(root).expect("project directory");
        let issue_id = "kbs-950";
        let now = Utc::now();
        let issue = IssueData {
            identifier: issue_id.to_string(),
            title: "Stale PR response test".to_string(),
            description: String::new(),
            issue_type: "task".to_string(),
            status: "in_progress".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: now,
            updated_at: now,
            closed_at: None,
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: BTreeMap::new(),
        };
        let issue_path = project_dir.join("issues").join(format!("{issue_id}.json"));
        std::fs::write(
            &issue_path,
            serde_json::to_vec_pretty(&issue).expect("serialize issue"),
        )
        .expect("write issue fixture");
        let history = vec![
            event(
                &format!("router:{issue_id}"),
                EventType::RouterAttempt,
                json!({"action":"started", "claim_id":"claim-old", "revision":1}),
                "2026-09-17T10:00:00Z",
            ),
            event(
                &format!("router:{issue_id}"),
                EventType::RouterAttempt,
                json!({"action":"started", "claim_id":"claim-new", "revision":2}),
                "2026-09-17T10:01:00Z",
            ),
        ];
        crate::event_history::write_events_batch(&events_dir_for_project(&project_dir), &history)
            .expect("write claim history");
        let configuration = crate::config_loader::load_project_configuration(
            &get_configuration_path(root).expect("configuration path"),
        )
        .expect("load configuration");
        let claim = RouterClaim {
            issue_id: issue_id.to_string(),
            claim_id: "claim-old".to_string(),
            revision: 1,
            resource: format!("router:issue:{issue_id}"),
            hard: false,
            owner: "worker-old".to_string(),
            resources: Vec::new(),
        };
        let pull = PullRequestInfo {
            number: 950,
            head_sha: "deadbeef".to_string(),
            url: "https://github.com/example/repo/pull/950".to_string(),
            branch: "codex/router/kbs-950/r1".to_string(),
        };
        let error = record_router_pull_response(
            &project_dir,
            &configuration,
            &claim,
            issue_id,
            "example/repo",
            &pull.branch,
            false,
            &pull,
            &[],
        )
        .expect_err("stale API response must not become local router state");
        assert!(error
            .to_string()
            .contains("current claim is claim-new at revision 2"));
        let issue_after = read_issue_from_file(&issue_path).expect("read unchanged issue");
        assert_eq!(issue_after.status, "in_progress");
        assert!(!load_router_events(&project_dir)
            .expect("read router events")
            .iter()
            .any(|candidate| {
                candidate.issue_id == format!("router:{issue_id}")
                    && matches!(&candidate.event_type, EventType::RouterForge)
            }));
    }

    #[test]
    fn stale_pr_response_rolls_back_only_unchanged_branch_and_checkpoint_refs() {
        let (_temp, root, _remote, _initial_sha) = git_remote_fixture();
        crate::file_io::initialize_project(&root, false).expect("initialize router project");
        let project_dir = crate::file_io::load_project_directory(&root).expect("project dir");
        let issue_id = "kbs-953";
        let now = Utc::now();
        let issue = IssueData {
            identifier: issue_id.to_string(),
            title: "Stale PR response cleanup".to_string(),
            description: String::new(),
            issue_type: "task".to_string(),
            status: "in_progress".to_string(),
            priority: 2,
            assignee: None,
            creator: None,
            parent: None,
            labels: Vec::new(),
            dependencies: Vec::new(),
            comments: Vec::new(),
            created_at: now,
            updated_at: now,
            closed_at: None,
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: BTreeMap::new(),
        };
        let issue_path = project_dir.join("issues").join(format!("{issue_id}.json"));
        std::fs::write(
            &issue_path,
            serde_json::to_vec_pretty(&issue).expect("serialize issue"),
        )
        .expect("write issue");
        git_success(&root, &["add", "-A"]);
        git_success(&root, &["commit", "-m", "router stale PR base"]);
        git_success(&root, &["push", "origin", "main"]);
        let previous_sha = git_success(&root, &["rev-parse", "HEAD"]);

        std::fs::write(root.join("router-published.txt"), "candidate\n")
            .expect("write pushed router candidate");
        git_success(&root, &["add", "router-published.txt"]);
        git_success(&root, &["commit", "-m", "router PR candidate"]);
        let pushed_sha = git_success(&root, &["rev-parse", "HEAD"]);
        let branch_ref = "refs/heads/codex/router/kbs-953/r1";
        let checkpoint_ref = "refs/kanbus/router/checkpoints/kbs-953";
        git_success(
            &root,
            &["push", "origin", &format!("{previous_sha}:{branch_ref}")],
        );
        git_success(
            &root,
            &["push", "origin", &format!("{pushed_sha}:{branch_ref}")],
        );
        git_success(
            &root,
            &[
                "push",
                "origin",
                &format!("{previous_sha}:{checkpoint_ref}"),
            ],
        );
        git_success(
            &root,
            &["push", "origin", &format!("{pushed_sha}:{checkpoint_ref}")],
        );
        git_success(&root, &["update-ref", checkpoint_ref, &previous_sha]);
        git_success(
            &root,
            &["update-ref", checkpoint_ref, &pushed_sha, &previous_sha],
        );

        let history = vec![
            event(
                &format!("router:{issue_id}"),
                EventType::RouterAttempt,
                json!({"action":"started", "claim_id":"claim-old", "revision":1}),
                "2026-09-17T10:00:00Z",
            ),
            event(
                &format!("router:{issue_id}"),
                EventType::RouterAttempt,
                json!({"action":"started", "claim_id":"claim-new", "revision":2}),
                "2026-09-17T10:01:00Z",
            ),
        ];
        crate::event_history::write_events_batch(&events_dir_for_project(&project_dir), &history)
            .expect("write claim history");
        let configuration = crate::config_loader::load_project_configuration(
            &get_configuration_path(&root).expect("configuration path"),
        )
        .expect("load configuration");
        let claim = RouterClaim {
            issue_id: issue_id.to_string(),
            claim_id: "claim-old".to_string(),
            revision: 1,
            resource: format!("router:issue:{issue_id}"),
            hard: false,
            owner: "worker-old".to_string(),
            resources: Vec::new(),
        };
        let pull = PullRequestInfo {
            number: 953,
            head_sha: pushed_sha.clone(),
            url: "https://github.com/example/repo/pull/953".to_string(),
            branch: "codex/router/kbs-953/r1".to_string(),
        };
        let published_branch = PublishedRouterRef {
            reference: branch_ref.to_string(),
            pushed_sha: pushed_sha.clone(),
            previous_remote_sha: previous_sha.clone(),
            previous_local_sha: None,
            remote_published: true,
        };
        let published_checkpoint = PublishedRouterRef {
            reference: checkpoint_ref.to_string(),
            pushed_sha: pushed_sha.clone(),
            previous_remote_sha: previous_sha.clone(),
            previous_local_sha: Some(previous_sha.clone()),
            remote_published: true,
        };

        let error = record_router_pull_response(
            &project_dir,
            &configuration,
            &claim,
            issue_id,
            "example/repo",
            &pull.branch,
            false,
            &pull,
            &[&published_branch, &published_checkpoint],
        )
        .expect_err("stale post-PR fence must rollback unadvanced publication refs");
        assert!(error
            .to_string()
            .contains("current claim is claim-new at revision 2"));
        assert_eq!(remote_branch_sha(&root, branch_ref), previous_sha);
        assert_eq!(remote_ref_sha(&root, checkpoint_ref), previous_sha);
        assert_eq!(
            git_success(&root, &["show-ref", "--verify", "--hash", checkpoint_ref]),
            previous_sha
        );
        assert_eq!(
            read_issue_from_file(&issue_path).unwrap().status,
            "in_progress"
        );
        assert!(!load_router_events(&project_dir)
            .expect("load router events")
            .iter()
            .any(|candidate| {
                candidate.issue_id == format!("router:{issue_id}")
                    && matches!(&candidate.event_type, EventType::RouterForge)
            }));

        // A concurrent writer that advances either remote or local checkpoint
        // refs after publication must not have its ref overwritten by cleanup.
        std::fs::write(root.join("router-advanced.txt"), "advanced\n")
            .expect("write concurrent commit");
        git_success(&root, &["add", "router-advanced.txt"]);
        git_success(&root, &["commit", "-m", "concurrent router writer"]);
        let advanced_sha = git_success(&root, &["rev-parse", "HEAD"]);
        let advanced_branch_ref = "refs/heads/codex/router/kbs-953/r2";
        let advanced_checkpoint_ref = "refs/kanbus/router/checkpoints/kbs-953-r2";
        for reference in [advanced_branch_ref, advanced_checkpoint_ref] {
            git_success(
                &root,
                &["push", "origin", &format!("{previous_sha}:{reference}")],
            );
            git_success(
                &root,
                &["push", "origin", &format!("{pushed_sha}:{reference}")],
            );
        }
        git_success(
            &root,
            &["update-ref", advanced_checkpoint_ref, &previous_sha],
        );
        git_success(
            &root,
            &[
                "update-ref",
                advanced_checkpoint_ref,
                &pushed_sha,
                &previous_sha,
            ],
        );
        git_success(
            &root,
            &[
                "push",
                "origin",
                &format!("{advanced_sha}:{advanced_checkpoint_ref}"),
            ],
        );
        git_success(
            &root,
            &[
                "update-ref",
                advanced_checkpoint_ref,
                &advanced_sha,
                &pushed_sha,
            ],
        );
        let advanced_branch = PublishedRouterRef {
            reference: advanced_branch_ref.to_string(),
            pushed_sha: pushed_sha.clone(),
            previous_remote_sha: previous_sha.clone(),
            previous_local_sha: None,
            remote_published: true,
        };
        let advanced_checkpoint = PublishedRouterRef {
            reference: advanced_checkpoint_ref.to_string(),
            pushed_sha: pushed_sha.clone(),
            previous_remote_sha: previous_sha.clone(),
            previous_local_sha: Some(previous_sha.clone()),
            remote_published: true,
        };
        let advanced_error = record_router_pull_response(
            &project_dir,
            &configuration,
            &claim,
            issue_id,
            "example/repo",
            "codex/router/kbs-953/r2",
            false,
            &pull,
            &[&advanced_branch, &advanced_checkpoint],
        )
        .expect_err("cleanup must preserve an advanced checkpoint ref");
        assert!(advanced_error
            .to_string()
            .contains("operator inspection may be required"));
        assert_eq!(remote_branch_sha(&root, advanced_branch_ref), previous_sha);
        assert_eq!(remote_ref_sha(&root, advanced_checkpoint_ref), advanced_sha);
        assert_eq!(
            git_success(
                &root,
                &["show-ref", "--verify", "--hash", advanced_checkpoint_ref]
            ),
            advanced_sha
        );
        assert!(!load_router_events(&project_dir)
            .expect("load router events")
            .iter()
            .any(|candidate| {
                candidate.issue_id == format!("router:{issue_id}")
                    && matches!(&candidate.event_type, EventType::RouterForge)
            }));
    }

    #[test]
    fn router_status_transition_updates_only_the_hidden_shared_state_worktree() {
        let (_temp, root, _remote, _base_sha) = git_remote_fixture();
        crate::file_io::initialize_project(&root, false).expect("initialize project");
        let mut configuration = crate::config::default_project_configuration();
        configuration.router = Some(IssueRouterConfiguration {
            enabled: true,
            workflow: crate::models::IssueRouterWorkflowConfiguration {
                pending: "open".to_string(),
                active: "in_progress".to_string(),
                review: "review".to_string(),
                blocked: "blocked".to_string(),
                terminal: vec!["closed".to_string()],
            },
            limits: crate::models::IssueRouterLimitsConfiguration {
                project_wip: 3,
                review_wip: 2,
                class_wip: BTreeMap::new(),
                provider_wip: BTreeMap::new(),
            },
            providers: BTreeMap::from([(
                "default".to_string(),
                IssueRouterProviderConfiguration {
                    adapter: "codex".to_string(),
                    command: "codex".to_string(),
                    args: Vec::new(),
                },
            )]),
            classes: BTreeMap::from([(
                "implementation".to_string(),
                crate::models::IssueRouterClassConfiguration {
                    providers: vec!["default".to_string()],
                },
            )]),
            retries: crate::models::IssueRouterRetryConfiguration { max_attempts: 3 },
            watch_interval: "30s".to_string(),
            forge: Some(crate::models::IssueRouterForgeConfiguration {
                provider: "github".to_string(),
                repository: "example/repo".to_string(),
                base_branch: "main".to_string(),
                api_url: "https://api.github.com".to_string(),
                token_env: "GITHUB_TOKEN".to_string(),
            }),
        });
        configuration
            .statuses
            .push(crate::models::StatusDefinition {
                key: "review".to_string(),
                name: "Review".to_string(),
                category: "In progress".to_string(),
                semantic_category: "in_progress".to_string(),
                color: None,
                collapsed: false,
            });
        std::fs::write(
            get_configuration_path(&root).expect("configuration path"),
            serde_yaml::to_string(&configuration).expect("serialize configuration"),
        )
        .expect("write router config");
        let project_dir = load_project_directory(&root).expect("project directory");
        let issue_id = "kbs-951";
        let now = Utc::now();
        let issue = IssueData {
            identifier: issue_id.to_string(),
            title: "Hidden status worktree test".to_string(),
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
            created_at: now,
            updated_at: now,
            closed_at: None,
            agent: None,
            right_now_summary: None,
            right_now_updated_at: None,
            custom: BTreeMap::new(),
        };
        let issue_path = project_dir.join("issues").join(format!("{issue_id}.json"));
        std::fs::write(
            &issue_path,
            serde_json::to_vec_pretty(&issue).expect("serialize issue"),
        )
        .expect("write issue");
        git_success(&root, &["add", "-A"]);
        git_success(&root, &["commit", "-m", "router status fixture"]);
        git_success(&root, &["push", "origin", "main"]);
        let occurred_at = now.to_rfc3339_opts(SecondsFormat::Millis, true);
        let issue_claim = event(
            &format!("router:issue:{issue_id}"),
            EventType::CoordinationClaim,
            json!({"owner":"test-worker", "claim_id":"claim-status", "revision":1, "lease_expires_at":(now + chrono::Duration::minutes(5)).to_rfc3339_opts(SecondsFormat::Millis, true), "contention_window_s":0, "ttl_s":300}),
            &occurred_at,
        );
        crate::event_history::write_events_batch(
            &events_dir_for_project(&project_dir),
            std::slice::from_ref(&issue_claim),
        )
        .expect("write issue claim");
        let started = event(
            &format!("router:{issue_id}"),
            EventType::RouterAttempt,
            json!({"action":"started", "claim_id":"claim-status", "revision":1}),
            &occurred_at,
        );
        let repository_root = repository_root(&root).expect("canonical repository root");
        publish_shared_router_event(&repository_root, &issue_claim)
            .expect("publish selected issue claim");
        publish_shared_router_event(&repository_root, &started)
            .expect("publish router transition through the hidden worktree");

        assert_eq!(read_issue_from_file(&issue_path).unwrap().status, "open");
        assert!(git_success(&root, &["status", "--short", "--", "project/issues"]).is_empty());
        let shared_ref = remote_router_state_ref(&root, true)
            .expect("read shared ref")
            .expect("published shared branch");
        let shared_issue = Command::new("git")
            .args([
                "show",
                &format!("{shared_ref}:project/issues/{issue_id}.json"),
            ])
            .current_dir(&root)
            .output()
            .expect("read shared issue");
        assert!(shared_issue.status.success());
        assert_eq!(
            serde_json::from_slice::<IssueData>(&shared_issue.stdout)
                .expect("parse shared issue")
                .status,
            "in_progress"
        );
    }

    #[test]
    fn pause_and_hold_controls_reduce_locally_without_shared_publication() {
        let (_temp, root, _remote, _base_sha) = git_remote_fixture();
        crate::file_io::initialize_project(&root, false).expect("initialize project");
        let project_dir = load_project_directory(&root).expect("project directory");
        let controls = vec![
            event(
                "router:global",
                EventType::RouterControl,
                json!({"action":"pause"}),
                "2026-09-17T10:00:00Z",
            ),
            event(
                "router:global",
                EventType::RouterControl,
                json!({"action":"hold", "route":"class:implementation"}),
                "2026-09-17T10:01:00Z",
            ),
        ];
        crate::event_history::write_events_batch(&events_dir_for_project(&project_dir), &controls)
            .expect("write local controls");
        for control in &controls {
            publish_shared_router_event(&root, control).expect("local control is not published");
        }

        let reduced =
            reduce_router_events(&load_router_events(&project_dir).expect("load local state"));
        assert!(reduced.paused);
        assert!(reduced.holds.contains("class:implementation"));
        assert!(remote_branch_sha(&root, "refs/heads/kanbus/router-state").is_empty());
        assert!(read_shared_router_events(&root)
            .expect("read peer-visible router state")
            .is_empty());
    }

    #[test]
    fn cancel_after_adapter_exit_fences_result_publication() {
        let temp = tempfile::tempdir().expect("router cancellation temp dir");
        let root = temp.path();
        crate::file_io::initialize_project(root, false).expect("initialize project");
        let initialized = Command::new("git")
            .args(["init", "-b", "main"])
            .current_dir(root)
            .output()
            .expect("initialize repository");
        assert!(initialized.status.success());
        git_success(root, &["config", "user.name", "Router Test"]);
        git_success(
            root,
            &["config", "user.email", "router-test@example.invalid"],
        );
        git_success(root, &["add", "-A"]);
        git_success(root, &["commit", "-m", "router cancel fixture"]);
        let configuration = crate::config_loader::load_project_configuration(
            &get_configuration_path(root).expect("configuration path"),
        )
        .expect("load configuration");
        let project_dir = load_project_directory(root).expect("project directory");
        let issue_id = "kbs-952";
        let history = vec![
            event(
                &format!("router:{issue_id}"),
                EventType::RouterAttempt,
                json!({"action":"started", "claim_id":"claim-cancel", "revision":1}),
                "2026-09-17T10:00:00Z",
            ),
            event(
                &format!("router:{issue_id}"),
                EventType::RouterControl,
                json!({"action":"cancel", "claim_id":"claim-cancel", "revision":1}),
                "2026-09-17T10:01:00Z",
            ),
        ];
        crate::event_history::write_events_batch(&events_dir_for_project(&project_dir), &history)
            .expect("write start and cancellation");
        let claim = RouterClaim {
            issue_id: issue_id.to_string(),
            claim_id: "claim-cancel".to_string(),
            revision: 1,
            resource: format!("router:issue:{issue_id}"),
            hard: false,
            owner: "worker-cancel".to_string(),
            resources: Vec::new(),
        };
        let error = assert_current_router_claim(&project_dir, &configuration, &claim)
            .expect_err("a cancellation after child exit must fence publication");
        assert!(error
            .to_string()
            .contains("router package kbs-952 cancelled"));
        assert!(!load_router_events(&project_dir)
            .expect("load events")
            .iter()
            .any(|event| matches!(&event.event_type, EventType::RouterResult)));
    }

    #[test]
    fn pull_request_reviews_reduce_latest_state_per_reviewer_for_current_head() {
        let reviews = vec![
            json!({"id": 1, "user": {"login": "alice"}, "state": "CHANGES_REQUESTED", "commit_id": "head-a", "submitted_at": "2026-09-17T10:00:00Z"}),
            json!({"id": 2, "user": {"login": "bob"}, "state": "APPROVED", "commit_id": "head-a", "submitted_at": "2026-09-17T10:03:00Z"}),
            json!({"id": 3, "user": {"login": "alice"}, "state": "APPROVED", "commit_id": "head-a", "submitted_at": "2026-09-17T10:04:00Z"}),
            json!({"id": 4, "user": {"login": "carol"}, "state": "CHANGES_REQUESTED", "commit_id": "old-head", "submitted_at": "2026-09-17T10:05:00Z"}),
        ];
        assert_eq!(
            reduce_pull_request_reviews(&reviews[..2], "head-a"),
            Some("requested_changes")
        );
        assert_eq!(
            reduce_pull_request_reviews(&reviews, "head-a"),
            Some("approved")
        );
    }

    #[test]
    fn router_renewal_keeps_a_fixed_now_plus_ttl_horizon() {
        let now = DateTime::parse_from_rfc3339("2026-09-17T10:00:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let current_expiry = DateTime::parse_from_rfc3339("2026-09-17T10:04:00Z")
            .unwrap()
            .with_timezone(&Utc);
        assert_eq!(
            router_renewal_extension_seconds(Some(current_expiry), now, 300),
            60
        );
        assert_eq!(
            router_renewal_extension_seconds(Some(current_expiry), now, 240),
            0
        );
    }

    #[test]
    fn malformed_adapter_json_and_unknown_outcomes_are_validation_errors() {
        let error =
            parse_router_result("not JSON").expect_err("malformed adapter output must not parse");
        let message = match error {
            KanbusError::IssueOperation(message) => message,
            other => panic!("unexpected adapter parse error: {other}"),
        };
        assert_eq!(message, "Codex router adapter returned invalid JSON");
        let unknown =
            parse_router_result(r#"{"schema_version":1,"outcome":"done","checkpoint":null}"#)
                .expect("syntactically valid outcome parses before allowlist validation");
        assert_eq!(unknown.outcome, "done");
        assert!(!["completed", "blocked", "retryable_failure"].contains(&unknown.outcome.as_str()));
    }

    #[test]
    fn router_issue_comments_are_package_scoped_and_nonblank() {
        let package_issue_ids = vec!["kbs-701".to_string()];
        let comment = RouterIssueComment {
            issue_id: "kbs-701".to_string(),
            text: "Three paragraphs follow.".to_string(),
        };
        validate_router_issue_comments("kbs-701", &package_issue_ids, &[comment.clone()])
            .expect("a nonblank comment on a package issue is valid");
        assert!(validate_router_issue_comments(
            "kbs-701",
            &package_issue_ids,
            &[RouterIssueComment {
                issue_id: "kbs-702".to_string(),
                text: "Out of package".to_string(),
            }]
        )
        .expect_err("comments must stay inside the package")
        .to_string()
        .contains("outside router package"));
        assert!(validate_router_issue_comments(
            "kbs-701",
            &package_issue_ids,
            &[RouterIssueComment {
                issue_id: "kbs-701".to_string(),
                text: "  \n".to_string(),
            }]
        )
        .expect_err("blank comments are rejected")
        .to_string()
        .contains("must not be blank"));

        let parsed = parse_router_result(
            r#"{"schema_version":1,"outcome":"completed","issue_comments":[{"issue_id":"kbs-701","text":"Comment"}],"checkpoint":null}"#,
        )
        .expect("structured comments are accepted from Codex");
        assert_eq!(parsed.issue_comments.len(), 1);
    }

    #[test]
    fn parses_pretty_json_and_codex_jsonl_structured_output() {
        let result = json!({
            "schema_version":1,
            "outcome":"completed",
            "summary":"ready",
            "issue_updates":[],
            "checkpoint":null,
            "artifacts":[]
        });
        let pretty = serde_json::to_string_pretty(&result).unwrap();
        assert_eq!(parse_router_result(&pretty).unwrap().outcome, "completed");

        let envelope = json!({
            "type":"item.completed",
            "item":{
                "type":"agent_message",
                "content":[{"type":"text","text":result.to_string()}]
            }
        });
        assert_eq!(
            parse_router_result(&envelope.to_string()).unwrap().outcome,
            "completed"
        );
        let nested_envelope = json!({
            "type":"event_msg",
            "payload":{
                "type":"item_completed",
                "item":{
                    "type":"AgentMessage",
                    "text":result.to_string()
                }
            }
        });
        assert_eq!(
            parse_router_result(&nested_envelope.to_string())
                .unwrap()
                .outcome,
            "completed"
        );
    }

    #[test]
    fn normalizes_optional_artifacts_without_discarding_a_completed_turn() {
        let output = json!({
            "schema_version": 1,
            "outcome": "completed",
            "summary": "completed with evidence",
            "issue_updates": [],
            "issue_comments": [{"issue_id": "kbs-701", "text": "Review evidence is ready."}],
            "checkpoint": null,
            "artifacts": [
                {"name": "report", "ref": "refs/reports/r1"},
                {
                    "path": "artifacts/verification/report.json",
                    "description": "Verification report",
                    "verification": {"command": "pytest"}
                },
                {"description": "No usable reference"}
            ]
        });

        let envelope = json!({
            "type": "item.completed",
            "item": {"type": "AgentMessage", "text": output.to_string()}
        });
        let result = parse_router_result(&envelope.to_string())
            .expect("optional artifact metadata must not reject a valid result");
        assert_eq!(result.outcome, "completed");
        assert_eq!(result.summary, "completed with evidence");
        assert_eq!(result.issue_comments.len(), 1);
        assert_eq!(result.artifacts.len(), 2);
        assert_eq!(result.artifacts[0].name, "report");
        assert_eq!(result.artifacts[0].reference, "refs/reports/r1");
        assert_eq!(result.artifacts[1].name, "report.json");
        assert_eq!(
            result.artifacts[1].reference,
            "artifacts/verification/report.json"
        );
        assert!(parse_router_result(
            r#"{"schema_version":1,"outcome":"completed","artifacts":"invalid"}"#
        )
        .expect("a malformed optional artifact list is omitted")
        .artifacts
        .is_empty());
    }

    #[test]
    fn completed_turn_review_record_is_visible_without_agent_supplied_comments() {
        let pull = PullRequestInfo {
            number: 42,
            head_sha: "abc123".to_string(),
            url: "https://example.test/pull/42".to_string(),
            branch: "codex/router/kbs-701/r1".to_string(),
        };
        let comment = completed_router_review_comment(
            "",
            &pull,
            "refs/kanbus/router/checkpoints/kbs-701",
            &[RouterArtifact {
                name: "tests".to_string(),
                reference: "artifacts/tests.txt".to_string(),
            }],
        );

        assert_eq!(
            comment,
            "## Agent turn complete\n\nThe agent completed a turn. Review the preserved branch and draft pull request.\n\n- Draft PR: https://example.test/pull/42\n- Branch: `codex/router/kbs-701/r1`\n- Checkpoint: `refs/kanbus/router/checkpoints/kbs-701`\n- Artifacts:\n  - `tests`: `artifacts/tests.txt`"
        );
    }

    #[test]
    fn active_shared_issue_claim_is_not_planned_until_release_or_expiry() {
        let now = DateTime::parse_from_rfc3339("2026-09-17T10:02:00Z")
            .unwrap()
            .with_timezone(&Utc);
        let claim = event(
            "router:issue:kbs-601",
            EventType::CoordinationClaim,
            json!({
                "resource":"router:issue:kbs-601",
                "owner":"worker-a",
                "claim_id":"claim-a",
                "revision":1,
                "lease_expires_at":"2026-09-17T10:05:00Z",
                "contention_window_s":1,
                "ttl_s":300
            }),
            "2026-09-17T10:00:00Z",
        );
        assert!(has_live_router_claim(&[claim.clone()], "kbs-601", now));
        assert!(!has_live_router_claim(
            &[claim],
            "kbs-601",
            now + chrono::Duration::minutes(6)
        ));
    }

    #[test]
    fn started_event_requires_an_active_matching_issue_claim() {
        let temp = tempfile::tempdir().expect("router start-fence temp dir");
        let root = temp.path();
        crate::file_io::initialize_project(root, false).expect("initialize project");
        let issue_id = "kbs-996";
        let now = Utc::now();
        let started = EventRecord::new(
            format!("router:{issue_id}"),
            EventType::RouterAttempt,
            "worker-current",
            json!({"action":"started", "claim_id":"claim-current", "revision":2}),
            now.to_rfc3339_opts(SecondsFormat::Millis, true),
        );
        let expired_claim = event(
            &format!("router:issue:{issue_id}"),
            EventType::CoordinationClaim,
            json!({"owner":"worker-current", "claim_id":"claim-current", "revision":2, "lease_expires_at":(now - chrono::Duration::seconds(1)).to_rfc3339_opts(SecondsFormat::Millis, true), "contention_window_s":0}),
            &(now - chrono::Duration::seconds(5)).to_rfc3339_opts(SecondsFormat::Millis, true),
        );
        let error = validate_started_event_claim(root, &started, &[expired_claim])
            .expect_err("an expired issue claim cannot publish a started event");
        assert!(error
            .to_string()
            .contains("does not own the current live issue claim"));

        let active_claim = event(
            &format!("router:issue:{issue_id}"),
            EventType::CoordinationClaim,
            json!({"owner":"worker-current", "claim_id":"claim-current", "revision":2, "lease_expires_at":(now + chrono::Duration::minutes(5)).to_rfc3339_opts(SecondsFormat::Millis, true), "contention_window_s":5}),
            &now.to_rfc3339_opts(SecondsFormat::Millis, true),
        );
        let losing_claim = event(
            &format!("router:issue:{issue_id}"),
            EventType::CoordinationClaim,
            json!({"owner":"worker-loser", "claim_id":"z-loser", "revision":2, "lease_expires_at":(now + chrono::Duration::minutes(5)).to_rfc3339_opts(SecondsFormat::Millis, true), "contention_window_s":5}),
            &now.to_rfc3339_opts(SecondsFormat::Millis, true),
        );
        let losing_start = EventRecord::new(
            format!("router:{issue_id}"),
            EventType::RouterAttempt,
            "worker-loser",
            json!({"action":"started", "claim_id":"z-loser", "revision":2}),
            now.to_rfc3339_opts(SecondsFormat::Millis, true),
        );
        let contenders = [active_claim, losing_claim];
        let error = validate_started_event_claim(root, &losing_start, &contenders)
            .expect_err("a losing simultaneous claim cannot append a started event");
        assert!(error
            .to_string()
            .contains("does not own the current live issue claim"));
        validate_started_event_claim(root, &started, &contenders)
            .expect("the selected active issue claim may start");
    }

    #[test]
    fn hard_capacity_slots_start_after_preexisting_wip_and_share_one_race_slot() {
        let available = available_capacity_slots(2, 3).collect::<Vec<_>>();
        assert_eq!(available, vec![2]);
        assert_eq!(
            available_capacity_slots(3, 3).collect::<Vec<_>>(),
            Vec::<usize>::new()
        );

        // Two concurrent workers with the same snapshot contend for the same
        // final slot; a mutex lease can admit only one of those reservations.
        let first_worker_slots = available_capacity_slots(2, 3).collect::<Vec<_>>();
        let second_worker_slots = available_capacity_slots(2, 3).collect::<Vec<_>>();
        assert_eq!(first_worker_slots, second_worker_slots);
    }

    #[test]
    fn release_attempts_every_resource_in_reverse_order_after_partial_failure() {
        let resources = ["issue", "project", "provider"];
        let mut attempted = Vec::new();
        let failures = release_resources_in_reverse(&resources, |resource| {
            attempted.push(*resource);
            if *resource == "project" {
                Err("project release failed".to_string())
            } else {
                Ok(())
            }
        });
        assert_eq!(attempted, vec!["provider", "project", "issue"]);
        assert_eq!(failures, vec!["project: project release failed"]);
        assert!(matches!(
            release_failures_result(failures),
            Err(KanbusError::IssueOperation(message)) if message == "project: project release failed"
        ));
    }

    #[test]
    fn stale_soft_claim_cleanup_skips_resources_owned_by_the_contention_winner() {
        let temp = tempfile::tempdir().expect("router release temp dir");
        let root = temp.path();
        crate::file_io::initialize_project(root, false).expect("initialize project");
        let project_dir = load_project_directory(root).expect("project directory");
        let mut configuration = crate::config::default_project_configuration();
        configuration.coordination.contention_window = "5s".to_string();
        std::fs::write(
            get_configuration_path(root).expect("configuration path"),
            serde_yaml::to_string(&configuration).expect("serialize configuration"),
        )
        .expect("write configuration");
        let initialized = Command::new("git")
            .args(["init", "-b", "main"])
            .current_dir(root)
            .output()
            .expect("initialize release test repository");
        assert!(initialized.status.success());
        git_success(root, &["config", "user.name", "Router Test"]);
        git_success(
            root,
            &["config", "user.email", "router-test@example.invalid"],
        );
        git_success(root, &["add", "-A"]);
        git_success(root, &["commit", "-m", "router release fixture"]);

        let now = Utc::now();
        let occurred_at = now.to_rfc3339_opts(SecondsFormat::Millis, true);
        let expires_at =
            (now + chrono::Duration::minutes(5)).to_rfc3339_opts(SecondsFormat::Millis, true);
        let resource = "router:capacity:project:0";
        let claims = [
            event(
                resource,
                EventType::CoordinationClaim,
                json!({"owner":"worker-current", "claim_id":"a-current", "lease_expires_at":expires_at, "contention_window_s":5}),
                &occurred_at,
            ),
            event(
                resource,
                EventType::CoordinationClaim,
                json!({"owner":"worker-stale", "claim_id":"z-stale", "lease_expires_at":expires_at, "contention_window_s":5}),
                &occurred_at,
            ),
        ];
        crate::event_history::write_events_batch(&events_dir_for_project(&project_dir), &claims)
            .expect("write competing claims");

        let stale_claim = RouterClaim {
            issue_id: "kbs-999".to_string(),
            claim_id: "z-stale".to_string(),
            revision: 1,
            resource: "router:issue:kbs-999".to_string(),
            hard: false,
            owner: "worker-stale".to_string(),
            resources: vec![resource.to_string()],
        };
        assert_eq!(
            soft_lease_renewal_extension(&project_dir, resource, "worker-stale", "z-stale", 300,)
                .expect("a lost advisory soft renewal is not a claim failure"),
            0
        );
        release_router_claims(root, &configuration, &project_dir, &stale_claim)
            .expect("cleanup ignores a lease won by another worker");

        let inspection = crate::coordination::run_coordination(
            root,
            CoordinationOperation::Inspect {
                resource: resource.to_string(),
            },
        )
        .expect("inspect current lease");
        assert!(coordination_output_claim_matches(
            &inspection,
            "worker-current",
            "a-current"
        ));
        let history = load_router_events(&project_dir).expect("load events");
        assert!(!history.iter().any(|candidate| {
            candidate.issue_id == resource
                && matches!(&candidate.event_type, EventType::CoordinationRelease)
        }));

        let current_claim = RouterClaim {
            issue_id: "kbs-998".to_string(),
            claim_id: "a-current".to_string(),
            revision: 1,
            resource: "router:issue:kbs-998".to_string(),
            hard: false,
            owner: "worker-current".to_string(),
            resources: vec![resource.to_string()],
        };
        release_router_claims(root, &configuration, &project_dir, &current_claim)
            .expect("release failures for an owned lease must not be hidden");
        let inspection = crate::coordination::run_coordination(
            root,
            CoordinationOperation::Inspect {
                resource: resource.to_string(),
            },
        )
        .expect("inspect released lease");
        assert!(inspection.contains("state: eligible"));
    }

    #[test]
    fn soft_capacity_claim_scans_all_slots_for_a_self_reduced_claim() {
        let temp = tempfile::tempdir().expect("router capacity temp dir");
        let root = temp.path();
        crate::file_io::initialize_project(root, false).expect("initialize project");
        let project_dir = load_project_directory(root).expect("project directory");
        let mut coordination = crate::config::default_project_configuration();
        coordination.coordination.contention_window = "5s".to_string();
        std::fs::write(
            get_configuration_path(root).expect("configuration path"),
            serde_yaml::to_string(&coordination).expect("serialize configuration"),
        )
        .expect("write configuration");
        let initialized = Command::new("git")
            .args(["init", "-b", "main"])
            .current_dir(root)
            .output()
            .expect("initialize capacity test repository");
        assert!(initialized.status.success());
        git_success(root, &["config", "user.name", "Router Test"]);
        git_success(
            root,
            &["config", "user.email", "router-test@example.invalid"],
        );
        git_success(root, &["add", "-A"]);
        git_success(root, &["commit", "-m", "router capacity fixture"]);

        let now = Utc::now();
        let occurred_at = now.to_rfc3339_opts(SecondsFormat::Millis, true);
        let expires_at =
            (now + chrono::Duration::minutes(5)).to_rfc3339_opts(SecondsFormat::Millis, true);
        let occupied_slot = event(
            "router:capacity:project:0",
            EventType::CoordinationClaim,
            json!({"owner":"worker-existing", "claim_id":"a-existing", "lease_expires_at":expires_at, "contention_window_s":5}),
            &occurred_at,
        );
        crate::event_history::write_events_batch(
            &events_dir_for_project(&project_dir),
            &[occupied_slot],
        )
        .expect("write slot-zero winner");

        let router = IssueRouterConfiguration {
            enabled: true,
            workflow: crate::models::IssueRouterWorkflowConfiguration {
                pending: "open".to_string(),
                active: "in_progress".to_string(),
                review: "review".to_string(),
                blocked: "blocked".to_string(),
                terminal: vec!["closed".to_string()],
            },
            limits: crate::models::IssueRouterLimitsConfiguration {
                project_wip: 2,
                review_wip: 1,
                class_wip: BTreeMap::new(),
                provider_wip: BTreeMap::new(),
            },
            providers: BTreeMap::from([(
                "default".to_string(),
                IssueRouterProviderConfiguration {
                    adapter: "codex".to_string(),
                    command: "codex".to_string(),
                    args: Vec::new(),
                },
            )]),
            classes: BTreeMap::new(),
            retries: crate::models::IssueRouterRetryConfiguration { max_attempts: 3 },
            watch_interval: "30s".to_string(),
            forge: None,
        };
        let route = IssueRouterRoute {
            kind: "provider".to_string(),
            name: "default".to_string(),
            provider_profile: "default".to_string(),
        };
        let (claimed, resources, hard, renewer) = acquire_router_claims(
            root,
            &project_dir,
            &coordination,
            &router,
            "kbs-997",
            &route,
            "z-current-worker",
            1,
            "worker-current",
        )
        .expect("acquire soft issue and capacity claims");
        assert!(claimed);
        assert!(!hard);
        assert!(renewer.is_none());
        assert!(resources.contains(&"router:capacity:project:1".to_string()));
        assert!(!resources.contains(&"router:capacity:project:0".to_string()));

        let claim = RouterClaim {
            issue_id: "kbs-997".to_string(),
            claim_id: "z-current-worker".to_string(),
            revision: 1,
            resource: "router:issue:kbs-997".to_string(),
            hard: false,
            owner: "worker-current".to_string(),
            resources,
        };
        release_router_claims(root, &coordination, &project_dir, &claim)
            .expect("release acquired soft claims");
    }

    #[test]
    fn retry_delay_doubles_and_caps_at_fifteen_minutes() {
        for (attempt, expected) in [(1, 30), (2, 60), (3, 120), (6, 900), (7, 900)] {
            assert_eq!(retry_delay_seconds(attempt), expected);
        }
    }

    #[test]
    fn active_state_is_cleared_only_after_successful_claim_release() {
        let calls = std::cell::RefCell::new(Vec::new());
        let failure = KanbusError::IssueOperation("release failed".to_string());
        let result = release_then_clear(
            || {
                calls.borrow_mut().push("release");
                Err(failure)
            },
            || {
                calls.borrow_mut().push("clear");
                Ok(())
            },
        );
        assert!(result.is_err());
        assert_eq!(*calls.borrow(), vec!["release"]);

        calls.borrow_mut().clear();
        release_then_clear(
            || {
                calls.borrow_mut().push("release");
                Ok(())
            },
            || {
                calls.borrow_mut().push("clear");
                Ok(())
            },
        )
        .expect("successful release and clear");
        assert_eq!(*calls.borrow(), vec!["release", "clear"]);
    }

    #[test]
    fn adapter_error_cleanup_releases_every_hard_claim_before_clear_failure() {
        use std::io::{Read as _, Write as _};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock mutex API");
        listener
            .set_nonblocking(true)
            .expect("make cleanup API accept nonblocking");
        let address = listener.local_addr().expect("mock address");
        let server = thread::spawn(move || {
            let mut paths = Vec::new();
            let deadline = Instant::now() + Duration::from_secs(3);
            for _ in 0..2 {
                let (mut stream, _) = loop {
                    match listener.accept() {
                        Ok((stream, _address)) => {
                            stream
                                .set_nonblocking(false)
                                .expect("make release stream blocking");
                            stream
                                .set_read_timeout(Some(Duration::from_secs(2)))
                                .expect("bound release request reads");
                            stream
                                .set_write_timeout(Some(Duration::from_secs(2)))
                                .expect("bound release response writes");
                            break (stream, address);
                        }
                        Err(error)
                            if error.kind() == std::io::ErrorKind::WouldBlock
                                && Instant::now() < deadline =>
                        {
                            thread::sleep(Duration::from_millis(10));
                        }
                        Err(error) => {
                            panic!("release request was not received before deadline: {error}")
                        }
                    }
                };
                let mut request = Vec::new();
                let mut buffer = [0_u8; 4096];
                let body_start = loop {
                    let read = stream.read(&mut buffer).expect("read request");
                    assert!(read > 0, "request connection remains open");
                    request.extend_from_slice(&buffer[..read]);
                    if let Some(position) = request.windows(4).position(|part| part == b"\r\n\r\n")
                    {
                        break position + 4;
                    }
                };
                let headers = String::from_utf8_lossy(&request[..body_start]);
                let request_line = headers.lines().next().expect("request line");
                assert!(request_line.starts_with("DELETE "));
                let path = request_line
                    .split_whitespace()
                    .nth(1)
                    .expect("request path")
                    .to_string();
                let content_length = headers
                    .lines()
                    .find_map(|line| {
                        let (name, value) = line.split_once(':')?;
                        name.eq_ignore_ascii_case("content-length")
                            .then(|| value.trim().parse::<usize>().ok())
                            .flatten()
                    })
                    .unwrap_or_default();
                while request.len() < body_start + content_length {
                    let read = stream.read(&mut buffer).expect("read request body");
                    assert!(read > 0, "request body is complete");
                    request.extend_from_slice(&buffer[..read]);
                }
                write!(
                    stream,
                    "HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
                .expect("write release response");
                paths.push(path);
            }
            paths
        });

        let temp = tempfile::tempdir().expect("temporary repository");
        let root = temp.path();
        git_success(root, &["init", "-b", "main"]);
        git_success(root, &["config", "user.name", "Router Test"]);
        git_success(
            root,
            &["config", "user.email", "router-test@example.invalid"],
        );
        fs::write(root.join("README.md"), "router cleanup fixture\n")
            .expect("write repository fixture");
        git_success(root, &["add", "README.md"]);
        git_success(root, &["commit", "-m", "fixture base"]);
        let project_dir = root.join("project");
        fs::create_dir_all(project_dir.join("issues")).expect("create issue directory");
        fs::create_dir_all(project_dir.join("events")).expect("create event directory");
        fs::write(root.join(".git/kanbus"), "block router state directory")
            .expect("make active-state cleanup fail");

        let mut configuration = crate::config::default_project_configuration();
        configuration.coordination.mutex_api = crate::models::MutexApiConfiguration {
            endpoint: Some(format!("http://{address}")),
            bearer_token: Some("test-token".to_string()),
        };
        let claim = RouterClaim {
            issue_id: "kbs-cleanup".to_string(),
            claim_id: "claim-cleanup".to_string(),
            revision: 2,
            resource: "router:issue:kbs-cleanup".to_string(),
            hard: true,
            owner: "worker".to_string(),
            resources: vec![
                "router:issue:kbs-cleanup".to_string(),
                "router:capacity:project:0".to_string(),
            ],
        };
        let cleanup = release_then_clear(
            || release_router_claims(root, &configuration, &project_dir, &claim),
            || clear_active_router_state(root),
        );
        let error = preserve_router_error_after_adapter_failure(
            KanbusError::IssueOperation("Codex router adapter failed".to_string()),
            Err(KanbusError::IssueOperation(
                "router hard lease renewal failed: synthetic failure".to_string(),
            )),
            cleanup,
        );
        assert!(error.to_string().contains("Codex router adapter failed"));
        assert!(error.to_string().contains(
            "lease renewer shutdown failed: router hard lease renewal failed: synthetic failure"
        ));
        assert!(error.to_string().contains("router cleanup failed"));
        assert_eq!(
            server.join().expect("mock API releases"),
            vec![
                "/api/coordination/leases/router%3Acapacity%3Aproject%3A0",
                "/api/coordination/leases/router%3Aissue%3Akbs-cleanup",
            ]
        );
    }

    #[test]
    fn conversation_helpers_extract_a_session_and_redact_key_material() {
        let output = "{\"type\":\"thread.started\",\"thread_id\":\"session-123\"}\n";
        assert_eq!(codex_session_id(output).as_deref(), Some("session-123"));
        assert_eq!(
            redact_router_log("token sk-abcdefghijklmnop"),
            "token [REDACTED]"
        );
    }

    #[test]
    fn router_created_pull_requests_are_drafts() {
        use std::io::{Read as _, Write as _};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock GitHub API");
        let address = listener.local_addr().expect("read mock address");
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept PR request");
            let mut request = Vec::new();
            let mut buffer = [0_u8; 4096];
            let body_start = loop {
                let read = stream.read(&mut buffer).expect("read PR request");
                assert!(read > 0, "PR request remains open");
                request.extend_from_slice(&buffer[..read]);
                if let Some(position) = request.windows(4).position(|part| part == b"\r\n\r\n") {
                    break position + 4;
                }
            };
            let headers = String::from_utf8_lossy(&request[..body_start]);
            assert!(headers.starts_with("POST /repos/example/kanbus/pulls HTTP/1.1"));
            let content_length = headers
                .lines()
                .find_map(|line| {
                    let (name, value) = line.split_once(':')?;
                    name.eq_ignore_ascii_case("content-length")
                        .then(|| value.trim().parse::<usize>().ok())
                        .flatten()
                })
                .expect("content length");
            while request.len() < body_start + content_length {
                let read = stream.read(&mut buffer).expect("read PR body");
                assert!(read > 0, "PR body is complete");
                request.extend_from_slice(&buffer[..read]);
            }
            let body: Value =
                serde_json::from_slice(&request[body_start..body_start + content_length])
                    .expect("parse PR payload");
            assert_eq!(body.get("draft").and_then(Value::as_bool), Some(true));
            let response = r#"{"number":42,"html_url":"https://example.invalid/pull/42","head":{"sha":"abc","ref":"codex/router/kbs-test/r1"}}"#;
            write!(
                stream,
                "HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                response.len(), response
            )
            .expect("write mock PR response");
        });
        let forge = GitHubForge {
            client: reqwest::blocking::Client::new(),
            api_url: format!("http://{address}"),
            repository: "example/kanbus".to_string(),
            base_branch: "develop".to_string(),
            token: "test-token".to_string(),
        };

        let pull = forge
            .create_pull_request("kbs-test", "Test issue", "codex/router/kbs-test/r1")
            .expect("create draft PR");

        assert_eq!(pull.number, 42);
        assert_eq!(pull.branch, "codex/router/kbs-test/r1");
        server.join().expect("mock GitHub API");
    }
}
