use std::fs;

use cucumber::gherkin::Step;
use cucumber::{given, then};

use kanbus::config_loader::CONGREGATION_ENV_FILENAME;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn congregation_home_path(world: &KanbusWorld) -> std::path::PathBuf {
    let root = world.working_directory.as_ref().expect("working directory");
    root.join(".test-congregation-home")
}

fn congregation_env_path(world: &KanbusWorld) -> std::path::PathBuf {
    congregation_home_path(world).join(CONGREGATION_ENV_FILENAME)
}

#[given("the congregation env file is redirected to a temporary home")]
fn given_congregation_env_redirected(world: &mut KanbusWorld) {
    let congregation_home = congregation_home_path(world);
    fs::create_dir_all(&congregation_home).expect("create congregation home");
    world.environment_overrides.insert(
        "HOME".to_string(),
        congregation_home.to_string_lossy().to_string(),
    );
}

#[given(expr = "{word} is absent from the process environment")]
fn given_env_var_absent(world: &mut KanbusWorld, variable: String) {
    world.environment_overrides.remove(&variable);
    std::env::remove_var(&variable);
}

#[given("the congregation env file contains:")]
fn given_congregation_env_contains(world: &mut KanbusWorld, step: &Step) {
    let docstring = step
        .docstring()
        .expect("docstring for congregation env file contents");
    let congregation_home = congregation_home_path(world);
    fs::create_dir_all(&congregation_home).expect("create congregation home");
    let mut contents = docstring.trim_end_matches('\n').to_string();
    contents.push('\n');
    fs::write(congregation_env_path(world), contents).expect("write congregation env file");
}

#[then(expr = "the congregation env file should contain {string}")]
fn then_congregation_env_should_contain(world: &mut KanbusWorld, expected: String) {
    let path = congregation_env_path(world);
    let contents = fs::read_to_string(&path)
        .unwrap_or_else(|error| panic!("read congregation env file {path:?}: {error}"));
    assert!(
        contents.contains(&expected),
        "expected congregation env file to contain {expected:?}, got: {contents:?}"
    );
}

#[then(expr = "the congregation env file should not contain {string}")]
fn then_congregation_env_should_not_contain(world: &mut KanbusWorld, unexpected: String) {
    let path = congregation_env_path(world);
    let contents = fs::read_to_string(&path)
        .unwrap_or_else(|error| panic!("read congregation env file {path:?}: {error}"));
    assert!(
        !contents.contains(&unexpected),
        "expected congregation env file to not contain {unexpected:?}, got: {contents:?}"
    );
}

#[then("the congregation env file should have mode 600")]
fn then_congregation_env_should_have_mode_600(world: &mut KanbusWorld) {
    let path = congregation_env_path(world);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let metadata = fs::metadata(&path)
            .unwrap_or_else(|error| panic!("stat congregation env file {path:?}: {error}"));
        let mode = metadata.permissions().mode() & 0o777;
        assert_eq!(mode, 0o600, "expected mode 600, got {mode:o}");
    }
    #[cfg(not(unix))]
    {
        let _ = path;
    }
}
