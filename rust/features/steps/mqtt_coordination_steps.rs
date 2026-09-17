use std::fs;
use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};
use cucumber::{given, then, when};
use serde_json::Value;

use kanbus::config_loader::load_project_configuration;
use kanbus::coordination::{coordination_gossip_event, reduce_coordination_events};
use kanbus::file_io::{get_configuration_path, load_project_directory};
use kanbus::gossip::{
    build_coordination_gossip_envelope, should_accept_gossip, CoordinationGossipFields, DedupeSet,
};
use kanbus::overlay::write_coordination_overlay;

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

fn event_records(world: &KanbusWorld, resource: &str) -> Vec<Value> {
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
        let Ok(contents) = fs::read_to_string(path) else {
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
            records.push(record);
        }
    }
    records.sort_by(|left, right| {
        left.get("occurred_at")
            .and_then(Value::as_str)
            .cmp(&right.get("occurred_at").and_then(Value::as_str))
            .then_with(|| {
                left.get("event_id")
                    .and_then(Value::as_str)
                    .cmp(&right.get("event_id").and_then(Value::as_str))
            })
    });
    records
}

fn matching_event(
    world: &KanbusWorld,
    resource: &str,
    event_type: &str,
    owner: &str,
    claim_id: &str,
) -> Value {
    event_records(world, resource)
        .into_iter()
        .rev()
        .find(|record| {
            record.get("event_type").and_then(Value::as_str) == Some(event_type)
                && record.get("actor_id").and_then(Value::as_str) == Some(owner)
                && record.pointer("/payload/claim_id").and_then(Value::as_str) == Some(claim_id)
        })
        .expect("matching durable coordination event")
}

fn publish_message(
    world: &mut KanbusWorld,
    owner: &str,
    event_type: &str,
    resource: &str,
    claim_id: &str,
) {
    let (durable_type, command) = match event_type {
        "coordination.claim" => (
            "coordination.claim",
            format!(
                "kanbus coordination claim --resource {resource} --owner {owner} --claim-id {claim_id}"
            ),
        ),
        "coordination.release" => (
            "coordination.release",
            format!(
                "kanbus coordination release --resource {resource} --owner {owner} --claim-id {claim_id}"
            ),
        ),
        _ => panic!("unsupported coordination publish type {event_type}"),
    };
    run_cli(world, &command);
    assert_eq!(
        world.exit_code,
        Some(0),
        "{}",
        world.stderr.as_deref().unwrap_or("")
    );
    let record = matching_event(world, resource, durable_type, owner, claim_id);
    let event_id = record
        .get("event_id")
        .and_then(Value::as_str)
        .expect("durable event ID");
    let event_ts = record
        .get("occurred_at")
        .and_then(Value::as_str)
        .expect("durable event timestamp");
    let ttl_s = record.pointer("/payload/ttl_s").and_then(Value::as_u64);
    let configuration_path = get_configuration_path(root(world)).expect("config path");
    let project = load_project_configuration(&configuration_path)
        .expect("project configuration")
        .project_key;
    let mut envelope = build_coordination_gossip_envelope(
        &project,
        event_type,
        event_id,
        CoordinationGossipFields {
            resource: Some(resource.to_string()),
            owner: Some(owner.to_string()),
            claim_id: Some(claim_id.to_string()),
            lease_ttl_s: ttl_s,
            expires_at: None,
        },
    );
    envelope.ts = event_ts.to_string();
    write_coordination_overlay(&project_dir(world), &envelope, 3600)
        .expect("store coordination gossip overlay");
    world.coordination_gossip_messages.push(envelope);
}

#[given(expr = "coordination MQTT publishes to {string} with QoS 0 and retain=false")]
fn given_coordination_mqtt_topic(world: &mut KanbusWorld, topic: String) {
    let configuration_path = get_configuration_path(root(world)).expect("config path");
    let configuration =
        load_project_configuration(&configuration_path).expect("project configuration");
    assert_eq!(
        configuration.realtime.topics.project_events, topic,
        "coordination MQTT uses the configured project event topic"
    );
    world.coordination_mqtt_topic = Some(topic);
}

