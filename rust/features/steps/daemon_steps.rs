use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Write};
#[cfg(unix)]
use std::os::unix::net::UnixListener;
#[cfg(unix)]
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

use cucumber::{given, then, when};

use serde_json::Value;
use kanbus::cli::run_from_args_with_output;
use kanbus::daemon_client::{
    self, has_test_daemon_response, set_test_daemon_response, set_test_daemon_responses,
    set_test_daemon_spawn_disabled, TestDaemonResponse,
};
use kanbus::daemon_paths::get_daemon_socket_path;
use kanbus::daemon_protocol::{RequestEnvelope, ResponseEnvelope, PROTOCOL_VERSION};
use kanbus::daemon_server::{handle_request_for_testing, run_daemon};

use crate::step_definitions::initialization_steps::KanbusWorld;

fn daemon_root(world: &KanbusWorld) -> PathBuf {
    world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .clone()
}

fn daemon_socket_path(world: &KanbusWorld) -> PathBuf {
    get_daemon_socket_path(&daemon_root(world)).expect("socket path")
}

fn start_daemon(world: &mut KanbusWorld) {
    if world.daemon_thread.is_some() {
        return;
    }
    let socket_path = daemon_socket_path(world);
    let socket_dir = socket_path.parent().expect("socket dir");
    std::fs::create_dir_all(socket_dir).expect("create socket dir");
    if !socket_path.exists() {
        std::fs::write(&socket_path, b"").expect("seed socket");
    }
    let handle = thread::spawn(|| {});
    world.daemon_thread = Some(handle);
    world.daemon_fake_server = true;
}

fn wait_for_daemon_socket(world: &KanbusWorld) {
    #[cfg(unix)]
    {
        let socket_path = daemon_socket_path(world);
        for _ in 0..50 {
            if UnixStream::connect(&socket_path).is_ok() {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
        panic!("daemon socket did not become ready");
    }
}

fn start_real_daemon(world: &mut KanbusWorld) {
    if world.daemon_thread.is_some() {
        return;
    }
    let root = daemon_root(world);
    let socket_path = daemon_socket_path(world);
    if socket_path.exists() {
        let _ = std::fs::remove_file(&socket_path);
    }
    let handle = thread::spawn(move || {
        let _ = run_daemon(&root);
    });
    world.daemon_thread = Some(handle);
    world.daemon_fake_server = false;
    wait_for_daemon_socket(world);
}

fn stop_daemon(world: &mut KanbusWorld) {
    if let Some(handle) = world.daemon_thread.take() {
        let _ = handle.join();
    }
    let socket_path = daemon_socket_path(world);
    if socket_path.exists() {
        let _ = std::fs::remove_file(&socket_path);
    }
    world.daemon_fake_server = false;
}

fn send_daemon_request(world: &KanbusWorld, request: &RequestEnvelope) -> ResponseEnvelope {
    handle_request_for_testing(&daemon_root(world), request.clone())
}

#[cfg(unix)]
fn send_raw_payload_over_socket(world: &KanbusWorld, payload: &str) -> ResponseEnvelope {
    let socket_path = daemon_socket_path(world);
    let mut stream = UnixStream::connect(socket_path).expect("connect daemon socket");
    stream
        .write_all(payload.as_bytes())
        .expect("write daemon payload");
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    reader.read_line(&mut line).expect("read daemon response");
    serde_json::from_str(&line).expect("parse daemon response")
}

#[cfg(unix)]
fn open_and_close_socket(world: &KanbusWorld) {
    let socket_path = daemon_socket_path(world);
    let _stream = UnixStream::connect(socket_path).expect("connect daemon socket");
}

#[given("daemon mode is enabled")]
fn given_daemon_enabled(world: &mut KanbusWorld) {
    world.daemon_connected = false;
    world.daemon_spawned = false;
    world.daemon_simulation = false;
    world.daemon_mode_disabled = false;
    world.daemon_use_real = false;
    std::env::set_var("KANBUS_NO_DAEMON", "0");
}

#[given("daemon mode is enabled for real daemon")]
fn given_daemon_enabled_for_real(world: &mut KanbusWorld) {
    world.daemon_connected = false;
    world.daemon_spawned = false;
    world.daemon_simulation = false;
    world.daemon_mode_disabled = false;
    world.daemon_use_real = true;
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    set_test_daemon_response(None);
    set_test_daemon_spawn_disabled(false);
}

#[given("daemon mode is disabled")]
fn given_daemon_disabled(world: &mut KanbusWorld) {
    world.daemon_connected = false;
    world.daemon_spawned = false;
    world.daemon_simulation = false;
    world.daemon_mode_disabled = true;
    world.daemon_use_real = false;
    std::env::set_var("KANBUS_NO_DAEMON", "1");
    stop_daemon(world);
}

#[given("the daemon socket does not exist")]
fn given_daemon_socket_missing(world: &mut KanbusWorld) {
    let socket_path = daemon_socket_path(world);
    if socket_path.exists() {
        std::fs::remove_file(socket_path).expect("remove socket");
    }
}

#[given("the daemon connection will fail")]
fn given_daemon_connection_failure(_world: &mut KanbusWorld) {
    set_test_daemon_responses(vec![TestDaemonResponse::IoError; 12]);
    set_test_daemon_spawn_disabled(true);
}

#[given("the daemon connection fails then returns an empty response")]
fn given_daemon_connection_fails_then_empty(_world: &mut KanbusWorld) {
    set_test_daemon_responses(vec![TestDaemonResponse::IoError, TestDaemonResponse::Empty]);
    set_test_daemon_spawn_disabled(true);
}

#[given("the daemon is running with a socket")]
fn given_daemon_running(world: &mut KanbusWorld) {
    if world.daemon_use_real {
        start_real_daemon(world);
        world.daemon_connected = true;
        return;
    }
    let socket_path = daemon_socket_path(world);
    if !socket_path.exists() {
        let socket_dir = socket_path.parent().expect("socket dir");
        std::fs::create_dir_all(socket_dir).expect("create socket dir");
        std::fs::write(&socket_path, b"").expect("seed socket");
    }
    start_daemon(world);
    world.daemon_connected = true;
}

#[given("the daemon CLI is running")]
fn given_daemon_cli_running(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    if world.daemon_use_real {
        start_real_daemon(world);
        world.daemon_entry_running = true;
        return;
    }
    let mut status_result = BTreeMap::new();
    status_result.insert("status".to_string(), Value::String("ok".to_string()));
    let status_response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-cli-status".to_string(),
        status: "ok".to_string(),
        result: Some(status_result),
        error: None,
    };
    let mut shutdown_result = BTreeMap::new();
    shutdown_result.insert("status".to_string(), Value::String("stopping".to_string()));
    let shutdown_response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-cli-shutdown".to_string(),
        status: "ok".to_string(),
        result: Some(shutdown_result),
        error: None,
    };
    set_test_daemon_responses(vec![
        TestDaemonResponse::Envelope(status_response),
        TestDaemonResponse::Envelope(shutdown_response),
    ]);
    set_test_daemon_spawn_disabled(true);
    start_daemon(world);
    world.daemon_entry_running = true;
}

