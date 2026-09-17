use std::fs;
use std::path::{Path, PathBuf};

use chrono::{Duration, Utc};
use cucumber::{given, then, when};
use serde_json::Value;

use kanbus::coordination::{
    coordination_gossip_event, coordination_lease_gossip_if_closed, parse_duration_seconds,
    publish_coordination_lease_if_ready,
};
use kanbus::file_io::{get_configuration_path, load_project_directory};
use kanbus::gossip::{build_coordination_gossip_envelope, CoordinationGossipFields};

use crate::step_definitions::initialization_steps::{
    run_from_args_in_blocking_thread, KanbusWorld,
};

fn root(world: &KanbusWorld) -> &Path {
    world
        .working_directory
        .as_deref()
        .expect("working directory not set")
}

fn project_dir(world: &KanbusWorld) -> PathBuf {
    load_project_directory(root(world)).expect("project directory")
}

fn update_coordination_config(world: &KanbusWorld, key: &str, value: serde_yaml::Value) {
    let path = get_configuration_path(root(world)).expect("configuration path");
    let contents = fs::read_to_string(&path).expect("read project config");
    let mut configuration: serde_yaml::Value =
        serde_yaml::from_str(&contents).expect("parse project config");
    let root = configuration.as_mapping_mut().expect("config mapping");
    let coordination_key = serde_yaml::Value::String("coordination".to_string());
    if !root.contains_key(&coordination_key) {
        root.insert(
            coordination_key.clone(),
            serde_yaml::Value::Mapping(serde_yaml::Mapping::new()),
        );
    }
    let coordination = root
        .get_mut(&coordination_key)
        .and_then(serde_yaml::Value::as_mapping_mut)
        .expect("coordination mapping");
    coordination.insert(serde_yaml::Value::String(key.to_string()), value);
    fs::write(
        path,
        serde_yaml::to_string(&configuration).expect("serialize config"),
    )
    .expect("write project config");
}

fn run_cli(world: &mut KanbusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse command");
    let cwd = world
        .working_directory
        .as_deref()
        .expect("working directory not set");
    std::env::set_var("KANBUS_NO_DAEMON", "1");
    let previous_clock = std::env::var_os("KANBUS_TEST_COORDINATION_NOW");
    if let Some(clock) = &world.coordination_now_override {
        std::env::set_var("KANBUS_TEST_COORDINATION_NOW", clock);
    }
    match run_from_args_in_blocking_thread(args, cwd) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(output.stderr);
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
    match previous_clock {
        Some(value) => std::env::set_var("KANBUS_TEST_COORDINATION_NOW", value),
        None => std::env::remove_var("KANBUS_TEST_COORDINATION_NOW"),
    }
    world.last_command = Some(command.to_string());
}

fn set_coordination_clock(world: &mut KanbusWorld, timestamp: String) {
    if world.coordination_original_clock.is_none() {
        world.coordination_original_clock = Some(std::env::var_os("KANBUS_TEST_COORDINATION_NOW"));
    }
    std::env::set_var("KANBUS_TEST_COORDINATION_NOW", &timestamp);
    world.coordination_now_override = Some(timestamp);
}

fn event_records(world: &KanbusWorld, resource: &str) -> Vec<(PathBuf, Value)> {
    let events_dir = project_dir(world).join("events");
    let Ok(entries) = fs::read_dir(events_dir) else {
        return Vec::new();
    };
    let mut records = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|extension| extension.to_str()) != Some("json") {
            continue;
        }
        let Ok(contents) = fs::read_to_string(&path) else {
            continue;
        };
        let Ok(record) = serde_json::from_str::<Value>(&contents) else {
            continue;
        };
        if record.get("issue_id").and_then(Value::as_str) == Some(resource)
            && record
                .get("event_type")
                .and_then(Value::as_str)
                .is_some_and(|kind| kind.starts_with("coordination."))
        {
            records.push((path, record));
        }
    }
    records.sort_by(|left, right| left.0.cmp(&right.0));
    records
}

