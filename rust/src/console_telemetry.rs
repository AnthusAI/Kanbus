//! Console telemetry streaming helpers.

use std::fs::{create_dir_all, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

use reqwest::blocking::Client;
use serde::Deserialize;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;

#[derive(Debug, Deserialize)]
struct ConsoleTelemetryEvent {
    level: Option<String>,
    message: Option<String>,
    args: Option<Vec<serde_json::Value>>,
    timestamp: Option<String>,
    received_at: Option<String>,
    url: Option<String>,
    session_id: Option<String>,
}

pub fn stream_console_telemetry(
    root: &Path,
    output_override: Option<String>,
    url_override: Option<String>,
) -> Result<(), KanbusError> {
    let output_path = resolve_output_path(root, output_override)?;
    let url = resolve_telemetry_url(root, url_override)?;
    let file = open_output_file(&output_path)?;
    let client = Client::new();
    let response = client
        .get(&url)
        .header("Accept", "text/event-stream")
        .send()
        .map_err(|error| KanbusError::Io(format!("telemetry connection failed: {error}")))?;

    let reader = BufReader::new(response);
    let mut writer = std::io::BufWriter::new(file);

    for line in reader.lines() {
        let line = line.map_err(|error| KanbusError::Io(error.to_string()))?;
        if !line.starts_with("data: ") {
            continue;
        }
        let payload = line.trim_start_matches("data: ").trim();
        let formatted = format_telemetry_line(payload);
        writeln!(writer, "{formatted}").map_err(|error| KanbusError::Io(error.to_string()))?;
        writer
            .flush()
            .map_err(|error| KanbusError::Io(error.to_string()))?;
    }

    Ok(())
}

fn resolve_output_path(
    root: &Path,
    output_override: Option<String>,
) -> Result<PathBuf, KanbusError> {
    let path = if let Some(output) = output_override {
        PathBuf::from(output)
    } else {
        root.join(".kanbus").join("telemetry").join("console.log")
    };
    if let Some(parent) = path.parent() {
        create_dir_all(parent).map_err(|error| KanbusError::Io(error.to_string()))?;
    }
    Ok(path)
}

fn open_output_file(path: &Path) -> Result<std::fs::File, KanbusError> {
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| KanbusError::Io(error.to_string()))
}

fn resolve_telemetry_url(root: &Path, url_override: Option<String>) -> Result<String, KanbusError> {
    if let Some(url) = url_override {
        return Ok(url);
    }
    let config_path = get_configuration_path(root)?;
    let config = load_project_configuration(&config_path)?;
    let port = config.console_port.unwrap_or(5174);
    Ok(format!(
        "http://127.0.0.1:{port}/api/telemetry/console/events"
    ))
}

fn format_telemetry_line(payload: &str) -> String {
    let parsed = serde_json::from_str::<ConsoleTelemetryEvent>(payload);
    match parsed {
        Ok(event) => {
            let timestamp = event
                .timestamp
                .or(event.received_at)
                .unwrap_or_else(|| "unknown-time".to_string());
            let level = event.level.unwrap_or_else(|| "log".to_string());
            let message = event.message.or_else(|| flatten_args(event.args));
            let source = event.url.unwrap_or_else(|| "unknown-source".to_string());
            let session = event
                .session_id
                .unwrap_or_else(|| "unknown-session".to_string());
            let body = message.unwrap_or_else(|| payload.to_string());
            format!("[{timestamp}] [{level}] [{session}] {body} ({source})")
        }
        Err(_) => format!("[unparsed] {payload}"),
    }
}

fn flatten_args(args: Option<Vec<serde_json::Value>>) -> Option<String> {
    let values = args?;
    let parts: Vec<String> = values
        .into_iter()
        .map(|value| match value {
            serde_json::Value::String(text) => text,
            other => other.to_string(),
        })
        .collect();
    if parts.is_empty() {
        None
    } else {
        Some(parts.join(" "))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn resolve_output_path_creates_parent_directory() {
        let temp_dir = TempDir::new().expect("tempdir");
        let output_path = temp_dir.path().join("nested").join("console.log");

        let resolved = resolve_output_path(
            temp_dir.path(),
            Some(output_path.to_string_lossy().to_string()),
        )
        .expect("resolve path");

        assert_eq!(resolved, output_path);
        assert!(resolved.parent().expect("parent").is_dir());
    }

    #[test]
    fn format_telemetry_line_parses_json_payload() {
        let payload = r#"{"level":"warn","message":"test event","timestamp":"2026-03-06T10:00:00Z","url":"http://localhost","session_id":"session-1"}"#;

        let formatted = format_telemetry_line(payload);

        assert!(formatted.contains("[warn]"));
        assert!(formatted.contains("test event"));
        assert!(formatted.contains("[session-1]"));
    }

    #[test]
    fn format_telemetry_line_handles_unparsed_payload() {
        let formatted = format_telemetry_line("{invalid-json");
        assert!(formatted.starts_with("[unparsed]"));
    }

    #[test]
    fn flatten_args_joins_stringified_values() {
        let args = Some(vec![
            serde_json::Value::String("hello".to_string()),
            serde_json::json!(123),
            serde_json::json!({"k": "v"}),
        ]);

        let flattened = flatten_args(args);

        assert_eq!(flattened.as_deref(), Some("hello 123 {\"k\":\"v\"}"));
    }
}
