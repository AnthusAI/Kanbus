use kanbus::cli::run_from_args_with_output;
use kanbus::config_loader::{configuration_load_count, reset_configuration_load_count};
use std::fs;
use std::path::Path;

fn initialize_repository(root: &Path) -> String {
    std::env::set_var("KANBUS_REALTIME_BROKER", "off");
    fs::write(root.join(".kanbus.yml"), "project_key: kanbus\n").expect("write config");
    fs::create_dir_all(root.join("project/issues")).expect("create issues");
    fs::create_dir_all(root.join("project/events")).expect("create events");
    let output = run_from_args_with_output(
        ["kanbus", "create", "Seed issue", "--no-agent-provenance"],
        root,
    )
    .expect("create seed issue");
    output
        .stdout
        .lines()
        .find_map(|line| line.strip_prefix("ID: "))
        .expect("seed issue identifier")
        .trim()
        .to_string()
}

fn loads_for(root: &Path, arguments: &[&str]) -> usize {
    reset_configuration_load_count();
    let mut full = vec!["kanbus"];
    full.extend_from_slice(arguments);
    run_from_args_with_output(full, root).expect("command succeeds");
    configuration_load_count()
}

#[test]
fn list_loads_configuration_exactly_once() {
    let temp = tempfile::tempdir().expect("tempdir");
    initialize_repository(temp.path());
    assert_eq!(loads_for(temp.path(), &["list"]), 1);
}

#[test]
fn show_loads_configuration_exactly_once() {
    let temp = tempfile::tempdir().expect("tempdir");
    let identifier = initialize_repository(temp.path());
    assert_eq!(loads_for(temp.path(), &["show", &identifier]), 1);
}

#[test]
fn create_loads_configuration_exactly_once() {
    let temp = tempfile::tempdir().expect("tempdir");
    initialize_repository(temp.path());
    assert_eq!(
        loads_for(
            temp.path(),
            &["create", "Another issue", "--no-agent-provenance"]
        ),
        1
    );
}

fn assert_malformed_configuration_error(root: &Path, arguments: &[&str]) {
    let mut full = vec!["kanbus"];
    full.extend_from_slice(arguments);
    match run_from_args_with_output(full, root) {
        Err(kanbus::error::KanbusError::Configuration(message)) => {
            assert_eq!(message, "configuration is not valid YAML");
        }
        other => panic!("expected a configuration error, got {other:?}"),
    }
}

#[test]
fn malformed_configuration_fails_every_issue_command() {
    let temp = tempfile::tempdir().expect("tempdir");
    let identifier = initialize_repository(temp.path());
    fs::write(temp.path().join(".kanbus.yml"), "project_key: [unclosed\n")
        .expect("write malformed configuration");

    assert_malformed_configuration_error(temp.path(), &["list"]);
    assert_malformed_configuration_error(temp.path(), &["show", &identifier]);
    assert_malformed_configuration_error(
        temp.path(),
        &["create", "Broken", "--no-agent-provenance"],
    );
    assert_malformed_configuration_error(
        temp.path(),
        &["update", &identifier, "--status", "in_progress"],
    );
}

#[test]
fn update_loads_configuration_exactly_once() {
    let temp = tempfile::tempdir().expect("tempdir");
    let identifier = initialize_repository(temp.path());
    assert_eq!(
        loads_for(
            temp.path(),
            &["update", &identifier, "--status", "in_progress"]
        ),
        1
    );
}
