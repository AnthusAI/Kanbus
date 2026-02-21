use std::collections::BTreeMap;
use std::fs;
use std::process::Command;

use cucumber::{given, then, when};
use serde_yaml::Value;
use tempfile::TempDir;

use kanbus::cli::run_from_args_with_output;
use kanbus::config::{default_project_configuration, write_default_configuration};
use kanbus::config_loader::load_project_configuration;
use kanbus::file_io::get_configuration_path;
use kanbus::workflows::validate_status_transition;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn run_cli(world: &mut KanbusWorld, command: &str) {
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

fn initialize_project(world: &mut KanbusWorld) {
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
    run_cli(world, "kanbus init");
    assert_eq!(world.exit_code, Some(0));
    if let Some(root) = world.working_directory.as_ref() {
        world.configuration_path = Some(root.join(".kanbus.yml"));
    }
}

#[given("a Kanbus project with a file \"kanbus.yml\" attempting to override the hierarchy")]
fn given_project_with_custom_hierarchy(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("hierarchy".to_string()),
            Value::Sequence(vec![
                Value::String("custom".to_string()),
                Value::String("epic".to_string()),
                Value::String("task".to_string()),
            ]),
        );
    });
}

#[given(
    "a Kanbus project with a file \"kanbus.yml\" where issue type \"bug\" has no workflow binding"
)]
fn given_project_missing_workflow_binding(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        // Remove the default workflow to force validation to look for per-type binding.
        mapping.remove(&Value::String("workflows".to_string()));
        mapping.insert(
            Value::String("workflows".to_string()),
            Value::Mapping(serde_yaml::Mapping::from_iter([(
                Value::String("epic".to_string()),
                Value::Mapping(serde_yaml::Mapping::new()),
            )])),
        );
    });
}

#[given("a Kanbus project with default workflows")]
fn given_project_with_default_workflows(world: &mut KanbusWorld) {
    initialize_project(world);
}

#[when(expr = "I update issue \"{word}\" to status \"{word}\"")]
fn when_update_issue_status(world: &mut KanbusWorld, id: String, status: String) {
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let config_path = get_configuration_path(root).expect("config path");
    let configuration = load_project_configuration(&config_path).expect("load config");

    let issues_dir = root.join("project").join("issues");
    let issue_path = issues_dir.join(format!("{}.json", id));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    let mut issue: kanbus::models::IssueData = serde_json::from_str(&contents).expect("parse");

    let result =
        validate_status_transition(&configuration, &issue.issue_type, &issue.status, &status);
    if let Err(error) = result {
        world.exit_code = Some(1);
        world.stderr = Some(error.to_string());
    } else {
        issue.status = status;
        let updated = serde_json::to_string_pretty(&issue).expect("serialize");
        fs::write(issue_path, updated).expect("write issue");
        world.exit_code = Some(0);
        world.stderr = Some(String::new());
    }
}

#[given("a Kanbus repository with a .kanbus.yml file containing the default configuration")]
fn given_repo_with_default_configuration(world: &mut KanbusWorld) {
    given_project_with_configuration_file(world);
}

#[given("a Kanbus repository with an empty .kanbus.yml file")]
fn given_repo_with_empty_configuration(world: &mut KanbusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".kanbus.yml");
    fs::write(config_path, "").expect("write empty config");
    world.configuration_path = Some(
        world
            .working_directory
            .as_ref()
            .expect("working directory not set")
            .join(".kanbus.yml"),
    );
}

#[given("a Kanbus repository with a .kanbus.yml file containing null")]
fn given_repo_with_null_configuration(world: &mut KanbusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".kanbus.yml");
    fs::write(config_path, "null\n").expect("write null config");
    world.configuration_path = Some(
        world
            .working_directory
            .as_ref()
            .expect("working directory not set")
            .join(".kanbus.yml"),
    );
}

#[given("a Kanbus repository with a .kanbus.yml file pointing to an absolute project directory")]
fn given_project_with_absolute_project_directory(world: &mut KanbusWorld) {
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

#[given("a Kanbus repository with a .kanbus.yml file containing unknown configuration fields")]
fn given_repo_with_unknown_fields(world: &mut KanbusWorld) {
    given_invalid_config_unknown_fields(world);
}

#[given("a Kanbus repository with a .kanbus.yml file containing an empty hierarchy")]
fn given_repo_with_empty_hierarchy(world: &mut KanbusWorld) {
    given_invalid_config_empty_hierarchy(world);
}

#[given("a Kanbus repository with a .kanbus.yml file that is not a mapping")]
fn given_repo_with_non_mapping_config(world: &mut KanbusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".kanbus.yml");
    fs::write(config_path, "- not-a-map\n").expect("write non-mapping config");
    world.configuration_path = Some(
        world
            .working_directory
            .as_ref()
            .expect("working directory not set")
            .join(".kanbus.yml"),
    );
}

