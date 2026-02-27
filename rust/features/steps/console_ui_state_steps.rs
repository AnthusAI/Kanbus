use std::collections::BTreeMap;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::Duration;

use chrono::{TimeZone, Utc};
use cucumber::{given, when};
use reqwest::blocking::Client;
use serde_json::json;

use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("working directory");
    load_project_directory(cwd).expect("project dir")
}

fn write_issue_file(project_dir: &std::path::Path, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    std::fs::write(issue_path, contents).expect("write issue");
}

fn console_base_url(world: &KanbusWorld) -> String {
    let port = world.console_port.unwrap_or(5174);
    format!("http://127.0.0.1:{port}")
}

/// POST a notification event to the running console server's /api/notifications endpoint.
fn post_notification(world: &KanbusWorld, body: serde_json::Value) {
    let url = format!("{}/api/notifications", console_base_url(world));
    thread::spawn(move || {
        let client = Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .expect("build http client");
        client
            .post(&url)
            .json(&body)
            .send()
            .expect("post notification");
    })
    .join()
    .expect("post notification thread");
}

fn allocate_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .expect("bind ephemeral port")
        .local_addr()
        .expect("local addr")
        .port()
}

fn wait_for_server(port: u16) -> bool {
    thread::spawn(move || {
        let client = Client::builder()
            .timeout(Duration::from_millis(500))
            .build()
            .expect("build http client");
        let url = format!("http://127.0.0.1:{}/api/config", port);
        for _ in 0..100 {
            if let Ok(resp) = client.get(&url).send() {
                if resp.status().is_success() {
                    return true;
                }
            }
            thread::sleep(Duration::from_millis(100));
        }
        false
    })
    .join()
    .unwrap_or(false)
}

fn kbsc_binary_path() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let target_dir = std::env::var("CARGO_TARGET_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| manifest_dir.join("target"));
    target_dir.join("debug").join("kbsc")
}

fn start_kbsc(world: &KanbusWorld, port: u16) -> Child {
    let data_root = world.working_directory.as_ref().expect("working directory");
    let binary = kbsc_binary_path();
    if !binary.exists() {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let status = Command::new("cargo")
            .args(["build", "--bin", "kbsc"])
            .current_dir(&manifest_dir)
            .status()
            .expect("build kbsc");
        assert!(status.success(), "kbsc build failed");
    }
    Command::new(binary)
        .env("CONSOLE_PORT", port.to_string())
        .env("CONSOLE_DATA_ROOT", data_root)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn kbsc")
}

fn write_console_port_to_config(world: &KanbusWorld, port: u16) {
    let root = world.working_directory.as_ref().expect("working directory");
    let config_path = root.join(".kanbus.yml");
    let existing = if config_path.exists() {
        std::fs::read_to_string(&config_path).unwrap_or_default()
    } else {
        String::new()
    };
    // Replace or append console_port line.
    let new_contents = if existing.contains("console_port:") {
        let re = regex::Regex::new(r"(?m)^console_port:.*$").expect("regex");
        re.replace(&existing, format!("console_port: {port}"))
            .to_string()
    } else {
        format!("{existing}\nconsole_port: {port}\n")
    };
    std::fs::write(config_path, new_contents).expect("write console_port to config");
}

// ---------------------------------------------------------------------------
// Generic issue creation
// ---------------------------------------------------------------------------

#[given(expr = "an issue {string} exists with title {string}")]
fn given_issue_exists_with_title(world: &mut KanbusWorld, identifier: String, title: String) {
    let project_dir = load_project_dir(world);
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let issue = IssueData {
        identifier,
        title,
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
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: BTreeMap::new(),
    };
    write_issue_file(&project_dir, &issue);
}

// ---------------------------------------------------------------------------
// Console server lifecycle (non-@console path — no server running)
// ---------------------------------------------------------------------------

#[given("the console server is not running")]
fn given_console_server_not_running(_world: &mut KanbusWorld) {
    let port = allocate_port();
    let world = _world;
    world.console_port = Some(port);
    write_console_port_to_config(world, port);
}

// ---------------------------------------------------------------------------
// Console server lifecycle (@console path — real kbsc process)
// ---------------------------------------------------------------------------

#[given("the console server is running")]
fn given_console_server_is_running(world: &mut KanbusWorld) {
    if world.console_port.is_some() {
        // Already started.
        return;
    }
    let port = allocate_port();
    world.console_port = Some(port);
    write_console_port_to_config(world, port);
    let _child = start_kbsc(world, port);
    // Note: child is intentionally leaked; the process will be cleaned up when
    // the test process exits.  A full lifecycle would store the Child handle in
    // KanbusWorld, but KanbusWorld currently has no field for it.
    assert!(wait_for_server(port), "console server did not become ready");
}

#[when("the console server is restarted")]
fn when_console_server_is_restarted(world: &mut KanbusWorld) {
    let port = world.console_port.expect("console port not set");
    // Stop any running server via the shutdown endpoint (best-effort).
    let _ = thread::spawn(move || {
        let client = Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
            .expect("build http client");
        let _ = client
            .post(format!("http://127.0.0.1:{port}/api/shutdown"))
            .send();
    })
    .join();
    thread::sleep(Duration::from_millis(500));
    let _child = start_kbsc(world, port);
    assert!(
        wait_for_server(port),
        "console server did not become ready after restart"
    );
}

// ---------------------------------------------------------------------------
// Console state setup (requires running server — @console scenarios)
// ---------------------------------------------------------------------------

#[given(expr = "the console focused issue is {string}")]
fn given_console_focused_issue(world: &mut KanbusWorld, issue_id: String) {
    post_notification(
        world,
        json!({
            "type": "issue_focused",
            "issue_id": issue_id,
            "user": null,
            "comment_id": null
        }),
    );
}

#[given("no issue is focused in the console")]
fn given_no_issue_focused(world: &mut KanbusWorld) {
    post_notification(
        world,
        json!({
            "type": "ui_control",
            "action": {"action": "clear_focus"}
        }),
    );
}

#[given(expr = "the console view mode is {string}")]
fn given_console_view_mode(world: &mut KanbusWorld, mode: String) {
    post_notification(
        world,
        json!({
            "type": "ui_control",
            "action": {"action": "set_view_mode", "mode": mode}
        }),
    );
}

#[given(expr = "the console search query is {string}")]
fn given_console_search_query(world: &mut KanbusWorld, query: String) {
    post_notification(
        world,
        json!({
            "type": "ui_control",
            "action": {"action": "set_search", "query": query}
        }),
    );
}