fn rewrite_latest_claim(world: &KanbusWorld, resource: &str, claim_id: &str, expiry: &str) {
    let records = event_records(world, resource);
    let (path, mut record) = records
        .into_iter()
        .rev()
        .find(|(_, record)| {
            record.get("event_type").and_then(Value::as_str) == Some("coordination.claim")
                && record.pointer("/payload/claim_id").and_then(Value::as_str) == Some(claim_id)
        })
        .expect("matching coordination claim event");
    let ttl_s = record
        .pointer("/payload/ttl_s")
        .and_then(Value::as_u64)
        .unwrap_or(300);
    let expiry_time = chrono::DateTime::parse_from_rfc3339(expiry)
        .expect("expiry timestamp")
        .with_timezone(&Utc);
    let occurred_at = (expiry_time - Duration::seconds(ttl_s as i64))
        .to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
    let event_id = record
        .get("event_id")
        .and_then(Value::as_str)
        .expect("event id")
        .to_string();
    record["occurred_at"] = Value::String(occurred_at.clone());
    record["payload"]["lease_expires_at"] = Value::String(expiry.to_string());
    let new_path =
        path.parent()
            .expect("events directory")
            .join(kanbus::event_history::event_filename(
                &occurred_at,
                &event_id,
            ));
    fs::write(
        &new_path,
        serde_json::to_string_pretty(&record).expect("serialize event"),
    )
    .expect("update claim expiry");
    if path != new_path {
        fs::remove_file(path).expect("rename adjusted event");
    }
}

fn seed_claim(world: &mut KanbusWorld, resource: &str, owner: &str, claim_id: &str) {
    run_cli(
        world,
        &format!(
            "kanbus coordination claim --resource {resource} --owner {owner} --claim-id {claim_id}"
        ),
    );
    assert_eq!(
        world.exit_code,
        Some(0),
        "{}",
        world.stderr.as_deref().unwrap_or("")
    );
}

fn claim_count(world: &KanbusWorld, resource: &str) -> usize {
    event_records(world, resource)
        .iter()
        .filter(|(_, record)| {
            record.get("event_type").and_then(Value::as_str) == Some("coordination.claim")
        })
        .count()
}

#[given(
    expr = "coordination is configured with contention window {string} and default lease TTL {string}"
)]
fn given_coordination_durations(world: &mut KanbusWorld, window: String, ttl: String) {
    update_coordination_config(
        world,
        "contention_window",
        serde_yaml::Value::String(window),
    );
    update_coordination_config(world, "default_lease_ttl", serde_yaml::Value::String(ttl));
}

#[given(expr = "coordination is configured with default lease TTL {string}")]
fn given_coordination_default_ttl(world: &mut KanbusWorld, ttl: String) {
    update_coordination_config(world, "default_lease_ttl", serde_yaml::Value::String(ttl));
}

#[given(expr = "coordination providers are configured as {string}")]
fn given_coordination_providers(world: &mut KanbusWorld, providers: String) {
    update_coordination_config(
        world,
        "providers",
        serde_yaml::Value::Sequence(
            providers
                .split(',')
                .map(|value| serde_yaml::Value::String(value.trim().to_string()))
                .collect(),
        ),
    );
}

#[given(expr = "coordination mutex API endpoint is unset")]
fn given_mutex_api_unset(_world: &mut KanbusWorld) {}

#[given(expr = "realtime MQTT broker is unreachable")]
fn given_unreachable_mqtt_broker(_world: &mut KanbusWorld) {}

#[then(expr = "issue {string} should have assignee unset")]
fn then_issue_assignee_unset(world: &mut KanbusWorld, identifier: String) {
    let issue_path = project_dir(world)
        .join("issues")
        .join(format!("{identifier}.json"));
    let issue: Value =
        serde_json::from_slice(&fs::read(issue_path).expect("read issue")).expect("parse issue");
    assert!(issue.get("assignee").is_none_or(Value::is_null));
}

#[given(
    expr = "two workers submit competing coordination claims for resource {string} within the contention window"
)]
fn given_two_competing_claims(world: &mut KanbusWorld, resource: String) {
    seed_claim(world, &resource, "worker-b", "claim-b");
    seed_claim(world, &resource, "worker-a", "claim-a");
}

#[given(expr = "worker {string} submits coordination claim id {string} for resource {string}")]
fn given_worker_claim(world: &mut KanbusWorld, owner: String, claim_id: String, resource: String) {
    seed_claim(world, &resource, &owner, &claim_id);
}

