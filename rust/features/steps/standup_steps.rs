use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use chrono::{Duration, TimeZone, Utc};
use cucumber::{given, then};
use regex::Regex;
use serde_json::Value;
use serde_yaml::{Mapping, Value as YamlValue};

use kanbus::config::default_project_configuration;
use kanbus::config_loader::load_project_configuration;
use kanbus::file_io::get_configuration_path;
use kanbus::file_io::load_project_directory;
use kanbus::models::IssueData;
use kanbus::right_now_command::{
    select_right_now_issues_for_command, RightNowCommandOptions, RightNowOutputFormat,
};
use kanbus::standup::{
    extract_section_text, report_uses_first_person_voice, report_uses_third_person_executive_voice,
};
use kanbus::standup_command::{select_standup_fact_feed, StandupCommandOptions};
use kanbus::standup_window::{resolve_standup_report_time, resolve_standup_timezone};

use crate::step_definitions::initialization_steps::KanbusWorld;
use crate::step_definitions::query_steps::resolve_issue_project_directory;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn read_issue_file(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn strip_ansi(text: &str) -> String {
    static ANSI_RE: OnceLock<Regex> = OnceLock::new();
    let regex = ANSI_RE.get_or_init(|| Regex::new("\x1b\\[[0-9;]*m").expect("regex"));
    regex.replace_all(text, "").to_string()
}

fn stdout_text(world: &KanbusWorld) -> String {
    strip_ansi(world.stdout.as_ref().expect("stdout"))
}

fn parse_standup_json(world: &KanbusWorld) -> Value {
    serde_json::from_str(&stdout_text(world)).expect("parse standup json")
}

fn standup_options_from_last_command(world: &KanbusWorld) -> StandupCommandOptions {
    let command = world.last_command.as_deref().unwrap_or("");
    let mut issue_ids = Vec::new();
    let mut profile = None;
    let mut recursive = true;
    let tokens: Vec<&str> = command.split_whitespace().collect();
    let mut index = 0;
    while index < tokens.len() {
        let token = tokens[index];
        if token == "kanbus" && index + 1 < tokens.len() && tokens[index + 1] == "standup" {
            index += 2;
            continue;
        }
        if token == "--profile" && index + 1 < tokens.len() {
            profile = Some(tokens[index + 1].to_string());
            index += 2;
            continue;
        }
        if token == "--no-recursive" {
            recursive = false;
            index += 1;
            continue;
        }
        if token == "--rollup" && index + 1 < tokens.len() {
            index += 2;
            continue;
        }
        if token == "--skip-weekends" || token == "--no-skip-weekends" {
            index += 1;
            continue;
        }
        if (token == "--window" || token == "--lookback" || token == "--profile")
            && index + 1 < tokens.len()
        {
            index += 2;
            continue;
        }
        if token.starts_with("--") {
            index += 2;
            continue;
        }
        issue_ids.push(token.to_string());
        index += 1;
    }
    StandupCommandOptions {
        issue_ids,
        profile,
        as_json: false,
        recursive,
        window: None,
        lookback: None,
        skip_weekends: None,
        rollup: None,
    }
}

fn repository_root(world: &KanbusWorld) -> PathBuf {
    world.working_directory.as_ref().expect("cwd").to_path_buf()
}

fn current_standup_fact_feed(world: &KanbusWorld) -> Vec<String> {
    let root = repository_root(world);
    let options = standup_options_from_last_command(world);
    let issues = select_standup_fact_feed(&root, &options).expect("select standup fact feed");
    issues
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect()
}

fn expected_default_fact_feed(world: &KanbusWorld) -> Vec<String> {
    let root = repository_root(world);
    let options = StandupCommandOptions::default();
    let issues = select_standup_fact_feed(&root, &options).expect("select default fact feed");
    issues
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect()
}

fn kanbus_now_fact_feed(world: &KanbusWorld, status_filter: &str) -> Vec<String> {
    let root = repository_root(world);
    let options = RightNowCommandOptions {
        limit: None,
        tree: false,
        expanded: false,
        collapsed: false,
        raw: false,
        output_format: RightNowOutputFormat::Yaml,
        show_all: false,
        recursive: true,
        issue_ids: Vec::new(),
        status: Some(status_filter.to_string()),
        purge: false,
    };
    let issues =
        select_right_now_issues_for_command(&root, &options).expect("select right now issues");
    issues
        .iter()
        .map(|issue| issue.identifier.clone())
        .collect()
}

fn store_standup_json_profile(world: &mut KanbusWorld) {
    let payload = parse_standup_json(world);
    let profile = payload
        .get("profile")
        .and_then(Value::as_str)
        .expect("standup profile");
    if world.standup_json_by_profile.is_none() {
        world.standup_json_by_profile = Some(BTreeMap::new());
    }
    world
        .standup_json_by_profile
        .as_mut()
        .expect("standup json profiles")
        .insert(profile.to_string(), payload);
}

fn assert_standup_section_mentions(world: &mut KanbusWorld, section_name: &str, text: &str) {
    let stdout = stdout_text(world);
    if stdout.trim().starts_with('{') {
        let payload = parse_standup_json(world);
        let sections = payload
            .get("sections")
            .and_then(Value::as_array)
            .expect("sections array");
        let section = sections
            .iter()
            .find(|item| item.get("name") == Some(&Value::String(section_name.to_string())))
            .expect("section");
        let joined = section
            .get("bullets")
            .and_then(Value::as_array)
            .map(|bullets| {
                bullets
                    .iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join("\n")
            })
            .unwrap_or_default();
        assert!(joined.contains(text));
        return;
    }
    let section_text = extract_section_text(&stdout, section_name);
    assert!(section_text.contains(text));
}

fn assert_standup_section_does_not_mention(
    world: &mut KanbusWorld,
    section_name: &str,
    text: &str,
) {
    let stdout = stdout_text(world);
    if stdout.trim().starts_with('{') {
        let payload = parse_standup_json(world);
        let sections = payload
            .get("sections")
            .and_then(Value::as_array)
            .expect("sections array");
        let section = sections
            .iter()
            .find(|item| item.get("name") == Some(&Value::String(section_name.to_string())))
            .expect("section");
        let joined = section
            .get("bullets")
            .and_then(Value::as_array)
            .map(|bullets| {
                bullets
                    .iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join("\n")
            })
            .unwrap_or_default();
        assert!(!joined.contains(text));
        return;
    }
    let section_text = extract_section_text(&stdout, section_name);
    assert!(!section_text.contains(text));
}

#[given(expr = "standup lookback hours is {int}")]
fn given_standup_lookback_hours(world: &mut KanbusWorld, hours: u32) {
    let root = world.working_directory.as_ref().expect("cwd");
    let config_path = root.join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut mapping: Mapping = serde_yaml::from_str(&contents).expect("parse config");
    let mut standup_block = mapping
        .get(&YamlValue::String("standup".to_string()))
        .and_then(YamlValue::as_mapping)
        .cloned()
        .unwrap_or_else(|| {
            let defaults = default_project_configuration();
            serde_yaml::to_value(defaults.standup)
                .expect("serialize defaults")
                .as_mapping()
                .cloned()
                .expect("standup mapping")
        });
    standup_block.insert(
        YamlValue::String("lookback".to_string()),
        YamlValue::String(format!("{hours}h")),
    );
    mapping.insert(
        YamlValue::String("standup".to_string()),
        YamlValue::Mapping(standup_block),
    );
    let yaml = serde_yaml::to_string(&mapping).expect("serialize config");
    fs::write(config_path, yaml).expect("write config");
}

fn previous_calendar_day_timestamp(root: &Path) -> chrono::DateTime<Utc> {
    let configuration_path = get_configuration_path(root).expect("config path");
    let configuration = load_project_configuration(&configuration_path).expect("load config");
    let timezone = resolve_standup_timezone(&configuration);
    let report_time = resolve_standup_report_time().expect("report time");
    let report_local = report_time.with_timezone(&timezone);
    let previous_day = report_local.date_naive() - Duration::days(1);
    timezone
        .from_local_datetime(
            &previous_day
                .and_hms_opt(16, 0, 0)
                .expect("previous calendar day time"),
        )
        .single()
        .map(|timestamp| timestamp.with_timezone(&Utc))
        .unwrap_or_else(|| report_time - Duration::hours(24))
}

fn write_state_transition_event(
    project_dir: &PathBuf,
    identifier: &str,
    status: &str,
    occurred_at: chrono::DateTime<Utc>,
) {
    let events_dir = project_dir.join("events");
    fs::create_dir_all(&events_dir).expect("create events dir");
    let occurred_at_text = occurred_at.to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
    let event_id = format!("standup-transition-{identifier}");
    let filename = format!("{}__{event_id}.json", occurred_at_text.replace(':', "-"));
    let payload = serde_json::json!({
        "schema_version": 1,
        "event_id": event_id,
        "issue_id": identifier,
        "event_type": "state_transition",
        "occurred_at": occurred_at_text,
        "actor_id": "agent",
        "payload": {
            "from_status": "in_progress",
            "to_status": status,
        }
    });
    fs::write(
        events_dir.join(filename),
        serde_json::to_string_pretty(&payload).expect("serialize event"),
    )
    .expect("write event");
}

#[given(expr = "issue {string} closed on the previous calendar day in standup timezone")]
fn given_issue_closed_previous_calendar_day(world: &mut KanbusWorld, identifier: String) {
    let root = world.working_directory.as_ref().expect("cwd");
    let project_dir = resolve_issue_project_directory(world, &identifier);
    let issue = read_issue_file(&project_dir, &identifier);
    let closed_at = previous_calendar_day_timestamp(root);
    let updated = IssueData {
        closed_at: Some(closed_at),
        status: String::from("closed"),
        ..issue
    };
    write_issue_file(&project_dir, &updated);
}

#[given(
    expr = "issue {string} has a state transition to {string} on the previous calendar day in standup timezone"
)]
fn given_issue_state_transition_previous_calendar_day(
    world: &mut KanbusWorld,
    identifier: String,
    status: String,
) {
    let root = world.working_directory.as_ref().expect("cwd");
    let project_dir = resolve_issue_project_directory(world, &identifier);
    let occurred_at = previous_calendar_day_timestamp(root);
    write_state_transition_event(&project_dir, &identifier, &status, occurred_at);
}

