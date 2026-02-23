use std::sync::OnceLock;

use cucumber::then;
use regex::Regex;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[then(expr = "stdout should contain {string}")]
fn then_stdout_contains_text(world: &mut KanbusWorld, text: String) {
    let stdout = strip_ansi(world.stdout.as_ref().expect("stdout"));
    let normalized = text.replace("\\\"", "\"");
    assert!(stdout.contains(&normalized));
}

#[then(expr = "stdout should not contain {string}")]
fn then_stdout_not_contains_text(world: &mut KanbusWorld, text: String) {
    let stdout = strip_ansi(world.stdout.as_ref().expect("stdout"));
    let normalized = text.replace("\\\"", "\"");
    assert!(!stdout.contains(&normalized));
}

#[then(expr = "stderr should contain {string}")]
fn then_stderr_contains_text(world: &mut KanbusWorld, text: String) {
    let stderr = strip_ansi(world.stderr.as_ref().expect("stderr"));
    let normalized = text.replace("\\\"", "\"");
    assert!(
        stderr.contains(&normalized),
        "Expected stderr to contain '{normalized}', but it didn't.\nSTDERR:\n{stderr}"
    );
}

#[then(expr = "stderr should not contain {string}")]
fn then_stderr_not_contains_text(world: &mut KanbusWorld, text: String) {
    let stderr = strip_ansi(world.stderr.as_ref().expect("stderr"));
    let normalized = text.replace("\\\"", "\"");
    assert!(
        !stderr.contains(&normalized),
        "Expected stderr NOT to contain '{normalized}', but it did.\nSTDERR:\n{stderr}"
    );
}

#[then(expr = "the output should contain {string}")]
fn then_output_contains_text(world: &mut KanbusWorld, text: String) {
    let stdout = world.stdout.as_deref().unwrap_or("");
    let stderr = world.stderr.as_deref().unwrap_or("");
    let normalized = text.replace("\\\"", "\"");
    let combined = strip_ansi(&format!("{stdout}{stderr}"));
    assert!(combined.contains(&normalized));
}

#[then(expr = "stdout should contain {string} once")]
fn then_stdout_contains_once(world: &mut KanbusWorld, text: String) {
    let stdout = strip_ansi(world.stdout.as_ref().expect("stdout"));
    let normalized = text.replace("\\\"", "\"");
    assert_eq!(stdout.matches(&normalized).count(), 1);
}

#[then(expr = "stdout should contain the external project path for {string}")]
fn then_stdout_contains_external_project_path(world: &mut KanbusWorld, identifier: String) {
    let stdout = strip_ansi(world.stdout.as_ref().expect("stdout"));
    let project_path = world
        .expected_project_path
        .as_ref()
        .expect("expected project path");
    let project_path = project_path.to_string_lossy();
    let matches = stdout
        .lines()
        .any(|line| line.contains(identifier.as_str()) && line.contains(project_path.as_ref()));
    assert!(
        matches,
        "no line contains both external project path and identifier"
    );
}

#[then(expr = "stdout should list {string} before {string}")]
fn then_stdout_lists_before(world: &mut KanbusWorld, first: String, second: String) {
    let stdout = strip_ansi(world.stdout.as_ref().expect("stdout"));
    let first_index = stdout.find(&first).expect("first value not found");
    let second_index = stdout.find(&second).expect("second value not found");
    assert!(first_index < second_index);
}

#[then("stdout should contain parent reference")]
fn then_stdout_contains_parent_reference(world: &mut KanbusWorld) {
    let stdout = strip_ansi(world.stdout.as_ref().expect("stdout"));
    let lower = stdout.to_lowercase();
    assert!(
        lower.contains("parent") || lower.contains("parent-child"),
        "no parent reference found in stdout"
    );
}

fn strip_ansi(text: &str) -> String {
    static ANSI_RE: OnceLock<Regex> = OnceLock::new();
    let regex = ANSI_RE.get_or_init(|| Regex::new("\x1b\\[[0-9;]*m").expect("regex"));
    regex.replace_all(text, "").to_string()
}