#[given(
    expr = "worker {string} submits coordination claim id {string} for resource {string} within the contention window"
)]
fn given_worker_claim_in_window(
    world: &mut KanbusWorld,
    owner: String,
    claim_id: String,
    resource: String,
) {
    seed_claim(world, &resource, &owner, &claim_id);
}

#[given(expr = "coordination lease {string} is held by owner {string} with claim id {string}")]
fn given_held_lease(world: &mut KanbusWorld, resource: String, owner: String, claim_id: String) {
    seed_claim(world, &resource, &owner, &claim_id);
    let configuration_path = get_configuration_path(root(world)).expect("config path");
    let configuration = kanbus::config_loader::load_project_configuration(&configuration_path)
        .expect("project configuration");
    if configuration
        .coordination
        .providers
        .iter()
        .any(|provider| provider == "mqtt")
    {
        let claim = event_records(world, &resource)
            .into_iter()
            .rev()
            .find(|(_, record)| {
                record.get("event_type").and_then(Value::as_str) == Some("coordination.claim")
                    && record.pointer("/payload/owner").and_then(Value::as_str)
                        == Some(owner.as_str())
                    && record.pointer("/payload/claim_id").and_then(Value::as_str)
                        == Some(claim_id.as_str())
            })
            .map(|(_, record)| record)
            .expect("durable held claim");
        let event_id = claim
            .get("event_id")
            .and_then(Value::as_str)
            .expect("claim event ID");
        let occurred_at = claim
            .get("occurred_at")
            .and_then(Value::as_str)
            .expect("claim timestamp");
        let ttl_s = claim
            .pointer("/payload/ttl_s")
            .and_then(Value::as_u64)
            .expect("claim TTL");
        let mut envelope = build_coordination_gossip_envelope(
            &configuration.project_key,
            "coordination.claim",
            event_id,
            CoordinationGossipFields {
                resource: Some(resource.clone()),
                owner: Some(owner),
                claim_id: Some(claim_id),
                lease_ttl_s: Some(ttl_s),
                expires_at: None,
            },
        );
        envelope.ts = occurred_at.to_string();
        kanbus::overlay::write_coordination_overlay(&project_dir(world), &envelope, 3600)
            .expect("write held-claim MQTT overlay");
        world.coordination_gossip_messages.push(envelope);
    }
}

#[given(expr = "the lease expires at {string}")]
fn given_lease_expiry(world: &mut KanbusWorld, expiry: String) {
    let command = world
        .last_command
        .as_deref()
        .expect("preceding claim command");
    let args = shell_words::split(command).expect("parse prior command");
    let value = |flag: &str| {
        args.iter()
            .position(|arg| arg == flag)
            .and_then(|index| args.get(index + 1))
            .cloned()
            .expect("prior command argument")
    };
    rewrite_latest_claim(world, &value("--resource"), &value("--claim-id"), &expiry);
    let expiry_time = chrono::DateTime::parse_from_rfc3339(&expiry)
        .expect("expiry timestamp")
        .with_timezone(&Utc);
    set_coordination_clock(
        world,
        (expiry_time - Duration::seconds(1)).to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
    );
}

#[given(expr = "coordination lease {string} expired at {string}")]
fn given_expired_lease(world: &mut KanbusWorld, resource: String, expiry: String) {
    seed_claim(world, &resource, "worker-expired", "claim-expired");
    rewrite_latest_claim(world, &resource, "claim-expired", &expiry);
    let expiry_time = chrono::DateTime::parse_from_rfc3339(&expiry)
        .expect("expiry timestamp")
        .with_timezone(&Utc);
    set_coordination_clock(
        world,
        (expiry_time + Duration::seconds(1)).to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
    );
}

#[given(expr = "no renewal occurs before lease expiration")]
fn given_no_renewal(_world: &mut KanbusWorld) {}

#[when(expr = "worker {string} runs {string}")]
fn when_worker_runs(world: &mut KanbusWorld, _worker: String, command: String) {
    run_cli(world, &command);
}

#[when(expr = "worker {string} runs {string} after a simulated Git partition heals")]
fn when_worker_runs_after_partition(world: &mut KanbusWorld, _worker: String, command: String) {
    run_cli(world, &command);
}

