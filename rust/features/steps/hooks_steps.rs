//! Step definitions for lifecycle hook feature tests.

use std::fs;

use cucumber::{gherkin, given, then};

use crate::step_definitions::initialization_steps::KanbusWorld;

fn root(world: &KanbusWorld) -> std::path::PathBuf {
    world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .to_path_buf()
}

#[given(expr = "a lifecycle hook recorder script at {string}")]
async fn given_lifecycle_hook_recorder_script(world: &mut KanbusWorld, relative_path: String) {
    let root = root(world);
    let script_path = root.join(relative_path);
    if let Some(parent) = script_path.parent() {
        fs::create_dir_all(parent).expect("create script parent");
    }
    let script = r#"#!/bin/sh
set -eu
token="${1:-hook}"
log_path="${HOOK_LOG_PATH:-}"
if [ -z "$log_path" ]; then
  echo "HOOK_LOG_PATH is required" >&2
  exit 2
fi
cat >/dev/null
printf '%s\n' "$token" >> "$log_path"
exit_code="${HOOK_EXIT_CODE:-0}"
if [ "$exit_code" != "0" ]; then
  exit "$exit_code"
fi
"#;
    fs::write(&script_path, script).expect("write hook script");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&script_path).expect("metadata").permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&script_path, permissions).expect("chmod");
    }
}

#[given(expr = "the Kanbus hooks configuration is")]
#[given(expr = "the Kanbus hooks configuration is:")]
async fn given_kanbus_hooks_configuration(world: &mut KanbusWorld, step: &gherkin::Step) {
    let root = root(world);
    let config_path = root.join(".kanbus.yml");
    let content = fs::read_to_string(&config_path).expect("read .kanbus.yml");
    let mut config: serde_yaml::Value = serde_yaml::from_str(&content).expect("parse .kanbus.yml");
    let hooks_content = step.docstring.as_ref().expect("hooks content required");
    let hooks: serde_yaml::Value =
        serde_yaml::from_str(hooks_content).expect("parse hooks configuration");
    let Some(mapping) = config.as_mapping_mut() else {
        panic!(".kanbus.yml must deserialize to a mapping");
    };
    mapping.insert(serde_yaml::Value::String("hooks".to_string()), hooks);
    let updated = serde_yaml::to_string(&config).expect("serialize .kanbus.yml");
    fs::write(config_path, updated).expect("write .kanbus.yml");
}

#[then(expr = "hook log {string} should contain {string}")]
fn then_hook_log_contains(world: &mut KanbusWorld, relative_path: String, token: String) {
    let root = root(world);
    let log_path = root.join(relative_path);
    let content = fs::read_to_string(&log_path).expect("read hook log");
    assert!(
        content.contains(&token),
        "expected hook log to contain {token:?}, got:\n{content}"
    );
}

#[then(expr = "hook log {string} should not contain {string}")]
fn then_hook_log_not_contains(world: &mut KanbusWorld, relative_path: String, token: String) {
    let root = root(world);
    let log_path = root.join(relative_path);
    let content = fs::read_to_string(&log_path).unwrap_or_default();
    assert!(
        !content.contains(&token),
        "expected hook log to omit {token:?}, got:\n{content}"
    );
}
