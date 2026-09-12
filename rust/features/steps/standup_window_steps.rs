use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use chrono::{Datelike, Duration, TimeZone, Utc, Weekday};
use chrono_tz::Tz;
use cucumber::gherkin::Step;
use cucumber::{given, then, when};
use serde_json::Value;
use serde_yaml::{Mapping, Value as YamlValue};

use kanbus::config::default_project_configuration;
use kanbus::console_standup::StandupGenerateRequest;
use kanbus::models::IssueData;
use kanbus::standup::{load_standup_configuration, resolve_standup_profile};
use kanbus::standup_window::{
    parse_standup_lookback_hours, resolve_standup_report_time, resolve_standup_timezone,
    resolve_standup_window_settings, StandupWindowOverrides, StandupWindowSettings,
    STANDUP_REPORT_TIME_ENV,
};

use crate::step_definitions::initialization_steps::KanbusWorld;
use crate::step_definitions::query_steps::resolve_issue_project_directory;

fn repository_root(world: &KanbusWorld) -> PathBuf {
    world.working_directory.as_ref().expect("cwd").to_path_buf()
}

fn load_config_mapping(world: &KanbusWorld) -> Mapping {
    let config_path = repository_root(world).join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read config");
    serde_yaml::from_str(&contents).unwrap_or_else(|_| {
        let defaults = default_project_configuration();
        serde_yaml::to_value(defaults)
            .expect("serialize defaults")
            .as_mapping()
            .cloned()
            .expect("defaults mapping")
    })
}

fn write_config_mapping(world: &KanbusWorld, mapping: Mapping) {
    let config_path = repository_root(world).join(".kanbus.yml");
    let yaml = serde_yaml::to_string(&mapping).expect("serialize config");
    fs::write(config_path, yaml).expect("write config");
}

fn upsert_standup_field(world: &KanbusWorld, key: &str, value: YamlValue) {
    let mut mapping = load_config_mapping(world);
    let mut standup_block = mapping
        .get(&YamlValue::String("standup".to_string()))
        .and_then(YamlValue::as_mapping)
        .cloned()
        .unwrap_or_else(|| {
            let defaults = default_project_configuration();
            serde_yaml::to_value(defaults.standup)
                .expect("serialize standup defaults")
                .as_mapping()
                .cloned()
                .expect("standup mapping")
        });
    standup_block.insert(YamlValue::String(key.to_string()), value);
    mapping.insert(
        YamlValue::String("standup".to_string()),
        YamlValue::Mapping(standup_block),
    );
    write_config_mapping(world, mapping);
}

fn clear_report_time() {
    std::env::remove_var(STANDUP_REPORT_TIME_ENV);
}

fn set_report_time(report_time: chrono::DateTime<Utc>) {
    let text = report_time.to_rfc3339_opts(chrono::SecondsFormat::Secs, true);
    std::env::set_var(STANDUP_REPORT_TIME_ENV, text);
}

fn ensure_live_report_time() {
    if std::env::var(STANDUP_REPORT_TIME_ENV).is_err() {
        clear_report_time();
    }
}

fn standup_timezone(world: &KanbusWorld) -> Tz {
    if let Some(name) = world.standup_timezone_name.as_deref() {
        return name.parse::<Tz>().expect("timezone");
    }
    let configuration =
        load_standup_configuration(&repository_root(world)).expect("load standup config");
    resolve_standup_timezone(&configuration)
}

fn settings_to_value(settings: &StandupWindowSettings) -> Value {
    serde_json::json!({
        "window": settings.window,
        "lookback": settings.lookback,
        "lookback_hours": settings.lookback_hours,
        "skip_weekends": settings.skip_weekends,
        "timezone": settings.timezone.name(),
    })
}

fn resolved_window_settings(
    world: &KanbusWorld,
    profile: Option<&str>,
    apply_profile_defaults: bool,
) -> StandupWindowSettings {
    let root = repository_root(world);
    let configuration = load_standup_configuration(&root).expect("load standup config");
    let resolved_profile = if apply_profile_defaults {
        Some(resolve_standup_profile(profile).expect("resolve profile"))
    } else {
        None
    };
    resolve_standup_window_settings(
        &configuration,
        resolved_profile.as_deref(),
        &StandupWindowOverrides::default(),
    )
    .expect("resolve window settings")
}

