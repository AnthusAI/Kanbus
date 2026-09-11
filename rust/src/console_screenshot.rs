//! Capture PNG screenshots of the Kanbus console board.

use std::path::{Path, PathBuf};
use std::process::Command;

use serde::Serialize;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;

const DEFAULT_SCREENSHOT_FILENAME: &str = "kanbus-board.png";
const DEFAULT_APPEARANCE_MODE: &str = "light";
const TEST_LAST_MODE_ENV: &str = "KANBUS_TEST_SCREENSHOT_LAST_MODE";
const TEST_CAPTURE_OPTIONS_ENV: &str = "KANBUS_TEST_SCREENSHOT_CAPTURE_OPTIONS";
const TEST_PREREQUISITES_VERIFIED_ENV: &str = "KANBUS_TEST_SCREENSHOT_PREREQUISITES_VERIFIED";
const TEST_SCRIPT_SEARCH_ROOT_ENV: &str = "KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT";
const TEST_HIDE_PACKAGE_SCRIPT_ENV: &str = "KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT";
const TEST_FORCE_NODE_MISSING_ENV: &str = "KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING";
const TEST_NODE_EXECUTABLE_ENV: &str = "KANBUS_TEST_SCREENSHOT_NODE_EXECUTABLE";
const MOCK_PNG_BYTES: &[u8] = include_bytes!("../testdata/mock_board_screenshot.png");

/// Layout and appearance options for a single board screenshot.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ScreenshotCaptureOptions {
    /// Console light or dark appearance mode.
    pub appearance_mode: String,
    /// Board view filter (`initiatives`, `epics`, `issues`, or `all`).
    pub view: Option<String>,
    /// Expand every collapsed status column before capture.
    pub expand_all: bool,
    /// Status column keys to expand before capture.
    pub expand: Vec<String>,
    /// Status column keys to collapse before capture.
    pub collapse: Vec<String>,
}

impl ScreenshotCaptureOptions {
    /// Record capture options for behavior-spec assertions.
    pub fn record_for_tests(&self) {
        std::env::set_var(TEST_LAST_MODE_ENV, &self.appearance_mode);
        if let Ok(payload) = serde_json::to_string(self) {
            std::env::set_var(TEST_CAPTURE_OPTIONS_ENV, payload);
        }
    }

    fn to_capture_json(&self) -> Result<String, KanbusError> {
        serde_json::to_string(self).map_err(|error| KanbusError::Io(error.to_string()))
    }
}

/// Resolve the console HTTP port from project configuration.
///
/// # Arguments
/// * `root` - Repository root path
///
/// # Returns
/// Console port number (defaults to 5174)
pub fn resolve_console_port(root: &Path) -> u16 {
    if let Ok(value) = std::env::var("CONSOLE_PORT") {
        if let Ok(port) = value.trim().parse::<u16>() {
            return port;
        }
    }
    match get_configuration_path(root).and_then(|path| load_project_configuration(&path)) {
        Ok(config) => config.console_port.unwrap_or(5174),
        Err(_) => 5174,
    }
}

/// Return whether the console server responds on its HTTP port.
///
/// # Arguments
/// * `root` - Repository root path
/// * `port` - Optional port override
///
/// # Returns
/// `true` when `/api/config` responds with HTTP 200
pub fn is_console_server_running(root: &Path, port: Option<u16>) -> bool {
    let resolved_port = port.unwrap_or_else(|| resolve_console_port(root));
    let url = format!("http://127.0.0.1:{resolved_port}/api/config");
    let client = reqwest::blocking::Client::new();
    client
        .get(&url)
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .map(|response| response.status().is_success())
        .unwrap_or(false)
}

