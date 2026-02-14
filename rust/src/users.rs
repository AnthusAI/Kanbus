//! User identification helpers.

use std::env;

/// Return the current user identifier.
pub fn get_current_user() -> String {
    if let Ok(value) = env::var("KANBUS_USER") {
        if !value.trim().is_empty() {
            return value;
        }
    }
    env::var("USER").unwrap_or_else(|_| "unknown".to_string())
}
