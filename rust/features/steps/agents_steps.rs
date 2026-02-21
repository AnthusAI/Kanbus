use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then};
use tempfile::TempDir;

use kanbus::agents_management::{kanbus_section_text, project_management_text};
use crate::step_definitions::initialization_steps::KanbusWorld;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn fixture_path(name: &str) -> PathBuf {
    repo_root()
        .join("specs")
        .join("fixtures")
        .join("agents_project")
        .join(name)
}

fn config_path() -> PathBuf {
    repo_root().join(".kanbus.yml")
}

fn copy_configuration(repo_path: &PathBuf) {
    let source = config_path();
    if source.exists() {
        fs::copy(source, repo_path.join(".kanbus.yml")).expect("copy configuration");
    }
}

fn setup_repo(world: &mut KanbusWorld) -> PathBuf {
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    copy_configuration(&repo_path);
    world.working_directory = Some(repo_path.clone());
    world.temp_dir = Some(temp_dir);
    repo_path
}

fn write_agents_fixture(world: &mut KanbusWorld, fixture_name: &str) {
    let repo_path = setup_repo(world);
    let content = fs::read_to_string(fixture_path(fixture_name)).expect("read fixture");
    fs::write(repo_path.join("AGENTS.md"), content).expect("write agents file");
}

fn read_agents(world: &KanbusWorld) -> String {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    fs::read_to_string(repo_path.join("AGENTS.md")).expect("read AGENTS.md")
}

fn extract_kanbus_section(content: &str) -> String {
    let lines: Vec<&str> = content.lines().collect();
    let mut start: Option<usize> = None;
    let mut end = lines.len();
    for (index, line) in lines.iter().enumerate() {
        let trimmed = line.trim_start();
        if !trimmed.starts_with('#') {
            continue;
        }
        if trimmed.to_lowercase().contains("kanbus") {
            start = Some(index);
            let level = trimmed.chars().take_while(|ch| *ch == '#').count();
            for next_index in (index + 1)..lines.len() {
                let next_trimmed = lines[next_index].trim_start();
                if !next_trimmed.starts_with('#') {
                    continue;
                }
                let next_level = next_trimmed.chars().take_while(|ch| *ch == '#').count();
                if next_level <= level {
                    end = next_index;
                    break;
                }
            }
            break;
        }
    }
    let start = start.expect("Kanbus section missing");
    lines[start..end].join("\n").trim().to_string()
}

#[given("a Kanbus repository without AGENTS.md")]
fn given_repo_without_agents(world: &mut KanbusWorld) {
    setup_repo(world);
}

#[given("a Kanbus repository with AGENTS.md without a Kanbus section")]
fn given_repo_agents_without_kanbus(world: &mut KanbusWorld) {
    write_agents_fixture(world, "agents_no_kanbus.md");
}

#[given("a Kanbus repository with AGENTS.md containing a Kanbus section")]
fn given_repo_agents_with_kanbus(world: &mut KanbusWorld) {
    write_agents_fixture(world, "agents_with_kanbus.md");
}


#[then("AGENTS.md should exist")]
fn then_agents_exists(world: &mut KanbusWorld) {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    assert!(repo_path.join("AGENTS.md").exists());
}

#[then("AGENTS.md should contain the Kanbus section")]
fn then_agents_contains_kanbus(world: &mut KanbusWorld) {
    let content = read_agents(world);
    let section = extract_kanbus_section(&content);
    let expected = kanbus_section_text();
    assert_eq!(section, expected.trim());
}

#[then("the Kanbus section should appear after the H1 heading")]
fn then_kanbus_after_h1(world: &mut KanbusWorld) {
    let content = read_agents(world);
    let lines: Vec<&str> = content.lines().collect();
    let h1_index = lines
        .iter()
        .position(|line| line.trim_start().starts_with("# "))
        .expect("missing h1");
    let kanbus_index = lines
        .iter()
        .position(|line| line.to_lowercase().contains("kanbus"))
        .expect("missing kanbus section");
    assert!(kanbus_index > h1_index);
    for line in &lines[(h1_index + 1)..kanbus_index] {
        if line.trim_start().starts_with("## ") {
            panic!("Kanbus section is not the first H2");
        }
    }
}

#[then("AGENTS.md should be unchanged")]
fn then_agents_unchanged(world: &mut KanbusWorld) {
    let content = read_agents(world);
    let expected = fs::read_to_string(fixture_path("agents_with_kanbus.md")).expect("fixture");
    assert_eq!(content, expected);
}

#[then("CONTRIBUTING_AGENT.md should exist")]
fn then_agent_instructions_exists(world: &mut KanbusWorld) {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let instructions_path = repo_path.join("CONTRIBUTING_AGENT.md");
    assert!(instructions_path.exists());
    let content = fs::read_to_string(instructions_path).expect("read instructions");
    let expected = project_management_text(repo_path).expect("instructions text");
    assert_eq!(content.trim(), expected.trim());
}

#[then(expr = "CONTRIBUTING_AGENT.md should contain {string}")]
fn then_project_management_contains_text(world: &mut KanbusWorld, text: String) {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let content =
        fs::read_to_string(repo_path.join("CONTRIBUTING_AGENT.md")).expect("read instructions");
    let normalized = text.replace("\\\"", "\"");
    assert!(content.contains(&normalized));
}