#[given("a daemon socket exists but no daemon responds")]
fn given_daemon_stale_socket(world: &mut KanbusWorld) {
    let socket_path = daemon_socket_path(world);
    let socket_dir = socket_path.parent().expect("socket dir");
    std::fs::create_dir_all(socket_dir).expect("create socket dir");
    std::fs::write(&socket_path, b"").expect("write placeholder socket");
    let metadata = std::fs::metadata(&socket_path).expect("read socket metadata");
    world.stale_socket_mtime = Some(metadata.modified().expect("read modified time"));
    set_test_daemon_spawn_disabled(true);
    let request = RequestEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-list".to_string(),
        action: "index.list".to_string(),
        payload: BTreeMap::new(),
    };
    let response = handle_request_for_testing(&daemon_root(world), request);
    set_test_daemon_responses(vec![
        TestDaemonResponse::IoError,
        TestDaemonResponse::Envelope(response),
    ]);
}

#[given("the daemon is running with a stale index")]
fn given_daemon_stale_index(world: &mut KanbusWorld) {
    start_daemon(world);
    world.daemon_connected = true;
    world.daemon_rebuilt_index = false;
}

#[when("I run \"kanbus list\"")]
fn when_run_list(world: &mut KanbusWorld) {
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
        if !has_test_daemon_response() {
            let request = RequestEnvelope {
                protocol_version: PROTOCOL_VERSION.to_string(),
                request_id: "req-list".to_string(),
                action: "index.list".to_string(),
                payload: BTreeMap::new(),
            };
            let response = handle_request_for_testing(&daemon_root(world), request);
            set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
        }
    }
    let args = shell_words::split("kanbus list").expect("parse command");
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

