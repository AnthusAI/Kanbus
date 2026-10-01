//! LLM usage cost reporting from the project usage log.

use std::fs;
use std::path::Path;

use chrono::{DateTime, Duration, Utc};
use serde_json::Value;

use crate::config_loader::load_project_configuration;
use crate::error::KanbusError;
use crate::file_io::get_configuration_path;

const LLM_USAGE_LOG: &str = "llm_usage.jsonl";

/// Message printed when no LLM usage log exists.
pub const NO_LLM_USAGE_MESSAGE: &str = "No LLM usage logs found.";

/// Aggregated LLM usage totals.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct LlmCostTotals {
    /// Tokens consumed across every counted call.
    pub total_tokens: u64,
    /// Summed cost in USD of calls with a known price.
    pub total_cost: f64,
    /// Calls whose cost is unknown and excluded from the total.
    pub unpriced_calls: u64,
}

/// Aggregate tokens and cost from an LLM usage log.
///
/// # Arguments
/// * `log_path` - Path to `llm_usage.jsonl`.
/// * `days` - Only count entries from the last `days` days when set.
///
/// # Errors
/// Returns `KanbusError` when the log cannot be read or an entry is malformed.
pub fn aggregate_llm_usage(
    log_path: &Path,
    days: Option<u32>,
) -> Result<LlmCostTotals, KanbusError> {
    let cutoff = days.map(|days| Utc::now() - Duration::days(i64::from(days)));
    let contents = fs::read_to_string(log_path)
        .map_err(|error| KanbusError::Io(format!("read llm usage log: {error}")))?;
    let mut totals = LlmCostTotals::default();
    for line in contents.lines().filter(|line| !line.trim().is_empty()) {
        let entry: Value = serde_json::from_str(line)
            .map_err(|error| KanbusError::Io(format!("parse llm usage log: {error}")))?;
        let timestamp = entry
            .get("timestamp")
            .and_then(Value::as_str)
            .and_then(|raw| DateTime::parse_from_rfc3339(raw).ok())
            .map(|parsed| parsed.with_timezone(&Utc))
            .ok_or_else(|| {
                KanbusError::Io("llm usage log entry has no valid timestamp".to_string())
            })?;
        if cutoff.is_some_and(|cutoff| timestamp < cutoff) {
            continue;
        }
        totals.total_tokens += entry
            .get("total_tokens")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        match entry.get("cost").and_then(Value::as_f64) {
            Some(cost) => totals.total_cost += cost,
            None => totals.unpriced_calls += 1,
        }
    }
    Ok(totals)
}

/// Build the `kanbus cost` report text.
///
/// # Arguments
/// * `root` - Repository root path.
/// * `days` - Only count entries from the last `days` days when set.
///
/// # Errors
/// Returns `KanbusError` when configuration or the usage log cannot be read.
pub fn build_llm_cost_report(root: &Path, days: Option<u32>) -> Result<String, KanbusError> {
    let configuration = load_project_configuration(&get_configuration_path(root)?)?;
    let log_path = root
        .join(&configuration.project_directory)
        .join("events")
        .join(LLM_USAGE_LOG);
    if !log_path.exists() {
        return Ok(NO_LLM_USAGE_MESSAGE.to_string());
    }
    let totals = aggregate_llm_usage(&log_path, days)?;
    Ok(format!(
        "Total Tokens:   {}\nTotal Cost:     ${:.4}\nUnpriced Calls: {}",
        totals.total_tokens, totals.total_cost, totals.unpriced_calls
    ))
}