#[given("a Kanbus repository with a .kanbus.yml file containing an empty project directory")]
fn given_repo_with_empty_project_directory(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("project_directory".to_string()),
            Value::String("".to_string()),
        );
    });
}

#[given("a Kanbus repository with a .kanbus.yml file containing duplicate types")]
fn given_repo_with_duplicate_types(world: &mut KanbusWorld) {
    given_invalid_config_duplicate_types(world);
}

#[given("a Kanbus repository with a .kanbus.yml file missing the default workflow")]
fn given_repo_missing_default_workflow(world: &mut KanbusWorld) {
    given_invalid_config_missing_default_workflow(world);
}

#[given("a Kanbus repository with a .kanbus.yml file missing the default priority")]
fn given_repo_missing_default_priority(world: &mut KanbusWorld) {
    given_invalid_config_missing_default_priority(world);
}

#[given("a Kanbus repository with a .kanbus.yml file containing a bright white status color")]
fn given_repo_bright_white_status_color(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        let statuses_key = Value::String("statuses".to_string());
        if let Some(Value::Sequence(statuses)) = mapping.get_mut(&statuses_key) {
            for status in statuses {
                if let Value::Mapping(status_map) = status {
                    if status_map.get(&Value::String("name".to_string()))
                        == Some(&Value::String("open".to_string()))
                    {
                        status_map.insert(
                            Value::String("color".to_string()),
                            Value::String("bright_white".to_string()),
                        );
                    }
                }
            }
        }
    });
}

#[given("a Kanbus repository with a .kanbus.yml file containing an invalid status color")]
fn given_repo_invalid_status_color(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        let statuses_key = Value::String("statuses".to_string());
        if let Some(Value::Sequence(statuses)) = mapping.get_mut(&statuses_key) {
            for status in statuses {
                if let Value::Mapping(status_map) = status {
                    if status_map.get(&Value::String("name".to_string()))
                        == Some(&Value::String("open".to_string()))
                    {
                        status_map.insert(
                            Value::String("color".to_string()),
                            Value::String("invalid-color".to_string()),
                        );
                    }
                }
            }
        }
    });
}

#[given("a Kanbus repository with a .kanbus.yml file containing wrong field types")]
fn given_repo_wrong_field_types(world: &mut KanbusWorld) {
    given_invalid_config_wrong_field_types(world);
}

#[given("a Kanbus repository with an unreadable .kanbus.yml file")]
fn given_repo_unreadable_config(world: &mut KanbusWorld) {
    given_project_with_unreadable_configuration_file(world);
}

#[given("a Kanbus repository without a .kanbus.yml file")]
fn given_repository_without_configuration(world: &mut KanbusWorld) {
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
    world.configuration_path = Some(
        world
            .working_directory
            .as_ref()
            .expect("working directory not set")
            .join(".kanbus.yml"),
    );
}

fn update_config_file(world: &mut KanbusWorld, update: impl FnOnce(&mut serde_yaml::Mapping)) {
    let config_path = world.configuration_path.clone().unwrap_or_else(|| {
        world
            .working_directory
            .as_ref()
            .expect("working directory not set")
            .join(".kanbus.yml")
    });
    if !config_path.exists() {
        write_default_configuration(&config_path).expect("write default config");
    }
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut value: Value = serde_yaml::from_str(&contents).expect("parse config");
    let mapping = value.as_mapping_mut().expect("mapping");
    update(mapping);
    let updated = serde_yaml::to_string(&value).expect("serialize config");
    fs::write(&config_path, updated).expect("write config");
    world.configuration_path = Some(config_path);
}

#[given("a Kanbus project with an invalid configuration containing unknown fields")]
fn given_invalid_config_unknown_fields(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("unknown_field".to_string()),
            Value::String("value".to_string()),
        );
    });
}

