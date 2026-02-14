use std::collections::HashSet;

use cucumber::{given, then, when};
use regex::Regex;

use kanbus::ids::{
    generate_issue_identifier, generate_many_identifiers, set_test_uuid_sequence,
    IssueIdentifierRequest,
};
use uuid::Uuid;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given(expr = "a project with project key {string}")]
fn given_project_key(world: &mut KanbusWorld, project_key: String) {
    world.id_prefix = Some(project_key);
    world.existing_ids = Some(HashSet::new());
}

#[given(expr = "a project with an existing issue {string}")]
fn given_project_existing_issue(world: &mut KanbusWorld, identifier: String) {
    let mut existing = HashSet::new();
    existing.insert(identifier.clone());
    world.existing_ids = Some(existing);
    let prefix = identifier.split('-').next().unwrap_or("kanbus");
    world.id_prefix = Some(prefix.to_string());
}

#[when("I generate an issue ID")]
fn when_generate_issue_id(world: &mut KanbusWorld) {
    let prefix = world.id_prefix.clone().unwrap_or_else(|| "kanbus".to_string());
    let existing = world.existing_ids.clone().unwrap_or_default();
    let request = IssueIdentifierRequest {
        title: "Test title".to_string(),
        existing_ids: existing,
        prefix,
    };
    let result = generate_issue_identifier(&request).expect("generate identifier");
    world.generated_id = Some(result.identifier);
}

#[when("I generate 100 issue IDs")]
fn when_generate_many_ids(world: &mut KanbusWorld) {
    let prefix = world.id_prefix.clone().unwrap_or_else(|| "kanbus".to_string());
    let ids = generate_many_identifiers("Test title", &prefix, 100).expect("generate ids");
    world.generated_ids = Some(ids);
}

#[given(expr = "the UUID generator always returns {string}")]
fn given_uuid_generator_returns(_world: &mut KanbusWorld, uuid_text: String) {
    let parsed = Uuid::parse_str(&uuid_text).expect("parse uuid");
    set_test_uuid_sequence(Some(vec![parsed; 11]));
}

#[when("I attempt to generate an issue ID")]
fn when_attempt_generate_issue_id(world: &mut KanbusWorld) {
    let prefix = world.id_prefix.clone().unwrap_or_else(|| "kanbus".to_string());
    let existing = world.existing_ids.clone().unwrap_or_default();
    let request = IssueIdentifierRequest {
        title: "Test title".to_string(),
        existing_ids: existing,
        prefix,
    };
    match generate_issue_identifier(&request) {
        Ok(result) => {
            world.generated_id = Some(result.identifier);
            world.id_generation_error = None;
        }
        Err(error) => {
            world.generated_id = None;
            world.id_generation_error = Some(error.to_string());
        }
    }
}

#[then(expr = "the ID should match the pattern {string}")]
fn then_id_matches_pattern(world: &mut KanbusWorld, pattern: String) {
    let identifier = world.generated_id.as_ref().expect("generated id");
    let regex = Regex::new(&format!("^{pattern}$")).expect("regex");
    assert!(regex.is_match(identifier));
}

#[then("all 100 IDs should be unique")]
fn then_ids_unique(world: &mut KanbusWorld) {
    let ids = world.generated_ids.as_ref().expect("generated ids");
    assert_eq!(ids.len(), 100);
}

#[then(expr = "the ID should not be {string}")]
fn then_id_not_collision(world: &mut KanbusWorld, forbidden: String) {
    let identifier = world.generated_id.as_ref().expect("generated id");
    assert_ne!(identifier, &forbidden);
}

#[then(expr = "ID generation should fail with {string}")]
fn then_id_generation_failed(world: &mut KanbusWorld, message: String) {
    let error = world
        .id_generation_error
        .as_ref()
        .expect("id generation error");
    assert_eq!(error, &message);
}