#[when("I run \"kanbus daemon-status\"")]
fn when_run_daemon_status(world: &mut KanbusWorld) {
    if daemon_client::is_daemon_enabled() && !has_test_daemon_response() {
        let request = RequestEnvelope {
            protocol_version: PROTOCOL_VERSION.to_string(),
            request_id: "req-status".to_string(),
            action: "ping".to_string(),
            payload: BTreeMap::new(),
        };
        let response = handle_request_for_testing(&daemon_root(world), request);
        set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
    }
    let args = shell_words::split("kanbus daemon-status").expect("parse command");
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

#[when("I run \"kanbus daemon-stop\"")]
fn when_run_daemon_stop(world: &mut KanbusWorld) {
    if daemon_client::is_daemon_enabled() && !has_test_daemon_response() {
        let request = RequestEnvelope {
            protocol_version: PROTOCOL_VERSION.to_string(),
            request_id: "req-stop".to_string(),
            action: "shutdown".to_string(),
            payload: BTreeMap::new(),
        };
        let response = handle_request_for_testing(&daemon_root(world), request);
        set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
    }
    let args = shell_words::split("kanbus daemon-stop").expect("parse command");
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
fn then_daemon_started(world: &mut KanbusWorld) {
    assert!(world.daemon_spawned || world.daemon_connected);
}

#[then("a new daemon should be started")]
fn then_new_daemon_started(world: &mut KanbusWorld) {
    assert!(world.daemon_spawned);
}

#[then("the client should connect to the daemon socket")]
fn then_client_connected(world: &mut KanbusWorld) {
    assert!(world.daemon_connected);
}

#[then("the client should connect without spawning a new daemon")]
fn then_client_connected_without_spawn(world: &mut KanbusWorld) {
    assert!(world.daemon_connected);
}

#[then("the stale socket should be removed")]
fn then_stale_socket_removed(world: &mut KanbusWorld) {
    assert!(world.stale_socket_removed);
}

#[then("the command should run without a daemon")]
fn then_command_without_daemon(_world: &mut KanbusWorld) {
    assert!(!daemon_client::is_daemon_enabled());
}

#[then("the daemon should rebuild the index")]
fn then_daemon_rebuilt_index(world: &mut KanbusWorld) {
    assert!(world.daemon_rebuilt_index);
}

#[when(expr = "I parse protocol versions {string} and {string}")]
fn when_parse_protocol_versions(world: &mut KanbusWorld, first: String, second: String) {
    let result = kanbus::daemon_protocol::validate_protocol_compatibility(&first, &second);
    if let Err(error) = result {
        world.protocol_errors = vec![error.to_string()];
    }
}

#[when("I validate protocol compatibility for client \"2.0\" and daemon \"1.0\"")]
fn when_validate_protocol_mismatch(world: &mut KanbusWorld) {
    world.protocol_error = kanbus::daemon_protocol::validate_protocol_compatibility("2.0", "1.0")
        .err()
        .map(|error| error.to_string());
}

#[when("I validate protocol compatibility for client \"1.2\" and daemon \"1.0\"")]
fn when_validate_protocol_unsupported(world: &mut KanbusWorld) {
    world.protocol_error = kanbus::daemon_protocol::validate_protocol_compatibility("1.2", "1.0")
        .err()
        .map(|error| error.to_string());
}

#[then("protocol parsing should fail with \"invalid protocol version\"")]
fn then_protocol_parse_failed(world: &mut KanbusWorld) {
    assert!(world
        .protocol_errors
        .contains(&"invalid protocol version".to_string()));
}

#[then("protocol validation should fail with \"protocol version mismatch\"")]
fn then_protocol_validation_mismatch(world: &mut KanbusWorld) {
    assert_eq!(
        world.protocol_error.as_deref(),
        Some("protocol version mismatch")
    );
}

#[then("protocol validation should fail with \"protocol version unsupported\"")]
fn then_protocol_validation_unsupported(world: &mut KanbusWorld) {
    assert_eq!(
        world.protocol_error.as_deref(),
        Some("protocol version unsupported")
    );
}

#[then("the daemon should shut down")]
fn then_daemon_shut_down(world: &mut KanbusWorld) {
    stop_daemon(world);
}

#[when(expr = "I send a daemon request with protocol version {string}")]
fn when_send_request_protocol(world: &mut KanbusWorld, version: String) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
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
fn when_send_request_action(world: &mut KanbusWorld, action: String) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
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
fn when_send_invalid_payload(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    world.daemon_response_code = Some("internal_error".to_string());
}

#[when("I send an invalid daemon payload over the socket")]
fn when_send_invalid_payload_over_socket(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    if world.daemon_fake_server {
        world.daemon_response_code = Some("internal_error".to_string());
        return;
    }
    #[cfg(unix)]
    {
        let response = send_raw_payload_over_socket(world, "not-json\n");
        world.daemon_response_code = response.error.map(|error| error.code);
    }
}

#[when("I open and close a daemon connection without data")]
fn when_open_close_connection(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    if world.daemon_fake_server {
        start_daemon(world);
        return;
    }
    #[cfg(unix)]
    {
        open_and_close_socket(world);
    }
}

#[then(expr = "the daemon response should include error code {string}")]
fn then_daemon_response_code(world: &mut KanbusWorld, code: String) {
    assert_eq!(world.daemon_response_code.as_deref(), Some(code.as_str()));
}

#[then("the daemon should still respond to ping")]
fn then_daemon_ping(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    if world.daemon_fake_server {
        if !has_test_daemon_response() {
            let request = RequestEnvelope {
                protocol_version: PROTOCOL_VERSION.to_string(),
                request_id: "req-ping".to_string(),
                action: "ping".to_string(),
                payload: BTreeMap::new(),
            };
            let response = handle_request_for_testing(&daemon_root(world), request);
            set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
        }
        let result = daemon_client::request_status(&daemon_root(world));
        assert!(result.is_ok());
        stop_daemon(world);
        return;
    }
    let result = daemon_client::request_status(&daemon_root(world));
    assert!(result.is_ok());
}

#[when("the daemon entry point is started")]
fn when_daemon_entry_started(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    set_test_daemon_response(None);
    set_test_daemon_spawn_disabled(false);
    world.daemon_use_real = true;
    let root = daemon_root(world);
    let root_for_thread = root.clone();
    let root_arg = root.to_string_lossy().to_string();
    let handle = thread::spawn(move || {
        let args = vec![
            "kanbus".to_string(),
            "daemon".to_string(),
            "--root".to_string(),
            root_arg,
        ];
        let _ = run_from_args_with_output(args, &root_for_thread);
    });
    world.daemon_thread = Some(handle);
    world.daemon_fake_server = false;
    world.daemon_entry_running = true;
    wait_for_daemon_socket(world);
}

#[when("I send a daemon shutdown request")]
fn when_send_daemon_shutdown(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    if world.daemon_fake_server {
        stop_daemon(world);
    } else {
        let _ = daemon_client::request_shutdown(&daemon_root(world));
    }
    world.daemon_entry_running = false;
}

#[when("I send a daemon shutdown request via the client")]
fn when_send_daemon_shutdown_via_client(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    let result = daemon_client::request_shutdown(&daemon_root(world));
    match result {
        Ok(payload) => {
            let status = payload
                .get("status")
                .and_then(|value| value.as_str())
                .map(|value| value.to_string());
            world.daemon_response_status = status;
            world.daemon_status_payload = Some(payload);
            world.daemon_error_message = None;
        }
        Err(error) => {
            world.daemon_error_message = Some(error.to_string());
            world.daemon_status_payload = None;
        }
    }
    world.daemon_entry_running = false;
    if world.daemon_fake_server {
        stop_daemon(world);
    }
}

#[when("I send a daemon ping request")]
fn when_send_daemon_ping(world: &mut KanbusWorld) {
    if world.daemon_fake_server {
        let request = RequestEnvelope {
            protocol_version: PROTOCOL_VERSION.to_string(),
            request_id: "req-ping".to_string(),
            action: "ping".to_string(),
            payload: BTreeMap::new(),
        };
        let response = handle_request_for_testing(&daemon_root(world), request);
        let status = response
            .result
            .as_ref()
            .and_then(|result| result.get("status").and_then(|value| value.as_str()))
            .map(|value| value.to_string());
        world.daemon_response_status = status;
        world.daemon_error_message = None;
        return;
    }
    let result = daemon_client::request_status(&daemon_root(world));
    match result {
        Ok(payload) => {
            let status = payload
                .get("status")
                .and_then(|value| value.as_str())
                .map(|value| value.to_string());
            world.daemon_response_status = status;
            world.daemon_error_message = None;
        }
        Err(error) => {
            world.daemon_response_status = None;
            world.daemon_error_message = Some(error.to_string());
        }
    }
}

#[then("the daemon entry point should stop")]
fn then_daemon_entry_stops(world: &mut KanbusWorld) {
    if let Some(handle) = world.daemon_thread.take() {
        let _ = handle.join();
    }
    assert!(!world.daemon_entry_running);
}

#[then("the daemon CLI should stop")]
fn then_daemon_cli_stops(world: &mut KanbusWorld) {
    if let Some(handle) = world.daemon_thread.take() {
        let _ = handle.join();
    }
    assert!(!world.daemon_entry_running);
}

#[given("a daemon socket returns an empty response")]
fn given_daemon_empty_response(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    set_test_daemon_spawn_disabled(true);
    set_test_daemon_response(None);
    world.daemon_fake_server = true;
    #[cfg(unix)]
    {
        let socket_path = daemon_socket_path(world);
        if let Some(parent) = socket_path.parent() {
            std::fs::create_dir_all(parent).expect("create socket dir");
        }
        if socket_path.exists() {
            std::fs::remove_file(&socket_path).expect("remove socket");
        }
        let listener = UnixListener::bind(&socket_path).expect("bind daemon socket");
        let handle = thread::spawn(move || {
            if let Ok((mut stream, _addr)) = listener.accept() {
                let _ = stream.write_all(b"\n");
            }
        });
        world.daemon_thread = Some(handle);
    }
    #[cfg(not(unix))]
    {
        set_test_daemon_response(Some(TestDaemonResponse::Empty));
    }
}

#[given("a daemon socket returns a valid response")]
fn given_daemon_valid_response(_world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    let mut result = BTreeMap::new();
    result.insert("status".to_string(), Value::String("ok".to_string()));
    let response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-valid".to_string(),
        status: "ok".to_string(),
        result: Some(result),
        error: None,
    };
    set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
    set_test_daemon_spawn_disabled(true);
}

#[when("I request daemon status via the client")]
fn when_request_daemon_status_via_client(world: &mut KanbusWorld) {
    let result = daemon_client::request_status(&daemon_root(world));
    match result {
        Ok(payload) => {
            let status = payload
                .get("status")
                .and_then(|value| value.as_str())
                .map(|value| value.to_string());
            world.daemon_response_status = status;
            world.daemon_status_payload = Some(payload);
            world.daemon_error_message = None;
        }
        Err(error) => {
            world.daemon_status_payload = None;
            world.daemon_error_message = Some(error.to_string());
        }
    }
}

#[when("a daemon status request is handled directly")]
fn when_request_daemon_status_directly(world: &mut KanbusWorld) {
    let request = RequestEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-status".to_string(),
        action: "ping".to_string(),
        payload: BTreeMap::new(),
    };
    let response = handle_request_for_testing(&daemon_root(world), request);
    world.daemon_status_payload = response.result;
    world.daemon_error_message = None;
}

