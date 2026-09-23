use cucumber::then;
use serde_json::Value;
use serde_yaml::Value as YamlValue;

use crate::step_definitions::initialization_steps::KanbusWorld;

const RIGHT_NOW_YAML_ITEM_KEYS: [&str; 9] = [
    "id",
    "title",
    "type",
    "status",
    "priority",
    "updated_at",
    "right_now_summary",
    "parent",
    "children",
];

fn stdout_text(world: &KanbusWorld) -> &str {
    world.stdout.as_deref().expect("stdout missing")
}

fn parse_stdout_json(world: &KanbusWorld) -> Value {
    serde_json::from_str(stdout_text(world)).expect("parse stdout json")
}

fn parse_stdout_yaml(world: &KanbusWorld) -> YamlValue {
    serde_yaml::from_str(stdout_text(world)).expect("parse stdout yaml")
}

#[then(expr = "stdout YAML should not fold fields {string}")]
fn then_stdout_yaml_should_not_fold_fields(world: &mut KanbusWorld, fields_csv: String) {
    let stdout = stdout_text(world);
    let fields: Vec<String> = fields_csv
        .split(',')
        .map(str::trim)
        .filter(|field| !field.is_empty())
        .map(str::to_string)
        .collect();
    let lines: Vec<&str> = stdout.lines().collect();
    for (index, line) in lines.iter().enumerate() {
        for field in &fields {
            let marker = format!("{field}:");
            if !line.contains(&marker) {
                continue;
            }
            if index + 1 >= lines.len() {
                continue;
            }
            let next_line = lines[index + 1];
            if next_line.trim().is_empty() {
                continue;
            }
            let current_indent = line.len() - line.trim_start().len();
            let next_indent = next_line.len() - next_line.trim_start().len();
            if next_indent > current_indent && !is_yaml_item_key_line(next_line) {
                panic!(
                    "folded YAML scalar for {} at line {}: {}",
                    field,
                    index + 1,
                    next_line
                );
            }
        }
    }
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
    let stdout = stdout_text(world);
    let expected_fields: Vec<String> = fields_csv
        .split(',')
        .map(str::trim)
        .map(str::to_string)
        .collect();
    let actual_fields = extract_json_key_order(&stdout, &identifier);
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

fn is_yaml_item_key_line(line: &str) -> bool {
    let stripped = line.trim_start();
    if stripped.starts_with("- ") {
        return true;
    }
    let key = stripped.split(':').next().unwrap_or("").trim();
    RIGHT_NOW_YAML_ITEM_KEYS.contains(&key)
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

fn extract_flat_json_key_order(stdout: &str, identifier: &str) -> Vec<String> {
    extract_json_key_order(stdout, identifier)
}

fn extract_json_key_order(stdout: &str, identifier: &str) -> Vec<String> {
    let marker = format!("\"id\": \"{identifier}\"");
    let marker_index = stdout
        .find(&marker)
        .unwrap_or_else(|| panic!("JSON item for {identifier} not found"));
    let object_start = stdout[..marker_index].rfind('{').expect("object start");
    let object_text = extract_balanced_json_object(&stdout[object_start..]);
    extract_top_level_json_keys(object_text)
}

fn extract_balanced_json_object(text: &str) -> &str {
    let mut depth = 0;
    for (index, character) in text.char_indices() {
        if character == '{' {
            depth += 1;
        } else if character == '}' {
            depth -= 1;
            if depth == 0 {
                return &text[..=index];
            }
        }
    }
    panic!("unbalanced JSON object");
}

fn extract_top_level_json_keys(object_text: &str) -> Vec<String> {
    let mut keys = Vec::new();
    let mut depth = 0;
    let mut index = 0;
    let characters: Vec<char> = object_text.chars().collect();
    while index < characters.len() {
        let character = characters[index];
        if character == '{' || character == '[' {
            depth += 1;
            index += 1;
            continue;
        }
        if character == '}' || character == ']' {
            depth -= 1;
            index += 1;
            continue;
        }
        if depth == 1 && character == '"' {
            let key_start = index + 1;
            index += 1;
            while index < characters.len() && characters[index] != '"' {
                index += 1;
            }
            let key = characters[key_start..index].iter().collect::<String>();
            index += 1;
            while index < characters.len() && characters[index].is_whitespace() {
                index += 1;
            }
            if index < characters.len() && characters[index] == ':' {
                keys.push(key);
            }
            continue;
        }
        index += 1;
    }
    keys
}
