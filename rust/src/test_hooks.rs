use std::env::VarError;
use std::ffi::OsString;

pub const TEST_HOOKS_ENABLED: bool = cfg!(any(test, feature = "test-hooks"));

pub fn var(name: &str) -> Result<String, VarError> {
    if TEST_HOOKS_ENABLED {
        std::env::var(name)
    } else {
        Err(VarError::NotPresent)
    }
}

pub fn var_os(name: &str) -> Option<OsString> {
    if TEST_HOOKS_ENABLED {
        std::env::var_os(name)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hooks_are_readable_when_test_hooks_are_compiled_in() {
        std::env::set_var("KANBUS_TEST_HOOKS_SELF_CHECK", "on");
        assert_eq!(var("KANBUS_TEST_HOOKS_SELF_CHECK").as_deref(), Ok("on"));
        assert!(var_os("KANBUS_TEST_HOOKS_SELF_CHECK").is_some());
        std::env::remove_var("KANBUS_TEST_HOOKS_SELF_CHECK");
        assert!(var("KANBUS_TEST_HOOKS_SELF_CHECK").is_err());
    }
}
