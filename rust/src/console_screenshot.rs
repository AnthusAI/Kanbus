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
    for directory in root.ancestors() {
        let candidate = directory.join(&script_rel);
        if candidate.is_file() {
            return Ok(candidate);
        }
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
            std::fs::create_dir_all(parent)
                .map_err(|error| KanbusError::Io(error.to_string()))?;
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
    if matches!(resolved.as_str(), "initiatives" | "epics" | "issues" | "all") {
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
        options.record_for_tests();
        std::fs::write(&output_path, MOCK_PNG_BYTES)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
        return Ok(output_path);
    }

    let port = resolve_console_port(root);
    let console_url = format!("http://127.0.0.1:{port}/");
    let node_executable = which_node_executable()?;
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

    #[test]
    fn mock_success_writes_png() {
        let _guard = test_lock();
        let temp = TempDir::new().expect("tempdir");
        env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "success");
        env::set_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER", "1");
        let path = capture_console_screenshot(
            temp.path(),
            None,
            None,
            None,
            false,
            vec![],
            vec![],
        )
        .expect("capture");
        assert!(path.is_file());
        env::remove_var("KANBUS_TEST_SCREENSHOT_MOCK");
        env::remove_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER");
        env::remove_var(TEST_LAST_MODE_ENV);
        env::remove_var(TEST_CAPTURE_OPTIONS_ENV);
    }

    #[test]
    fn mock_unavailable_returns_actionable_error() {
        let _guard = test_lock();
        let temp = TempDir::new().expect("tempdir");
        env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "unavailable");
        env::set_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER", "1");
        let error = capture_console_screenshot(
            temp.path(),
            None,
            None,
            None,
            false,
            vec![],
            vec![],
        )
        .unwrap_err();
        let message = error.to_string().to_ascii_lowercase();
        assert!(message.contains("headless browser"));
        assert!(message.contains("playwright"));
        env::remove_var("KANBUS_TEST_SCREENSHOT_MOCK");
        env::remove_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER");
    }
}
