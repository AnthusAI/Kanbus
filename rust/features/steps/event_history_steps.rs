use std::fs;
use std::path::PathBuf;

use cucumber::{then, when};
use regex::Regex;
use serde_json::Value;

use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn run_cli(world: &mut KanbusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse command");
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    if std::env::var("KANBUS_NO_DAEMON").is_err() {
        std::env::set_var("KANBUS_NO_DAEMON", "1");
    }

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

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn parse_issue_identifier(world: &KanbusWorld) -> String {
    let stdout = world.stdout.as_ref().expect("stdout");
    let ansi_regex = Regex::new(r"\x1b\[[0-9;]*m").expect("regex");
    let clean_stdout = ansi_regex.replace_all(stdout, "");
    let full_regex = Regex::new(
        r"([A-Za-z0-9]+-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    )
    .expect("regex");
    if let Some(capture) = full_regex
        .captures(&clean_stdout)
        .and_then(|matches| matches.get(1))
        .map(|match_value| match_value.as_str().to_string())
    {
        return capture;
    }

    let labeled_regex = Regex::new(r"(?i)\bID:\s*([A-Za-z0-9.-]+)").expect("regex");
    let abbreviated = labeled_regex
        .captures(&clean_stdout)
        .and_then(|matches| matches.get(1))
        .map(|match_value| match_value.as_str().to_string())
        .unwrap_or_else(|| {
            let fallback_regex = Regex::new(r"\b([A-Za-z0-9]{6}(?:\.[0-9]+)?)\b").expect("regex");
            fallback_regex
                .captures(&clean_stdout)
                .and_then(|matches| matches.get(1))
                .map(|match_value| match_value.as_str().to_string())
                .expect("issue id not found")
        });
    let (abbrev_base, abbrev_suffix) = parse_abbreviation(&abbreviated);
    let project_dir = load_project_dir(world);
    let issues_dir = project_dir.join("issues");
    let entries = fs::read_dir(issues_dir).expect("read issues dir");
    for entry in entries {
        let path = entry.expect("issue entry").path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let identifier = path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .unwrap_or_default()
            .to_string();
        if matches_abbreviation(&identifier, &abbrev_base, abbrev_suffix.as_deref()) {
            return identifier;
        }
    }
    panic!("issue id not found");
}

fn parse_abbreviation(value: &str) -> (String, Option<String>) {
    let remainder = if let Some((_, rest)) = value.split_once('-') {
        rest
    } else {
        value
    };
    if let Some((base, suffix)) = remainder.split_once('.') {
        (base.to_lowercase(), Some(suffix.to_lowercase()))
    } else {
        (remainder.to_lowercase(), None)
    }
}

fn matches_abbreviation(identifier: &str, base: &str, suffix: Option<&str>) -> bool {
    let remainder = if let Some((_, rest)) = identifier.split_once('-') {
        rest
    } else {
        identifier
    };
    let (id_base, id_suffix) = if let Some((head, tail)) = remainder.split_once('.') {
        (head, Some(tail))
    } else {
        (remainder, None)
    };
    let normalized = id_base.replace('-', "").to_lowercase();
    if !normalized.starts_with(base) {
        return false;
    }
    match (suffix, id_suffix) {
        (None, _) => true,
        (Some(expected), Some(actual)) => actual.to_lowercase() == expected.to_lowercase(),
        _ => false,
    }
}

fn last_issue_id(world: &KanbusWorld) -> String {
    world
        .last_kanbus_issue_id
        .clone()
        .expect("last issue id not set")
}

fn load_issue_events(world: &KanbusWorld, issue_id: &str) -> Vec<(String, Value)> {
    let project_dir = load_project_dir(world);
    let events_dir = project_dir.join("events");
    if !events_dir.exists() {
        return Vec::new();
    }
    let mut events = Vec::new();
    for entry in fs::read_dir(&events_dir).expect("read events dir") {
        let entry = entry.expect("event entry");
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let filename = path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_string();
        let contents = fs::read_to_string(&path).expect("read event");
        let record: Value = serde_json::from_str(&contents).expect("parse event");
        if record.get("issue_id").and_then(|value| value.as_str()) == Some(issue_id) {
            events.push((filename, record));
        }
    }
    events
}

fn find_event<'a>(events: &'a [(String, Value)], event_type: &str) -> Option<&'a Value> {
    events.iter().find_map(|(_, record)| {
        if record.get("event_type").and_then(|value| value.as_str()) == Some(event_type) {
            Some(record)
        } else {
            None
        }
    })
}

#[when(expr = "I run the command {string}")]
fn when_run_command(world: &mut KanbusWorld, command: String) {
    run_cli(world, &command);
}

#[when("I capture the issue identifier")]
fn when_capture_issue_identifier(world: &mut KanbusWorld) {
    let identifier = parse_issue_identifier(world);
    world.last_kanbus_issue_id = Some(identifier);
}

#[when(expr = "I update the last issue status to {string}")]
fn when_update_last_issue_status(world: &mut KanbusWorld, status: String) {
    let identifier = last_issue_id(world);
    run_cli(
        world,
        &format!("kanbus update {identifier} --status {status}"),
    );
}

#[when(expr = "I update the last issue title to {string}")]
fn when_update_last_issue_title(world: &mut KanbusWorld, title: String) {
    let identifier = last_issue_id(world);
    run_cli(
        world,
        &format!("kanbus update {identifier} --title \"{title}\""),
    );
}

