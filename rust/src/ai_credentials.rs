//! User-level API key storage and resolution for Kanbus AI features.
//!
//! Kanbus loads `~/.kanbus.env` (the "congregation" env file) before the
//! project `.env` file, and neither overrides a value already present in the
//! process environment (see `config_loader::load_repository_environment`).
//! This module centralizes the messages, lookup order, and file-writing
//! logic behind `kbs setup ai`.

use std::fs;
use std::io::Write;
use std::path::Path;

use crate::error::KanbusError;

/// Default environment variable name used for the LLM API key.
pub const DEFAULT_API_KEY_VARIABLE: &str = "OPENAI_API_KEY";

/// Error message shown when `OPENAI_API_KEY` is not set anywhere Kanbus looks.
pub const OPENAI_API_KEY_MISSING_MESSAGE: &str =
    "OPENAI_API_KEY is not set. Run 'kbs setup ai' (or 'kanbus setup ai') to store it once in ~/.kanbus.env, or set it in your shell environment or the project .env file.";

/// Build the missing-API-key message for an arbitrary variable name.
///
/// For [`DEFAULT_API_KEY_VARIABLE`] this returns exactly
/// [`OPENAI_API_KEY_MISSING_MESSAGE`].
///
/// # Arguments
/// * `variable` - Environment variable name to mention in the message.
pub fn missing_api_key_message(variable: &str) -> String {
    format!(
        "{variable} is not set. Run 'kbs setup ai' (or 'kanbus setup ai') to store it once in ~/.kanbus.env, or set it in your shell environment or the project .env file."
    )
}

/// Where an API key value currently resolves from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CredentialSource {
    /// Already set directly in the process environment (e.g. exported by the shell).
    ProcessEnv,
    /// Loaded from `~/.kanbus.env`.
    CongregationFile,
    /// Loaded from the project's `.env` file.
    ProjectFile,
    /// Not configured anywhere Kanbus looks.
    None,
}

impl CredentialSource {
    /// Human-readable description of the source, used in CLI output.
    pub fn describe(self) -> &'static str {
        match self {
            CredentialSource::ProcessEnv => "process environment",
            CredentialSource::CongregationFile => "~/.kanbus.env",
            CredentialSource::ProjectFile => "project .env",
            CredentialSource::None => "not set",
        }
    }
}

/// Parse a single dotenv-style line into a key/value pair.
///
/// Skips blank lines and comments (returning `None`). Strips a leading
/// `export ` prefix, splits on the first `=`, trims the key and value, and
/// strips one pair of matching surrounding quotes (`"..."` or `'...'`) from
/// the value.
///
/// # Arguments
/// * `line` - Raw line from a dotenv file.
pub fn parse_dotenv_line(line: &str) -> Option<(String, String)> {
    let mut stripped = line.trim();
    if stripped.is_empty() || stripped.starts_with('#') {
        return None;
    }
    if let Some(rest) = stripped.strip_prefix("export ") {
        stripped = rest.trim_start();
    }
    let (key, value) = stripped.split_once('=')?;
    let key = key.trim();
    if key.is_empty() {
        return None;
    }
    let mut value = value.trim().to_string();
    if value.len() >= 2 {
        let bytes = value.as_bytes();
        let first = bytes[0];
        let last = bytes[bytes.len() - 1];
        if (first == b'"' && last == b'"') || (first == b'\'' && last == b'\'') {
            value = value[1..value.len() - 1].to_string();
        }
    }
    Some((key.to_string(), value))
}

/// Read the last value of `key` set in a dotenv-style file, if any.
///
/// Returns `None` when the file cannot be read or `key` is never set.
///
/// # Arguments
/// * `path` - Path to the dotenv file.
/// * `key` - Environment variable name to look up.
pub fn read_dotenv_value(path: &Path, key: &str) -> Option<String> {
    let contents = fs::read_to_string(path).ok()?;
    let mut found = None;
    for line in contents.lines() {
        if let Some((line_key, value)) = parse_dotenv_line(line) {
            if line_key == key {
                found = Some(value);
            }
        }
    }
    found
}

