use std::collections::BTreeMap;
use std::fs;

use cucumber::given;

use taskulus::config::default_project_configuration;
use taskulus::console_snapshot::ConsoleProjectConfig;
use taskulus::file_io::load_project_directory;

use crate::step_definitions::initialization_steps::TaskulusWorld;

#[given("a Taskulus project with a console configuration file")]
fn given_console_configuration_file(world: &mut TaskulusWorld) {
    let root = world.working_directory.as_ref().expect("working directory");
    let project_dir = load_project_directory(root).expect("project dir");
    let default_config = default_project_configuration();
    let priorities: BTreeMap<u8, String> = default_config
        .priorities
        .iter()
        .map(|(key, value)| (*key, value.name.clone()))
        .collect();
    let console_config = ConsoleProjectConfig {
        prefix: default_config.project_key,
        hierarchy: default_config.hierarchy,
        types: default_config.types,
        workflows: default_config.workflows,
        initial_status: default_config.initial_status,
        priorities,
        default_priority: default_config.default_priority,
        beads_compatibility: default_config.beads_compatibility,
    };
    let payload = serde_yaml::to_string(&console_config).expect("serialize console config");
    let config_path = project_dir.join("config.yaml");
    fs::write(config_path, payload).expect("write console config");
}