#[given(expr = "issue {string} has closed_at within standup lookback")]
fn given_issue_closed_at_within_standup_lookback(world: &mut KanbusWorld, identifier: String) {
    let project_dir = resolve_issue_project_directory(world, &identifier);
    let issue = read_issue_file(&project_dir, &identifier);
    let recent = Utc::now() - Duration::hours(1);
    let updated = IssueData {
        closed_at: Some(recent),
        ..issue
    };
    write_issue_file(&project_dir, &updated);
}

#[given(expr = "issue {string} has updated_at within standup lookback")]
fn given_issue_updated_at_within_standup_lookback(world: &mut KanbusWorld, identifier: String) {
    let project_dir = resolve_issue_project_directory(world, &identifier);
    let issue = read_issue_file(&project_dir, &identifier);
    let recent = Utc::now() - Duration::hours(1);
    let updated = IssueData {
        updated_at: recent,
        ..issue
    };
    write_issue_file(&project_dir, &updated);
}

#[given(expr = "issue {string} has updated_at older than standup lookback")]
fn given_issue_updated_at_older_than_standup_lookback(world: &mut KanbusWorld, identifier: String) {
    let project_dir = resolve_issue_project_directory(world, &identifier);
    let issue = read_issue_file(&project_dir, &identifier);
    let stale = Utc::now() - Duration::hours(48);
    let updated = IssueData {
        updated_at: stale,
        ..issue
    };
    write_issue_file(&project_dir, &updated);
}

