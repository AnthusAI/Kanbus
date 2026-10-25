use std::collections::BTreeMap;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::Duration;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};
use reqwest::blocking::Client;
use serde_json::json;

use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("working directory");
    load_project_directory(cwd).expect("project dir")
}

pub(crate) fn write_issue_file(project_dir: &std::path::Path, issue: &IssueData) {
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
            .header("X-Kanbus-Console", "1")
            .json(&body)
            .send()
            .expect("post notification");
    })
    .join()
    .expect("post notification thread");
}

pub(crate) fn allocate_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .expect("bind ephemeral port")
        .local_addr()
        .expect("local addr")
        .port()
}

pub(crate) fn wait_for_server(port: u16) -> bool {
    thread::spawn(move || {
        let client = Client::builder()
            .timeout(Duration::from_millis(500))
            .build()
            .expect("build http client");
        let url = format!("http://127.0.0.1:{port}/api/config");
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

fn request_console_shutdown(port: u16) {
    let _ = thread::spawn(move || {
        let client = Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
            .expect("build http client");
        let _ = client
            .post(format!("http://127.0.0.1:{port}/api/shutdown"))
            .header("X-Kanbus-Console", "1")
            .send();
    })
    .join();
}

/// Stop any kbsc process started for the current scenario.
pub fn stop_console_server(world: &mut KanbusWorld) {
    if let Some(port) = world.console_port {
        request_console_shutdown(port);
    }
    if let Some(mut child) = world.console_server_child.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    world.console_port = None;
}

fn kbsc_binary_path() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_kbsc"))
}

pub(crate) fn start_kbsc(world: &KanbusWorld, port: u16) -> Child {
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
        .env("KANBUS_NO_DAEMON", "1")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn kbsc")
}

pub(crate) fn write_console_port_to_config(world: &KanbusWorld, port: u16) {
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
        agent: None,
        right_now_summary: None,
        right_now_updated_at: None,
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
    if world.console_server_child.is_some() {
        return;
    }
    stop_console_server(world);
    let port = allocate_port();
    write_console_port_to_config(world, port);
    let child = start_kbsc(world, port);
    assert!(
        wait_for_server(port),
        "console server did not become ready on port {port}"
    );
    world.console_port = Some(port);
    world.console_server_child = Some(child);
}

#[when("the console server is restarted")]
fn when_console_server_is_restarted(world: &mut KanbusWorld) {
    let port = world.console_port.expect("console port not set");
    stop_console_server(world);
    thread::sleep(Duration::from_millis(500));
    let child = start_kbsc(world, port);
    assert!(
        wait_for_server(port),
        "console server did not become ready after restart on port {port}"
    );
    world.console_port = Some(port);
    world.console_server_child = Some(child);
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

struct TenantConsoleFixture {
    child: Child,
    base: String,
}

impl TenantConsoleFixture {
    fn start(root: &std::path::Path, multi: bool) -> Self {
        let port = allocate_port();
        let child = Command::new(kbsc_binary_path())
            .env("CONSOLE_PORT", port.to_string())
            .env("CONSOLE_DATA_ROOT", root)
            .env(
                "CONSOLE_TENANT_MODE",
                if multi { "multi" } else { "single" },
            )
            .env("KANBUS_NO_DAEMON", "1")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("start fixture");
        let fixture = Self {
            child,
            base: format!("http://127.0.0.1:{port}"),
        };
        for _ in 0..100 {
            if Client::new()
                .get(format!("{}/api/auth/bootstrap", fixture.base))
                .timeout(Duration::from_millis(200))
                .send()
                .is_ok()
            {
                return fixture;
            }
            thread::sleep(Duration::from_millis(50));
        }
        panic!("fixture console did not start");
    }

    fn request(&self, path: &str, event: Option<serde_json::Value>) -> reqwest::blocking::Response {
        let client = Client::builder()
            .timeout(Duration::from_secs(3))
            .build()
            .unwrap();
        let url = format!("{}{path}", self.base);
        match event {
            Some(event) => client
                .post(url)
                .header("X-Kanbus-Console", "1")
                .json(&event),
            None => client.get(url),
        }
        .send()
        .expect("fixture request")
    }

    fn post(&self, tenant: &str, event: serde_json::Value) {
        assert_eq!(
            self.request(&format!("/{tenant}/api/notifications"), Some(event))
                .status(),
            200
        );
    }

    fn state(&self, tenant: &str) -> serde_json::Value {
        let response = self.request(&format!("/{tenant}/api/ui-state"), None);
        assert_eq!(response.status(), 200);
        response.json().expect("UI state JSON")
    }
}

impl Drop for TenantConsoleFixture {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn tenant_event(reader: &mut impl std::io::BufRead) -> serde_json::Value {
    let mut line = String::new();
    loop {
        line.clear();
        assert!(reader.read_line(&mut line).expect("SSE read") > 0);
        if let Some(data) = line.strip_prefix("data: ") {
            return serde_json::from_str(data.trim()).expect("SSE JSON");
        }
    }
}

fn tenant_contract(world: &KanbusWorld, check: impl FnOnce(PathBuf) + Send + 'static) {
    let root = world.working_directory.clone().unwrap();
    for tenant in ["alpha/project", "beta/project", "alpha/other"] {
        let tenant_root = root.join(tenant);
        std::fs::create_dir_all(tenant_root.join("project/issues")).unwrap();
        std::fs::copy(root.join(".kanbus.yml"), tenant_root.join(".kanbus.yml")).unwrap();
    }
    thread::spawn(move || check(root))
        .join()
        .expect("tenant contract");
}

#[then("focus and search state stays within its console tenant")]
fn tenant_state_contract(world: &mut KanbusWorld) {
    tenant_contract(world, |root| {
        let tenants = ["alpha/project", "beta/project", "alpha/other"];
        {
            let server = TenantConsoleFixture::start(&root, true);
            for (index, tenant) in tenants.iter().enumerate() {
                server.post(
                    tenant,
                    json!({"type":"issue_focused", "issue_id":index.to_string()}),
                );
                server.post(
                    tenant,
                    json!({"type":"ui_control", "action":{"action":"set_search", "query":tenant}}),
                );
            }
            for (index, tenant) in tenants.iter().enumerate() {
                assert_eq!(server.state(tenant)["focused_issue_id"], index.to_string());
                assert_eq!(server.state(tenant)["search_query"], *tenant);
            }
            server.post(
                tenants[0],
                json!({"type":"ui_control", "action":{"action":"clear_focus"}}),
            );
            assert!(server.state(tenants[0])["focused_issue_id"].is_null());
            assert_eq!(server.state(tenants[1])["focused_issue_id"], "1");
        }
        let server = TenantConsoleFixture::start(&root, true);
        for (index, tenant) in tenants.iter().enumerate() {
            let state = server.state(tenant);
            assert_eq!(
                state["focused_issue_id"],
                if index == 0 {
                    serde_json::Value::Null
                } else {
                    json!(index.to_string())
                }
            );
            assert_eq!(state["search_query"], *tenant);
        }
    });
}

#[then("live and replayed notifications stay within their console tenant")]
fn tenant_delivery_contract(world: &mut KanbusWorld) {
    tenant_contract(world, |root| {
        let server = TenantConsoleFixture::start(&root, true);
        let mut alpha =
            std::io::BufReader::new(server.request("/alpha/project/api/events/realtime", None));
        let mut beta =
            std::io::BufReader::new(server.request("/beta/project/api/events/realtime", None));
        let mut other =
            std::io::BufReader::new(server.request("/alpha/other/api/events/realtime", None));
        let other_marker = json!({"type":"issue_focused", "issue_id":"other-marker"});
        let focus = json!({"type":"issue_focused", "issue_id":"alpha-focus"});
        let marker = json!({"type":"issue_focused", "issue_id":"beta-marker"});
        let mut spoofed = focus.clone();
        spoofed["account"] = json!("beta");
        spoofed["project"] = json!("project");
        server.post("alpha/project", spoofed);
        server.post("beta/project", marker.clone());
        server.post("alpha/other", other_marker.clone());
        assert_eq!(tenant_event(&mut alpha), focus);
        assert_eq!(tenant_event(&mut beta), marker);
        assert_eq!(tenant_event(&mut other), other_marker);
        let update = json!({"type":"issue_updated", "issue_id":"private-alpha", "issue_data":{
            "id":"private-alpha", "title":"Private alpha issue", "description":"", "type":"task",
            "status":"open", "priority":2, "labels":[], "dependencies":[], "comments":[],
            "created_at":"2026-10-19T00:00:00Z", "updated_at":"2026-10-19T00:00:00Z"
        }});
        server.post("alpha/project", update);
        server.post("beta/project", marker.clone());
        server.post("alpha/other", other_marker.clone());
        assert_eq!(
            tenant_event(&mut alpha)["issue_data"]["title"],
            "Private alpha issue"
        );
        assert_eq!(tenant_event(&mut beta), marker);
        assert_eq!(tenant_event(&mut other), other_marker);
        for (tenant, expected) in [
            ("alpha/project", "alpha-focus"),
            ("beta/project", "beta-marker"),
            ("alpha/other", "other-marker"),
        ] {
            let mut replay = std::io::BufReader::new(
                server.request(&format!("/{tenant}/api/events/realtime"), None),
            );
            assert_eq!(tenant_event(&mut replay)["issue_id"], expected);
        }
        server.post(
            "alpha/project",
            json!({"type":"ui_control", "action":{"action":"clear_focus"}}),
        );
        server.post(
            "alpha/project",
            json!({"type":"ui_control", "action":{"action":"set_search", "query":"alpha-private"}}),
        );
        let mut replay =
            std::io::BufReader::new(server.request("/alpha/project/api/events/realtime", None));
        assert_eq!(
            tenant_event(&mut replay)["action"]["query"],
            "alpha-private"
        );
        let mut replay =
            std::io::BufReader::new(server.request("/beta/project/api/events/realtime", None));
        assert_eq!(tenant_event(&mut replay)["issue_id"], "beta-marker");
    });
}

#[then("root console notification routes require a tenant")]
fn tenant_required_contract(world: &mut KanbusWorld) {
    tenant_contract(world, |root| {
        let server = TenantConsoleFixture::start(&root, true);
        for (path, event, expected) in [
            ("/api/ui-state?account=alpha&project=project", None, 400),
            ("/api/events/realtime", None, 400),
            (
                "/api/notifications",
                Some(json!({"type":"issue_deleted", "issue_id":"x"})),
                400,
            ),
            ("/missing/project/api/ui-state", None, 404),
            ("/..%2Falpha/project/api/ui-state", None, 400),
        ] {
            assert_eq!(server.request(path, event).status(), expected, "{path}");
        }
    });
}

#[then("single tenant console notifications retain their state and stream")]
fn single_tenant_contract(world: &mut KanbusWorld) {
    tenant_contract(world, |root| {
        {
            let server = TenantConsoleFixture::start(&root, false);
            let mut stream = std::io::BufReader::new(server.request("/api/events/realtime", None));
            let focus = json!({"type":"issue_focused", "issue_id":"local-focus"});
            assert_eq!(
                server
                    .request("/api/notifications", Some(focus.clone()))
                    .status(),
                200
            );
            assert_eq!(tenant_event(&mut stream), focus);
            let search = json!({"type":"ui_control", "action":{"action":"set_search", "query":"single-search"}});
            server.post("alpha/project", search.clone());
            assert_eq!(tenant_event(&mut stream), search);
            let state: serde_json::Value = server.request("/api/ui-state", None).json().unwrap();
            assert_eq!(state["focused_issue_id"], "local-focus");
            assert_eq!(state["search_query"], "single-search");
        }
        let server = TenantConsoleFixture::start(&root, false);
        let state: serde_json::Value = server.request("/api/ui-state", None).json().unwrap();
        assert_eq!(state["focused_issue_id"], "local-focus");
        assert_eq!(state["search_query"], "single-search");
    });
}

#[then("tenant console persistence rejects redirected project and cache paths")]
fn tenant_persistence_boundary_contract(world: &mut KanbusWorld) {
    tenant_contract(world, |root| {
        let server = TenantConsoleFixture::start(&root, true);
        server.post(
            "beta/project",
            json!({"type":"ui_control", "action":{"action":"set_search", "query":"beta-private"}}),
        );
        let configuration_path = root.join("alpha/project/.kanbus.yml");
        let mut configuration: serde_yaml::Value =
            serde_yaml::from_str(&std::fs::read_to_string(&configuration_path).unwrap()).unwrap();
        configuration["project_directory"] =
            serde_yaml::Value::String("../../beta/project/project".into());
        std::fs::write(
            &configuration_path,
            serde_yaml::to_string(&configuration).unwrap(),
        )
        .unwrap();
        assert_eq!(
            server.request("/alpha/project/api/ui-state", None).status(),
            403
        );
        configuration["project_directory"] = serde_yaml::Value::String("project".into());
        std::fs::write(
            &configuration_path,
            serde_yaml::to_string(&configuration).unwrap(),
        )
        .unwrap();
        #[cfg(unix)]
        {
            let cache = root.join("alpha/project/project/.cache");
            std::os::unix::fs::symlink(root.join("beta/project/project/.cache"), &cache).unwrap();
            assert_eq!(
                server.request("/alpha/project/api/ui-state", None).status(),
                403
            );
            std::fs::remove_file(&cache).unwrap();
            std::os::unix::fs::symlink(root.join("beta/project/missing-cache"), &cache).unwrap();
            assert_eq!(
                server.request("/alpha/project/api/ui-state", None).status(),
                403
            );
            let alias = root.join("alpha/other");
            std::fs::remove_dir_all(&alias).unwrap();
            std::os::unix::fs::symlink(root.join("beta/project"), alias).unwrap();
            assert_eq!(
                server.request("/alpha/other/api/ui-state", None).status(),
                403
            );
            std::fs::remove_file(cache).unwrap();
        }
        assert!(server.state("alpha/project")["search_query"].is_null());
        configuration["project_directory"] =
            serde_yaml::Value::String("../../beta/project/project".into());
        std::fs::write(
            &configuration_path,
            serde_yaml::to_string(&configuration).unwrap(),
        )
        .unwrap();
        server.post(
            "alpha/project",
            json!({"type":"ui_control", "action":{"action":"set_search", "query":"alpha-private"}}),
        );
        let persisted: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(root.join("beta/project/project/.cache/console_state.json"))
                .unwrap(),
        )
        .unwrap();
        assert_eq!(persisted["search_query"], "beta-private");
        assert_eq!(server.state("beta/project")["search_query"], "beta-private");
    });
}