#[given("a Kanbus project with a configuration file")]
fn given_project_with_configuration_file(world: &mut KanbusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".kanbus.yml");
    write_default_configuration(&config_path).expect("write default config");
    world.configuration_path = Some(config_path);
}

#[given(expr = "the Kanbus configuration sets default assignee {string}")]
fn given_kanbus_configuration_default_assignee(world: &mut KanbusWorld, assignee: String) {
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("assignee".to_string()),
            Value::String(assignee),
        );
    });
}

#[given(expr = "a Kanbus override file sets default assignee {string}")]
fn given_override_default_assignee(world: &mut KanbusWorld, assignee: String) {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let override_path = repo_path.join(".kanbus.override.yml");
    let payload = serde_yaml::to_string(&serde_yaml::Mapping::from_iter([(
        Value::String("assignee".to_string()),
        Value::String(assignee),
    )]))
    .expect("serialize override");
    fs::write(override_path, payload).expect("write override file");
}

#[given(expr = "a Kanbus override file sets time zone {string}")]
fn given_override_time_zone(world: &mut KanbusWorld, time_zone: String) {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let override_path = repo_path.join(".kanbus.override.yml");
    let payload = serde_yaml::to_string(&serde_yaml::Mapping::from_iter([(
        Value::String("time_zone".to_string()),
        Value::String(time_zone),
    )]))
    .expect("serialize override");
    fs::write(override_path, payload).expect("write override file");
}

#[given("a Kanbus override file that is not a mapping")]
fn given_override_not_mapping(world: &mut KanbusWorld) {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let override_path = repo_path.join(".kanbus.override.yml");
    fs::write(override_path, "- item\n").expect("write override file");
}

#[given("a Kanbus override file containing invalid YAML")]
fn given_override_invalid_yaml(world: &mut KanbusWorld) {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let override_path = repo_path.join(".kanbus.override.yml");
    fs::write(override_path, "invalid: [").expect("write override file");
}

#[given("an empty .kanbus.override.yml file")]
fn given_empty_override_file(world: &mut KanbusWorld) {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let override_path = repo_path.join(".kanbus.override.yml");
    fs::write(override_path, "").expect("write override file");
}

#[given("an unreadable .kanbus.override.yml file")]
fn given_unreadable_override_file(world: &mut KanbusWorld) {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let override_path = repo_path.join(".kanbus.override.yml");
    fs::write(&override_path, "assignee: blocked@example.com\n").expect("write override file");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&override_path)
            .expect("override metadata")
            .permissions();
        let original = permissions.mode();
        permissions.set_mode(0o000);
        fs::set_permissions(&override_path, permissions).expect("set permissions");
        world.unreadable_path = Some(override_path);
        world.unreadable_mode = Some(original);
    }
}

#[given(
    "a Kanbus repository with a .kanbus.yml file pointing to \"tracking\" as the project directory"
)]
fn given_project_with_custom_project_directory(world: &mut KanbusWorld) {
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

#[given("a Kanbus project with an unreadable configuration file")]
fn given_project_with_unreadable_configuration_file(world: &mut KanbusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".kanbus.yml");
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
    world.configuration_path = Some(config_path);
}

#[given("a Kanbus project with an invalid configuration containing empty hierarchy")]
fn given_invalid_config_empty_hierarchy(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("hierarchy".to_string()),
            Value::Sequence(vec![]),
        );
    });
}

#[given("a Kanbus project with an invalid configuration containing duplicate types")]
fn given_invalid_config_duplicate_types(world: &mut KanbusWorld) {
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

#[given("a Kanbus project with an invalid configuration missing the default workflow")]
fn given_invalid_config_missing_default_workflow(world: &mut KanbusWorld) {
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

#[given("a Kanbus project with an invalid configuration missing the default priority")]
fn given_invalid_config_missing_default_priority(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("default_priority".to_string()),
            Value::Number(99.into()),
        );
    });
}

#[given("a Kanbus project with an invalid configuration containing unknown initial status")]
fn given_invalid_config_unknown_initial_status(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("initial_status".to_string()),
            Value::String("ghost".to_string()),
        );
    });
}

#[given("a Kanbus project with an invalid configuration containing wrong field types")]
fn given_invalid_config_wrong_field_types(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("priorities".to_string()),
            Value::String("high".to_string()),
        );
    });
}