#[given(expr = "issue {string} has a state transition to {string} within standup lookback")]
fn given_issue_state_transition_within_standup_lookback(
    world: &mut KanbusWorld,
    identifier: String,
    status: String,
) {
    let project_dir = resolve_issue_project_directory(world, &identifier);
    let occurred_at = Utc::now() - Duration::hours(1);
    write_state_transition_event(&project_dir, &identifier, &status, occurred_at);
}

#[then("the standup fact feed should match standup default listing")]
fn then_standup_fact_feed_matches_default(world: &mut KanbusWorld) {
    let actual = current_standup_fact_feed(world);
    let expected = expected_default_fact_feed(world);
    assert_eq!(actual, expected);
}

#[then("the standup fact feed should match kanbus now listing with status in_progress,blocked")]
fn then_standup_fact_feed_matches_kanbus_now_status(world: &mut KanbusWorld) {
    let actual = current_standup_fact_feed(world);
    let expected = kanbus_now_fact_feed(world, "in_progress,blocked");
    assert_eq!(actual, expected);
}

#[then(expr = "the standup fact feed should include issue {string}")]
fn then_standup_fact_feed_includes_issue(world: &mut KanbusWorld, identifier: String) {
    let feed = current_standup_fact_feed(world);
    assert!(feed.iter().any(|value| value == &identifier));
}

