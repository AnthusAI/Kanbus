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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prefers_kanbus_user_when_set() {
        let original = env::var("KANBUS_USER").ok();
        env::set_var("KANBUS_USER", "kanbus-user");
        assert_eq!(get_current_user(), "kanbus-user");
        match original {
            Some(value) => env::set_var("KANBUS_USER", value),
            None => env::remove_var("KANBUS_USER"),
        }
    }

    #[test]
    fn falls_back_to_user_when_kanbus_user_empty() {
        let original_kanbus = env::var("KANBUS_USER").ok();
        let original_user = env::var("USER").ok();
        env::set_var("KANBUS_USER", "  ");
        env::set_var("USER", "shell-user");
        assert_eq!(get_current_user(), "shell-user");
        match original_kanbus {
            Some(value) => env::set_var("KANBUS_USER", value),
            None => env::remove_var("KANBUS_USER"),
        }
        match original_user {
            Some(value) => env::set_var("USER", value),
            None => env::remove_var("USER"),
        }
    }
}
