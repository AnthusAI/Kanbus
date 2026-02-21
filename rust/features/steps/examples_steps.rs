use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then, when};

use kanbus::agents_management::{kanbus_section_text, project_management_text};

use crate::step_definitions::initialization_steps::KanbusWorld;

const README_STUB: &str = "This is a sample project that uses Kanbus.";

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn example_dir(name: &str) -> PathBuf {
    let slug = name.trim().to_lowercase().replace(' ', "-");
    repo_root().join("examples").join(slug)
}

fn build_kbs_binary() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let target_dir = std::env::var("CARGO_TARGET_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| manifest_dir.join("target"));
    let binary_path = target_dir.join("debug").join("kbs");
    if binary_path.exists() {
        return binary_path;
    }

    let status = Command::new("cargo")
        .args(["build", "--bin", "kbs"])
        .current_dir(&manifest_dir)
        .env("CARGO_TARGET_DIR", &target_dir)
        .status()
        .expect("build kbs binary");
    if !status.success() {
        panic!("failed to build kbs binary");
    }
    binary_path
}

#[given(expr = "the {string} example project does not exist")]
fn given_example_missing(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    if path.exists() {
        fs::remove_dir_all(&path).expect("remove example dir");
    }
}

#[when(expr = "I create the {string} example project")]
fn when_create_example_project(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    fs::create_dir_all(&path).expect("create example dir");
    let status = Command::new("git")
        .args(["init"])
        .current_dir(&path)
        .status()
        .expect("git init failed");
    if !status.success() {
        panic!("git init failed");
    }
}

#[when(expr = "I run \"kanbus init\" in the {string} example project")]
fn when_run_kanbus_init_in_example(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    let binary_path = build_kbs_binary();
    let status = Command::new(binary_path)
        .args(["init"])
        .current_dir(&path)
        .env("KANBUS_NO_DAEMON", "1")
        .status()
        .expect("kanbus init failed");
    if !status.success() {
        panic!("kanbus init failed");
    }
}

#[when(expr = "I run \"kanbus setup agents\" in the {string} example project")]
fn when_run_kanbus_setup_agents_in_example(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    let binary_path = build_kbs_binary();
    let status = Command::new(binary_path)
        .args(["setup", "agents"])
        .current_dir(&path)
        .env("KANBUS_NO_DAEMON", "1")
        .status()
        .expect("kanbus setup agents failed");
    if !status.success() {
        panic!("kanbus setup agents failed");
    }
}

#[when(expr = "I add a README stub to the {string} example project")]
fn when_add_readme_stub(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    let readme = path.join("README.md");
    fs::write(readme, format!("{README_STUB}\n")).expect("write README");
}

#[then(expr = "the {string} example project should contain a README stub")]
fn then_example_contains_readme(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    let readme = path.join("README.md");
    assert!(readme.exists());
    let content = fs::read_to_string(readme).expect("read README");
    assert_eq!(content.trim(), README_STUB);
}

#[then(expr = "the {string} example project should contain .kanbus.yml")]
fn then_example_contains_config(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    assert!(path.join(".kanbus.yml").exists());
}

#[then(expr = "the {string} example project should contain the project directory")]
fn then_example_contains_project_dir(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    assert!(path.join("project").exists());
}

#[then(expr = "the {string} example project should contain AGENTS.md with Kanbus instructions")]
fn then_example_contains_agents(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    let agents = path.join("AGENTS.md");
    assert!(agents.exists());
    let content = fs::read_to_string(agents).expect("read AGENTS.md");
    assert!(content.contains(kanbus_section_text().trim()));
}

#[then(expr = "the {string} example project should contain CONTRIBUTING_AGENT.md")]
fn then_example_contains_instructions(_world: &mut KanbusWorld, name: String) {
    let path = example_dir(&name);
    let instructions = path.join("CONTRIBUTING_AGENT.md");
    assert!(instructions.exists());
    let content = fs::read_to_string(instructions).expect("read instructions");
    let expected = project_management_text(&path).expect("instructions text");
    assert_eq!(content.trim(), expected.trim());
}