#[then(expr = "the standup fact feed should not include issue {string}")]
fn then_standup_fact_feed_excludes_issue(world: &mut KanbusWorld, identifier: String) {
    let feed = current_standup_fact_feed(world);
    assert!(!feed.iter().any(|value| value == &identifier));
}

#[then(expr = "the standup fact feed should have {int} issues")]
fn then_standup_fact_feed_count(world: &mut KanbusWorld, count: usize) {
    assert_eq!(current_standup_fact_feed(world).len(), count);
}

#[then(expr = "the standup report should have profile {string}")]
fn then_standup_report_profile(world: &mut KanbusWorld, profile: String) {
    let stdout = stdout_text(world);
    if stdout.trim().starts_with('{') {
        let payload = parse_standup_json(world);
        assert_eq!(
            payload.get("profile"),
            Some(&Value::String(profile.clone()))
        );
        return;
    }
    assert!(stdout.contains(&format!("Standup ({profile})")));
}

#[then(expr = "the standup report should include section {string}")]
fn then_standup_report_includes_section(world: &mut KanbusWorld, section_name: String) {
    let stdout = stdout_text(world);
    if stdout.trim().starts_with('{') {
        let payload = parse_standup_json(world);
        let section_names: Vec<String> = payload
            .get("sections")
            .and_then(Value::as_array)
            .expect("sections array")
            .iter()
            .filter_map(|section| {
                section
                    .get("name")
                    .and_then(Value::as_str)
                    .map(str::to_string)
            })
            .collect();
        assert!(section_names.iter().any(|name| name == &section_name));
        return;
    }
    assert!(
        stdout.contains(&format!("\n{section_name}\n")) || stdout.trim().ends_with(&section_name)
    );
}

#[then(expr = "the standup report section {string} should mention {string}")]
fn then_standup_section_mentions(world: &mut KanbusWorld, section_name: String, text: String) {
    assert_standup_section_mentions(world, &section_name, &text);
}

#[then(expr = "the standup report section {string} should not contain {string}")]
fn then_standup_section_does_not_contain(
    world: &mut KanbusWorld,
    section_name: String,
    text: String,
) {
    let stdout = stdout_text(world);
    if stdout.trim().starts_with('{') {
        let payload = parse_standup_json(world);
        let sections = payload
            .get("sections")
            .and_then(Value::as_array)
            .expect("sections array");
        let section = sections
            .iter()
            .find(|item| item.get("name") == Some(&Value::String(section_name.clone())))
            .expect("section");
        let joined = section
            .get("bullets")
            .and_then(Value::as_array)
            .map(|bullets| {
                bullets
                    .iter()
                    .filter_map(|bullet| bullet.as_str())
                    .collect::<Vec<_>>()
                    .join("\n")
            })
            .unwrap_or_default();
        assert!(!joined.contains(&text));
        return;
    }
    let section_text = extract_section_text(&stdout, &section_name);
    assert!(!section_text.contains(&text));
}

#[given(expr = "standup rollup reduce uses completion {string}")]
fn given_standup_rollup_reduce_completion(world: &mut KanbusWorld, summary: String) {
    world.environment_overrides.insert(
        "KANBUS_TEST_STANDUP_ROLLUP_COMPLETION".to_string(),
        summary.clone(),
    );
    if !world
        .jira_unset_env_vars
        .iter()
        .any(|(name, _)| name == "KANBUS_TEST_STANDUP_ROLLUP_COMPLETION")
    {
        world.jira_unset_env_vars.push((
            "KANBUS_TEST_STANDUP_ROLLUP_COMPLETION".to_string(),
            std::env::var("KANBUS_TEST_STANDUP_ROLLUP_COMPLETION").ok(),
        ));
    }
    std::env::set_var("KANBUS_TEST_STANDUP_ROLLUP_COMPLETION", summary);
}

