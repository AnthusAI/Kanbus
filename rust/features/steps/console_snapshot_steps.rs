use std::fs;

use cucumber::{given, when};
use serde_json;

use kanbus::console_snapshot::build_console_snapshot;
use kanbus::file_io::load_project_directory;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given("the Kanbus configuration file is missing")]
fn given_kanbus_configuration_missing(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("working directory");
    let project_dir = load_project_directory(root).expect("project dir");
    let config_path = project_dir
        .parent()
        .expect("project root")
        .join(".kanbus.yml");
    if config_path.exists() {
        if config_path.is_dir() {
            fs::remove_dir_all(&config_path).expect("remove config dir");
        } else {
            fs::remove_file(&config_path).expect("remove config file");
        }
    }
}

#[given("a Kanbus configuration file that is not a mapping")]
fn given_kanbus_configuration_not_mapping(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("working directory");
    let project_dir = load_project_directory(root).expect("project dir");
    let config_path = project_dir
        .parent()
        .expect("project root")
        .join(".kanbus.yml");
    fs::write(config_path, "- item\n- other\n").expect("write non-mapping config");
}

#[given("the issues directory is a file")]
fn given_issues_directory_is_file(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("working directory");
    let project_dir = load_project_directory(root).expect("project dir");
    let issues_path = project_dir.join("issues");
    if issues_path.exists() {
        if issues_path.is_dir() {
            fs::remove_dir_all(&issues_path).expect("remove issues dir");
        } else {
            fs::remove_file(&issues_path).expect("remove issues file");
        }
    }
    fs::write(issues_path, "not a directory").expect("write issues file");
}

#[given("the issues directory is unreadable")]
fn given_issues_directory_is_unreadable(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("working directory");
    let project_dir = load_project_directory(root).expect("project dir");
    let issues_dir = project_dir.join("issues");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let metadata = fs::metadata(&issues_dir).expect("issues dir metadata");
        let original_mode = metadata.permissions().mode();
        let mut permissions = metadata.permissions();
        permissions.set_mode(0);
        fs::set_permissions(&issues_dir, permissions).expect("make issues dir unreadable");
        world.unreadable_path = Some(issues_dir);
        world.unreadable_mode = Some(original_mode);
    }
}

#[when("I build a console snapshot directly")]
fn when_build_console_snapshot_directly(world: &mut KanbusWorld) {
    let root = world.working_directory.as_ref().expect("working directory");
    match build_console_snapshot(root) {
        Ok(snapshot) => {
            let payload = serde_json::to_string_pretty(&snapshot).expect("serialize snapshot");
            world.exit_code = Some(0);
            world.stdout = Some(payload);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}