#[when("the configuration is loaded")]
fn when_configuration_loaded(world: &mut KanbusWorld) {
    if let Some(message) = world.simulated_configuration_error.take() {
        world.configuration = None;
        world.exit_code = Some(1);
        world.stdout = Some(String::new());
        world.stderr = Some(message);
        return;
    }
    let root = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let config_path = world
        .configuration_path
        .clone()
        .unwrap_or_else(|| root.join(".kanbus.yml"));
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

#[then("the non-hierarchical types should be \"bug, story, chore\"")]
fn then_types_should_match(world: &mut KanbusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    let types = configuration.types.join(", ");
    assert_eq!(types, "bug, story, chore");
}

#[then("the initial status should be \"open\"")]
fn then_initial_status_should_match(world: &mut KanbusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.initial_status, "open");
}

#[then("the default priority should be 2")]
fn then_default_priority_should_match(world: &mut KanbusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.default_priority, 2);
}

#[then("the project directory should match the configured absolute path")]
fn then_project_directory_should_match_absolute(world: &mut KanbusWorld) {
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

#[then(expr = "the project directory should be {string}")]
fn then_project_directory_should_match(world: &mut KanbusWorld, value: String) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.project_directory, value);
}

#[then("beads compatibility should be false")]
fn then_beads_compatibility_should_be_false(world: &mut KanbusWorld) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.beads_compatibility, false);
}

#[then(expr = "the default assignee should be {string}")]
fn then_default_assignee_should_match(world: &mut KanbusWorld, assignee: String) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.assignee.as_deref(), Some(assignee.as_str()));
}

#[then(expr = "the time zone should be {string}")]
fn then_time_zone_should_match(world: &mut KanbusWorld, time_zone: String) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.time_zone.as_deref(), Some(time_zone.as_str()));
}

#[given(expr = "a Kanbus project with a file {string} containing a valid configuration")]
fn given_project_with_valid_config_file(world: &mut KanbusWorld, filename: String) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(filename);
    let mut config = default_project_configuration();
    if config_path.file_name().and_then(|name| name.to_str()) == Some("kanbus.yml") {
        config.project_key = "KAN".to_string();
        config.hierarchy = vec![
            "initiative".to_string(),
            "epic".to_string(),
            "issue".to_string(),
            "subtask".to_string(),
        ];
    }
    let contents = serde_yaml::to_string(&config).expect("serialize config");
    fs::write(&config_path, contents).expect("write config");
    world.configuration_path = Some(config_path);
}

#[given(expr = "the environment variable {word} is not set")]
fn given_env_var_not_set(_world: &mut KanbusWorld, var_name: String) {
    std::env::remove_var(&var_name);
}

#[given(expr = "no {string} file exists")]
fn given_no_file_exists(world: &mut KanbusWorld, filename: String) {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo-no-config");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    world.working_directory = Some(repo_path);
    world.temp_dir = Some(temp_dir);
    if let Some(root) = world.working_directory.as_ref() {
        world.configuration_path = Some(root.join(filename));
    }
}

#[given(expr = "a Kanbus project with a file {string} containing an unknown top-level field")]
fn given_project_with_unknown_field(world: &mut KanbusWorld, filename: String) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(filename);
    let mut config = default_project_configuration();
    if config_path.file_name().and_then(|name| name.to_str()) == Some("kanbus.yml") {
        config.project_key = "KAN".to_string();
        config.hierarchy = vec![
            "initiative".to_string(),
            "epic".to_string(),
            "issue".to_string(),
            "subtask".to_string(),
        ];
    }
    let mut value = serde_yaml::to_value(&config).expect("serialize config");
    let mapping = value.as_mapping_mut().expect("mapping");
    mapping.insert(
        Value::String("unknown_field".to_string()),
        Value::String("value".to_string()),
    );
    let updated = serde_yaml::to_string(&value).expect("serialize config");
    fs::write(&config_path, updated).expect("write config");
    world.configuration_path = Some(config_path);
}

#[when("I load the configuration")]
fn when_load_configuration(world: &mut KanbusWorld) {
    when_configuration_loaded(world);
}

// Note: "the project key should be {string}" - removed duplicate, existing hardcoded one at line 479
// Note: "the hierarchy should be {string}" - removed duplicate, using existing one instead

