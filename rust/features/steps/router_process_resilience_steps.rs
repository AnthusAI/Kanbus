//! Steps for router process hygiene and watch resilience.

use std::fs;
use std::io::Read;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use cucumber::{given, then, when};
use kanbus::error::KanbusError;
use kanbus::router::{
    decide_watch_poll_failure, router_adapter_process_record_path, router_process_identity,
    signal_registered_router_adapter, spawn_router_child_in_own_process_group,
    terminate_router_child_process_tree, WatchPollFailureDecision,
};
use serde_json::json;
use tempfile::TempDir;

use crate::step_definitions::initialization_steps::KanbusWorld;

const PACKAGE_IDENTIFIER: &str = "kbs-resilience";
const CLAIM_IDENTIFIER: &str = "claim-resilience";
const SHUTDOWN_DEADLINE: Duration = Duration::from_secs(5);

#[derive(Default)]
struct ResilienceFixture {
    adapter: Option<Child>,
    grandchild_pid: Option<u32>,
    interval_seconds: u64,
    decision: Option<WatchPollFailureDecision>,
    decoy: Option<Child>,
    repository: Option<TempDir>,
}

fn fixture() -> &'static Mutex<ResilienceFixture> {
    static FIXTURE: OnceLock<Mutex<ResilienceFixture>> = OnceLock::new();
    FIXTURE.get_or_init(|| Mutex::new(ResilienceFixture::default()))
}

fn process_is_alive(pid: u32) -> bool {
    let output = Command::new("ps")
        .args(["-o", "stat=", "-p", &pid.to_string()])
        .output()
        .expect("run ps");
    let status = String::from_utf8_lossy(&output.stdout).trim().to_string();
    !status.is_empty() && !status.starts_with('Z')
}

fn reset_fixture(fixture: &mut ResilienceFixture) {
    if let Some(pid) = fixture.grandchild_pid.take() {
        let _ = Command::new("kill").args(["-9", &pid.to_string()]).status();
    }
    if let Some(mut adapter) = fixture.adapter.take() {
        let _ = adapter.kill();
        let _ = adapter.wait();
    }
    if let Some(mut decoy) = fixture.decoy.take() {
        let _ = decoy.kill();
        let _ = decoy.wait();
    }
    *fixture = ResilienceFixture::default();
}

#[given("a router adapter process that forked a sleeping grandchild")]
fn given_adapter_with_sleeping_grandchild(_world: &mut KanbusWorld) {
    let mut state = fixture().lock().expect("lock fixture");
    reset_fixture(&mut state);
    let mut command = Command::new("sh");
    command
        .args(["-c", "sleep 300 & echo $!; wait"])
        .stdout(Stdio::piped());
    let mut adapter = spawn_router_child_in_own_process_group(&mut command).expect("spawn adapter");
    let mut stdout = adapter.stdout.take().expect("adapter stdout");
    let mut announced = [0u8; 32];
    let length = stdout.read(&mut announced).expect("read grandchild pid");
    let grandchild_pid: u32 = String::from_utf8_lossy(&announced[..length])
        .trim()
        .parse()
        .expect("grandchild pid");
    assert!(process_is_alive(grandchild_pid));
    state.grandchild_pid = Some(grandchild_pid);
    state.adapter = Some(adapter);
}

#[when("the router terminates the adapter process tree")]
fn when_router_terminates_adapter_tree(_world: &mut KanbusWorld) {
    let mut state = fixture().lock().expect("lock fixture");
    let adapter = state.adapter.as_mut().expect("adapter process");
    terminate_router_child_process_tree(adapter);
}

#[then("the adapter process should be reaped")]
fn then_adapter_process_reaped(_world: &mut KanbusWorld) {
    let mut state = fixture().lock().expect("lock fixture");
    let adapter = state.adapter.as_mut().expect("adapter process");
    assert!(adapter.try_wait().expect("adapter wait status").is_some());
}

#[then("the grandchild process should no longer be running")]
fn then_grandchild_gone(_world: &mut KanbusWorld) {
    let mut state = fixture().lock().expect("lock fixture");
    let grandchild_pid = state.grandchild_pid.expect("grandchild pid");
    let deadline = Instant::now() + SHUTDOWN_DEADLINE;
    while process_is_alive(grandchild_pid) && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(50));
    }
    let survived = process_is_alive(grandchild_pid);
    reset_fixture(&mut state);
    assert!(!survived, "grandchild survived termination of its adapter");
}

#[given(regex = r#"^the router watch interval is (?P<interval>\d+) seconds$"#)]
fn given_watch_interval_seconds(_world: &mut KanbusWorld, interval: u64) {
    fixture().lock().expect("lock fixture").interval_seconds = interval;
}