/// Resolve where a credential currently comes from.
///
/// Lookup order mirrors `config_loader::load_repository_environment`: the
/// process environment wins if already set, otherwise `~/.kanbus.env`, then
/// the project `.env` file.
///
/// # Arguments
/// * `repository_root` - Repository root containing `.env`, if known.
/// * `variable` - Environment variable name to resolve.
pub fn resolve_api_key_source(repository_root: Option<&Path>, variable: &str) -> CredentialSource {
    let congregation = read_dotenv_value(&crate::config_loader::congregation_env_path(), variable)
        .filter(|value| !value.is_empty());
    let project = repository_root
        .and_then(|root| read_dotenv_value(&root.join(".env"), variable))
        .filter(|value| !value.is_empty());
    let env = std::env::var(variable)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());

    if let Some(env_value) = env {
        if Some(&env_value) == congregation.as_ref() {
            CredentialSource::CongregationFile
        } else if Some(&env_value) == project.as_ref() {
            CredentialSource::ProjectFile
        } else {
            CredentialSource::ProcessEnv
        }
    } else if congregation.is_some() {
        CredentialSource::CongregationFile
    } else if project.is_some() {
        CredentialSource::ProjectFile
    } else {
        CredentialSource::None
    }
}

fn quote_value_if_needed(value: &str) -> String {
    if value.chars().any(|c| c.is_whitespace() || c == '#') {
        format!("\"{value}\"")
    } else {
        value.to_string()
    }
}

