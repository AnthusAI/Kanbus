use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then, when};
use serde_yaml::Value;
use tempfile::TempDir;

use taskulus::cli::run_from_args_with_output;
use taskulus::config::write_default_configuration;
use taskulus::config_loader::load_project_configuration;
use taskulus::file_io::load_project_directory;

use crate::step_definitions::initialization_steps::TaskulusWorld;

fn run_cli(world: &mut TaskulusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse command");
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

fn initialize_project(world: &mut TaskulusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
    run_cli(world, "tsk init");
    assert_eq!(world.exit_code, Some(0));
}

fn load_project_dir(world: &TaskulusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn update_config_file(world: &TaskulusWorld, update: impl FnOnce(&mut serde_yaml::Mapping)) {
    let project_dir = load_project_dir(world);
    let config_path = project_dir.join("config.yaml");
    if !config_path.exists() {
        write_default_configuration(&config_path).expect("write default config");
    }
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut value: Value = serde_yaml::from_str(&contents).expect("parse config");
    let mapping = value.as_mapping_mut().expect("mapping");
    update(mapping);
    let updated = serde_yaml::to_string(&value).expect("serialize config");
    fs::write(config_path, updated).expect("write config");
}

#[given("a Taskulus project with an invalid configuration containing unknown fields")]
fn given_invalid_config_unknown_fields(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("unknown_field".to_string()),
            Value::String("value".to_string()),
        );
    });
}

#[given("a Taskulus project with a configuration file")]
fn given_project_with_configuration_file(world: &mut TaskulusWorld) {
    initialize_project(world);
    let project_dir = load_project_dir(world);
    let config_path = project_dir.join("config.yaml");
    write_default_configuration(&config_path).expect("write default config");
}

#[given("a Taskulus project with an unreadable configuration file")]
fn given_project_with_unreadable_configuration_file(world: &mut TaskulusWorld) {
    initialize_project(world);
    let project_dir = load_project_dir(world);
    let config_path = project_dir.join("config.yaml");
    write_default_configuration(&config_path).expect("write default config");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&config_path)
            .expect("config metadata")
            .permissions();
        permissions.set_mode(0o000);
        fs::set_permissions(&config_path, permissions).expect("set permissions");
    }
}

#[given("a Taskulus project with an invalid configuration containing empty hierarchy")]
fn given_invalid_config_empty_hierarchy(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("hierarchy".to_string()),
            Value::Sequence(vec![]),
        );
    });
}

#[given("a Taskulus project with an invalid configuration containing duplicate types")]
fn given_invalid_config_duplicate_types(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("types".to_string()),
            Value::Sequence(vec![
                Value::String("bug".to_string()),
                Value::String("task".to_string()),
            ]),
        );
    });
}

#[given("a Taskulus project with an invalid configuration missing the default workflow")]
fn given_invalid_config_missing_default_workflow(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        let mut workflows = serde_yaml::Mapping::new();
        workflows.insert(
            Value::String("epic".to_string()),
            Value::Mapping({
                let mut epic = serde_yaml::Mapping::new();
                epic.insert(
                    Value::String("open".to_string()),
                    Value::Sequence(vec![Value::String("in_progress".to_string())]),
                );
                epic
            }),
        );
        mapping.insert(
            Value::String("workflows".to_string()),
            Value::Mapping(workflows),
        );
    });
}

#[given("a Taskulus project with an invalid configuration missing the default priority")]
fn given_invalid_config_missing_default_priority(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("default_priority".to_string()),
            Value::Number(99.into()),
        );
    });
}

#[given("a Taskulus project with an invalid configuration containing wrong field types")]
fn given_invalid_config_wrong_field_types(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("priorities".to_string()),
            Value::String("high".to_string()),
        );
    });
}

#[when("the configuration is loaded")]
fn when_configuration_loaded(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let config_path = project_dir.join("config.yaml");
    match load_project_configuration(&config_path) {
        Ok(configuration) => {
            world.configuration = Some(configuration);
            world.exit_code = Some(0);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.configuration = None;
            world.exit_code = Some(1);
            world.stderr = Some(error.to_string());
        }
    }
}

#[then("the prefix should be \"tsk\"")]
fn then_prefix_should_match(world: &mut TaskulusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.prefix, "tsk");
}

#[then("the hierarchy should be \"initiative, epic, task, sub-task\"")]
fn then_hierarchy_should_match(world: &mut TaskulusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    let hierarchy = configuration.hierarchy.join(", ");
    assert_eq!(hierarchy, "initiative, epic, task, sub-task");
}

#[then("the non-hierarchical types should be \"bug, story, chore\"")]
fn then_types_should_match(world: &mut TaskulusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    let types = configuration.types.join(", ");
    assert_eq!(types, "bug, story, chore");
}

#[then("the initial status should be \"open\"")]
fn then_initial_status_should_match(world: &mut TaskulusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.initial_status, "open");
}

#[then("the default priority should be 2")]
fn then_default_priority_should_match(world: &mut TaskulusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.default_priority, 2);
}