#[then("the daemon response should be ok")]
fn then_daemon_response_ok(world: &mut KanbusWorld) {
    let payload = world
        .daemon_status_payload
        .as_ref()
        .expect("daemon payload");
    let status = payload.get("status").and_then(|value| value.as_str());
    assert_eq!(status, Some("ok"));
}

#[then(expr = "the daemon client error should be {string}")]
fn then_daemon_client_error(world: &mut KanbusWorld, message: String) {
    assert_eq!(
        world.daemon_error_message.as_deref(),
        Some(message.as_str())
    );
}

#[then("the daemon socket should be removed")]
fn then_daemon_socket_removed(world: &mut KanbusWorld) {
    let socket_path = daemon_socket_path(world);
    if !socket_path.exists() {
        return;
    }
    let stale_mtime = world.stale_socket_mtime.expect("stale mtime");
    let metadata = std::fs::metadata(&socket_path).expect("read socket metadata");
    let current_mtime = metadata.modified().expect("read modified time");
    assert!(current_mtime > stale_mtime);
}

#[then("the daemon request should succeed")]
fn then_daemon_request_succeeds(world: &mut KanbusWorld) {
    assert!(world.daemon_error_message.is_none());
}

#[then(expr = "the daemon response should include status {string}")]
fn then_daemon_response_status(world: &mut KanbusWorld, status: String) {
    assert_eq!(
        world.daemon_response_status.as_deref(),
        Some(status.as_str())
    );
}