fn read_issue_file(project_dir: &Path, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

fn write_issue_file(project_dir: &Path, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn weekday_from_name(name: &str) -> Weekday {
    match name {
        "Monday" => Weekday::Mon,
        "Tuesday" => Weekday::Tue,
        "Wednesday" => Weekday::Wed,
        "Thursday" => Weekday::Thu,
        "Friday" => Weekday::Fri,
        "Saturday" => Weekday::Sat,
        "Sunday" => Weekday::Sun,
        other => panic!("unknown weekday: {other}"),
    }
}

#[given(expr = "standup window is {string}")]
fn given_standup_window(world: &mut KanbusWorld, window: String) {
    ensure_live_report_time();
    upsert_standup_field(world, "window", YamlValue::String(window));
}

#[given(expr = "standup lookback is {string}")]
fn given_standup_lookback(world: &mut KanbusWorld, lookback: String) {
    upsert_standup_field(world, "lookback", YamlValue::String(lookback));
}

#[given(expr = "standup skip_weekends is {word}")]
fn given_standup_skip_weekends(world: &mut KanbusWorld, enabled: String) {
    let value = enabled.eq_ignore_ascii_case("true");
    upsert_standup_field(world, "skip_weekends", YamlValue::Bool(value));
}

#[given(expr = "standup timezone is {string}")]
fn given_standup_timezone(world: &mut KanbusWorld, timezone_name: String) {
    world.standup_timezone_name = Some(timezone_name.clone());
    upsert_standup_field(world, "timezone", YamlValue::String(timezone_name));
}

#[given("the report time is fixed")]
fn given_report_time_is_fixed(_world: &mut KanbusWorld) {
    set_report_time(Utc.with_ymd_and_hms(2026, 3, 10, 15, 0, 0).unwrap());
}

#[given(expr = "the report time is {word} {int}:00 in standup timezone")]
fn given_report_time_in_standup_timezone(world: &mut KanbusWorld, weekday: String, hour: i64) {
    let target_weekday = weekday_from_name(&weekday);
    let timezone = standup_timezone(world);
    let mut base = timezone
        .with_ymd_and_hms(2026, 3, 9, hour as u32, 0, 0)
        .single()
        .expect("base report time");
    while base.weekday() != target_weekday {
        base += Duration::days(1);
    }
    set_report_time(base.with_timezone(&Utc));
}

#[given(expr = "issue {string} has closed_at {int} hours before report time")]
fn given_issue_closed_at_hours_before_report(
    world: &mut KanbusWorld,
    identifier: String,
    hours: i64,
) {
    let project_dir = resolve_issue_project_directory(world, &identifier);
    let issue = read_issue_file(&project_dir, &identifier);
    let report_time = resolve_standup_report_time().expect("report time");
    let closed_at = report_time - Duration::hours(hours);
    let updated = IssueData {
        closed_at: Some(closed_at),
        status: "closed".to_string(),
        ..issue
    };
    write_issue_file(&project_dir, &updated);
}

#[given(expr = "issue {string} closed two calendar days before report day in standup timezone")]
fn given_issue_closed_two_calendar_days_before(world: &mut KanbusWorld, identifier: String) {
    let project_dir = resolve_issue_project_directory(world, &identifier);
    let issue = read_issue_file(&project_dir, &identifier);
    let timezone = standup_timezone(world);
    let report_time = resolve_standup_report_time().expect("report time");
    let report_local = report_time.with_timezone(&timezone);
    let closed_day = report_local.date_naive() - Duration::days(2);
    let closed_at = timezone
        .from_local_datetime(&closed_day.and_hms_opt(16, 0, 0).expect("time"))
        .single()
        .map(|value| value.with_timezone(&Utc))
        .expect("closed_at");
    let updated = IssueData {
        closed_at: Some(closed_at),
        status: "closed".to_string(),
        ..issue
    };
    write_issue_file(&project_dir, &updated);
}

#[given(expr = "issue {string} closed on {word} before this Monday in standup timezone")]
fn given_issue_closed_on_weekday_before_monday(
    world: &mut KanbusWorld,
    identifier: String,
    weekday: String,
) {
    let target = weekday_from_name(&weekday);
    let project_dir = resolve_issue_project_directory(world, &identifier);
    let issue = read_issue_file(&project_dir, &identifier);
    let timezone = standup_timezone(world);
    let report_time = resolve_standup_report_time().expect("report time");
    let report_local = report_time.with_timezone(&timezone);
    let mut days_back = (report_local.weekday().num_days_from_monday() as i64
        - target.num_days_from_monday() as i64)
        .rem_euclid(7);
    if days_back == 0 {
        days_back = 7;
    }
    let closed_day = report_local.date_naive() - Duration::days(days_back);
    let closed_at = timezone
        .from_local_datetime(&closed_day.and_hms_opt(16, 0, 0).expect("time"))
        .single()
        .map(|value| value.with_timezone(&Utc))
        .expect("closed_at");
    let updated = IssueData {
        closed_at: Some(closed_at),
        status: "closed".to_string(),
        ..issue
    };
    write_issue_file(&project_dir, &updated);
}

#[given(expr = "the Kanbus configuration sets standup window to {string}")]
fn given_config_standup_window(world: &mut KanbusWorld, window: String) {
    given_standup_window(world, window);
}

#[given(expr = "the Kanbus configuration sets standup lookback to {string}")]
fn given_config_standup_lookback(world: &mut KanbusWorld, lookback: String) {
    given_standup_lookback(world, lookback);
}

#[given(expr = "the Kanbus configuration sets standup skip_weekends to {word}")]
fn given_config_standup_skip_weekends(world: &mut KanbusWorld, enabled: String) {
    given_standup_skip_weekends(world, enabled);
}

#[when("I inspect standup window configuration")]
fn when_inspect_standup_window_configuration(world: &mut KanbusWorld) {
    let settings = resolved_window_settings(world, None, false);
    world.standup_window_settings = Some(settings_to_value(&settings));
}

#[when(expr = "I resolve standup window settings for profile {string}")]
fn when_resolve_standup_window_settings(world: &mut KanbusWorld, profile: String) {
    let settings = resolved_window_settings(world, Some(&profile), true);
    world.standup_window_settings = Some(settings_to_value(&settings));
}

#[when("I resolve standup lookback duration")]
fn when_resolve_standup_lookback_duration(world: &mut KanbusWorld) {
    let mapping = load_config_mapping(world);
    let lookback = mapping
        .get(&YamlValue::String("standup".to_string()))
        .and_then(YamlValue::as_mapping)
        .and_then(|standup| standup.get(&YamlValue::String("lookback".to_string())))
        .and_then(YamlValue::as_str)
        .unwrap_or("24h");
    world.resolved_standup_lookback_hours =
        Some(parse_standup_lookback_hours(lookback).expect("parse lookback"));
}

#[when("I resolve standup window settings in both runtimes")]
fn when_resolve_standup_window_settings_both_runtimes(world: &mut KanbusWorld) {
    let root = repository_root(world);
    let configuration = load_standup_configuration(&root).expect("load standup config");
    let rust_settings =
        resolve_standup_window_settings(&configuration, None, &StandupWindowOverrides::default())
            .expect("resolve rust settings");
    world.rust_window_settings = Some(settings_to_value(&rust_settings));

    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let probe = repo_root.join("tools").join("standup_window_probe.py");
    let python_src = repo_root.join("python").join("src");
    let output = Command::new("python3")
        .env("PYTHONPATH", python_src)
        .arg(&probe)
        .arg(&root)
        .output()
        .expect("run python probe");
    assert!(
        output.status.success(),
        "python probe failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload: Value = serde_json::from_slice(&output.stdout).expect("parse python probe json");
    world.python_window_settings = Some(payload);
}

#[then(expr = "standup window should be {string}")]
fn then_standup_window_should_be(world: &mut KanbusWorld, window: String) {
    let settings = world.standup_window_settings.as_ref().expect("settings");
    assert_eq!(settings["window"].as_str().expect("window"), window);
}

#[then(expr = "standup lookback should be {string}")]
fn then_standup_lookback_should_be(world: &mut KanbusWorld, lookback: String) {
    let settings = world.standup_window_settings.as_ref().expect("settings");
    assert_eq!(settings["lookback"].as_str().expect("lookback"), lookback);
}

#[then(expr = "standup skip_weekends should be {word}")]
fn then_standup_skip_weekends_should_be(world: &mut KanbusWorld, enabled: String) {
    let expected = enabled.eq_ignore_ascii_case("true");
    let settings = world.standup_window_settings.as_ref().expect("settings");
    assert_eq!(
        settings["skip_weekends"].as_bool().expect("skip_weekends"),
        expected
    );
}

#[then(expr = "standup lookback hours should be {int}")]
fn then_standup_lookback_hours_should_be(world: &mut KanbusWorld, hours: u32) {
    assert_eq!(
        world
            .resolved_standup_lookback_hours
            .expect("lookback hours"),
        hours
    );
}

#[then(expr = "Python and Rust should agree on window {string}")]
fn then_python_rust_agree_on_window(world: &mut KanbusWorld, window: String) {
    let python = world.python_window_settings.as_ref().expect("python");
    let rust = world.rust_window_settings.as_ref().expect("rust");
    assert_eq!(python["window"].as_str().expect("python window"), window);
    assert_eq!(rust["window"].as_str().expect("rust window"), window);
}

#[then(expr = "Python and Rust should agree on lookback hours {int}")]
fn then_python_rust_agree_on_lookback_hours(world: &mut KanbusWorld, hours: u32) {
    let python = world.python_window_settings.as_ref().expect("python");
    let rust = world.rust_window_settings.as_ref().expect("rust");
    assert_eq!(
        python["lookback_hours"].as_u64().expect("python hours") as u32,
        hours
    );
    assert_eq!(
        rust["lookback_hours"].as_u64().expect("rust hours") as u32,
        hours
    );
}

#[when(regex = r#"^I POST \"([^\"]+)\" with JSON:$"#)]
fn when_post_with_json(world: &mut KanbusWorld, path: String, step: &Step) {
    world.last_post_path = Some(path);
    let text = step.docstring().expect("json docstring");
    world.last_post_json = Some(serde_json::from_str(text).expect("parse post json"));
}

#[then(
    regex = r#"^the response should accept fields \"([^\"]+)\", \"([^\"]+)\", and \"([^\"]+)\"$"#
)]
fn then_response_accepts_fields(
    world: &mut KanbusWorld,
    field_a: String,
    field_b: String,
    field_c: String,
) {
    let payload = world.last_post_json.as_ref().expect("post json").clone();
    let accepted: StandupGenerateRequest =
        serde_json::from_value(payload.clone()).expect("validate standup request");
    let mut present = HashMap::new();
    present.insert("window", accepted.window.is_some());
    present.insert("lookback", accepted.lookback.is_some());
    present.insert("skip_weekends", accepted.skip_weekends.is_some());
    for field in [field_a, field_b, field_c] {
        assert!(
            present.get(field.as_str()).copied().unwrap_or(false),
            "missing accepted field: {field}"
        );
    }

    let Some(port) = world.console_port else {
        return;
    };
    let url = format!("http://127.0.0.1:{port}/api/standup");
    let response = std::thread::spawn(move || {
        reqwest::blocking::Client::new()
            .post(url)
            .json(&payload)
            .send()
    })
    .join()
    .expect("http thread")
    .expect("post standup");
    assert_eq!(response.status().as_u16(), 200);
}

#[then(expr = "command help should mention {string}")]
fn then_command_help_should_mention(world: &mut KanbusWorld, flag: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains(&flag), "help missing {flag}");
}
