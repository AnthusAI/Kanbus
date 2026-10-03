use std::fs;
use std::path::{Path, PathBuf};

use chrono::{TimeZone, Utc};
use cucumber::{given, then};
use serde_json::Value;

use crate::step_definitions::initialization_steps::KanbusWorld;
use kanbus::ids::issue_identifier_matches;
use kanbus::models::IssueData;

fn short_id_fixtures() -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("repo root")
        .join("specs")
        .join("fixtures")
        .join("short_id_fixtures.json");
    let contents = fs::read_to_string(path).expect("read short id fixtures");
    serde_json::from_str(&contents).expect("parse short id fixtures")
}

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    kanbus::file_io::load_project_directory(cwd).expect("project dir")
}

fn write_issue_file(project_dir: &Path, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn build_issue_with_title(identifier: &str, title: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: "".to_string(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        agent: None,
        right_now_summary: None,
        right_now_updated_at: None,
        custom: std::collections::BTreeMap::new(),
    }
}

#[given(expr = "a project issue {string} exists with title {string}")]
fn given_project_issue_with_title(world: &mut KanbusWorld, identifier: String, title: String) {
    let project_dir = load_project_dir(world);
    write_issue_file(&project_dir, &build_issue_with_title(&identifier, &title));
}

#[given(expr = "the Kanbus configuration sets short_id_length to {int}")]
fn given_configuration_short_id_length(world: &mut KanbusWorld, length: usize) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let config_path = cwd.join(".kanbus.yml");
    let mut configuration: kanbus::models::ProjectConfiguration =
        serde_yaml::from_str(&fs::read_to_string(&config_path).expect("read config"))
            .expect("parse config");
    configuration.short_id_length = Some(length);
    let contents = serde_yaml::to_string(&configuration).expect("serialize config");
    fs::write(&config_path, contents).expect("write config");
}

#[given("project issues exist from the short ID uniqueness fixture")]
fn given_fixture_issues_exist(world: &mut KanbusWorld) {
    let fixtures = short_id_fixtures();
    let project_dir = load_project_dir(world);
    for id in fixtures["uniqueness_universe"]
        .as_array()
        .expect("universe array")
    {
        let identifier = id.as_str().expect("identifier string");
        write_issue_file(
            &project_dir,
            &build_issue_with_title(identifier, "Fixture issue"),
        );
    }
}

#[then(expr = "the list should show short ID {string} for issue {string}")]
fn then_list_shows_short_id(world: &mut KanbusWorld, short_id: String, identifier: String) {
    let stdout = world.stdout.as_deref().expect("list output");
    let ansi_free = strip_ansi(stdout);
    assert!(
        ansi_free.contains(&short_id),
        "list output does not contain {short_id} for {identifier}:\n{ansi_free}"
    );
    assert!(
        !ansi_free.contains(&identifier),
        "list output unexpectedly contains the full id {identifier}"
    );
}

fn strip_ansi(text: &str) -> String {
    let ansi = regex::Regex::new(r"\x1b\[[0-9;]*m").expect("ansi regex");
    ansi.replace_all(text, "").to_string()
}

fn displayed_id_fields(ansi_free: &str) -> Vec<String> {
    ansi_free
        .lines()
        .filter_map(|line| line.split_whitespace().nth(1))
        .filter(|id_field| !id_field.is_empty() && *id_field != "-")
        .map(str::to_string)
        .collect()
}

#[then("no two displayed list IDs should collide")]
fn then_no_displayed_id_collides(world: &mut KanbusWorld) {
    let stdout = world.stdout.as_deref().expect("list output");
    let ansi_free = strip_ansi(stdout);
    let mut seen = std::collections::HashSet::new();
    for id_field in displayed_id_fields(&ansi_free) {
        assert!(
            seen.insert(id_field.clone()),
            "displayed id {id_field} appears more than once"
        );
    }
}

#[then("no displayed short ID should be ambiguous in the visible set")]
fn then_no_displayed_id_ambiguous(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let mut full_ids = Vec::new();
    for entry in fs::read_dir(project_dir.join("issues")).expect("read issues dir") {
        let entry = entry.expect("entry");
        if entry.path().extension().map_or(true, |e| e != "json") {
            continue;
        }
        if let Some(stem) = entry.path().file_stem().and_then(|s| s.to_str()) {
            full_ids.push(stem.to_string());
        }
    }
    let stdout = world.stdout.as_deref().expect("list output");
    let ansi_free = strip_ansi(stdout);
    for id_field in displayed_id_fields(&ansi_free) {
        let matches = full_ids
            .iter()
            .filter(|full| issue_identifier_matches(&id_field, full))
            .count();
        assert_eq!(
            matches, 1,
            "displayed id {id_field} matches {matches} issues"
        );
    }
}

#[then(expr = "displayed list IDs should use hash width {int}")]
fn then_displayed_ids_use_hash_width(world: &mut KanbusWorld, width: usize) {
    let stdout = world.stdout.as_deref().expect("list output");
    let ansi_free = strip_ansi(stdout);
    let mut checked = 0;
    for line in ansi_free.lines() {
        let id_field = line.split_whitespace().nth(1).unwrap_or_default();
        if id_field.is_empty() || id_field == "-" {
            continue;
        }
        let hash_part = id_field.rsplit('-').next().unwrap_or(id_field);
        assert_eq!(
            hash_part.chars().count(),
            width,
            "displayed id {id_field} does not use hash width {width}"
        );
        checked += 1;
    }
    assert!(checked > 0, "no displayed list IDs found in output");
}

#[then(expr = "the ambiguity JSON should list full IDs {string}")]
fn then_ambiguity_json_lists_ids(world: &mut KanbusWorld, expected: String) {
    let stdout = world.stdout.as_deref().expect("ambiguity output");
    let payload: Value = serde_json::from_str(stdout).expect("parse ambiguity json");
    assert_eq!(payload["error"], "ambiguous_identifier");
    let expected_ids: Vec<&str> = expected.split(", ").collect();
    let actual_ids: Vec<String> = payload["matches"]
        .as_array()
        .expect("matches array")
        .iter()
        .filter_map(|entry| entry["id"].as_str().map(str::to_string))
        .collect();
    assert_eq!(actual_ids, expected_ids);
}