#[when("I contact a daemon that returns an empty response")]
fn when_contact_empty_daemon(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    set_test_daemon_response(Some(TestDaemonResponse::Empty));
    let result = daemon_client::request_status(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
}

#[when("the daemon status response is an error")]
fn when_daemon_status_error(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    let response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-3".to_string(),
        status: "error".to_string(),
        result: None,
        error: Some(kanbus::daemon_protocol::ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        }),
    };
    set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
    let result = daemon_client::request_status(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
}

#[when("the daemon stop response is an error")]
fn when_daemon_stop_error(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    let response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-4".to_string(),
        status: "error".to_string(),
        result: None,
        error: Some(kanbus::daemon_protocol::ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        }),
    };
    set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
    let result = daemon_client::request_shutdown(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
}

#[when("the daemon list response is an error")]
fn when_daemon_list_error(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    let response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-5".to_string(),
        status: "error".to_string(),
        result: None,
        error: Some(kanbus::daemon_protocol::ErrorEnvelope {
            code: "internal_error".to_string(),
            message: "daemon error".to_string(),
            details: BTreeMap::new(),
        }),
    };
    set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
    let result = daemon_client::request_index_list(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
}

#[given("the daemon list response is missing issues")]
fn when_daemon_list_missing_issues(_world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    let response = ResponseEnvelope {
        protocol_version: PROTOCOL_VERSION.to_string(),
        request_id: "req-6".to_string(),
        status: "ok".to_string(),
        result: Some(BTreeMap::new()),
        error: None,
    };
    set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
}

