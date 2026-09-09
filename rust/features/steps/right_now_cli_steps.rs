use cucumber::then;
use serde_json::Value;
use serde_yaml::Value as YamlValue;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn stdout_text(world: &KanbusWorld) -> &str {
    world.stdout.as_deref().expect("stdout missing")
}

fn parse_stdout_json(world: &KanbusWorld) -> Value {
    serde_json::from_str(stdout_text(world)).expect("parse stdout json")
}

fn parse_stdout_yaml(world: &KanbusWorld) -> YamlValue {
    serde_yaml::from_str(stdout_text(world)).expect("parse stdout yaml")
}

#[then("stdout should be valid YAML")]
fn then_stdout_is_valid_yaml(world: &mut KanbusWorld) {
    let _ = parse_stdout_yaml(world);
}

#[then(expr = "the right now YAML output should have {int} item")]
#[then(expr = "the right now YAML output should have {int} items")]
fn then_right_now_yaml_item_count(world: &mut KanbusWorld, count: usize) {
    let payload = parse_stdout_yaml(world);
    let items = payload.as_sequence().expect("yaml array");
    assert_eq!(items.len(), count);
}

#[then(expr = "the right now YAML item for {string} should include fields {string}")]
fn then_right_now_yaml_item_includes_fields(
    world: &mut KanbusWorld,
    identifier: String,
    fields_csv: String,
) {
    let payload = parse_stdout_yaml(world);
    let item = find_flat_yaml_item(&payload, &identifier);
    let expected_fields: Vec<String> = fields_csv
        .split(',')
        .map(str::trim)
        .map(str::to_string)
        .collect();
    let actual_fields: Vec<String> = item
        .as_mapping()
        .expect("yaml mapping")
        .iter()
        .filter_map(|(key, _)| key.as_str().map(str::to_string))
        .collect();
    assert_eq!(actual_fields, expected_fields);
}

#[then(expr = "the right now YAML item for {string} should have right_now_summary {string}")]
fn then_right_now_yaml_item_summary_equals(
    world: &mut KanbusWorld,
    identifier: String,
    expected: String,
) {
    let payload = parse_stdout_yaml(world);
    let item = find_flat_yaml_item(&payload, &identifier);
    assert_eq!(
        item.get("right_now_summary"),
        Some(&YamlValue::String(expected))
    );
}

#[then(expr = "the right now YAML item for {string} should have a non-empty right_now_summary")]
fn then_right_now_yaml_item_summary_non_empty(world: &mut KanbusWorld, identifier: String) {
    let payload = parse_stdout_yaml(world);
    let item = find_flat_yaml_item(&payload, &identifier);
    let summary = item
        .get("right_now_summary")
        .and_then(YamlValue::as_str)
        .expect("right_now_summary string");
    assert!(!summary.trim().is_empty());
}

#[then(expr = "the right now YAML item for {string} should not include field {string}")]
fn then_right_now_yaml_item_excludes_field(
    world: &mut KanbusWorld,
    identifier: String,
    field_name: String,
) {
    let payload = parse_stdout_yaml(world);
    let item = find_flat_yaml_item(&payload, &identifier);
    assert!(!item
        .as_mapping()
        .expect("yaml mapping")
        .contains_key(&YamlValue::String(field_name)));
}

#[then(expr = "the right now YAML tree should have root {string} with child {string}")]
fn then_right_now_yaml_tree_has_child(world: &mut KanbusWorld, root_id: String, child_id: String) {
    let payload = parse_stdout_yaml(world);
    let roots = payload.as_sequence().expect("yaml array");
    let root = roots
        .iter()
        .find(|item| item.get("id") == Some(&YamlValue::String(root_id.clone())))
        .expect("root item");
    let children = root
        .get("children")
        .and_then(YamlValue::as_sequence)
        .expect("children array");
    let child_ids: Vec<String> = children
        .iter()
        .filter_map(|child| {
            child
                .get("id")
                .and_then(YamlValue::as_str)
                .map(str::to_string)
        })
        .collect();
    assert!(child_ids.iter().any(|value| value == &child_id));
}

#[then(expr = "the right now YAML tree item for {string} should include fields {string}")]
fn then_right_now_yaml_tree_item_includes_fields(
    world: &mut KanbusWorld,
    identifier: String,
    fields_csv: String,
) {
    let payload = parse_stdout_yaml(world);
    let item = find_tree_yaml_item(&payload, &identifier);
    let expected_fields: Vec<String> = fields_csv
        .split(',')
        .map(str::trim)
        .map(str::to_string)
        .collect();
    let actual_fields: Vec<String> = item
        .as_mapping()
        .expect("yaml mapping")
        .iter()
        .filter_map(|(key, _)| key.as_str().map(str::to_string))
        .collect();
    assert_eq!(actual_fields, expected_fields);
}

