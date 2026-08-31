use std::path::PathBuf;

use cucumber::{given, then};

use crate::step_definitions::initialization_steps::KanbusWorld;

const TEST_LAST_MODE_ENV: &str = "KANBUS_TEST_SCREENSHOT_LAST_MODE";
const TEST_CAPTURE_OPTIONS_ENV: &str = "KANBUS_TEST_SCREENSHOT_CAPTURE_OPTIONS";
const TEST_PREREQUISITES_VERIFIED_ENV: &str = "KANBUS_TEST_SCREENSHOT_PREREQUISITES_VERIFIED";
const TEST_NODE_EXECUTABLE_ENV: &str = "KANBUS_TEST_SCREENSHOT_NODE_EXECUTABLE";

fn clear_live_capture_overrides(world: &mut KanbusWorld) {
    for key in [
        "KANBUS_TEST_SCREENSHOT_MOCK",
        TEST_LAST_MODE_ENV,
        TEST_CAPTURE_OPTIONS_ENV,
        TEST_PREREQUISITES_VERIFIED_ENV,
        "KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT",
        "KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT",
        "KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING",
        TEST_NODE_EXECUTABLE_ENV,
    ] {
        world.environment_overrides.remove(key);
    }
}

fn write_fake_node_executable(world: &KanbusWorld, script_body: &str) -> PathBuf {
    let working_directory = world.working_directory.as_ref().expect("working directory");
    let script_path = working_directory.join("fake-node-screenshot.sh");
    std::fs::write(&script_path, script_body).expect("write fake node script");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = std::fs::metadata(&script_path)
            .expect("fake node metadata")
            .permissions();
        permissions.set_mode(0o755);
        std::fs::set_permissions(&script_path, permissions).expect("chmod fake node");
    }
    script_path
}

fn set_fake_node_override(world: &mut KanbusWorld, script_body: &str) {
    let script_path = write_fake_node_executable(world, script_body);
    clear_live_capture_overrides(world);
    world.environment_overrides.insert(
        TEST_NODE_EXECUTABLE_ENV.to_string(),
        script_path.to_string_lossy().to_string(),
    );
}

#[given("screenshot capture is mocked to succeed")]
fn given_screenshot_capture_mocked_success(world: &mut KanbusWorld) {
    clear_live_capture_overrides(world);
    world.environment_overrides.insert(
        "KANBUS_TEST_SCREENSHOT_MOCK".to_string(),
        "success".to_string(),
    );
}

#[given("screenshot capture is mocked as unavailable")]
fn given_screenshot_capture_mocked_unavailable(world: &mut KanbusWorld) {
    world.environment_overrides.insert(
        "KANBUS_TEST_SCREENSHOT_MOCK".to_string(),
        "unavailable".to_string(),
    );
}

#[given("the environment variable CONSOLE_PORT is set to the console server port")]
fn given_console_port_matches_server(world: &mut KanbusWorld) {
    let port = world
        .console_port
        .expect("console server must be running before setting CONSOLE_PORT");
    world
        .environment_overrides
        .insert("CONSOLE_PORT".to_string(), port.to_string());
}

#[given("the capture script cannot be located")]
fn given_capture_script_cannot_be_located(world: &mut KanbusWorld) {
    let working_directory = world.working_directory.as_ref().expect("working directory");
    let empty_root = working_directory.join("empty-script-root");
    std::fs::create_dir_all(&empty_root).expect("create empty script root");
    clear_live_capture_overrides(world);
    world.environment_overrides.insert(
        "KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT".to_string(),
        empty_root.to_string_lossy().to_string(),
    );
    world.environment_overrides.insert(
        "KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT".to_string(),
        "1".to_string(),
    );
}

#[given("Node.js is unavailable for screenshot capture")]
fn given_node_unavailable_for_screenshot(world: &mut KanbusWorld) {
    clear_live_capture_overrides(world);
    world.environment_overrides.insert(
        "KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING".to_string(),
        "1".to_string(),
    );
}

#[given("screenshot capture uses a Node executable that reports Playwright is unavailable")]
fn given_fake_node_reports_playwright_unavailable(world: &mut KanbusWorld) {
    set_fake_node_override(
        world,
        "#!/bin/sh\nprintf 'playwright browser missing\\n' >&2\nexit 1\n",
    );
}