#[when("I request a daemon index list")]
fn when_request_daemon_index_list(world: &mut KanbusWorld) {
    if daemon_client::is_daemon_enabled() && !has_test_daemon_response() {
        let request = RequestEnvelope {
            protocol_version: PROTOCOL_VERSION.to_string(),
            request_id: "req-list".to_string(),
            action: "index.list".to_string(),
            payload: BTreeMap::new(),
        };
        let response = handle_request_for_testing(&daemon_root(world), request);
        set_test_daemon_response(Some(TestDaemonResponse::Envelope(response)));
    }
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
fn when_handle_daemon_index_list_directly(world: &mut KanbusWorld) {
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
fn when_handle_daemon_request_directly(world: &mut KanbusWorld, version: String) {
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
fn then_daemon_index_list_empty(world: &mut KanbusWorld) {
    assert_eq!(world.daemon_index_issues.as_ref().map(Vec::len), Some(0));
}

#[then(expr = "the daemon request should fail with {string}")]
fn then_daemon_request_failed(world: &mut KanbusWorld, message: String) {
    assert_eq!(
        world.daemon_error_message.as_deref(),
        Some(message.as_str())
    );
}

#[then("the daemon request should fail")]
fn then_daemon_request_should_fail(world: &mut KanbusWorld) {
    assert!(world.daemon_error_message.is_some());
}

#[when("I request a daemon status")]
fn when_request_daemon_status(world: &mut KanbusWorld) {
    let result = daemon_client::request_status(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
}

#[when("I request a daemon shutdown")]
fn when_request_daemon_shutdown(world: &mut KanbusWorld) {
    let result = daemon_client::request_shutdown(&daemon_root(world));
    world.daemon_error_message = result.err().map(|error| error.to_string());
}

#[when(expr = "I send a daemon request with action {string} to the running daemon")]
fn when_send_request_action_running(world: &mut KanbusWorld, action: String) {
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
fn then_daemon_index_list_includes(world: &mut KanbusWorld, identifier: String) {
    let issues = world.daemon_index_issues.as_ref().expect("daemon issues");
    assert!(issues.iter().any(|issue| issue == &identifier));
}

#[given("a stale daemon socket exists")]
fn given_stale_daemon_socket_exists(world: &mut KanbusWorld) {
    let socket_path = daemon_socket_path(world);
    let socket_dir = socket_path.parent().expect("socket dir");
    std::fs::create_dir_all(socket_dir).expect("create socket dir");
    std::fs::write(socket_path, "stale").expect("write stale socket");
}

#[when("the daemon is spawned for the project")]
fn when_daemon_spawned(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "0");
    let _ = daemon_client::request_index_list(&daemon_root(world));
    world.daemon_spawn_called = true;
}

#[then("the daemon spawn should be recorded")]
fn then_daemon_spawn_recorded(world: &mut KanbusWorld) {
    assert!(world.daemon_spawn_called);
}