fn locate_capture_script(root: &Path) -> Result<PathBuf, KanbusError> {
    let script_rel = Path::new("scripts").join("capture_console_screenshot.mjs");
    if let Ok(override_root) = std::env::var(TEST_SCRIPT_SEARCH_ROOT_ENV) {
        let candidate = PathBuf::from(override_root).join(&script_rel);
        if candidate.is_file() {
            return Ok(candidate);
        }
    } else {
        for directory in root.ancestors() {
            let candidate = directory.join(&script_rel);
            if candidate.is_file() {
                return Ok(candidate);
            }
        }
    }
    if std::env::var(TEST_HIDE_PACKAGE_SCRIPT_ENV)
        .ok()
        .map(|value| value == "1")
        .unwrap_or(false)
    {
        return Err(KanbusError::IssueOperation(
            "headless browser capture script not found (scripts/capture_console_screenshot.mjs)."
                .to_string(),
        ));
    }
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let candidate = manifest_dir
        .parent()
        .map(|parent| parent.join(&script_rel))
        .unwrap_or_else(|| manifest_dir.join(&script_rel));
    if candidate.is_file() {
        return Ok(candidate);
    }
    Err(KanbusError::IssueOperation(
        "headless browser capture script not found (scripts/capture_console_screenshot.mjs)."
            .to_string(),
    ))
}

fn resolve_output_path(root: &Path, output: Option<String>) -> Result<PathBuf, KanbusError> {
    let path = if let Some(output) = output {
        let path = PathBuf::from(output);
        if path.is_absolute() {
            path
        } else {
            root.join(path)
        }
    } else {
        root.join(DEFAULT_SCREENSHOT_FILENAME)
    };
    if let Some(parent) = path.parent() {
        if parent != Path::new("") {
            std::fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
        }
    }
    Ok(path)
}

