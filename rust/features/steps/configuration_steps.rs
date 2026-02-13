use std::fs;
use std::process::Command;

use cucumber::{given, then, when};
use serde_yaml::Value;
use tempfile::TempDir;

use taskulus::cli::run_from_args_with_output;
use taskulus::config::write_default_configuration;
use taskulus::config_loader::load_project_configuration;

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

#[given("a Taskulus repository with a .taskulus.yml file containing the default configuration")]
fn given_repo_with_default_configuration(world: &mut TaskulusWorld) {
    given_project_with_configuration_file(world);
}

#[given("a Taskulus repository with an empty .taskulus.yml file")]
fn given_repo_with_empty_configuration(world: &mut TaskulusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".taskulus.yml");
    fs::write(config_path, "").expect("write empty config");
}

#[given("a Taskulus repository with a .taskulus.yml file containing null")]
fn given_repo_with_null_configuration(world: &mut TaskulusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".taskulus.yml");
    fs::write(config_path, "null\n").expect("write null config");
}

#[given(
    "a Taskulus repository with a .taskulus.yml file pointing to an absolute project directory"
)]
fn given_project_with_absolute_project_directory(world: &mut TaskulusWorld) {
    initialize_project(world);
    let abs_project = world
        .temp_dir
        .as_ref()
        .expect("temp dir")
        .path()
        .join("abs-project");
    fs::create_dir_all(abs_project.join("issues")).expect("create abs project issues");
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("project_directory".to_string()),
            Value::String(abs_project.display().to_string()),
        );
    });
    world.expected_project_dir = Some(abs_project.clone());
}

#[given("a Taskulus repository with a .taskulus.yml file containing unknown configuration fields")]
fn given_repo_with_unknown_fields(world: &mut TaskulusWorld) {
    given_invalid_config_unknown_fields(world);
}

#[given("a Taskulus repository with a .taskulus.yml file containing an empty hierarchy")]
fn given_repo_with_empty_hierarchy(world: &mut TaskulusWorld) {
    given_invalid_config_empty_hierarchy(world);
}

#[given("a Taskulus repository with a .taskulus.yml file that is not a mapping")]
fn given_repo_with_non_mapping_config(world: &mut TaskulusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".taskulus.yml");
    fs::write(config_path, "- not-a-map\n").expect("write non-mapping config");
}

#[given("a Taskulus repository with a .taskulus.yml file containing an empty project directory")]
fn given_repo_with_empty_project_directory(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("project_directory".to_string()),
            Value::String("".to_string()),
        );
    });
}

#[given("a Taskulus repository with a .taskulus.yml file containing duplicate types")]
fn given_repo_with_duplicate_types(world: &mut TaskulusWorld) {
    given_invalid_config_duplicate_types(world);
}

#[given("a Taskulus repository with a .taskulus.yml file missing the default workflow")]
fn given_repo_missing_default_workflow(world: &mut TaskulusWorld) {
    given_invalid_config_missing_default_workflow(world);
}

#[given("a Taskulus repository with a .taskulus.yml file missing the default priority")]
fn given_repo_missing_default_priority(world: &mut TaskulusWorld) {
    given_invalid_config_missing_default_priority(world);
}

#[given("a Taskulus repository with a .taskulus.yml file containing a bright white status color")]
fn given_repo_bright_white_status_color(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        let status_colors_key = Value::String("status_colors".to_string());
        let mut colors = mapping
            .get(&status_colors_key)
            .cloned()
            .unwrap_or_else(|| Value::Mapping(serde_yaml::Mapping::new()));
        if let Some(color_map) = colors.as_mapping_mut() {
            color_map.insert(
                Value::String("open".to_string()),
                Value::String("bright_white".to_string()),
            );
        }
        mapping.insert(status_colors_key, colors);
    });
}

#[given("a Taskulus repository with a .taskulus.yml file containing an invalid status color")]
fn given_repo_invalid_status_color(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        let status_colors_key = Value::String("status_colors".to_string());
        let mut colors = mapping
            .get(&status_colors_key)
            .cloned()
            .unwrap_or_else(|| Value::Mapping(serde_yaml::Mapping::new()));
        if let Some(color_map) = colors.as_mapping_mut() {
            color_map.insert(
                Value::String("open".to_string()),
                Value::String("invalid-color".to_string()),
            );
        }
        mapping.insert(status_colors_key, colors);
    });
}

#[given("a Taskulus repository with a .taskulus.yml file containing wrong field types")]
fn given_repo_wrong_field_types(world: &mut TaskulusWorld) {
    given_invalid_config_wrong_field_types(world);
}

#[given("a Taskulus repository with an unreadable .taskulus.yml file")]
fn given_repo_unreadable_config(world: &mut TaskulusWorld) {
    given_project_with_unreadable_configuration_file(world);
}

#[given("a Taskulus repository without a .taskulus.yml file")]
fn given_repository_without_configuration(world: &mut TaskulusWorld) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo-missing-config");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
}

fn update_config_file(world: &TaskulusWorld, update: impl FnOnce(&mut serde_yaml::Mapping)) {
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".taskulus.yml");
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
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".taskulus.yml");
    write_default_configuration(&config_path).expect("write default config");
}

#[given("a Taskulus repository with a .taskulus.yml file pointing to \"tracking\" as the project directory")]
fn given_project_with_custom_project_directory(world: &mut TaskulusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("project_directory".to_string()),
            Value::String("tracking".to_string()),
        );
    });
    let repo_path = world.working_directory.as_ref().expect("working directory");
    fs::create_dir_all(repo_path.join("tracking").join("issues")).expect("create tracking issues");
}

#[given("a Taskulus project with an unreadable configuration file")]
fn given_project_with_unreadable_configuration_file(world: &mut TaskulusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".taskulus.yml");
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
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".taskulus.yml");
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

#[then("the project key should be \"tsk\"")]
fn then_project_key_should_match(world: &mut TaskulusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.project_key, "tsk");
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

#[then("the project directory should match the configured absolute path")]
fn then_project_directory_should_match_absolute(world: &mut TaskulusWorld) {
    let expected = world
        .expected_project_dir
        .as_ref()
        .expect("expected project directory");
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(
        &configuration.project_directory,
        &expected.display().to_string()
    );
}

#[then(expr = "the project directory should be \"{string}\"")]
fn then_project_directory_should_match(world: &mut TaskulusWorld, value: String) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.project_directory, value);
}

#[then("beads compatibility should be false")]
fn then_beads_compatibility_should_be_false(world: &mut TaskulusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.beads_compatibility, false);
}