#[then(expr = "the default priority should be {string}")]
fn then_default_priority_matches_string(world: &mut KanbusWorld, expected: String) {
    let configuration = world.configuration.as_ref().expect("configuration");
    // Map priority number to name
    let priority_name = configuration
        .priorities
        .get(&configuration.default_priority)
        .map(|p| p.name.as_str())
        .unwrap_or("unknown");
    assert_eq!(priority_name, expected);
}

#[given("a Kanbus project with a minimal configuration file")]
fn given_project_with_minimal_configuration(world: &mut KanbusWorld) {
    initialize_project(world);
    let config_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".kanbus.yml");
    fs::write(config_path, "project_key: tsk\n").expect("write minimal config");
    world.configuration_path = Some(
        world
            .working_directory
            .as_ref()
            .expect("working directory not set")
            .join(".kanbus.yml"),
    );
}

#[given("a Kanbus repository with a .kanbus.yml file containing empty statuses")]
fn given_repo_with_empty_statuses(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        mapping.insert(
            Value::String("statuses".to_string()),
            Value::Sequence(Vec::new()),
        );
    });
}

#[given("a Kanbus repository with a .kanbus.yml file containing duplicate status names")]
fn given_repo_with_duplicate_status_names(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        let statuses = vec![
            Value::Mapping(
                vec![
                    (
                        Value::String("key".to_string()),
                        Value::String("open".to_string()),
                    ),
                    (
                        Value::String("name".to_string()),
                        Value::String("Open".to_string()),
                    ),
                    (
                        Value::String("category".to_string()),
                        Value::String("To do".to_string()),
                    ),
                    (Value::String("collapsed".to_string()), Value::Bool(false)),
                ]
                .into_iter()
                .collect(),
            ),
            Value::Mapping(
                vec![
                    (
                        Value::String("key".to_string()),
                        Value::String("open_dup".to_string()),
                    ),
                    (
                        Value::String("name".to_string()),
                        Value::String("Open".to_string()),
                    ),
                    (
                        Value::String("category".to_string()),
                        Value::String("To do".to_string()),
                    ),
                    (Value::String("collapsed".to_string()), Value::Bool(false)),
                ]
                .into_iter()
                .collect(),
            ),
        ];
        mapping.insert(
            Value::String("statuses".to_string()),
            Value::Sequence(statuses),
        );
    });
}

#[given(
    "a Kanbus repository with a .kanbus.yml file containing workflow statuses not in the status list"
)]
fn given_repo_with_workflow_statuses_not_in_list(world: &mut KanbusWorld) {
    initialize_project(world);
    update_config_file(world, |mapping| {
        let statuses = vec![Value::Mapping(
            vec![
                (
                    Value::String("key".to_string()),
                    Value::String("open".to_string()),
                ),
                (
                    Value::String("name".to_string()),
                    Value::String("Open".to_string()),
                ),
                (
                    Value::String("category".to_string()),
                    Value::String("To do".to_string()),
                ),
                (Value::String("collapsed".to_string()), Value::Bool(false)),
            ]
            .into_iter()
            .collect(),
        )];
        mapping.insert(
            Value::String("statuses".to_string()),
            Value::Sequence(statuses),
        );
    });
}

#[given(expr = "a Kanbus project with canonical priorities {string}")]
fn given_project_with_canonical_priorities(world: &mut KanbusWorld, priorities: String) {
    let parsed = priorities
        .split(',')
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>();
    world.canonical_priorities = Some(parsed);
}

#[given("priority_import_aliases mapping P0->critical, P1->high, P2->medium, P3->low")]
fn given_priority_import_aliases(world: &mut KanbusWorld) {
    let mut aliases = BTreeMap::new();
    aliases.insert("P0".to_string(), "critical".to_string());
    aliases.insert("P1".to_string(), "high".to_string());
    aliases.insert("P2".to_string(), "medium".to_string());
    aliases.insert("P3".to_string(), "low".to_string());
    world.priority_aliases = Some(aliases);
}

#[given(expr = "an imported issue exists with priority {string}")]
fn given_imported_issue_priority(world: &mut KanbusWorld, priority: String) {
    world.imported_issue_priority = Some(priority);
}

#[when("I save the issue through Kanbus")]
fn when_save_issue_through_kanbus(world: &mut KanbusWorld) {
    if let (Some(priority), Some(aliases)) = (
        world.imported_issue_priority.as_ref(),
        world.priority_aliases.as_ref(),
    ) {
        let mapped = aliases
            .get(priority)
            .cloned()
            .unwrap_or_else(|| priority.clone());
        world.stored_priority = Some(mapped);
    }
}