#[when(
    regex = r#"^GitHub pull request polling fails with (?P<failure>.+) for consecutive failure (?P<count>\d+)$"#
)]
fn when_pull_request_polling_fails(_world: &mut KanbusWorld, failure: String, count: u32) {
    let message = match failure.as_str() {
        "HTTP status 500" => {
            "GitHub pull request polling failed with status 500 Internal Server Error"
        }
        "HTTP status 429" => "GitHub pull request polling failed with status 429 Too Many Requests",
        "HTTP status 401" => "GitHub pull request polling failed with status 401 Unauthorized",
        "a network error" => "GitHub pull request polling failed: connection reset",
        other => panic!("unknown polling failure {other}"),
    };
    let mut state = fixture().lock().expect("lock fixture");
    let interval = state.interval_seconds;
    state.decision = Some(decide_watch_poll_failure(
        &KanbusError::IssueOperation(message.to_string()),
        interval,
        count,
    ));
}

#[then(regex = r#"^the router watch should retry after (?P<seconds>\d+) seconds$"#)]
fn then_watch_retries(_world: &mut KanbusWorld, seconds: u64) {
    let state = fixture().lock().expect("lock fixture");
    assert_eq!(
        state.decision,
        Some(WatchPollFailureDecision::Retry {
            backoff_seconds: seconds
        })
    );
}

#[then("the router watch should stop")]
fn then_watch_stops(_world: &mut KanbusWorld) {
    let state = fixture().lock().expect("lock fixture");
    assert_eq!(state.decision, Some(WatchPollFailureDecision::Abort));
}

fn record_active_adapter(identity: Option<String>, decoy: Child) {
    let mut state = fixture().lock().expect("lock fixture");
    reset_fixture(&mut state);
    let repository = TempDir::new().expect("temporary repository");
    let initialized = Command::new("git")
        .args(["init", "--quiet"])
        .current_dir(repository.path())
        .status()
        .expect("initialize repository");
    assert!(initialized.success());
    let record_path: PathBuf =
        router_adapter_process_record_path(repository.path(), PACKAGE_IDENTIFIER, CLAIM_IDENTIFIER)
            .expect("adapter record path");
    fs::create_dir_all(record_path.parent().expect("record directory"))
        .expect("create record directory");
    fs::write(
        &record_path,
        json!({
            "schema_version": 2,
            "package_id": PACKAGE_IDENTIFIER,
            "claim_id": CLAIM_IDENTIFIER,
            "pid": decoy.id(),
            "process_identity": identity,
        })
        .to_string(),
    )
    .expect("write adapter record");
    state.repository = Some(repository);
    state.decoy = Some(decoy);
}

fn start_decoy() -> Child {
    Command::new("sleep")
        .arg("300")
        .process_group(0)
        .spawn()
        .expect("start decoy process")
}

#[given("a recorded active adapter whose process ID now belongs to an unrelated process")]
fn given_recorded_adapter_with_reused_process_id(_world: &mut KanbusWorld) {
    let foreign_identity = router_process_identity(std::process::id());
    assert!(foreign_identity.is_some());
    record_active_adapter(foreign_identity, start_decoy());
}

#[given("a recorded active adapter whose process identity matches")]
fn given_recorded_adapter_with_matching_identity(_world: &mut KanbusWorld) {
    let decoy = start_decoy();
    let identity = router_process_identity(decoy.id());
    assert!(identity.is_some());
    record_active_adapter(identity, decoy);
}

#[when("the router signals the registered adapter for its package claim")]
fn when_router_signals_registered_adapter(_world: &mut KanbusWorld) {
    let state = fixture().lock().expect("lock fixture");
    let repository = state.repository.as_ref().expect("repository");
    signal_registered_router_adapter(repository.path(), PACKAGE_IDENTIFIER, CLAIM_IDENTIFIER);
}

#[then("the unrelated process should still be running")]
fn then_unrelated_process_still_running(_world: &mut KanbusWorld) {
    thread::sleep(Duration::from_millis(300));
    let mut state = fixture().lock().expect("lock fixture");
    let still_running = state
        .decoy
        .as_mut()
        .expect("decoy process")
        .try_wait()
        .expect("decoy status")
        .is_none();
    reset_fixture(&mut state);
    assert!(still_running);
}

#[then("the recorded adapter process should have been terminated")]
fn then_recorded_adapter_terminated(_world: &mut KanbusWorld) {
    let mut state = fixture().lock().expect("lock fixture");
    let deadline = Instant::now() + SHUTDOWN_DEADLINE;
    let decoy = state.decoy.as_mut().expect("decoy process");
    let terminated = loop {
        if decoy.try_wait().expect("decoy status").is_some() {
            break true;
        }
        if Instant::now() >= deadline {
            break false;
        }
        thread::sleep(Duration::from_millis(50));
    };
    reset_fixture(&mut state);
    assert!(terminated);
}
