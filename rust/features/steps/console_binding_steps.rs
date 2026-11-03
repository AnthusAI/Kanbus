//! Cucumber steps for the `kbsc` network binding (`CONSOLE_HOST`) scenarios.

use std::io::{BufRead, BufReader, Read};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use cucumber::then;

use crate::step_definitions::console_ui_state_steps::{
    allocate_port, write_console_port_to_config,
};
use crate::step_definitions::initialization_steps::KanbusWorld;

const STARTUP_TIMEOUT: Duration = Duration::from_secs(60);
const LISTENING_MARKER: &str = "Console backend listening on ";

struct KbscLaunch {
    listening_line: Option<String>,
    exit_code: Option<i32>,
    stderr_text: String,
}

fn launch_kbsc(world: &KanbusWorld, console_host: Option<&str>) -> KbscLaunch {
    let data_root = world.working_directory.as_ref().expect("working directory");
    let port = allocate_port();
    write_console_port_to_config(world, port);
    let mut command = Command::new(env!("CARGO_BIN_EXE_kbsc"));
    command
        .env_remove("CONSOLE_HOST")
        .env("CONSOLE_PORT", port.to_string())
        .env("CONSOLE_DATA_ROOT", data_root)
        .env("KANBUS_DAEMON", "0")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(host) = console_host {
        command.env("CONSOLE_HOST", host);
    }
    let mut child = command.spawn().expect("spawn kbsc");

    let stdout = child.stdout.take().expect("kbsc stdout");
    let (sender, receiver) = mpsc::channel::<String>();
    thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if sender.send(line).is_err() {
                break;
            }
        }
    });
    let mut stderr = child.stderr.take().expect("kbsc stderr");
    let stderr_reader = thread::spawn(move || {
        let mut text = String::new();
        let _ = stderr.read_to_string(&mut text);
        text
    });

    let deadline = Instant::now() + STARTUP_TIMEOUT;
    let mut listening_line = None;
    let mut exit_code = None;
    while Instant::now() < deadline {
        if let Ok(line) = receiver.recv_timeout(Duration::from_millis(50)) {
            if line.contains(LISTENING_MARKER) {
                listening_line = Some(line);
                break;
            }
        }
        if let Some(status) = child.try_wait().expect("poll kbsc") {
            exit_code = Some(status.code().unwrap_or(-1));
            break;
        }
    }
    let _ = child.kill();
    let _ = child.wait();
    let stderr_text = stderr_reader.join().unwrap_or_default();
    KbscLaunch {
        listening_line,
        exit_code,
        stderr_text,
    }
}

fn assert_listens_on(launch: &KbscLaunch, expected_host: &str) {
    let line = launch.listening_line.as_ref().unwrap_or_else(|| {
        panic!(
            "kbsc did not report listening (exit {:?}); stderr: {}",
            launch.exit_code, launch.stderr_text
        )
    });
    let expected = format!("{LISTENING_MARKER}http://{expected_host}:");
    assert!(
        line.contains(&expected),
        "expected '{expected}' in '{line}'"
    );
}

#[then(expr = "kbsc started without CONSOLE_HOST listens on {string}")]
fn then_kbsc_default_host_listens_on(world: &mut KanbusWorld, expected_host: String) {
    assert_listens_on(&launch_kbsc(world, None), &expected_host);
}

#[then(expr = "kbsc started with CONSOLE_HOST {string} listens on {string}")]
fn then_kbsc_host_listens_on(world: &mut KanbusWorld, console_host: String, expected_host: String) {
    assert_listens_on(&launch_kbsc(world, Some(&console_host)), &expected_host);
}

#[then(expr = "kbsc started with CONSOLE_HOST {string} exits with an error naming {string}")]
fn then_kbsc_invalid_host_exits(world: &mut KanbusWorld, console_host: String, named: String) {
    let launch = launch_kbsc(world, Some(&console_host));
    assert_eq!(
        launch.exit_code,
        Some(1),
        "kbsc should exit with status 1; stderr: {}",
        launch.stderr_text
    );
    assert!(
        launch.listening_line.is_none(),
        "kbsc must not start listening with an invalid CONSOLE_HOST"
    );
    assert!(
        launch.stderr_text.contains(&named),
        "stderr should name '{named}': {}",
        launch.stderr_text
    );
}