/// Write (or update in place) a single key/value pair in a dotenv-style file.
///
/// If `key` already appears on some line, that line is replaced with the new
/// value (preserving an `export ` prefix if present); every other line is
/// kept byte-for-byte. Otherwise the pair is appended, adding a trailing
/// newline to the existing content first if needed. The file is written
/// atomically and, on Unix, given mode `0600`.
///
/// # Arguments
/// * `path` - Path to the dotenv file to update.
/// * `key` - Environment variable name to write.
/// * `value` - Value to store.
///
/// # Errors
/// Returns `KanbusError::IssueOperation` if `value` contains a newline, or
/// `KanbusError::Io` if the file cannot be read or written.
pub fn write_congregation_env_value(
    path: &Path,
    key: &str,
    value: &str,
) -> Result<(), KanbusError> {
    if value.contains('\n') || value.contains('\r') {
        return Err(KanbusError::IssueOperation(
            "API key value must not contain newlines".to_string(),
        ));
    }

    let existing = fs::read_to_string(path).unwrap_or_default();
    let formatted_value = quote_value_if_needed(value);
    let new_line = format!("{key}={formatted_value}");

    let new_contents = if existing.is_empty() {
        format!("{new_line}\n")
    } else {
        let mut replaced = false;
        let mut lines: Vec<String> = Vec::new();
        for line in existing.lines() {
            if !replaced {
                if let Some((line_key, _)) = parse_dotenv_line(line) {
                    if line_key == key {
                        let export_prefix = if line.trim_start().starts_with("export ") {
                            "export "
                        } else {
                            ""
                        };
                        lines.push(format!("{export_prefix}{new_line}"));
                        replaced = true;
                        continue;
                    }
                }
            }
            lines.push(line.to_string());
        }
        if !replaced {
            lines.push(new_line);
        }
        let mut joined = lines.join("\n");
        joined.push('\n');
        joined
    };

    let parent = path.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;

    let mut temp_file = tempfile::NamedTempFile::new_in(parent)
        .map_err(|error| KanbusError::Io(error.to_string()))?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let permissions = std::fs::Permissions::from_mode(0o600);
        temp_file
            .as_file()
            .set_permissions(permissions)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }

    temp_file
        .write_all(new_contents.as_bytes())
        .map_err(|error| KanbusError::Io(error.to_string()))?;
    temp_file
        .flush()
        .map_err(|error| KanbusError::Io(error.to_string()))?;

    temp_file
        .persist(path)
        .map_err(|error| KanbusError::Io(error.to_string()))?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let permissions = std::fs::Permissions::from_mode(0o600);
        fs::set_permissions(path, permissions)
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::OsString;
    use tempfile::TempDir;

    struct EnvRestore {
        home: Option<OsString>,
        variable: Option<OsString>,
        variable_name: String,
    }

    impl EnvRestore {
        fn capture(variable_name: &str) -> Self {
            Self {
                home: std::env::var_os("HOME"),
                variable: std::env::var_os(variable_name),
                variable_name: variable_name.to_string(),
            }
        }
    }

    impl Drop for EnvRestore {
        fn drop(&mut self) {
            match self.home.take() {
                Some(value) => std::env::set_var("HOME", value),
                None => std::env::remove_var("HOME"),
            }
            match self.variable.take() {
                Some(value) => std::env::set_var(&self.variable_name, value),
                None => std::env::remove_var(&self.variable_name),
            }
        }
    }

    #[test]
    fn missing_api_key_message_matches_default_constant() {
        assert_eq!(
            missing_api_key_message(DEFAULT_API_KEY_VARIABLE),
            OPENAI_API_KEY_MISSING_MESSAGE
        );
        assert!(missing_api_key_message("ANTHROPIC_API_KEY").contains("setup ai"));
    }

    #[test]
    fn credential_source_describe_matches_expected_strings() {
        assert_eq!(
            CredentialSource::ProcessEnv.describe(),
            "process environment"
        );
        assert_eq!(
            CredentialSource::CongregationFile.describe(),
            "~/.kanbus.env"
        );
        assert_eq!(CredentialSource::ProjectFile.describe(), "project .env");
        assert_eq!(CredentialSource::None.describe(), "not set");
    }

    #[test]
    fn parse_dotenv_line_cases() {
        assert_eq!(parse_dotenv_line(""), None);
        assert_eq!(parse_dotenv_line("   "), None);
        assert_eq!(parse_dotenv_line("# comment"), None);
        assert_eq!(
            parse_dotenv_line("KEY=value"),
            Some(("KEY".to_string(), "value".to_string()))
        );
        assert_eq!(
            parse_dotenv_line("export KEY=value"),
            Some(("KEY".to_string(), "value".to_string()))
        );
        assert_eq!(
            parse_dotenv_line("KEY=\"quoted value\""),
            Some(("KEY".to_string(), "quoted value".to_string()))
        );
        assert_eq!(
            parse_dotenv_line("KEY='quoted value'"),
            Some(("KEY".to_string(), "quoted value".to_string()))
        );
        assert_eq!(parse_dotenv_line("no-equals-sign"), None);
        assert_eq!(
            parse_dotenv_line("  KEY = value  "),
            Some(("KEY".to_string(), "value".to_string()))
        );
    }

    #[test]
    fn read_dotenv_value_strips_quotes_and_uses_last_match() {
        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join(".env");
        fs::write(
            &path,
            "OPENAI_API_KEY=\"first\"\nOTHER=1\nOPENAI_API_KEY=second\n",
        )
        .expect("write env");
        assert_eq!(
            read_dotenv_value(&path, "OPENAI_API_KEY"),
            Some("second".to_string())
        );
        assert_eq!(read_dotenv_value(&path, "MISSING"), None);
        assert_eq!(
            read_dotenv_value(&dir.path().join("nope"), "OPENAI_API_KEY"),
            None
        );
    }

    #[test]
    #[serial_test::serial]
    fn writer_creates_file_with_mode_600() {
        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join(".kanbus.env");
        write_congregation_env_value(&path, "OPENAI_API_KEY", "abc123").expect("write");
        let contents = fs::read_to_string(&path).expect("read");
        assert_eq!(contents, "OPENAI_API_KEY=abc123\n");

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = fs::metadata(&path).expect("metadata").permissions().mode();
            assert_eq!(mode & 0o777, 0o600);
        }
    }

    #[test]
    #[serial_test::serial]
    fn writer_updates_in_place_preserving_other_lines() {
        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join(".kanbus.env");
        fs::write(
            &path,
            "# my keys\nOTHER_SETTING=1\nOPENAI_API_KEY=old-value\n",
        )
        .expect("write initial");

        write_congregation_env_value(&path, "OPENAI_API_KEY", "new-value").expect("write");

        let contents = fs::read_to_string(&path).expect("read");
        assert_eq!(
            contents,
            "# my keys\nOTHER_SETTING=1\nOPENAI_API_KEY=new-value\n"
        );
    }

    #[test]
    #[serial_test::serial]
    fn writer_preserves_export_prefix() {
        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join(".kanbus.env");
        fs::write(&path, "export OPENAI_API_KEY=old-value\n").expect("write initial");

        write_congregation_env_value(&path, "OPENAI_API_KEY", "new-value").expect("write");

        let contents = fs::read_to_string(&path).expect("read");
        assert_eq!(contents, "export OPENAI_API_KEY=new-value\n");
    }

    #[test]
    #[serial_test::serial]
    fn writer_appends_when_key_absent_without_trailing_newline() {
        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join(".kanbus.env");
        fs::write(&path, "OTHER_SETTING=1").expect("write initial (no trailing newline)");

        write_congregation_env_value(&path, "OPENAI_API_KEY", "value").expect("write");

        let contents = fs::read_to_string(&path).expect("read");
        assert_eq!(contents, "OTHER_SETTING=1\nOPENAI_API_KEY=value\n");
    }

    #[test]
    fn writer_rejects_newline_values() {
        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join(".kanbus.env");
        let error = write_congregation_env_value(&path, "OPENAI_API_KEY", "a\nb").unwrap_err();
        match error {
            KanbusError::IssueOperation(_) => {}
            other => panic!("expected IssueOperation error, got {other:?}"),
        }
    }

    #[test]
    #[serial_test::serial]
    fn writer_quotes_values_with_whitespace_or_hash() {
        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join(".kanbus.env");
        write_congregation_env_value(&path, "OPENAI_API_KEY", "has space").expect("write");
        let contents = fs::read_to_string(&path).expect("read");
        assert_eq!(contents, "OPENAI_API_KEY=\"has space\"\n");

        write_congregation_env_value(&path, "OTHER_KEY", "value#with-hash").expect("write");
        let contents = fs::read_to_string(&path).expect("read");
        assert!(contents.contains("OTHER_KEY=\"value#with-hash\"\n"));
    }

    #[test]
    #[serial_test::serial]
    fn resolve_api_key_source_covers_all_outcomes() {
        let _restore = EnvRestore::capture("KANBUS_TEST_RESOLVE_VAR");
        let home_dir = TempDir::new().expect("home tempdir");
        std::env::set_var("HOME", home_dir.path());
        std::env::remove_var("KANBUS_TEST_RESOLVE_VAR");

        let project_dir = TempDir::new().expect("project tempdir");

        // Nothing set anywhere.
        assert_eq!(
            resolve_api_key_source(Some(project_dir.path()), "KANBUS_TEST_RESOLVE_VAR"),
            CredentialSource::None
        );

        // Congregation file only.
        fs::write(
            home_dir.path().join(".kanbus.env"),
            "KANBUS_TEST_RESOLVE_VAR=congregation-value\n",
        )
        .expect("write congregation env");
        assert_eq!(
            resolve_api_key_source(Some(project_dir.path()), "KANBUS_TEST_RESOLVE_VAR"),
            CredentialSource::CongregationFile
        );

        // Project file only (remove congregation file).
        fs::remove_file(home_dir.path().join(".kanbus.env")).expect("remove congregation env");
        fs::write(
            project_dir.path().join(".env"),
            "KANBUS_TEST_RESOLVE_VAR=project-value\n",
        )
        .expect("write project env");
        assert_eq!(
            resolve_api_key_source(Some(project_dir.path()), "KANBUS_TEST_RESOLVE_VAR"),
            CredentialSource::ProjectFile
        );

        // Process env set and matches congregation file.
        fs::write(
            home_dir.path().join(".kanbus.env"),
            "KANBUS_TEST_RESOLVE_VAR=congregation-value\n",
        )
        .expect("write congregation env");
        std::env::set_var("KANBUS_TEST_RESOLVE_VAR", "congregation-value");
        assert_eq!(
            resolve_api_key_source(Some(project_dir.path()), "KANBUS_TEST_RESOLVE_VAR"),
            CredentialSource::CongregationFile
        );

        // Process env set and matches project file (not congregation).
        std::env::set_var("KANBUS_TEST_RESOLVE_VAR", "project-value");
        assert_eq!(
            resolve_api_key_source(Some(project_dir.path()), "KANBUS_TEST_RESOLVE_VAR"),
            CredentialSource::ProjectFile
        );

        // Process env set to something matching neither file.
        std::env::set_var("KANBUS_TEST_RESOLVE_VAR", "shell-value");
        assert_eq!(
            resolve_api_key_source(Some(project_dir.path()), "KANBUS_TEST_RESOLVE_VAR"),
            CredentialSource::ProcessEnv
        );

        // No repository root at all, env set.
        assert_eq!(
            resolve_api_key_source(None, "KANBUS_TEST_RESOLVE_VAR"),
            CredentialSource::ProcessEnv
        );
    }
}