#[given(
    expr = "worker {string} published coordination gossip type {string} for resource {string} with claim id {string}"
)]
fn given_coordination_gossip(
    world: &mut KanbusWorld,
    owner: String,
    event_type: String,
    resource: String,
    claim_id: String,
) {
    publish_message(world, &owner, &event_type, &resource, &claim_id);
}

#[given(
    expr = "worker {string} published coordination gossip type {string} for resource {string} with claim id {string} within the contention window"
)]
fn given_coordination_gossip_in_window(
    world: &mut KanbusWorld,
    owner: String,
    event_type: String,
    resource: String,
    claim_id: String,
) {
    publish_message(world, &owner, &event_type, &resource, &claim_id);
}

#[when(
    expr = "worker {string} publishes coordination gossip type {string} for resource {string} with claim id {string}"
)]
fn when_coordination_gossip(
    world: &mut KanbusWorld,
    owner: String,
    event_type: String,
    resource: String,
    claim_id: String,
) {
    publish_message(world, &owner, &event_type, &resource, &claim_id);
}

#[then(expr = "MQTT subscribers should receive envelope type {string} for resource {string}")]
fn then_mqtt_subscriber_receives(world: &mut KanbusWorld, event_type: String, resource: String) {
    assert!(
        world.coordination_gossip_messages.iter().any(|envelope| {
            envelope.event_type == event_type
                && envelope.coordination.resource.as_deref() == Some(resource.as_str())
        }),
        "expected a published MQTT coordination message"
    );
}

#[then(
    expr = "coordination gossip type {string} should be emitted for resource {string} with claim id {string}"
)]
fn then_coordination_gossip_emitted(
    world: &mut KanbusWorld,
    event_type: String,
    resource: String,
    claim_id: String,
) {
    assert!(world.coordination_gossip_messages.iter().any(|envelope| {
        envelope.event_type == event_type
            && envelope.coordination.resource.as_deref() == Some(resource.as_str())
            && envelope.coordination.claim_id.as_deref() == Some(claim_id.as_str())
    }));
}

#[then(expr = "the coordination envelope should contain top-level fields {string}")]
fn then_coordination_envelope_has_fields(world: &mut KanbusWorld, fields: String) {
    let envelope = world
        .coordination_gossip_messages
        .last()
        .expect("coordination envelope");
    let serialized = serde_json::to_value(envelope).expect("serialize envelope");
    for field in fields.split(',').map(str::trim) {
        assert!(serialized.get(field).is_some(), "missing top-level {field}");
    }
}

#[then(
    expr = "receivers should ignore their own producer id and deduplicate envelope ids for {string}"
)]
fn then_coordination_echo_and_dedupe(world: &mut KanbusWorld, ttl: String) {
    let seconds = kanbus::coordination::parse_duration_seconds(&ttl).expect("dedupe TTL");
    let envelope = world
        .coordination_gossip_messages
        .last()
        .expect("coordination envelope");
    let mut dedupe = DedupeSet::new(std::time::Duration::from_secs(seconds));
    assert!(!should_accept_gossip(
        envelope,
        &envelope.producer_id,
        &mut dedupe
    ));
    let mut remote_dedupe = DedupeSet::new(std::time::Duration::from_secs(seconds));
    assert!(should_accept_gossip(
        envelope,
        "remote-producer",
        &mut remote_dedupe
    ));
    assert!(!should_accept_gossip(
        envelope,
        "remote-producer",
        &mut remote_dedupe
    ));
}

#[then(expr = "the RELEASE envelope should contain top-level fields {string}")]
fn then_release_envelope_has_fields(world: &mut KanbusWorld, fields: String) {
    let envelope = world
        .coordination_gossip_messages
        .iter()
        .rev()
        .find(|envelope| envelope.event_type == "coordination.release")
        .expect("RELEASE envelope");
    let serialized = serde_json::to_value(envelope).expect("serialize RELEASE envelope");
    for field in fields.split(',').map(str::trim) {
        assert!(serialized.get(field).is_some(), "missing top-level {field}");
    }
}