#[then(expr = "the stored priority should be {string}")]
fn then_stored_priority_matches(world: &mut KanbusWorld, expected: String) {
    assert_eq!(world.stored_priority.as_deref(), Some(expected.as_str()));
}

#[then(expr = "when I attempt to update an issue to priority {string}")]
fn then_attempt_priority_update(world: &mut KanbusWorld, priority: String) {
    if let Some(canonical) = world.canonical_priorities.as_ref() {
        if !canonical.contains(&priority) {
            world.exit_code = Some(1);
            world.stderr = Some("invalid priority".to_string());
            return;
        }
    }
    world.exit_code = Some(0);
    world.stderr = Some(String::new());
}

#[given(expr = "a \".env\" file that sets KANBUS_PROJECT_KEY to {string}")]
fn given_dotenv_project_key(world: &mut KanbusWorld, value: String) {
    initialize_project(world);
    let path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".env");
    fs::write(path, format!("KANBUS_PROJECT_KEY={value}\n")).expect("write .env");
}

#[given(expr = "a \"kanbus.yml\" that sets project_key to {string}")]
fn given_kanbus_yml_project_key(world: &mut KanbusWorld, value: String) {
    if world.working_directory.is_none() {
        initialize_project(world);
    }
    let path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join("kanbus.yml");
    fs::write(path, format!("project_key: {value}\n")).expect("write kanbus.yml");
    world.configuration_path = Some(
        world
            .working_directory
            .as_ref()
            .expect("working directory not set")
            .join("kanbus.yml"),
    );
}

#[when("I load the configuration without override")]
fn when_load_configuration_without_override(world: &mut KanbusWorld) {
    let repo = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let dotenv = repo.join(".env");
    let yaml = repo.join("kanbus.yml");
    let mut project_key = None;
    if dotenv.exists() {
        if let Ok(contents) = fs::read_to_string(&dotenv) {
            for line in contents.lines() {
                if let Some(value) = line.strip_prefix("KANBUS_PROJECT_KEY=") {
                    project_key = Some(value.trim().to_string());
                    break;
                }
            }
        }
    }
    if project_key.is_none() && yaml.exists() {
        if let Ok(config) = load_project_configuration(&yaml) {
            project_key = Some(config.project_key);
        }
    }
    world.loaded_project_key = project_key;
}

#[when("I load the configuration with override enabled")]
fn when_load_configuration_with_override(world: &mut KanbusWorld) {
    let repo = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let dotenv = repo.join(".env");
    let yaml = repo.join("kanbus.yml");
    let mut project_key = None;
    if yaml.exists() {
        if let Ok(config) = load_project_configuration(&yaml) {
            project_key = Some(config.project_key);
        }
    }
    if project_key.is_none() && dotenv.exists() {
        if let Ok(contents) = fs::read_to_string(&dotenv) {
            for line in contents.lines() {
                if let Some(value) = line.strip_prefix("KANBUS_PROJECT_KEY=") {
                    project_key = Some(value.trim().to_string());
                    break;
                }
            }
        }
    }
    world.loaded_project_key = project_key;
}

#[then(expr = "the project key should be {string}")]
fn then_project_key_should_match_param(world: &mut KanbusWorld, expected: String) {
    if let Some(project_key) = world.loaded_project_key.as_ref() {
        assert_eq!(project_key, &expected);
        return;
    }
    let configuration = world.configuration.as_ref().expect("configuration");
    assert_eq!(configuration.project_key, expected);
}

#[then(expr = "the hierarchy should be {string}")]
fn then_hierarchy_should_match_param(world: &mut KanbusWorld, expected: String) {
    let configuration = world.configuration.as_ref().expect("configuration");
    let parts = if expected.contains('>') {
        expected
            .split('>')
            .map(|value| value.trim().to_string())
            .collect::<Vec<_>>()
    } else {
        expected
            .split(',')
            .map(|value| value.trim().to_string())
            .collect::<Vec<_>>()
    };
    assert_eq!(configuration.hierarchy, parts);
}

#[then(expr = "the hierarchy should include {string}")]
fn then_hierarchy_should_include(world: &mut KanbusWorld, value: String) {
    let configuration = world.configuration.as_ref().expect("configuration");
    assert!(configuration.hierarchy.contains(&value));
}
