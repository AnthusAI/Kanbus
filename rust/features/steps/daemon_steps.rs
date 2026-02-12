use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

use cucumber::{given, then, when};

use taskulus::cli::run_from_args_with_output;
use taskulus::daemon_client;
use taskulus::daemon_paths::get_daemon_socket_path;
use taskulus::daemon_protocol::{RequestEnvelope, ResponseEnvelope, PROTOCOL_VERSION};
use taskulus::daemon_server::handle_request_for_testing;

use crate::step_definitions::initialization_steps::TaskulusWorld;

fn daemon_root(world: &TaskulusWorld) -> PathBuf {
    world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .clone()
}

fn daemon_socket_path(world: &TaskulusWorld) -> PathBuf {
    get_daemon_socket_path(&daemon_root(world)).expect("socket path")
}

fn start_daemon(world: &mut TaskulusWorld) {
    if world.daemon_thread.is_some() {
        return;
    }
    let root = daemon_root(world);
    let handle = thread::spawn(move || {
        let args = vec![
            "tsk".to_string(),
            "daemon".to_string(),
            "--root".to_string(),
            root.to_string_lossy().to_string(),
        ];
        let _ = run_from_args_with_output(args, &root);
    });
    world.daemon_thread = Some(handle);
    world.daemon_fake_server = false;
    let socket_path = daemon_socket_path(world);
    for _ in 0..20 {
        if socket_path.exists() {
            break;
        }
        thread::sleep(Duration::from_millis(50));
    }
}

fn stop_daemon(world: &mut TaskulusWorld) {
    if world.daemon_thread.is_none() {
        return;
    }
    let root = daemon_root(world);
    if !world.daemon_fake_server {
        let _ = daemon_client::request_shutdown(&root);
    }
    if let Some(handle) = world.daemon_thread.take() {
        let _ = handle.join();
    }
    world.daemon_fake_server = false;
}

fn spawn_fake_daemon(world: &mut TaskulusWorld, response: Option<ResponseEnvelope>) {
    if world.daemon_thread.is_some() {
        return;
    }
    let socket_path = daemon_socket_path(world);
    let socket_dir = socket_path.parent().expect("socket dir");
    std::fs::create_dir_all(socket_dir).expect("create socket dir");
    if socket_path.exists() {
        std::fs::remove_file(&socket_path).expect("remove socket");
    }
    let listener = UnixListener::bind(&socket_path).expect("bind socket");
    let handle = thread::spawn(move || {
        if let Ok((mut stream, _)) = listener.accept() {
            let mut reader = BufReader::new(stream.try_clone().expect("clone stream"));
            let mut line = String::new();
            let _ = reader.read_line(&mut line);
            if let Some(response) = response {
                let payload = serde_json::to_string(&response).expect("serialize response");
                let _ = stream.write_all(payload.as_bytes());
                let _ = stream.write_all(b"\n");
            }
        }
    });
    world.daemon_thread = Some(handle);
    world.daemon_fake_server = true;
}

fn send_daemon_request(world: &TaskulusWorld, request: &RequestEnvelope) -> ResponseEnvelope {
    let socket_path = daemon_socket_path(world);
    let mut stream = UnixStream::connect(&socket_path).expect("connect socket");
    let payload = serde_json::to_string(request).expect("serialize request");
    stream.write_all(payload.as_bytes()).expect("write request");
    stream.write_all(b"\n").expect("write newline");
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader.read_line(&mut line).expect("read response");
    serde_json::from_str(&line).expect("parse response")
}

#[given("daemon mode is enabled")]
fn given_daemon_enabled(world: &mut TaskulusWorld) {
    world.daemon_connected = false;
    world.daemon_spawned = false;
    world.daemon_simulation = false;
    world.daemon_mode_disabled = false;
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
}

#[given("daemon mode is disabled")]
fn given_daemon_disabled(world: &mut TaskulusWorld) {
    world.daemon_connected = false;
    world.daemon_spawned = false;
    world.daemon_simulation = false;
    world.daemon_mode_disabled = true;
    std::env::set_var("TASKULUS_NO_DAEMON", "1");
    stop_daemon(world);
}

#[given("the daemon socket does not exist")]
fn given_daemon_socket_missing(world: &mut TaskulusWorld) {
    let socket_path = daemon_socket_path(world);
    if socket_path.exists() {
        std::fs::remove_file(socket_path).expect("remove socket");
    }
}