#[when(
    expr = "two workers submit competing coordination claims for resource {string} within the contention window"
)]
fn when_two_workers_claim(world: &mut KanbusWorld, resource: String) {
    seed_claim(world, &resource, "worker-b", "claim-b");
    seed_claim(world, &resource, "worker-a", "claim-a");
}

#[when(expr = "the contention window closes for resource {string}")]
fn when_contention_window_closes(world: &mut KanbusWorld, resource: String) {
    let first_claim = event_records(world, &resource)
        .into_iter()
        .filter(|(_, record)| {
            record.get("event_type").and_then(Value::as_str) == Some("coordination.claim")
        })
        .min_by_key(|(_, record)| {
            record
                .get("occurred_at")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string()
        })
        .map(|(_, record)| record)
        .expect("first claim event");
    let started_at = chrono::DateTime::parse_from_rfc3339(
        first_claim
            .get("occurred_at")
            .and_then(Value::as_str)
            .expect("occurred_at"),
    )
    .expect("claim timestamp")
    .with_timezone(&Utc);
    let window_s = first_claim
        .pointer("/payload/contention_window_s")
        .and_then(Value::as_u64)
        .unwrap_or(5);
    let closes_at = started_at + Duration::seconds(window_s as i64 + 1);
    let closes_at_text = closes_at.to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
    set_coordination_clock(world, closes_at_text.clone());

    let mqtt_claims = world
        .coordination_gossip_messages
        .iter()
        .filter(|envelope| {
            envelope.event_type == "coordination.claim"
                && envelope.coordination.resource.as_deref() == Some(resource.as_str())
        })
        .filter_map(|envelope| coordination_gossip_event(envelope.clone(), window_s))
        .collect::<Vec<_>>();
    if let Some((event_id, fields)) =
        coordination_lease_gossip_if_closed(&mqtt_claims, closes_at, &resource)
    {
        let _ = publish_coordination_lease_if_ready(root(world), &resource, closes_at)
            .expect("publish MQTT lease when contention closes");
        let configuration_path = get_configuration_path(root(world)).expect("config path");
        let configuration = kanbus::config_loader::load_project_configuration(&configuration_path)
            .expect("project configuration");
        let mut envelope = build_coordination_gossip_envelope(
            &configuration.project_key,
            "coordination.lease",
            &event_id,
            fields,
        );
        envelope.ts = closes_at_text;
        world.coordination_gossip_messages.push(envelope);
    }
}

#[when(expr = "simulated time advances past the lease expiration")]
fn when_advance_past_expiry(world: &mut KanbusWorld) {
    let command = world
        .last_command
        .as_deref()
        .expect("preceding claim command");
    let args = shell_words::split(command).expect("parse prior command");
    let resource = args
        .iter()
        .position(|arg| arg == "--resource")
        .and_then(|index| args.get(index + 1))
        .expect("resource argument");
    let claim_id = args
        .iter()
        .position(|arg| arg == "--claim-id")
        .and_then(|index| args.get(index + 1))
        .expect("claim id argument");
    let expiry = event_records(world, resource)
        .into_iter()
        .rev()
        .find(|(_, record)| {
            record.get("event_type").and_then(Value::as_str) == Some("coordination.claim")
                && record.pointer("/payload/claim_id").and_then(Value::as_str)
                    == Some(claim_id.as_str())
        })
        .and_then(|(_, record)| {
            record
                .pointer("/payload/lease_expires_at")
                .and_then(Value::as_str)
                .map(str::to_string)
        })
        .expect("lease expiry");
    let expiry = chrono::DateTime::parse_from_rfc3339(&expiry)
        .expect("expiry timestamp")
        .with_timezone(&Utc);
    set_coordination_clock(
        world,
        (expiry + Duration::seconds(1)).to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
    );
}

#[then(expr = "coordination lease {string} should have owner {string}")]
fn then_lease_owner(world: &mut KanbusWorld, resource: String, owner: String) {
    run_cli(
        world,
        &format!("kanbus coordination inspect --resource {resource}"),
    );
    assert!(world
        .stdout
        .as_deref()
        .unwrap_or("")
        .contains(&format!("owner: {owner}")));
}