#[then(expr = "the standup report section {string} should not mention {string}")]
fn then_standup_section_does_not_mention(
    world: &mut KanbusWorld,
    section_name: String,
    text: String,
) {
    assert_standup_section_does_not_mention(world, &section_name, &text);
}

#[then(expr = "the standup report section {string} should not be empty")]
fn then_standup_section_not_empty(world: &mut KanbusWorld, section_name: String) {
    let stdout = stdout_text(world);
    if stdout.trim().starts_with('{') {
        let payload = parse_standup_json(world);
        let sections = payload
            .get("sections")
            .and_then(Value::as_array)
            .expect("sections array");
        let section = sections
            .iter()
            .find(|item| item.get("name") == Some(&Value::String(section_name.clone())))
            .expect("section");
        let bullets = section
            .get("bullets")
            .and_then(Value::as_array)
            .expect("bullets array");
        assert!(!bullets.is_empty());
        return;
    }
    let section_text = extract_section_text(&stdout, &section_name);
    assert!(section_text
        .lines()
        .any(|line| line.trim().starts_with('-')));
}

#[then(expr = "the standup report section \"Health\" should report {int} in-progress issues")]
fn then_standup_health_in_progress_count(world: &mut KanbusWorld, count: usize) {
    assert_standup_section_mentions(world, "Health", &format!("{count} in-progress issues"));
}

#[then(expr = "the standup report section \"Health\" should report {int} blocked issue")]
#[then(expr = "the standup report section \"Health\" should report {int} blocked issues")]
fn then_standup_health_blocked_count(world: &mut KanbusWorld, count: usize) {
    let label = if count == 1 {
        "blocked issue"
    } else {
        "blocked issues"
    };
    assert_standup_section_mentions(world, "Health", &format!("{count} {label}"));
}

#[then("the standup report should use first person voice")]
fn then_standup_first_person_voice(world: &mut KanbusWorld) {
    assert!(report_uses_first_person_voice(&stdout_text(world)));
}

#[then("the standup report should not use first person voice")]
fn then_standup_not_first_person_voice(world: &mut KanbusWorld) {
    assert!(!report_uses_first_person_voice(&stdout_text(world)));
}

#[then("the standup report should use third person executive voice")]
fn then_standup_third_person_executive_voice(world: &mut KanbusWorld) {
    assert!(report_uses_third_person_executive_voice(&stdout_text(
        world
    )));
}

#[then("the standup report should not use third person executive voice")]
fn then_standup_not_third_person_executive_voice(world: &mut KanbusWorld) {
    assert!(!report_uses_third_person_executive_voice(&stdout_text(
        world
    )));
}

#[then(expr = "each standup report bullet should be at most {int} characters")]
fn then_each_standup_bullet_max_length(world: &mut KanbusWorld, max_length: usize) {
    let stdout = stdout_text(world);
    for line in stdout.lines() {
        if let Some(bullet) = line.strip_prefix("- ") {
            assert!(bullet.len() <= max_length);
        }
    }
}

#[then(expr = "the standup JSON output should include fields {string}")]
fn then_standup_json_includes_fields(world: &mut KanbusWorld, fields_csv: String) {
    let payload = parse_standup_json(world);
    let object = payload.as_object().expect("json object");
    for field_name in fields_csv.split(',') {
        assert!(object.contains_key(field_name.trim()));
    }
}

#[then(expr = "the standup JSON source_issues should include issue {string}")]
fn then_standup_json_source_issue(world: &mut KanbusWorld, identifier: String) {
    let payload = parse_standup_json(world);
    let source_issues = payload
        .get("source_issues")
        .and_then(Value::as_array)
        .expect("source_issues array");
    assert!(source_issues
        .iter()
        .any(|value| value == &Value::String(identifier.clone())));
}

#[then(expr = "the standup JSON output should record source issue {string}")]
fn then_standup_json_records_source_issue(world: &mut KanbusWorld, identifier: String) {
    store_standup_json_profile(world);
    then_standup_json_source_issue(world, identifier);
}