fn server_ready_for_screenshot(root: &Path) -> bool {
    if std::env::var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER")
        .ok()
        .map(|value| {
            let normalized = value.trim().to_ascii_lowercase();
            matches!(normalized.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(false)
    {
        return true;
    }
    is_console_server_running(root, None)
}

fn mock_mode() -> Option<String> {
    let value = std::env::var("KANBUS_TEST_SCREENSHOT_MOCK").ok();
    value.map(|raw| {
        let normalized = raw.trim().to_ascii_lowercase();
        match normalized.as_str() {
            "1" | "true" | "yes" | "on" | "success" | "succeed" => "success".to_string(),
            "unavailable" | "missing" | "fail" | "error" => "unavailable".to_string(),
            other => other.to_string(),
        }
    })
}

fn normalize_appearance_mode(mode: Option<String>) -> Result<String, KanbusError> {
    let resolved = mode
        .unwrap_or_else(|| DEFAULT_APPEARANCE_MODE.to_string())
        .trim()
        .to_ascii_lowercase();
    if matches!(resolved.as_str(), "light" | "dark") {
        Ok(resolved)
    } else {
        Err(KanbusError::IssueOperation(
            "appearance mode must be light or dark".to_string(),
        ))
    }
}

fn normalize_view(view: Option<String>) -> Result<Option<String>, KanbusError> {
    if view.is_none() {
        return Ok(None);
    }
    let resolved = view.unwrap().trim().to_ascii_lowercase();
    if matches!(
        resolved.as_str(),
        "initiatives" | "epics" | "issues" | "all"
    ) {
        Ok(Some(resolved))
    } else {
        Err(KanbusError::IssueOperation(
            "view must be one of: initiatives, epics, issues, all".to_string(),
        ))
    }
}

/// Build validated screenshot capture options.
pub fn build_capture_options(
    appearance_mode: Option<String>,
    view: Option<String>,
    expand_all: bool,
    expand_columns: Vec<String>,
    collapse_columns: Vec<String>,
) -> Result<ScreenshotCaptureOptions, KanbusError> {
    Ok(ScreenshotCaptureOptions {
        appearance_mode: normalize_appearance_mode(appearance_mode)?,
        view: normalize_view(view)?,
        expand_all,
        expand: expand_columns,
        collapse: collapse_columns,
    })
}

/// Capture a PNG screenshot of the console board to the requested path.
///
/// # Errors
/// Returns `KanbusError::IssueOperation` when capture fails or prerequisites are missing
pub fn capture_console_screenshot(
    root: &Path,
    output: Option<String>,
    appearance_mode: Option<String>,
    view: Option<String>,
    expand_all: bool,
    expand_columns: Vec<String>,
    collapse_columns: Vec<String>,
) -> Result<PathBuf, KanbusError> {
    let options = build_capture_options(
        appearance_mode,
        view,
        expand_all,
        expand_columns,
        collapse_columns,
    )?;
    let output_path = resolve_output_path(root, output)?;
    if !server_ready_for_screenshot(root) {
        return Err(KanbusError::IssueOperation(
            "Console server is not running.".to_string(),
        ));
    }

    let mock_mode = mock_mode();
    if mock_mode.as_deref() == Some("unavailable") {
        return Err(KanbusError::IssueOperation(
            "headless browser capture is unavailable. Install Chromium for Playwright \
             (npx playwright install chromium)."
                .to_string(),
        ));
    }
    if mock_mode.as_deref() == Some("success") {
        locate_capture_script(root)?;
        resolve_node_executable()?;
        options.record_for_tests();
        std::env::set_var(TEST_PREREQUISITES_VERIFIED_ENV, "1");
        std::fs::write(&output_path, MOCK_PNG_BYTES)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        return Ok(output_path);
    }

    let port = resolve_console_port(root);
    let console_url = format!("http://127.0.0.1:{port}/");
    let node_executable = resolve_node_executable()?;
    let script_path = locate_capture_script(root)?;
    let options_json = options.to_capture_json()?;
    let output = Command::new(&node_executable)
        .arg(script_path)
        .arg(console_url)
        .arg(&output_path)
        .arg(options_json)
        .output()
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        let details = if !stderr.trim().is_empty() {
            stderr.trim().to_string()
        } else {
            stdout.trim().to_string()
        };
        let lowered = details.to_ascii_lowercase();
        if lowered.contains("playwright") || lowered.contains("headless browser") {
            return Err(KanbusError::IssueOperation(details));
        }
        return Err(KanbusError::IssueOperation(format!(
            "headless browser capture failed. Install Chromium for Playwright \
             (npx playwright install chromium). {details}"
        )));
    }

    if !output_path.is_file() {
        return Err(KanbusError::IssueOperation(
            "headless browser capture did not produce an output file.".to_string(),
        ));
    }

    Ok(output_path)
}

fn resolve_node_executable() -> Result<String, KanbusError> {
    if let Ok(override_path) = std::env::var(TEST_NODE_EXECUTABLE_ENV) {
        let path = PathBuf::from(override_path);
        if path.is_file() {
            return Ok(path.to_string_lossy().to_string());
        }
    }
    if std::env::var(TEST_FORCE_NODE_MISSING_ENV)
        .ok()
        .map(|value| value == "1")
        .unwrap_or(false)
    {
        return Err(KanbusError::IssueOperation(
            "headless browser capture requires Node.js on PATH to run Playwright.".to_string(),
        ));
    }
    which_node_executable()
}

fn which_node_executable() -> Result<String, KanbusError> {
    let output = Command::new("which")
        .arg("node")
        .output()
        .map_err(|error| KanbusError::IssueOperation(error.to_string()))?;
    if !output.status.success() {
        return Err(KanbusError::IssueOperation(
            "headless browser capture requires Node.js on PATH to run Playwright.".to_string(),
        ));
    }
    let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if path.is_empty() {
        return Err(KanbusError::IssueOperation(
            "headless browser capture requires Node.js on PATH to run Playwright.".to_string(),
        ));
    }
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;
    use std::sync::{Mutex, OnceLock};
    use tempfile::TempDir;

    fn test_lock() -> std::sync::MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
            .lock()
            .expect("screenshot test lock")
    }

    fn clear_screenshot_test_env() {
        for key in [
            "KANBUS_TEST_SCREENSHOT_MOCK",
            "KANBUS_TEST_SCREENSHOT_ASSUME_SERVER",
            "CONSOLE_PORT",
            TEST_LAST_MODE_ENV,
            TEST_CAPTURE_OPTIONS_ENV,
            TEST_PREREQUISITES_VERIFIED_ENV,
            TEST_SCRIPT_SEARCH_ROOT_ENV,
            TEST_HIDE_PACKAGE_SCRIPT_ENV,
            TEST_FORCE_NODE_MISSING_ENV,
            TEST_NODE_EXECUTABLE_ENV,
        ] {
            env::remove_var(key);
        }
    }

    #[test]
    fn mock_success_writes_png() {
        let _guard = test_lock();
        clear_screenshot_test_env();
        let temp = TempDir::new().expect("tempdir");
        env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "success");
        env::set_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER", "1");
        let path = capture_console_screenshot(temp.path(), None, None, None, false, vec![], vec![])
            .expect("capture");
        assert!(path.is_file());
        clear_screenshot_test_env();
    }

    #[test]
    fn mock_unavailable_returns_actionable_error() {
        let _guard = test_lock();
        clear_screenshot_test_env();
        let temp = TempDir::new().expect("tempdir");
        env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "unavailable");
        env::set_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER", "1");
        let error =
            capture_console_screenshot(temp.path(), None, None, None, false, vec![], vec![])
                .unwrap_err();
        let message = error.to_string().to_ascii_lowercase();
        assert!(message.contains("headless browser"));
        assert!(message.contains("playwright"));
        clear_screenshot_test_env();
    }

    #[test]
    fn resolve_port_from_env_and_invalid_fallback() {
        let _guard = test_lock();
        clear_screenshot_test_env();
        let temp = TempDir::new().expect("tempdir");
        env::set_var("CONSOLE_PORT", "4242");
        assert_eq!(resolve_console_port(temp.path()), 4242);
        env::set_var("CONSOLE_PORT", "nope");
        assert_eq!(resolve_console_port(temp.path()), 5174);
        env::remove_var("CONSOLE_PORT");
        assert_eq!(resolve_console_port(temp.path()), 5174);
        clear_screenshot_test_env();
    }

    #[test]
    fn server_not_running_on_closed_port() {
        let _guard = test_lock();
        clear_screenshot_test_env();
        let temp = TempDir::new().expect("tempdir");
        assert!(!is_console_server_running(temp.path(), Some(1)));
        let error =
            capture_console_screenshot(temp.path(), None, None, None, false, vec![], vec![])
                .unwrap_err();
        assert!(error.to_string().contains("Console server is not running"));
        clear_screenshot_test_env();
    }

    #[test]
    fn build_options_and_output_path_and_script() {
        let _guard = test_lock();
        clear_screenshot_test_env();
        let temp = TempDir::new().expect("tempdir");
        let options = build_capture_options(
            Some("DARK".to_string()),
            Some("epics".to_string()),
            true,
            vec!["backlog".to_string()],
            vec!["closed".to_string()],
        )
        .expect("options");
        assert_eq!(options.appearance_mode, "dark");
        assert_eq!(options.view.as_deref(), Some("epics"));
        assert!(options.expand_all);
        assert!(options
            .to_capture_json()
            .expect("json")
            .contains("expandAll"));

        let nested =
            resolve_output_path(temp.path(), Some("exports/board.png".to_string())).expect("path");
        assert!(nested.parent().expect("parent").is_dir());

        let script_dir = temp.path().join("scripts");
        std::fs::create_dir_all(&script_dir).expect("scripts dir");
        let script = script_dir.join("capture_console_screenshot.mjs");
        std::fs::write(&script, "export {}\n").expect("script");
        env::set_var(TEST_SCRIPT_SEARCH_ROOT_ENV, temp.path());
        assert_eq!(locate_capture_script(temp.path()).expect("script"), script);

        let missing = TempDir::new().expect("missing root");
        env::set_var(TEST_SCRIPT_SEARCH_ROOT_ENV, missing.path());
        env::set_var(TEST_HIDE_PACKAGE_SCRIPT_ENV, "1");
        let located = locate_capture_script(missing.path());
        assert!(located.unwrap_err().to_string().contains("not found"));

        assert!(normalize_appearance_mode(Some("sepia".to_string())).is_err());
        assert!(normalize_view(Some("pods".to_string())).is_err());
        assert!(normalize_view(None).expect("none").is_none());
        assert_eq!(normalize_appearance_mode(None).expect("default"), "light");
        clear_screenshot_test_env();
    }

    #[cfg(unix)]
    #[test]
    fn live_capture_with_stub_node_success_and_errors() {
        let _guard = test_lock();
        clear_screenshot_test_env();
        let temp = TempDir::new().expect("tempdir");
        let scripts = temp.path().join("scripts");
        std::fs::create_dir_all(&scripts).expect("scripts");
        std::fs::write(
            scripts.join("capture_console_screenshot.mjs"),
            "export {}\n",
        )
        .expect("script");

        let bin = temp.path().join("bin");
        std::fs::create_dir(&bin).expect("bin");
        let node = bin.join("node");
        let output_copy = temp.path().join("kanbus-board.png");
        std::fs::write(
            &node,
            "#!/bin/sh\nprintf '\\211PNG\\r\\n\\032\\n' > \"$3\"\nexit 0\n",
        )
        .expect("node stub");
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&node, std::fs::Permissions::from_mode(0o755)).expect("chmod");

        env::set_var(TEST_NODE_EXECUTABLE_ENV, &node);
        env::set_var(TEST_SCRIPT_SEARCH_ROOT_ENV, temp.path());
        env::set_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER", "1");

        let path = capture_console_screenshot(
            temp.path(),
            None,
            Some("light".to_string()),
            Some("all".to_string()),
            true,
            vec!["backlog".to_string()],
            vec![],
        )
        .expect("live stub capture");
        assert!(path.is_file());
        assert_eq!(path, output_copy);

        std::fs::write(
            &node,
            "#!/bin/sh\necho \"Cannot find module 'playwright'\" >&2\nexit 1\n",
        )
        .expect("node fail playwright");
        let error = capture_console_screenshot(
            temp.path(),
            Some("missing.png".to_string()),
            None,
            None,
            false,
            vec![],
            vec![],
        )
        .unwrap_err();
        assert!(error
            .to_string()
            .to_ascii_lowercase()
            .contains("playwright"));

        std::fs::write(&node, "#!/bin/sh\necho boom >&2\nexit 1\n").expect("node fail generic");
        let error = capture_console_screenshot(
            temp.path(),
            Some("generic.png".to_string()),
            None,
            None,
            false,
            vec![],
            vec![],
        )
        .unwrap_err();
        assert!(error
            .to_string()
            .contains("headless browser capture failed"));

        std::fs::write(&node, "#!/bin/sh\nexit 0\n").expect("node no file");
        let error = capture_console_screenshot(
            temp.path(),
            Some("no-file.png".to_string()),
            None,
            None,
            false,
            vec![],
            vec![],
        )
        .unwrap_err();
        assert!(error.to_string().contains("did not produce an output file"));

        clear_screenshot_test_env();
    }

    #[test]
    fn mock_mode_aliases_and_which_node() {
        let _guard = test_lock();
        clear_screenshot_test_env();
        env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "yes");
        assert_eq!(mock_mode().as_deref(), Some("success"));
        env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "fail");
        assert_eq!(mock_mode().as_deref(), Some("unavailable"));
        env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "custom");
        assert_eq!(mock_mode().as_deref(), Some("custom"));
        env::remove_var("KANBUS_TEST_SCREENSHOT_MOCK");
        assert!(mock_mode().is_none());
        let node = which_node_executable();
        assert!(node.is_ok() || node.unwrap_err().to_string().contains("Node.js"));
        clear_screenshot_test_env();
    }
}