#[then(expr = "coordination lease {string} should have claim id {string}")]
fn then_lease_claim_id(world: &mut KanbusWorld, resource: String, claim_id: String) {
    run_cli(
        world,
        &format!("kanbus coordination inspect --resource {resource}"),
    );
    assert!(world
        .stdout
        .as_deref()
        .unwrap_or("")
        .contains(&format!("claim_id: {claim_id}")));
}

#[then(expr = "both claims are recorded in the contention window for resource {string}")]
fn then_two_claims_recorded(world: &mut KanbusWorld, resource: String) {
    assert_eq!(claim_count(world, &resource), 2);
}

#[then(expr = "the winning lease TTL should be {string} not {string}")]
fn then_ttl_independent(world: &mut KanbusWorld, ttl: String, window: String) {
    let resource = world
        .last_command
        .as_deref()
        .and_then(|command| shell_words::split(command).ok())
        .and_then(|args| {
            args.iter()
                .position(|arg| arg == "--resource")
                .and_then(|i| args.get(i + 1))
                .cloned()
        })
        .expect("resource from last claim");
    let expected_ttl = parse_duration_seconds(&ttl).expect("TTL");
    let expected_window = parse_duration_seconds(&window).expect("window");
    let winner = event_records(world, &resource)
        .into_iter()
        .find(|(_, event)| {
            event.pointer("/payload/owner").and_then(Value::as_str) == Some("worker-a")
        })
        .map(|(_, event)| event)
        .expect("winner event");
    assert_eq!(
        winner.pointer("/payload/ttl_s").and_then(Value::as_u64),
        Some(expected_ttl)
    );
    assert_eq!(
        winner
            .pointer("/payload/contention_window_s")
            .and_then(Value::as_u64),
        Some(expected_window)
    );
}

#[then(expr = "coordination lease {string} should expire after {string}")]
fn then_lease_expiry_after(world: &mut KanbusWorld, resource: String, timestamp: String) {
    run_cli(
        world,
        &format!("kanbus coordination inspect --resource {resource}"),
    );
    let output = world.stdout.as_deref().unwrap_or("");
    let expiry = output
        .lines()
        .find_map(|line| line.strip_prefix("expires_at: "))
        .expect("active lease expiry");
    let actual = chrono::DateTime::parse_from_rfc3339(expiry).expect("actual timestamp");
    let expected = chrono::DateTime::parse_from_rfc3339(&timestamp).expect("expected timestamp");
    assert!(actual > expected, "{actual} should be after {expected}");
}

#[then(expr = "coordination lease {string} should not be active")]
fn then_lease_not_active(world: &mut KanbusWorld, resource: String) {
    run_cli(
        world,
        &format!("kanbus coordination inspect --resource {resource}"),
    );
    assert!(world
        .stdout
        .as_deref()
        .unwrap_or("")
        .contains("state: eligible"));
}

#[then(expr = "coordination provider used should be {string}")]
fn then_provider_used(world: &mut KanbusWorld, provider: String) {
    assert!(world
        .stdout
        .as_deref()
        .unwrap_or("")
        .contains(&format!("provider: {provider}")));
}

#[then(expr = "the command exit code should be {int}")]
fn then_command_exit_code(world: &mut KanbusWorld, code: i32) {
    assert_eq!(world.exit_code, Some(code));
}

#[then(expr = "both coordination claims for resource {string} should succeed")]
fn then_both_claims_succeed(world: &mut KanbusWorld, resource: String) {
    assert_eq!(claim_count(world, &resource), 2);
    assert_eq!(world.exit_code, Some(0));
}

#[then(
    expr = "coordination inspect for resource {string} should report soft ownership not hard mutex"
)]
fn then_soft_ownership(world: &mut KanbusWorld, resource: String) {
    run_cli(
        world,
        &format!("kanbus coordination inspect --resource {resource}"),
    );
    let output = world.stdout.as_deref().unwrap_or("");
    assert!(output.contains("state: active soft ownership"));
    assert!(!output.to_ascii_lowercase().contains("hard mutex"));
}

#[then(expr = "Git history for resource {string} should contain both claim events")]
fn then_git_has_two_claims(world: &mut KanbusWorld, resource: String) {
    assert_eq!(claim_count(world, &resource), 2);
}