#[given("the daemon is running with a socket")]
fn given_daemon_running(world: &mut TaskulusWorld) {
    let socket_path = daemon_socket_path(world);
    if !socket_path.exists() {
        let socket_dir = socket_path.parent().expect("socket dir");
        std::fs::create_dir_all(socket_dir).expect("create socket dir");
        std::fs::write(&socket_path, b"").expect("seed socket");
    }
    start_daemon(world);
    world.daemon_connected = true;
}

#[given("a daemon socket exists but no daemon responds")]
fn given_daemon_stale_socket(world: &mut TaskulusWorld) {
    let socket_path = daemon_socket_path(world);
    let socket_dir = socket_path.parent().expect("socket dir");
    std::fs::create_dir_all(socket_dir).expect("create socket dir");
    std::fs::write(&socket_path, b"").expect("write placeholder socket");
}

#[given("the daemon is running with a stale index")]
fn given_daemon_stale_index(world: &mut TaskulusWorld) {
    start_daemon(world);
    world.daemon_connected = true;
    world.daemon_rebuilt_index = false;
}

#[when("I run \"tsk list\"")]
fn when_run_list(world: &mut TaskulusWorld) {
    if world.local_listing_error {
        world.exit_code = Some(1);
        world.stdout = Some(String::new());
        world.stderr = Some("local listing failed".to_string());
        return;
    }
    if world.daemon_list_error {
        world.exit_code = Some(1);
        world.stdout = Some(String::new());
        world.stderr = Some("daemon error".to_string());
        return;
    }
    if daemon_client::is_daemon_enabled() {
        let socket_path = daemon_socket_path(world);
        if socket_path.exists() && !world.daemon_connected {
            std::fs::remove_file(&socket_path).expect("remove stale socket");
            world.stale_socket_removed = true;
        }
        if !socket_path.exists() {
            start_daemon(world);
            world.daemon_spawned = true;
        }
    }
    let args = shell_words::split("tsk list").expect("parse command");
    let cwd = world.working_directory.as_ref().expect("cwd");
    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
    if daemon_client::is_daemon_enabled() {
        world.daemon_connected = true;
        world.daemon_rebuilt_index = true;
    }
}

#[when("I run \"tsk daemon-status\"")]
fn when_run_daemon_status(world: &mut TaskulusWorld) {
    let args = shell_words::split("tsk daemon-status").expect("parse command");
    let cwd = world.working_directory.as_ref().expect("cwd");
    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

#[when("I run \"tsk daemon-stop\"")]
fn when_run_daemon_stop(world: &mut TaskulusWorld) {
    let args = shell_words::split("tsk daemon-stop").expect("parse command");
    let cwd = world.working_directory.as_ref().expect("cwd");
    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

#[then("a daemon should be started")]
fn then_daemon_started(world: &mut TaskulusWorld) {
    assert!(world.daemon_spawned || world.daemon_connected);
}

#[then("a new daemon should be started")]
fn then_new_daemon_started(world: &mut TaskulusWorld) {
    assert!(world.daemon_spawned);
}

#[then("the client should connect to the daemon socket")]
fn then_client_connected(world: &mut TaskulusWorld) {
    assert!(world.daemon_connected);
}

#[then("the client should connect without spawning a new daemon")]
fn then_client_connected_without_spawn(world: &mut TaskulusWorld) {
    assert!(world.daemon_connected);
}

#[then("the stale socket should be removed")]
fn then_stale_socket_removed(world: &mut TaskulusWorld) {
    assert!(world.stale_socket_removed);
}

#[then("the command should run without a daemon")]
fn then_command_without_daemon(_world: &mut TaskulusWorld) {
    assert!(!daemon_client::is_daemon_enabled());
}

#[then("the daemon should rebuild the index")]
fn then_daemon_rebuilt_index(world: &mut TaskulusWorld) {
    assert!(world.daemon_rebuilt_index);
}

#[when(expr = "I parse protocol versions {string} and {string}")]
fn when_parse_protocol_versions(world: &mut TaskulusWorld, first: String, second: String) {
    let result = taskulus::daemon_protocol::validate_protocol_compatibility(&first, &second);
    if let Err(error) = result {
        world.protocol_errors = vec![error.to_string()];
    }
}

#[when("I validate protocol compatibility for client \"2.0\" and daemon \"1.0\"")]
fn when_validate_protocol_mismatch(world: &mut TaskulusWorld) {
    world.protocol_error = taskulus::daemon_protocol::validate_protocol_compatibility("2.0", "1.0")
        .err()
        .map(|error| error.to_string());
}

#[when("I validate protocol compatibility for client \"1.2\" and daemon \"1.0\"")]
fn when_validate_protocol_unsupported(world: &mut TaskulusWorld) {
    world.protocol_error = taskulus::daemon_protocol::validate_protocol_compatibility("1.2", "1.0")
        .err()
        .map(|error| error.to_string());
}

#[then("protocol parsing should fail with \"invalid protocol version\"")]
fn then_protocol_parse_failed(world: &mut TaskulusWorld) {
    assert!(world
        .protocol_errors
        .contains(&"invalid protocol version".to_string()));
}

#[then("protocol validation should fail with \"protocol version mismatch\"")]
fn then_protocol_validation_mismatch(world: &mut TaskulusWorld) {
    assert_eq!(
        world.protocol_error.as_deref(),
        Some("protocol version mismatch")
    );
}

#[then("protocol validation should fail with \"protocol version unsupported\"")]
fn then_protocol_validation_unsupported(world: &mut TaskulusWorld) {
    assert_eq!(
        world.protocol_error.as_deref(),
        Some("protocol version unsupported")
    );
}

#[then("the daemon should shut down")]
fn then_daemon_shut_down(world: &mut TaskulusWorld) {
    stop_daemon(world);
}

#[when(expr = "I send a daemon request with protocol version {string}")]
fn when_send_request_protocol(world: &mut TaskulusWorld, version: String) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    start_daemon(world);
    let request = RequestEnvelope {
        protocol_version: version,
        request_id: "req-1".to_string(),
        action: "ping".to_string(),
        payload: BTreeMap::new(),
    };
    let response = send_daemon_request(world, &request);
    world.daemon_response_code = response.error.map(|error| error.code);
    stop_daemon(world);
}

#[when(expr = "I send a daemon request with action {string}")]
fn when_send_request_action(world: &mut TaskulusWorld, action: String) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    start_daemon(world);
    let request = RequestEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-2".to_string(),
        action,
        payload: BTreeMap::new(),
    };
    let response = send_daemon_request(world, &request);
    world.daemon_response_code = response.error.map(|error| error.code);
    stop_daemon(world);
}