#[then(expr = "the right now YAML tree item for {string} should have type {string}")]
fn then_right_now_yaml_tree_item_type_equals(
    world: &mut KanbusWorld,
    identifier: String,
    expected: String,
) {
    let payload = parse_stdout_yaml(world);
    let item = find_tree_yaml_item(&payload, &identifier);
    assert_eq!(item.get("type"), Some(&YamlValue::String(expected)));
}

#[then(expr = "the right now YAML tree item for {string} should have priority {int}")]
fn then_right_now_yaml_tree_item_priority_equals(
    world: &mut KanbusWorld,
    identifier: String,
    expected: i64,
) {
    let payload = parse_stdout_yaml(world);
    let item = find_tree_yaml_item(&payload, &identifier);
    assert_eq!(
        item.get("priority"),
        Some(&YamlValue::Number(expected.into()))
    );
}

#[then(expr = "the right now JSON tree item for {string} should include fields {string}")]
fn then_right_now_json_tree_item_includes_fields(
    world: &mut KanbusWorld,
    identifier: String,
    fields_csv: String,
) {
    let payload = parse_stdout_json(world);
    let item = find_tree_json_item(&payload, &identifier);
    let expected_fields: Vec<String> = fields_csv
        .split(',')
        .map(str::trim)
        .map(str::to_string)
        .collect();
    let actual_fields: Vec<String> = item
        .as_object()
        .expect("json object")
        .keys()
        .cloned()
        .collect();
    assert_eq!(actual_fields, expected_fields);
}

#[then("stdout should be valid JSON")]
fn then_stdout_is_valid_json(world: &mut KanbusWorld) {
    let _ = parse_stdout_json(world);
}

#[then(expr = "the right now JSON output should have {int} item")]
#[then(expr = "the right now JSON output should have {int} items")]
fn then_right_now_json_item_count(world: &mut KanbusWorld, count: usize) {
    let payload = parse_stdout_json(world);
    let items = payload.as_array().expect("json array");
    assert_eq!(items.len(), count);
}

#[then(expr = "the right now JSON item for {string} should include fields {string}")]
fn then_right_now_json_item_includes_fields(
    world: &mut KanbusWorld,
    identifier: String,
    fields_csv: String,
) {
    let stdout = stdout_text(world);
    let expected_fields: Vec<String> = fields_csv
        .split(',')
        .map(str::trim)
        .map(str::to_string)
        .collect();
    let actual_fields = extract_flat_json_key_order(stdout, &identifier);
    assert_eq!(actual_fields, expected_fields);
}

#[then(expr = "the right now JSON item for {string} should have priority {int}")]
fn then_right_now_json_item_priority_equals(
    world: &mut KanbusWorld,
    identifier: String,
    expected: i64,
) {
    let payload = parse_stdout_json(world);
    let item = find_flat_json_item(&payload, &identifier);
    assert_eq!(item.get("priority"), Some(&Value::Number(expected.into())));
}

#[then(expr = "the right now JSON item for {string} should have right_now_summary {string}")]
fn then_right_now_json_item_summary_equals(
    world: &mut KanbusWorld,
    identifier: String,
    expected: String,
) {
    let payload = parse_stdout_json(world);
    let item = find_flat_json_item(&payload, &identifier);
    assert_eq!(
        item.get("right_now_summary"),
        Some(&Value::String(expected))
    );
}

#[then(expr = "the right now JSON item for {string} should have a non-empty right_now_summary")]
fn then_right_now_json_item_summary_non_empty(world: &mut KanbusWorld, identifier: String) {
    let payload = parse_stdout_json(world);
    let item = find_flat_json_item(&payload, &identifier);
    let summary = item
        .get("right_now_summary")
        .and_then(Value::as_str)
        .expect("right_now_summary string");
    assert!(!summary.trim().is_empty());
}

#[then(expr = "the right now JSON item for {string} should have right_now_summary null")]
fn then_right_now_json_item_summary_null(world: &mut KanbusWorld, identifier: String) {
    let payload = parse_stdout_json(world);
    let item = find_flat_json_item(&payload, &identifier);
    assert!(item.get("right_now_summary").is_some());
    assert!(item.get("right_now_summary").unwrap().is_null());
}

#[then(expr = "the right now JSON item for {string} should not include field {string}")]
fn then_right_now_json_item_excludes_field(
    world: &mut KanbusWorld,
    identifier: String,
    field_name: String,
) {
    let payload = parse_stdout_json(world);
    let item = find_flat_json_item(&payload, &identifier);
    assert!(!item
        .as_object()
        .expect("json object")
        .contains_key(&field_name));
}

