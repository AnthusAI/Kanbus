use std::fs;
use std::path::PathBuf;
use std::process::Command;

use cucumber::{given, then, when};
use tempfile::TempDir;

use crate::step_definitions::initialization_steps::KanbusWorld;
use kanbus::agents_management::{kanbus_section_text, project_management_text};

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

fn read_project_management_file(world: &KanbusWorld) -> String {
    let repo_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    fs::read_to_string(repo_path.join("CONTRIBUTING_AGENT.md")).expect("read instructions")
}

const PROJECT_BUNDLE_STEP_PREFIX: &str = "path:";

fn methodology_selection_from_step_text(selection_text: &str) -> serde_yaml::Value {
    match selection_text.strip_prefix(PROJECT_BUNDLE_STEP_PREFIX) {
        Some(bundle_relative_path) => {
            let mut bundle_reference = serde_yaml::Mapping::new();
            bundle_reference.insert(
                serde_yaml::Value::from("path"),
                serde_yaml::Value::from(bundle_relative_path),
            );
            serde_yaml::Value::Mapping(bundle_reference)
        }
        None => serde_yaml::Value::from(selection_text),
    }
}

fn write_methodology_bundle_document(
    world: &KanbusWorld,
    bundle_relative_path: &str,
    document_text: &str,
) {
    let bundle_directory = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(bundle_relative_path);
    fs::create_dir_all(&bundle_directory).expect("create bundle directory");
    fs::write(bundle_directory.join("METHODOLOGY.md"), document_text)
        .expect("write methodology document");
}

#[given(
    expr = "the repository has a methodology bundle at {string} named {string} with heading {string}"
)]
fn given_repository_has_methodology_bundle(
    world: &mut KanbusWorld,
    bundle_relative_path: String,
    methodology_name: String,
    heading: String,
) {
    write_methodology_bundle_document(
        world,
        &bundle_relative_path,
        &format!(
            "---\nname: {methodology_name}\ntitle: {heading}\n---\n## {heading}\n\nProject key: {{{{ project_key }}}}.\n"
        ),
    );
}

#[given(expr = "the repository has a methodology bundle at {string} without frontmatter")]
fn given_repository_has_methodology_bundle_without_frontmatter(
    world: &mut KanbusWorld,
    bundle_relative_path: String,
) {
    write_methodology_bundle_document(world, &bundle_relative_path, "## Plain Guidance\n");
}

fn methodology_tool_frontmatter(
    methodology_name: &str,
    tool_declarations: &[(&str, &str, &str)],
) -> String {
    let tool_entries: Vec<serde_yaml::Value> = tool_declarations
        .iter()
        .map(|(tool_name, command, purpose)| {
            let mut tool_entry = serde_yaml::Mapping::new();
            tool_entry.insert("name".into(), (*tool_name).into());
            tool_entry.insert("command".into(), (*command).into());
            tool_entry.insert("purpose".into(), (*purpose).into());
            serde_yaml::Value::Mapping(tool_entry)
        })
        .collect();
    let mut frontmatter = serde_yaml::Mapping::new();
    frontmatter.insert("name".into(), methodology_name.into());
    frontmatter.insert(
        "title".into(),
        format!("{methodology_name} methodology").into(),
    );
    frontmatter.insert("tools".into(), serde_yaml::Value::Sequence(tool_entries));
    format!(
        "---\n{}---\n## Tool Guidance\n",
        serde_yaml::to_string(&frontmatter).expect("serialize frontmatter")
    )
}

fn write_methodology_tool_script(
    world: &KanbusWorld,
    bundle_relative_path: &str,
    script_text: &str,
) {
    use std::os::unix::fs::PermissionsExt;
    let tool_script = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(bundle_relative_path)
        .join("tools")
        .join("run-tool");
    fs::create_dir_all(tool_script.parent().expect("tool directory")).expect("create tools");
    fs::write(&tool_script, format!("#!/bin/sh\n{script_text}\n")).expect("write tool script");
    fs::set_permissions(&tool_script, fs::Permissions::from_mode(0o755))
        .expect("make tool executable");
}