#[given("screenshot capture uses a Node executable that exits successfully without output")]
fn given_fake_node_exits_without_output(world: &mut KanbusWorld) {
    set_fake_node_override(world, "#!/bin/sh\nexit 0\n");
}

#[given("screenshot capture uses a Node executable that fails with a generic error")]
fn given_fake_node_fails_generically(world: &mut KanbusWorld) {
    set_fake_node_override(
        world,
        "#!/bin/sh\nprintf 'capture harness exploded\\n' >&2\nexit 1\n",
    );
}

#[given("screenshot capture uses a Node executable that writes a PNG file")]
fn given_fake_node_writes_png(world: &mut KanbusWorld) {
    set_fake_node_override(
        world,
        "#!/bin/sh\noutput=\"$3\"\nprintf '\\211PNG\\r\\n\\032\\n\\000\\000\\000\\rIHDR\\000\\000\\000\\001\\000\\000\\000\\001\\010\\006\\000\\000\\000\\037\\025\\306\\211\\000\\000\\000\\nIDATx\\234c\\360\\017\\000\\001\\001\\000\\005\\030\\326\\212\\000\\000\\000\\000IEND\\256B`\\202' > \"$output\"\nexit 0\n",
    );
}

#[given("the capture script is available from a custom search root")]
fn given_capture_script_from_custom_search_root(world: &mut KanbusWorld) {
    let working_directory = world.working_directory.as_ref().expect("working directory");
    let search_root = working_directory.join("custom-script-root");
    let script_dir = search_root.join("scripts");
    std::fs::create_dir_all(&script_dir).expect("create custom script dir");
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let package_script = manifest_dir
        .parent()
        .map(|parent| {
            parent
                .join("scripts")
                .join("capture_console_screenshot.mjs")
        })
        .unwrap_or_else(|| {
            manifest_dir
                .join("scripts")
                .join("capture_console_screenshot.mjs")
        });
    let contents = std::fs::read_to_string(&package_script).expect("read capture script");
    std::fs::write(script_dir.join("capture_console_screenshot.mjs"), contents)
        .expect("write capture script copy");
    clear_live_capture_overrides(world);
    world.environment_overrides.insert(
        "KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT".to_string(),
        search_root.to_string_lossy().to_string(),
    );
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
fn then_screenshot_appearance_mode(_world: &mut KanbusWorld, mode: String) {
    let recorded = std::env::var(TEST_LAST_MODE_ENV).unwrap_or_default();
    assert_eq!(recorded, mode, "expected appearance mode {}", mode);
}

#[then(expr = "the screenshot capture view should be {string}")]
fn then_screenshot_capture_view(_world: &mut KanbusWorld, view: String) {
    let raw = std::env::var(TEST_CAPTURE_OPTIONS_ENV).unwrap_or_default();
    let parsed: serde_json::Value =
        serde_json::from_str(&raw).expect("screenshot capture options json");
    let recorded = parsed
        .get("view")
        .and_then(|value| value.as_str())
        .unwrap_or_default();
    assert_eq!(recorded, view.as_str(), "expected view {}", view);
}

#[then("screenshot capture expand-all should be enabled")]
fn then_screenshot_capture_expand_all(_world: &mut KanbusWorld) {
    let raw = std::env::var(TEST_CAPTURE_OPTIONS_ENV).unwrap_or_default();
    let parsed: serde_json::Value =
        serde_json::from_str(&raw).expect("screenshot capture options json");
    assert_eq!(
        parsed.get("expandAll").and_then(|value| value.as_bool()),
        Some(true)
    );
}

#[then("screenshot capture prerequisites should be verified")]
fn then_screenshot_capture_prerequisites_verified(_world: &mut KanbusWorld) {
    let verified = std::env::var(TEST_PREREQUISITES_VERIFIED_ENV).unwrap_or_default();
    assert_eq!(
        verified, "1",
        "expected mocked screenshot capture to verify prerequisites"
    );
}

#[then(expr = "the screenshot capture expanded columns should include {string}")]
fn then_screenshot_capture_expanded_columns_include(_world: &mut KanbusWorld, column: String) {
    let raw = std::env::var(TEST_CAPTURE_OPTIONS_ENV).unwrap_or_default();
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
fn then_screenshot_capture_collapsed_columns_include(_world: &mut KanbusWorld, column: String) {
    let raw = std::env::var(TEST_CAPTURE_OPTIONS_ENV).unwrap_or_default();
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