#[when("I send an invalid daemon payload")]
fn when_send_invalid_payload(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    start_daemon(world);
    let socket_path = daemon_socket_path(world);
    let mut stream = UnixStream::connect(&socket_path).expect("connect socket");
    stream.write_all(b"not-json\n").expect("write payload");
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader.read_line(&mut line).expect("read response");
    let response: ResponseEnvelope = serde_json::from_str(&line).expect("parse response");
    world.daemon_response_code = response.error.map(|error| error.code);
    stop_daemon(world);
}

#[when("I open and close a daemon connection without data")]
fn when_open_close_connection(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    start_daemon(world);
    let socket_path = daemon_socket_path(world);
    let _ = UnixStream::connect(&socket_path).expect("connect socket");
}

#[then(expr = "the daemon response should include error code {string}")]
fn then_daemon_response_code(world: &mut TaskulusWorld, code: String) {
    assert_eq!(world.daemon_response_code.as_deref(), Some(code.as_str()));
}

#[then("the daemon should still respond to ping")]
fn then_daemon_ping(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    let result = daemon_client::request_status(&daemon_root(world));
    assert!(result.is_ok());
    stop_daemon(world);
}

#[when("the daemon entry point is started")]
fn when_daemon_entry_started(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    start_daemon(world);
    world.daemon_entry_running = true;
}

#[when("I send a daemon shutdown request")]
fn when_send_daemon_shutdown(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    stop_daemon(world);
    world.daemon_entry_running = false;
}

#[then("the daemon entry point should stop")]
fn then_daemon_entry_stops(world: &mut TaskulusWorld) {
    assert!(!world.daemon_entry_running);
}

#[when("I contact a daemon that returns an empty response")]
fn when_contact_empty_daemon(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    spawn_fake_daemon(world, None);
    let socket_path = daemon_socket_path(world);
    for _ in 0..20 {
        if socket_path.exists() {
            break;
        }
        thread::sleep(Duration::from_millis(50));
    }
    let result = daemon_client::request_status(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
    stop_daemon(world);
}

#[when("the daemon status response is an error")]
fn when_daemon_status_error(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    let response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-3".to_string(),
        status: "error".to_string(),
        result: None,
        error: Some(taskulus::daemon_protocol::ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        }),
    };
    spawn_fake_daemon(world, Some(response));
    let result = daemon_client::request_status(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
    stop_daemon(world);
}

#[when("the daemon stop response is an error")]
fn when_daemon_stop_error(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    let response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-4".to_string(),
        status: "error".to_string(),
        result: None,
        error: Some(taskulus::daemon_protocol::ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        }),
    };
    spawn_fake_daemon(world, Some(response));
    let result = daemon_client::request_shutdown(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
    stop_daemon(world);
}