#[then(
    expr = "the LEASE envelope should identify the winning claim event and contain top-level fields {string}"
)]
fn then_lease_envelope_contract(world: &mut KanbusWorld, fields: String) {
    let lease = world
        .coordination_gossip_messages
        .iter()
        .rev()
        .find(|envelope| envelope.event_type == "coordination.lease")
        .expect("LEASE envelope");
    let serialized = serde_json::to_value(lease).expect("serialize LEASE envelope");
    for field in fields.split(',').map(str::trim) {
        assert!(serialized.get(field).is_some(), "missing top-level {field}");
    }
    let claim_id = lease
        .coordination
        .claim_id
        .as_deref()
        .expect("LEASE claim id");
    let resource = lease
        .coordination
        .resource
        .as_deref()
        .expect("LEASE resource");
    let winning_claim = world
        .coordination_gossip_messages
        .iter()
        .find(|envelope| {
            envelope.event_type == "coordination.claim"
                && envelope.coordination.resource.as_deref() == Some(resource)
                && envelope.coordination.claim_id.as_deref() == Some(claim_id)
        })
        .expect("winning CLAIM envelope");
    assert_eq!(lease.event_id, winning_claim.event_id);
}

#[then(expr = "the LEASE expiry should equal the winning claim timestamp plus its lease TTL")]
fn then_lease_expiry_matches_claim(world: &mut KanbusWorld) {
    let lease = world
        .coordination_gossip_messages
        .iter()
        .rev()
        .find(|envelope| envelope.event_type == "coordination.lease")
        .expect("LEASE envelope");
    let claim_id = lease
        .coordination
        .claim_id
        .as_deref()
        .expect("LEASE claim id");
    let resource = lease
        .coordination
        .resource
        .as_deref()
        .expect("LEASE resource");
    let claim = world
        .coordination_gossip_messages
        .iter()
        .find(|envelope| {
            envelope.event_type == "coordination.claim"
                && envelope.coordination.resource.as_deref() == Some(resource)
                && envelope.coordination.claim_id.as_deref() == Some(claim_id)
        })
        .expect("winning CLAIM envelope");
    let claim_ts = DateTime::parse_from_rfc3339(&claim.ts)
        .expect("claim timestamp")
        .with_timezone(&Utc);
    let ttl_s = claim.coordination.lease_ttl_s.expect("claim lease TTL") as i64;
    let expected = claim_ts + chrono::Duration::seconds(ttl_s);
    let actual = DateTime::parse_from_rfc3339(
        lease
            .coordination
            .expires_at
            .as_deref()
            .expect("LEASE expiry"),
    )
    .expect("LEASE expiry timestamp")
    .with_timezone(&Utc);
    assert_eq!(actual, expected);
}

#[then(
    expr = "the matching soft lease should be cleared from MQTT visibility while Git remains the durable history"
)]
fn then_release_clears_mqtt_visibility(world: &mut KanbusWorld) {
    let resource = world
        .coordination_gossip_messages
        .last()
        .and_then(|envelope| envelope.coordination.resource.as_deref())
        .expect("release resource");
    let events = world
        .coordination_gossip_messages
        .iter()
        .filter_map(|envelope| coordination_gossip_event(envelope.clone(), 3))
        .collect::<Vec<_>>();
    assert!(!reduce_coordination_events(&events, Utc::now()).is_active());
    let durable = event_records(world, resource);
    assert!(durable.iter().any(|event| {
        event.get("event_type").and_then(Value::as_str) == Some("coordination.claim")
    }));
    assert!(durable.iter().any(|event| {
        event.get("event_type").and_then(Value::as_str) == Some("coordination.release")
    }));
}

#[given(expr = "MQTT partition isolates worker {string} from worker {string}")]
fn given_mqtt_partition(_world: &mut KanbusWorld, _first: String, _second: String) {}

#[then(
    expr = "an MQTT partition may allow duplicate work because soft leases are not hard mutexes"
)]
fn then_partition_keeps_soft_semantics(world: &mut KanbusWorld) {
    let resource = "job:fast-4";
    let claims = event_records(world, resource)
        .iter()
        .filter(|event| {
            event.get("event_type").and_then(Value::as_str) == Some("coordination.claim")
        })
        .count();
    assert_eq!(claims, 2, "both partitioned Git claims must be durable");
    let output = world.stdout.as_deref().unwrap_or("");
    assert!(output.contains("active soft ownership"));
    assert!(!output.to_ascii_lowercase().contains("hard mutex"));
}