#[then(expr = "the right now JSON tree should have root {string} with child {string}")]
fn then_right_now_json_tree_has_child(world: &mut KanbusWorld, root_id: String, child_id: String) {
    let payload = parse_stdout_json(world);
    let roots = payload.as_array().expect("json array");
    let root = roots
        .iter()
        .find(|item| item.get("id") == Some(&Value::String(root_id.clone())))
        .expect("root item");
    let children = root
        .get("children")
        .and_then(Value::as_array)
        .expect("children array");
    let child_ids: Vec<String> = children
        .iter()
        .filter_map(|child| child.get("id").and_then(Value::as_str).map(str::to_string))
        .collect();
    assert!(child_ids.iter().any(|value| value == &child_id));
}

fn find_flat_json_item<'a>(payload: &'a Value, identifier: &str) -> &'a Value {
    let items = payload.as_array().expect("json array");
    items
        .iter()
        .find(|item| item.get("id") == Some(&Value::String(identifier.to_string())))
        .unwrap_or_else(|| panic!("JSON item for {identifier} not found"))
}

fn find_flat_yaml_item<'a>(payload: &'a YamlValue, identifier: &str) -> &'a YamlValue {
    let items = payload.as_sequence().expect("yaml array");
    items
        .iter()
        .find(|item| item.get("id") == Some(&YamlValue::String(identifier.to_string())))
        .unwrap_or_else(|| panic!("YAML item for {identifier} not found"))
}

fn find_tree_yaml_item<'a>(payload: &'a YamlValue, identifier: &str) -> &'a YamlValue {
    search_tree_yaml_item(payload, identifier)
        .unwrap_or_else(|| panic!("YAML tree item for {identifier} not found"))
}

fn search_tree_yaml_item<'a>(payload: &'a YamlValue, identifier: &str) -> Option<&'a YamlValue> {
    if let Some(items) = payload.as_sequence() {
        for item in items {
            if let Some(found) = search_tree_yaml_item(item, identifier) {
                return Some(found);
            }
        }
        return None;
    }
    if let Some(mapping) = payload.as_mapping() {
        if mapping.get(&YamlValue::String("id".to_string()))
            == Some(&YamlValue::String(identifier.to_string()))
        {
            return Some(payload);
        }
        if let Some(children) = mapping.get(&YamlValue::String("children".to_string())) {
            if let Some(sequence) = children.as_sequence() {
                for child in sequence {
                    if let Some(found) = search_tree_yaml_item(child, identifier) {
                        return Some(found);
                    }
                }
            }
        }
    }
    None
}

fn find_tree_json_item<'a>(payload: &'a Value, identifier: &str) -> &'a Value {
    search_tree_json_item(payload, identifier)
        .unwrap_or_else(|| panic!("JSON tree item for {identifier} not found"))
}

fn search_tree_json_item<'a>(payload: &'a Value, identifier: &str) -> Option<&'a Value> {
    if let Some(items) = payload.as_array() {
        for item in items {
            if let Some(found) = search_tree_json_item(item, identifier) {
                return Some(found);
            }
        }
        return None;
    }
    if let Some(mapping) = payload.as_object() {
        if mapping.get("id") == Some(&Value::String(identifier.to_string())) {
            return Some(payload);
        }
        if let Some(children) = mapping.get("children").and_then(Value::as_array) {
            for child in children {
                if let Some(found) = search_tree_json_item(child, identifier) {
                    return Some(found);
                }
            }
        }
    }
    None
}

fn extract_flat_json_key_order(stdout: &str, identifier: &str) -> Vec<String> {
    extract_json_key_order(stdout, identifier)
}

fn extract_json_key_order(stdout: &str, identifier: &str) -> Vec<String> {
    let marker = format!("\"id\": \"{identifier}\"");
    let marker_index = stdout
        .find(&marker)
        .unwrap_or_else(|| panic!("JSON item for {identifier} not found"));
    let object_start = stdout[..marker_index].rfind('{').expect("object start");
    let object_end = stdout[marker_index..]
        .find('}')
        .map(|index| marker_index + index)
        .expect("object end");
    let object_text = &stdout[object_start..=object_end];
    let mut keys = Vec::new();
    let mut search_from = 0;
    while let Some(quote_index) = object_text[search_from..].find('"') {
        let absolute = search_from + quote_index;
        let remainder = &object_text[absolute + 1..];
        let Some(end_quote) = remainder.find('"') else {
            break;
        };
        let key = &remainder[..end_quote];
        if remainder.get(end_quote + 1..end_quote + 2) == Some(":") {
            keys.push(key.to_string());
        }
        search_from = absolute + end_quote + 2;
    }
    keys
}
