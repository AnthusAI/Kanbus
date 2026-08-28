use std::env;
use std::path::PathBuf;

use cucumber::{given, then};

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given("screenshot capture is mocked to succeed")]
fn given_screenshot_capture_mocked_success(world: &mut KanbusWorld) {
    world.original_screenshot_mock_env = Some(env::var("KANBUS_TEST_SCREENSHOT_MOCK").ok());
    env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "success");
}

#[given("screenshot capture is mocked as unavailable")]
fn given_screenshot_capture_mocked_unavailable(world: &mut KanbusWorld) {
    world.original_screenshot_mock_env = Some(env::var("KANBUS_TEST_SCREENSHOT_MOCK").ok());
    env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "unavailable");
}

fn resolve_working_path(world: &KanbusWorld, path: &str) -> PathBuf {
    let working_directory = world.working_directory.as_ref().expect("working directory");
    let candidate = PathBuf::from(path);
    if candidate.is_absolute() {
        candidate
    } else {
        working_directory.join(candidate)
    }
}

#[then(expr = "a PNG file should exist at {string}")]
fn then_png_file_should_exist(world: &mut KanbusWorld, path: String) {
    let file_path = resolve_working_path(world, &path);
    assert!(file_path.is_file(), "expected PNG at {}", file_path.display());
    let header = std::fs::read(&file_path).expect("read png");
    assert!(
        header.starts_with(&[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
        "expected PNG header at {}",
        file_path.display()
    );
}

#[then(expr = "the PNG file at {string} should be larger than {int} bytes")]
fn then_png_file_larger_than(world: &mut KanbusWorld, path: String, size: u64) {
    let file_path = resolve_working_path(world, &path);
    assert!(file_path.is_file(), "expected PNG at {}", file_path.display());
    let bytes = std::fs::metadata(&file_path).expect("png metadata").len();
    assert!(bytes > size, "expected {} > {} bytes", bytes, size);
}

#[then(expr = "the screenshot appearance mode should be {string}")]
fn then_screenshot_appearance_mode(world: &mut KanbusWorld, mode: String) {
    let recorded = std::env::var("KANBUS_TEST_SCREENSHOT_LAST_MODE").unwrap_or_default();
    assert_eq!(recorded, mode, "expected appearance mode {}", mode);
}

#[then(expr = "the screenshot capture view should be {string}")]
fn then_screenshot_capture_view(world: &mut KanbusWorld, view: String) {
    let raw = std::env::var("KANBUS_TEST_SCREENSHOT_CAPTURE_OPTIONS").unwrap_or_default();
    let parsed: serde_json::Value =
        serde_json::from_str(&raw).expect("screenshot capture options json");
    let recorded = parsed
        .get("view")
        .and_then(|value| value.as_str())
        .unwrap_or_default();
    assert_eq!(recorded, view.as_str(), "expected view {}", view);
}

#[then("screenshot capture expand-all should be enabled")]
fn then_screenshot_capture_expand_all(world: &mut KanbusWorld) {
    let raw = std::env::var("KANBUS_TEST_SCREENSHOT_CAPTURE_OPTIONS").unwrap_or_default();
    let parsed: serde_json::Value =
        serde_json::from_str(&raw).expect("screenshot capture options json");
    assert_eq!(
        parsed.get("expandAll").and_then(|value| value.as_bool()),
        Some(true)
    );
}

#[then(expr = "the screenshot capture expanded columns should include {string}")]
fn then_screenshot_capture_expanded_columns_include(
    world: &mut KanbusWorld,
    column: String,
) {
    let raw = std::env::var("KANBUS_TEST_SCREENSHOT_CAPTURE_OPTIONS").unwrap_or_default();
    let parsed: serde_json::Value =
        serde_json::from_str(&raw).expect("screenshot capture options json");
    let expanded = parsed
        .get("expand")
        .and_then(|value| value.as_array())
        .expect("expand array");
    let includes = expanded
        .iter()
        .any(|value| value.as_str() == Some(column.as_str()));
    assert!(includes, "expected expand to include {}", column);
}
