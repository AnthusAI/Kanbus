use cucumber::then;

use crate::step_definitions::initialization_steps::TaskulusWorld;

#[then(expr = "stdout should contain {string}")]
fn then_stdout_contains_text(world: &mut TaskulusWorld, text: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let normalized = text.replace("\\\"", "\"");
    assert!(stdout.contains(&normalized));
}

#[then(expr = "stdout should not contain {string}")]
fn then_stdout_not_contains_text(world: &mut TaskulusWorld, text: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let normalized = text.replace("\\\"", "\"");
    assert!(!stdout.contains(&normalized));
}

#[then(expr = "stderr should contain {string}")]
fn then_stderr_contains_text(world: &mut TaskulusWorld, text: String) {
    let stderr = world.stderr.as_ref().expect("stderr");
    let normalized = text.replace("\\\"", "\"");
    assert!(stderr.contains(&normalized));
}

#[then(expr = "stdout should contain {string} once")]
fn then_stdout_contains_once(world: &mut TaskulusWorld, text: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let normalized = text.replace("\\\"", "\"");
    assert_eq!(stdout.matches(&normalized).count(), 1);
}

#[then(expr = "stdout should contain the external project path for {string}")]
fn then_stdout_contains_external_project_path(world: &mut TaskulusWorld, identifier: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
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