#[then("the standup JSON source_issues set should match between profiles")]
fn then_standup_json_source_issues_match_between_profiles(world: &mut KanbusWorld) {
    store_standup_json_profile(world);
    let profiles = world
        .standup_json_by_profile
        .as_ref()
        .expect("standup json profiles");
    assert!(profiles.len() >= 2);
    let source_sets: Vec<BTreeMap<String, ()>> = profiles
        .values()
        .map(|payload| {
            payload
                .get("source_issues")
                .and_then(Value::as_array)
                .expect("source_issues array")
                .iter()
                .filter_map(Value::as_str)
                .map(|value| (value.to_string(), ()))
                .collect()
        })
        .collect();
    assert!(source_sets.iter().all(|set| set == &source_sets[0]));
}

#[then("the standup JSON right_now_texts should match between profiles")]
fn then_standup_json_right_now_texts_match_between_profiles(world: &mut KanbusWorld) {
    store_standup_json_profile(world);
    let profiles = world
        .standup_json_by_profile
        .as_ref()
        .expect("standup json profiles");
    assert!(profiles.len() >= 2);
    let texts: Vec<&Value> = profiles
        .values()
        .map(|payload| payload.get("right_now_texts").expect("right_now_texts"))
        .collect();
    assert!(texts.iter().all(|text| *text == texts[0]));
}

#[then("standup generation should use the right now litellm configuration")]
fn then_standup_uses_right_now_litellm_configuration(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let log_path = project_dir.join("events").join("llm_usage.jsonl");
    assert!(log_path.is_file(), "expected {:?} to exist", log_path);
    let entries: Vec<serde_json::Value> = std::fs::read_to_string(&log_path)
        .expect("read llm usage log")
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str(line).expect("parse llm usage entry"))
        .collect();
    let matching = entries
        .iter()
        .filter(|entry| {
            entry.get("operation")
                == Some(&serde_json::Value::String("right_now_summary".to_string()))
        })
        .count();
    assert!(
        matching > 0,
        "expected right_now_summary entry in llm usage log"
    );
}

#[then("standup generation should not use a separate standup litellm client")]
fn then_standup_does_not_use_separate_litellm_client(_world: &mut KanbusWorld) {
    assert_ne!(
        std::env::var("KANBUS_STANDUP_LITELLM_CALLED").ok(),
        Some("1".to_string())
    );
}

#[given("standup parity is tracked by tools/check_spec_parity.py")]
#[then("standup parity is tracked by tools/check_spec_parity.py")]
fn then_standup_parity_tracked(world: &mut KanbusWorld) {
    let _ = world;
    let parity_script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("tools")
        .join("check_spec_parity.py");
    assert!(parity_script.is_file());
}

#[then(
    "standup scenarios should not be considered complete until both Python behave and Rust cucumber pass without wip tags"
)]
fn then_standup_completion_requires_dual_runtime(world: &mut KanbusWorld) {
    let _ = world;
}

fn standup_section_bullets(world: &KanbusWorld, section_name: &str) -> Vec<String> {
    let stdout = stdout_text(world);
    if stdout.trim().starts_with('{') {
        let payload = parse_standup_json(world);
        let sections = payload
            .get("sections")
            .and_then(Value::as_array)
            .expect("sections array");
        let section = sections
            .iter()
            .find(|item| item.get("name") == Some(&Value::String(section_name.to_string())))
            .expect("section");
        return section
            .get("bullets")
            .and_then(Value::as_array)
            .expect("bullets array")
            .iter()
            .filter_map(|value| value.as_str().map(str::to_string))
            .collect();
    }
    let section_text = extract_section_text(&stdout, section_name);
    section_text
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim_start();
            trimmed.strip_prefix("- ").map(|bullet| bullet.to_string())
        })
        .collect()
}

#[then(expr = "the standup report section {string} should have {int} bullet")]
#[then(expr = "the standup report section {string} should have {int} bullets")]
fn then_standup_section_bullet_count(world: &mut KanbusWorld, section_name: String, count: usize) {
    let bullets = standup_section_bullets(world, &section_name);
    assert_eq!(bullets.len(), count);
}

#[then(expr = "the standup report section {string} should match pattern {string}")]
fn then_standup_section_matches_pattern(
    world: &mut KanbusWorld,
    section_name: String,
    pattern: String,
) {
    let bullets = standup_section_bullets(world, &section_name);
    let joined = bullets.join("\n");
    let regex = Regex::new(&pattern).expect("valid pattern");
    assert!(regex.is_match(&joined));
}