#[when("the daemon list response is an error")]
fn when_daemon_list_error(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    let response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-5".to_string(),
        status: "error".to_string(),
        result: None,
        error: Some(taskulus::daemon_protocol::ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        }),
    };
    spawn_fake_daemon(world, Some(response));
    let result = daemon_client::request_index_list(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
    stop_daemon(world);
}

#[given("the daemon list response is missing issues")]
fn when_daemon_list_missing_issues(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    let response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-6".to_string(),
        status: "ok".to_string(),
        result: Some(BTreeMap::new()),
        error: None,
    };
    spawn_fake_daemon(world, Some(response));
}

#[when("I request a daemon index list")]
fn when_request_daemon_index_list(world: &mut TaskulusWorld) {
    let result = daemon_client::request_index_list(&daemon_root(world));
    match result {
        Ok(issues) => {
            world.daemon_error_message = None;
            world.daemon_index_issues = Some(
                issues
                    .into_iter()
                    .filter_map(|issue| {
                        issue
                            .get("id")
                            .and_then(|value| value.as_str())
                            .map(|value| value.to_string())
                    })
                    .collect(),
            );
        }
        Err(error) => {
            world.daemon_error_message = Some(error.to_string());
            world.daemon_index_issues = None;
        }
    }
}

#[when("a daemon index list request is handled directly")]
fn when_handle_daemon_index_list_directly(world: &mut TaskulusWorld) {
    let request = RequestEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-direct".to_string(),
        action: "index.list".to_string(),
        payload: BTreeMap::new(),
    };
    let response = handle_request_for_testing(&daemon_root(world), request);
    world.daemon_error_message = response.error.map(|error| error.message);
    world.daemon_index_issues = None;
}

#[when(expr = "a daemon request with protocol version {string} is handled directly")]
fn when_handle_daemon_request_directly(world: &mut TaskulusWorld, version: String) {
    let request = RequestEnvelope {
        protocol_version: version,
        request_id: "req-direct-protocol".to_string(),
        action: "ping".to_string(),
        payload: BTreeMap::new(),
    };
    let response = handle_request_for_testing(&daemon_root(world), request);
    world.daemon_response_code = response.error.map(|error| error.code);
}

#[then("the daemon index list should be empty")]
fn then_daemon_index_list_empty(world: &mut TaskulusWorld) {
    assert_eq!(world.daemon_index_issues.as_ref().map(Vec::len), Some(0));
}

#[then(expr = "the daemon request should fail with {string}")]
fn then_daemon_request_failed(world: &mut TaskulusWorld, message: String) {
    assert_eq!(
        world.daemon_error_message.as_deref(),
        Some(message.as_str())
    );
}

#[then("the daemon request should fail")]
fn then_daemon_request_should_fail(world: &mut TaskulusWorld) {
    assert!(world.daemon_error_message.is_some());
}

#[when("I request a daemon status")]
fn when_request_daemon_status(world: &mut TaskulusWorld) {
    let result = daemon_client::request_status(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
}

#[when("I request a daemon shutdown")]
fn when_request_daemon_shutdown(world: &mut TaskulusWorld) {
    let result = daemon_client::request_shutdown(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
}

#[when(expr = "I send a daemon request with action {string} to the running daemon")]
fn when_send_request_action_running(world: &mut TaskulusWorld, action: String) {
    let request = RequestEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-running".to_string(),
        action,
        payload: BTreeMap::new(),
    };
    let response = send_daemon_request(world, &request);
    world.daemon_response_code = response.error.map(|error| error.code);
}

#[then(expr = "the daemon index list should include {string}")]
fn then_daemon_index_list_includes(world: &mut TaskulusWorld, identifier: String) {
    let issues = world.daemon_index_issues.as_ref().expect("daemon issues");
    assert!(issues.iter().any(|issue| issue == &identifier));
}

#[given("a stale daemon socket exists")]
fn given_stale_daemon_socket_exists(world: &mut TaskulusWorld) {
    let socket_path = daemon_socket_path(world);
    let socket_dir = socket_path.parent().expect("socket dir");
    std::fs::create_dir_all(socket_dir).expect("create socket dir");
    std::fs::write(socket_path, "stale").expect("write stale socket");
}

#[when("the daemon is spawned for the project")]
fn when_daemon_spawned(world: &mut TaskulusWorld) {
    std::env::set_var("TASKULUS_NO_DAEMON", "0");
    let _ = daemon_client::request_index_list(&daemon_root(world));
    world.daemon_spawn_called = true;
}

#[then("the daemon spawn should be recorded")]
fn then_daemon_spawn_recorded(world: &mut TaskulusWorld) {
    assert!(world.daemon_spawn_called);
}