#[given(
    expr = "the repository has a methodology bundle at {string} named {string} with a tool {string} that prints {string}"
)]
fn given_repository_has_methodology_bundle_with_tool(
    world: &mut KanbusWorld,
    bundle_relative_path: String,
    methodology_name: String,
    tool_name: String,
    printed_text: String,
) {
    write_methodology_bundle_document(
        world,
        &bundle_relative_path,
        &methodology_tool_frontmatter(
            &methodology_name,
            &[(&tool_name, "tools/run-tool", "Report the demo output")],
        ),
    );
    write_methodology_tool_script(
        world,
        &bundle_relative_path,
        &format!("echo \"{printed_text} $*\""),
    );
}

#[given(
    expr = "the repository has a methodology bundle at {string} named {string} with a failing tool {string}"
)]
fn given_repository_has_methodology_bundle_with_failing_tool(
    world: &mut KanbusWorld,
    bundle_relative_path: String,
    methodology_name: String,
    tool_name: String,
) {
    write_methodology_bundle_document(
        world,
        &bundle_relative_path,
        &methodology_tool_frontmatter(
            &methodology_name,
            &[(&tool_name, "tools/run-tool", "Always fails")],
        ),
    );
    write_methodology_tool_script(
        world,
        &bundle_relative_path,
        "echo \"tool failed loudly\"\nexit 3",
    );
}

#[given(
    expr = "the repository has a methodology bundle at {string} declaring a tool {string} with command {string}"
)]
fn given_repository_has_methodology_bundle_declaring_tool_command(
    world: &mut KanbusWorld,
    bundle_relative_path: String,
    tool_name: String,
    command: String,
) {
    let methodology_name = PathBuf::from(&bundle_relative_path)
        .file_name()
        .expect("bundle directory name")
        .to_string_lossy()
        .to_string();
    write_methodology_bundle_document(
        world,
        &bundle_relative_path,
        &methodology_tool_frontmatter(
            &methodology_name,
            &[(&tool_name, &command, "Declared only")],
        ),
    );
}

#[given(
    expr = "the repository has a methodology bundle at {string} declaring the tool {string} twice"
)]
fn given_repository_has_methodology_bundle_declaring_tool_twice(
    world: &mut KanbusWorld,
    bundle_relative_path: String,
    tool_name: String,
) {
    let methodology_name = PathBuf::from(&bundle_relative_path)
        .file_name()
        .expect("bundle directory name")
        .to_string_lossy()
        .to_string();
    write_methodology_bundle_document(
        world,
        &bundle_relative_path,
        &methodology_tool_frontmatter(
            &methodology_name,
            &[
                (&tool_name, "tools/run-tool", "Declared twice"),
                (&tool_name, "tools/run-tool", "Declared twice"),
            ],
        ),
    );
}

#[given(expr = "the Kanbus configuration selects methodologies {string}")]
#[when(expr = "the Kanbus configuration selects methodologies {string}")]
fn given_configuration_selects_methodologies(world: &mut KanbusWorld, methodology_list: String) {
    let selected_methodologies: Vec<serde_yaml::Value> = methodology_list
        .split(',')
        .map(str::trim)
        .filter(|name| !name.is_empty())
        .map(methodology_selection_from_step_text)
        .collect();
    let configuration_path = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join(".kanbus.yml");
    let configuration_text = fs::read_to_string(&configuration_path).expect("read configuration");
    let mut configuration_document: serde_yaml::Mapping =
        serde_yaml::from_str(&configuration_text).expect("parse configuration");
    configuration_document.insert(
        serde_yaml::Value::from("methodologies"),
        serde_yaml::Value::Sequence(selected_methodologies),
    );
    fs::write(
        &configuration_path,
        serde_yaml::to_string(&configuration_document).expect("serialize configuration"),
    )
    .expect("write configuration");
}

#[given("the Kanbus configuration selects no methodologies")]
fn given_configuration_selects_no_methodologies(world: &mut KanbusWorld) {
    given_configuration_selects_methodologies(world, String::new());
}

#[then(expr = "CONTRIBUTING_AGENT.md should not contain {string}")]
fn then_project_management_does_not_contain_text(world: &mut KanbusWorld, text: String) {
    assert!(!read_project_management_file(world).contains(&text));
}

#[then(expr = "CONTRIBUTING_AGENT.md should show {string} before {string}")]
fn then_project_management_orders_text(
    world: &mut KanbusWorld,
    earlier_text: String,
    later_text: String,
) {
    let content = read_project_management_file(world);
    let earlier_index = content.find(&earlier_text).expect("earlier text present");
    let later_index = content.find(&later_text).expect("later text present");
    assert!(earlier_index < later_index);
}
