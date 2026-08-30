//! Kanbus CLI version requirement enforcement.

use std::path::Path;

use regex::Regex;
use std::sync::LazyLock;

/// Error text for an invalid kanbus-version file.
pub const INVALID_KANBUS_VERSION_MESSAGE: &str =
    "kanbus-version is invalid: expected a single MAJOR.MINOR.PATCH value";

static SEMVER_CORE_PATTERN: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(\d+)\.(\d+)\.(\d+)").expect("semver core regex"));
static SEMVER_CORE_FULL_PATTERN: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\d+\.\d+\.\d+$").expect("semver core full regex"));

/// Parsed MAJOR.MINOR.PATCH tuple.
pub type SemverCore = (u64, u64, u64);

/// Errors raised while enforcing kanbus-version.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct KanbusVersionError {
    message: String,
}

impl KanbusVersionError {
    /// Create a version enforcement error.
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }

    /// Return the user-facing error message.
    pub fn message(&self) -> &str {
        &self.message
    }
}

impl std::fmt::Display for KanbusVersionError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}", self.message)
    }
}

impl std::error::Error for KanbusVersionError {}

/// Parse the leading MAJOR.MINOR.PATCH from a version string.
pub fn parse_semver_core(version: &str) -> Option<SemverCore> {
    let captures = SEMVER_CORE_PATTERN.captures(version.trim())?;
    Some((
        captures.get(1)?.as_str().parse().ok()?,
        captures.get(2)?.as_str().parse().ok()?,
        captures.get(3)?.as_str().parse().ok()?,
    ))
}

/// Return whether the running version satisfies the required core version.
pub fn compare_semver_cores(running: &str, required: &str) -> bool {
    let Some(running_core) = parse_semver_core(running) else {
        return false;
    };
    let Some(required_core) = parse_semver_core(required) else {
        return false;
    };
    running_core >= required_core
}

/// Build the user-facing version mismatch message.
pub fn format_version_mismatch_error(running: &str, required: &str) -> String {
    format!(
        "Kanbus CLI {running} does not satisfy this project's required version {required}.\n\
         Upgrade:\n  pip install --upgrade kanbus\n  cargo install kanbus --locked --force"
    )
}

/// Build the user-facing error for an unparseable running version.
pub fn format_unparseable_running_version_error(raw: &str) -> String {
    format!("Kanbus CLI version '{raw}' cannot be compared with kanbus-version")
}

/// Read the required version from a root-level kanbus-version file.
pub fn read_required_kanbus_version(root: &Path) -> Result<Option<String>, KanbusVersionError> {
    let version_path = root.join("kanbus-version");
    if !version_path.is_file() {
        return Ok(None);
    }
    let content = std::fs::read_to_string(&version_path)
        .map_err(|error| KanbusVersionError::new(error.to_string()))?
        .trim()
        .to_string();
    if content.is_empty() || !SEMVER_CORE_FULL_PATTERN.is_match(&content) {
        return Err(KanbusVersionError::new(INVALID_KANBUS_VERSION_MESSAGE));
    }
    Ok(Some(content))
}

/// Enforce the repository kanbus-version requirement against the running CLI.
pub fn enforce_kanbus_version(
    root: &Path,
    running_version: &str,
) -> Result<(), KanbusVersionError> {
    let Some(required) = read_required_kanbus_version(root)? else {
        return Ok(());
    };
    if parse_semver_core(running_version).is_none() {
        return Err(KanbusVersionError::new(
            format_unparseable_running_version_error(running_version),
        ));
    }
    if !compare_semver_cores(running_version, &required) {
        return Err(KanbusVersionError::new(format_version_mismatch_error(
            running_version,
            &required,
        )));
    }
    Ok(())
}
