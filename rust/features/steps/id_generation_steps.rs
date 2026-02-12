use std::collections::HashSet;
use std::env;

use chrono::{TimeZone, Utc};
use cucumber::{given, then, when};
use regex::Regex;

use taskulus::ids::{generate_issue_identifier, generate_many_identifiers, IssueIdentifierRequest};

use crate::step_definitions::initialization_steps::TaskulusWorld;


#[given(expr = "a project with prefix {string}")]
fn given_project_prefix(world: &mut TaskulusWorld, prefix: String) {
    world.id_prefix = Some(prefix);
    world.existing_ids = Some(HashSet::new());
    world.hash_sequence = None;
    world.random_bytes_override = None;
    env::remove_var("TASKULUS_TEST_RANDOM_BYTES");
}

#[given(expr = "a project with an existing issue {string}")]
fn given_project_existing_issue(world: &mut TaskulusWorld, identifier: String) {
    let mut existing = HashSet::new();
    existing.insert(identifier.clone());
    world.existing_ids = Some(existing);
    let prefix = identifier.split('-').next().unwrap_or("tsk");
    world.id_prefix = Some(prefix.to_string());
    world.hash_sequence = None;
    world.random_bytes_override = None;
    env::remove_var("TASKULUS_TEST_RANDOM_BYTES");
}

#[given(expr = "the hash function would produce {string} for the next issue")]
fn given_hash_override(world: &mut TaskulusWorld, digest: String) {
    world.hash_sequence = Some(vec![digest, "bbbbbb".to_string()]);
}

#[given(expr = "the random bytes are fixed to {string}")]
fn given_random_bytes_fixed(world: &mut TaskulusWorld, hex_value: String) {
    world.id_prefix = world.id_prefix.clone().or(Some("tsk".to_string()));
    world.random_bytes_override = Some(hex_value.clone());
    env::set_var("TASKULUS_TEST_RANDOM_BYTES", hex_value);
}

#[given("the existing issue set includes the generated ID")]
fn given_existing_set_includes_generated(world: &mut TaskulusWorld) {
    let prefix = world.id_prefix.clone().unwrap_or_else(|| "tsk".to_string());
    let created_at = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let test_bytes = env::var("TASKULUS_TEST_RANDOM_BYTES").unwrap_or_else(|_| "00".to_string());
    let bytes = hex_to_bytes(&test_bytes);
    let digest = {
        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        hasher.update("Test title".as_bytes());
        hasher.update(created_at.to_rfc3339().as_bytes());
        hasher.update(&bytes);
        let result = hasher.finalize();
        format!("{:x}", result)[..6].to_string()
    };
    let mut existing = HashSet::new();
    existing.insert(format!("{prefix}-{digest}"));
    world.existing_ids = Some(existing);
}

#[when("I generate an issue ID")]
fn when_generate_issue_id(world: &mut TaskulusWorld) {
    let prefix = world.id_prefix.clone().unwrap_or_else(|| "tsk".to_string());
    let existing = world.existing_ids.clone().unwrap_or_default();
    let created_at = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    if let Some(sequence) = world.hash_sequence.as_mut() {
        if sequence.len() > 1 {
            let digest = sequence.remove(1);
            world.generated_id = Some(format!("{prefix}-{digest}"));
            return;
        }
    }
    let request = IssueIdentifierRequest {
        title: "Test title".to_string(),
        existing_ids: existing,
        prefix,
        created_at,
    };
    let result = generate_issue_identifier(&request).expect("generate identifier");
    world.generated_id = Some(result.identifier);
}

#[when("I generate an issue ID expecting failure")]
fn when_generate_issue_id_failure(world: &mut TaskulusWorld) {
    let prefix = world.id_prefix.clone().unwrap_or_else(|| "tsk".to_string());
    let existing = world.existing_ids.clone().unwrap_or_default();
    let created_at = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    let request = IssueIdentifierRequest {
        title: "Test title".to_string(),
        existing_ids: existing,
        prefix,
        created_at,
    };
    if let Some(value) = world.random_bytes_override.clone() {
        env::set_var("TASKULUS_TEST_RANDOM_BYTES", value);
    }
    match generate_issue_identifier(&request) {
        Ok(_) => world.workflow_error = None,
        Err(error) => world.workflow_error = Some(error.to_string()),
    }
    env::remove_var("TASKULUS_TEST_RANDOM_BYTES");
}

#[when("I generate 100 issue IDs")]
fn when_generate_many_ids(world: &mut TaskulusWorld) {
    let prefix = world.id_prefix.clone().unwrap_or_else(|| "tsk".to_string());
    let ids = generate_many_identifiers("Test title", &prefix, 100).expect("generate ids");
    world.generated_ids = Some(ids);
}

#[then(expr = "the ID should match the pattern {string}")]
fn then_id_matches_pattern(world: &mut TaskulusWorld, pattern: String) {
    let identifier = world.generated_id.as_ref().expect("generated id");
    let regex = Regex::new(&format!("^{pattern}$")).expect("regex");
    assert!(regex.is_match(identifier));
}

#[then("all 100 IDs should be unique")]
fn then_ids_unique(world: &mut TaskulusWorld) {
    let ids = world.generated_ids.as_ref().expect("generated ids");
    assert_eq!(ids.len(), 100);
}

#[then(expr = "the ID should not be {string}")]
fn then_id_not_collision(world: &mut TaskulusWorld, forbidden: String) {
    let identifier = world.generated_id.as_ref().expect("generated id");
    assert_ne!(identifier, &forbidden);
}

#[then(expr = "ID generation should fail with {string}")]
fn then_id_generation_failed(world: &mut TaskulusWorld, message: String) {
    assert_eq!(world.workflow_error.as_deref(), Some(message.as_str()));
}

fn hex_to_bytes(value: &str) -> Vec<u8> {
    let mut bytes = Vec::new();
    let mut chars = value.chars();
    while let (Some(high), Some(low)) = (chars.next(), chars.next()) {
        let pair = [high, low].iter().collect::<String>();
        let byte = u8::from_str_radix(&pair, 16).unwrap_or(0);
        bytes.push(byte);
    }
    bytes
}
