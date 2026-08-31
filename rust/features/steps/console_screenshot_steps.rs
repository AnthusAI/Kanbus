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

#[given("the environment variable CONSOLE_PORT is set to the console server port")]
fn given_console_port_matches_server(world: &mut KanbusWorld) {
    let port = world
        .console_port
        .expect("console server must be running before setting CONSOLE_PORT");
    world
        .environment_overrides
        .insert("CONSOLE_PORT".to_string(), port.to_string());
    env::set_var("CONSOLE_PORT", port.to_string());
}

#[given("the capture script cannot be located")]
fn given_capture_script_cannot_be_located(world: &mut KanbusWorld) {
    let working_directory = world.working_directory.as_ref().expect("working directory");
    let empty_root = working_directory.join("empty-script-root");
    std::fs::create_dir_all(&empty_root).expect("create empty script root");
    world
        .environment_overrides
        .remove("KANBUS_TEST_SCREENSHOT_MOCK");
    world.environment_overrides.insert(
        "KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT".to_string(),
        empty_root.to_string_lossy().to_string(),
    );
    world.environment_overrides.insert(
        "KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT".to_string(),
        "1".to_string(),
    );
    env::remove_var("KANBUS_TEST_SCREENSHOT_MOCK");
    env::set_var(
        "KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT",
        empty_root.to_string_lossy().to_string(),
    );
    env::set_var("KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT", "1");
}

#[given("Node.js is unavailable for screenshot capture")]
fn given_node_unavailable_for_screenshot(world: &mut KanbusWorld) {
    world
        .environment_overrides
        .remove("KANBUS_TEST_SCREENSHOT_MOCK");
    world.environment_overrides.insert(
        "KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING".to_string(),
        "1".to_string(),
    );
    env::remove_var("KANBUS_TEST_SCREENSHOT_MOCK");
    env::set_var("KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING", "1");
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
    assert!(
        file_path.is_file(),
        "expected PNG at {}",
        file_path.display()
    );
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
    assert!(
        file_path.is_file(),
        "expected PNG at {}",
        file_path.display()
    );
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

#[then("screenshot capture prerequisites should be verified")]
fn then_screenshot_capture_prerequisites_verified(world: &mut KanbusWorld) {
    let verified =
        std::env::var("KANBUS_TEST_SCREENSHOT_PREREQUISITES_VERIFIED").unwrap_or_default();
    assert_eq!(
        verified, "1",
        "expected mocked screenshot capture to verify prerequisites"
    );
}

#[then(expr = "the screenshot capture expanded columns should include {string}")]
fn then_screenshot_capture_expanded_columns_include(world: &mut KanbusWorld, column: String) {
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

#[then(expr = "the screenshot capture collapsed columns should include {string}")]
fn then_screenshot_capture_collapsed_columns_include(world: &mut KanbusWorld, column: String) {
    let raw = std::env::var("KANBUS_TEST_SCREENSHOT_CAPTURE_OPTIONS").unwrap_or_default();
    let parsed: serde_json::Value =
        serde_json::from_str(&raw).expect("screenshot capture options json");
    let collapsed = parsed
        .get("collapse")
        .and_then(|value| value.as_array())
        .expect("collapse array");
    let includes = collapsed
        .iter()
        .any(|value| value.as_str() == Some(column.as_str()));
    assert!(includes, "expected collapse to include {}", column);
}
