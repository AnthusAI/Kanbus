//! Regression test for config schema compatibility.
//!
//! Tests that .kanbus.yml with newer optional fields can still be loaded by older binaries.
//! Prevents the "unknown configuration fields" error when deploy configs have evolved.

use kanbus::config_loader::load_project_configuration;
use std::fs;
use tempfile::TempDir;

#[test]
fn test_config_loads_with_all_optional_fields() {
    let temp_dir = TempDir::new().unwrap();
    let project_dir = temp_dir.path().join("project");
    fs::create_dir(&project_dir).unwrap();
    let config_path = temp_dir.path().join(".kanbus.yml");

    let config_yaml = r#"
project_directory: project
project_key: test
beads_compatibility: false
ai:
  provider: litellm
  model: gpt-4
jira:
  url: https://example.atlassian.net
  project_key: TEST
  sync_direction: pull
  type_mappings:
    Story: story
    Bug: bug
snyk:
  org_id: test-org-id
  min_severity: high
github_security:
  repo: owner/repo
  dependabot:
    min_severity: high
    state: open
"#;

    fs::write(&config_path, config_yaml).unwrap();

    let config = load_project_configuration(&config_path);
    assert!(
        config.is_ok(),
        "Config with all optional fields should load: {:?}",
        config.err()
    );

    let config = config.unwrap();
    assert_eq!(config.project_key, "test");
    assert_eq!(config.ai.as_ref().unwrap().model, "gpt-4");
    assert!(config.github_security.is_some());
}

#[test]
fn test_config_loads_with_minimal_required_fields() {
    let temp_dir = TempDir::new().unwrap();
    let project_dir = temp_dir.path().join("project");
    fs::create_dir(&project_dir).unwrap();
    let config_path = temp_dir.path().join(".kanbus.yml");

    let config_yaml = r#"
project_directory: project
project_key: test
"#;

    fs::write(&config_path, config_yaml).unwrap();

    let config = load_project_configuration(&config_path);
    assert!(
        config.is_ok(),
        "Config with only required fields should load: {:?}",
        config.err()
    );
}