#[when(expr = "I add a comment to the last issue with text {string}")]
fn when_add_comment_last_issue(world: &mut KanbusWorld, text: String) {
    let identifier = last_issue_id(world);
    run_cli(world, &format!("kanbus comment {identifier} \"{text}\""));
}

#[when(expr = "I add a blocked-by dependency from the last issue to {string}")]
fn when_add_dependency(world: &mut KanbusWorld, target: String) {
    let identifier = last_issue_id(world);
    run_cli(
        world,
        &format!("kanbus dep {identifier} blocked-by {target}"),
    );
}

#[when("I delete the last issue")]
fn when_delete_last_issue(world: &mut KanbusWorld) {
    let identifier = last_issue_id(world);
    run_cli(world, &format!("kanbus delete {identifier}"));
}

#[then(expr = "the event log for the last issue should include event type {string}")]
fn then_event_log_includes_type(world: &mut KanbusWorld, event_type: String) {
    let identifier = last_issue_id(world);
    let events = load_issue_events(world, &identifier);
    assert!(
        find_event(&events, &event_type).is_some(),
        "expected event type {event_type}"
    );
}

#[then("the event log filenames for the last issue should be ISO timestamped")]
fn then_event_filenames_iso(world: &mut KanbusWorld) {
    let identifier = last_issue_id(world);
    let events = load_issue_events(world, &identifier);
    let filename_regex =
        Regex::new(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z__.+\.json$").expect("regex");
    assert!(!events.is_empty(), "expected events for issue");
    for (filename, _) in events {
        assert!(
            filename_regex.is_match(&filename),
            "unexpected event filename: {filename}"
        );
    }
}

#[then(
    expr = "the event log for the last issue should include a state transition from {string} to {string}"
)]
fn then_event_log_state_transition(world: &mut KanbusWorld, from: String, to: String) {
    let identifier = last_issue_id(world);
    let events = load_issue_events(world, &identifier);
    let found = events.iter().any(|(_, record)| {
        record.get("event_type").and_then(|value| value.as_str()) == Some("state_transition")
            && record
                .get("payload")
                .and_then(|payload| payload.get("from_status"))
                .and_then(|value| value.as_str())
                == Some(from.as_str())
            && record
                .get("payload")
                .and_then(|payload| payload.get("to_status"))
                .and_then(|value| value.as_str())
                == Some(to.as_str())
    });
    assert!(found, "expected state transition {from} -> {to}");
}

#[then(
    expr = "the event log for the last issue should include a field update for {string} from {string} to {string}"
)]
fn then_event_log_field_update(world: &mut KanbusWorld, field: String, from: String, to: String) {
    let identifier = last_issue_id(world);
    let events = load_issue_events(world, &identifier);
    let found = events.iter().any(|(_, record)| {
        if record.get("event_type").and_then(|value| value.as_str()) != Some("field_updated") {
            return false;
        }
        let change = record
            .get("payload")
            .and_then(|payload| payload.get("changes"))
            .and_then(|changes| changes.get(&field));
        let Some(change) = change else {
            return false;
        };
        let from_value = change.get("from").and_then(|value| value.as_str());
        let to_value = change.get("to").and_then(|value| value.as_str());
        from_value == Some(from.as_str()) && to_value == Some(to.as_str())
    });
    assert!(found, "expected field update for {field}");
}

#[then(
    expr = "the event log for the last issue should include a comment_added event by {string} with a comment id"
)]
fn then_event_log_comment_added(world: &mut KanbusWorld, author: String) {
    let identifier = last_issue_id(world);
    let events = load_issue_events(world, &identifier);
    let found = events.iter().any(|(_, record)| {
        if record.get("event_type").and_then(|value| value.as_str()) != Some("comment_added") {
            return false;
        }
        let Some(payload) = record.get("payload") else {
            return false;
        };
        let comment_author = payload.get("comment_author").and_then(|v| v.as_str());
        let comment_id = payload.get("comment_id").and_then(|v| v.as_str());
        comment_author == Some(author.as_str()) && comment_id.is_some()
    });
    assert!(found, "expected comment_added event for {author}");
}

#[then("the event log for the last issue should not include comment text")]
fn then_event_log_no_comment_text(world: &mut KanbusWorld) {
    let identifier = last_issue_id(world);
    let events = load_issue_events(world, &identifier);
    for (_, record) in events {
        let event_type = record
            .get("event_type")
            .and_then(|value| value.as_str())
            .unwrap_or_default();
        if !event_type.starts_with("comment_") {
            continue;
        }
        let payload = record.get("payload").expect("payload");
        assert!(
            payload.get("text").is_none(),
            "comment text should not be stored in events"
        );
    }
}

#[then(expr = "the event log for the last issue should include a dependency {string} on {string}")]
fn then_event_log_dependency(world: &mut KanbusWorld, dependency_type: String, target: String) {
    let identifier = last_issue_id(world);
    let events = load_issue_events(world, &identifier);
    let found = events.iter().any(|(_, record)| {
        if record.get("event_type").and_then(|value| value.as_str()) != Some("dependency_added") {
            return false;
        }
        let Some(payload) = record.get("payload") else {
            return false;
        };
        let dep_type = payload.get("dependency_type").and_then(|v| v.as_str());
        let target_id = payload.get("target_id").and_then(|v| v.as_str());
        dep_type == Some(dependency_type.as_str()) && target_id == Some(target.as_str())
    });
    assert!(
        found,
        "expected dependency event for {dependency_type} -> {target}"
    );
}
