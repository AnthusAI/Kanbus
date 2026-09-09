"""Behave steps for the right-now CLI command."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import yaml
from behave import given, then

from features.steps.output_steps import _strip_ansi
from features.steps.shared import build_issue, load_project_directory, write_issue_file


@given('{count:d} issues exist with identifier prefix "{prefix}"')
def given_issues_with_identifier_prefix(
    context: object, count: int, prefix: str
) -> None:
    """Create sequentially timestamped issues for default-limit coverage.

    Newer issues use lower sequence numbers so the highest suffix is oldest
    and falls outside the default right-now cap of 30.

    :param context: Behave context object.
    :type context: object
    :param count: Number of issues to create.
    :type count: int
    :param prefix: Identifier prefix before the numeric suffix.
    :type prefix: str
    """
    _write_prefixed_issues(context, count, prefix, "open")


@given('{count:d} in-progress issues exist with identifier prefix "{prefix}"')
def given_in_progress_issues_with_identifier_prefix(
    context: object, count: int, prefix: str
) -> None:
    """Create sequentially timestamped in-progress issues for default-limit coverage.

    Newer issues use lower sequence numbers so the highest suffix is oldest
    and falls outside the default right-now cap of 30.

    :param context: Behave context object.
    :type context: object
    :param count: Number of issues to create.
    :type count: int
    :param prefix: Identifier prefix before the numeric suffix.
    :type prefix: str
    """
    _write_prefixed_issues(context, count, prefix, "in_progress")


@then("stdout should be valid YAML")
def then_stdout_is_valid_yaml(context: object) -> None:
    """Verify stdout parses as YAML.

    :param context: Behave context object.
    :type context: object
    """
    yaml.safe_load(_strip_ansi(context.result.stdout))


@then("the right now YAML output should have {count:d} item")
@then("the right now YAML output should have {count:d} items")
def then_right_now_yaml_item_count(context: object, count: int) -> None:
    """Verify the right-now YAML array length.

    :param context: Behave context object.
    :type context: object
    :param count: Expected number of items.
    :type count: int
    """
    payload = yaml.safe_load(_strip_ansi(context.result.stdout))
    assert isinstance(payload, list)
    assert len(payload) == count


@then('the right now YAML item for "{identifier}" should include fields "{fields_csv}"')
def then_right_now_yaml_item_includes_fields(
    context: object, identifier: str, fields_csv: str
) -> None:
    """Verify YAML object key order and presence for a flat right-now item.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param fields_csv: Comma-separated expected field names in order.
    :type fields_csv: str
    """
    payload = yaml.safe_load(_strip_ansi(context.result.stdout))
    item = _find_flat_yaml_item(payload, identifier)
    expected_fields = [field.strip() for field in fields_csv.split(",")]
    actual_fields = list(item.keys())
    assert (
        actual_fields == expected_fields
    ), f"expected keys {expected_fields}, got {actual_fields}"


@then(
    'the right now YAML item for "{identifier}" should have right_now_summary "{expected}"'
)
def then_right_now_yaml_item_summary_equals(
    context: object, identifier: str, expected: str
) -> None:
    """Verify a flat YAML item right_now_summary value.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param expected: Expected summary text.
    :type expected: str
    """
    payload = yaml.safe_load(_strip_ansi(context.result.stdout))
    item = _find_flat_yaml_item(payload, identifier)
    assert item.get("right_now_summary") == expected


@then(
    'the right now YAML item for "{identifier}" should have a non-empty right_now_summary'
)
def then_right_now_yaml_item_summary_non_empty(
    context: object, identifier: str
) -> None:
    """Verify a flat YAML item has a non-empty right_now_summary value.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    """
    payload = yaml.safe_load(_strip_ansi(context.result.stdout))
    item = _find_flat_yaml_item(payload, identifier)
    summary = item.get("right_now_summary")
    assert isinstance(summary, str)
    assert summary.strip()


@then(
    'the right now YAML item for "{identifier}" should not include field "{field_name}"'
)
def then_right_now_yaml_item_excludes_field(
    context: object, identifier: str, field_name: str
) -> None:
    """Verify a flat YAML item omits a field.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param field_name: Field name that must be absent.
    :type field_name: str
    """
    payload = yaml.safe_load(_strip_ansi(context.result.stdout))
    item = _find_flat_yaml_item(payload, identifier)
    assert field_name not in item


@then('the right now YAML tree should have root "{root_id}" with child "{child_id}"')
def then_right_now_yaml_tree_has_child(
    context: object, root_id: str, child_id: str
) -> None:
    """Verify nested children in right-now tree YAML output.

    :param context: Behave context object.
    :type context: object
    :param root_id: Root issue identifier.
    :type root_id: str
    :param child_id: Expected child issue identifier.
    :type child_id: str
    """
    payload = yaml.safe_load(_strip_ansi(context.result.stdout))
    assert isinstance(payload, list)
    root = next(item for item in payload if item.get("id") == root_id)
    child_ids = [child.get("id") for child in root.get("children", [])]
    assert child_id in child_ids


@then(
    'the right now YAML tree item for "{identifier}" should include fields "{fields_csv}"'
)
def then_right_now_yaml_tree_item_includes_fields(
    context: object, identifier: str, fields_csv: str
) -> None:
    """Verify YAML object key order and presence for a tree right-now item.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param fields_csv: Comma-separated expected field names in order.
    :type fields_csv: str
    """
    payload = yaml.safe_load(_strip_ansi(context.result.stdout))
    item = _find_tree_yaml_item(payload, identifier)
    expected_fields = [field.strip() for field in fields_csv.split(",")]
    actual_fields = list(item.keys())
    assert (
        actual_fields == expected_fields
    ), f"expected keys {expected_fields}, got {actual_fields}"


@then('the right now YAML tree item for "{identifier}" should have type "{expected}"')
def then_right_now_yaml_tree_item_type_equals(
    context: object, identifier: str, expected: str
) -> None:
    """Verify a tree YAML item type value.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param expected: Expected issue type.
    :type expected: str
    """
    payload = yaml.safe_load(_strip_ansi(context.result.stdout))
    item = _find_tree_yaml_item(payload, identifier)
    assert item.get("type") == expected


@then(
    'the right now YAML tree item for "{identifier}" should have priority {expected:d}'
)
def then_right_now_yaml_tree_item_priority_equals(
    context: object, identifier: str, expected: int
) -> None:
    """Verify a tree YAML item priority value.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param expected: Expected priority integer.
    :type expected: int
    """
    payload = yaml.safe_load(_strip_ansi(context.result.stdout))
    item = _find_tree_yaml_item(payload, identifier)
    assert item.get("priority") == expected


@then(
    'the right now JSON tree item for "{identifier}" should include fields "{fields_csv}"'
)
def then_right_now_json_tree_item_includes_fields(
    context: object, identifier: str, fields_csv: str
) -> None:
    """Verify JSON object key order and presence for a tree right-now item.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param fields_csv: Comma-separated expected field names in order.
    :type fields_csv: str
    """
    payload = json.loads(_strip_ansi(context.result.stdout))
    item = _find_tree_json_item(payload, identifier)
    expected_fields = [field.strip() for field in fields_csv.split(",")]
    actual_fields = list(item.keys())
    assert (
        actual_fields == expected_fields
    ), f"expected keys {expected_fields}, got {actual_fields}"


@then("stdout should be valid JSON")
def then_stdout_is_valid_json(context: object) -> None:
    """Verify stdout parses as JSON.

    :param context: Behave context object.
    :type context: object
    """
    stdout = _strip_ansi(context.result.stdout)
    json.loads(stdout)


@then("the right now JSON output should have {count:d} item")
@then("the right now JSON output should have {count:d} items")
def then_right_now_json_item_count(context: object, count: int) -> None:
    """Verify the right-now JSON array length.

    :param context: Behave context object.
    :type context: object
    :param count: Expected number of items.
    :type count: int
    """
    payload = json.loads(_strip_ansi(context.result.stdout))
    assert isinstance(payload, list)
    assert len(payload) == count


@then('the right now JSON item for "{identifier}" should include fields "{fields_csv}"')
def then_right_now_json_item_includes_fields(
    context: object, identifier: str, fields_csv: str
) -> None:
    """Verify JSON object key order and presence for a flat right-now item.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param fields_csv: Comma-separated expected field names in order.
    :type fields_csv: str
    """
    payload = json.loads(_strip_ansi(context.result.stdout))
    item = _find_flat_json_item(payload, identifier)
    expected_fields = [field.strip() for field in fields_csv.split(",")]
    actual_fields = list(item.keys())
    assert (
        actual_fields == expected_fields
    ), f"expected keys {expected_fields}, got {actual_fields}"


@then(
    'the right now JSON item for "{identifier}" should have right_now_summary "{expected}"'
)
def then_right_now_json_item_summary_equals(
    context: object, identifier: str, expected: str
) -> None:
    """Verify a flat JSON item right_now_summary value.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param expected: Expected summary text.
    :type expected: str
    """
    payload = json.loads(_strip_ansi(context.result.stdout))
    item = _find_flat_json_item(payload, identifier)
    assert item.get("right_now_summary") == expected


@then('the right now JSON item for "{identifier}" should have priority {expected:d}')
def then_right_now_json_item_priority_equals(
    context: object, identifier: str, expected: int
) -> None:
    """Verify a flat JSON item priority value.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param expected: Expected priority integer.
    :type expected: int
    """
    payload = json.loads(_strip_ansi(context.result.stdout))
    item = _find_flat_json_item(payload, identifier)
    assert item.get("priority") == expected


@then(
    'the right now JSON item for "{identifier}" should have a non-empty right_now_summary'
)
def then_right_now_json_item_summary_non_empty(
    context: object, identifier: str
) -> None:
    """Verify a flat JSON item has a non-empty right_now_summary value.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    """
    payload = json.loads(_strip_ansi(context.result.stdout))
    item = _find_flat_json_item(payload, identifier)
    summary = item.get("right_now_summary")
    assert isinstance(summary, str)
    assert summary.strip()


@then('the right now JSON item for "{identifier}" should have right_now_summary null')
def then_right_now_json_item_summary_null(context: object, identifier: str) -> None:
    """Verify a flat JSON item has null right_now_summary.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    """
    payload = json.loads(_strip_ansi(context.result.stdout))
    item = _find_flat_json_item(payload, identifier)
    assert "right_now_summary" in item
    assert item["right_now_summary"] is None


@then(
    'the right now JSON item for "{identifier}" should not include field "{field_name}"'
)
def then_right_now_json_item_excludes_field(
    context: object, identifier: str, field_name: str
) -> None:
    """Verify a flat JSON item omits a field.

    :param context: Behave context object.
    :type context: object
    :param identifier: Issue identifier to locate.
    :type identifier: str
    :param field_name: Field name that must be absent.
    :type field_name: str
    """
    payload = json.loads(_strip_ansi(context.result.stdout))
    item = _find_flat_json_item(payload, identifier)
    assert field_name not in item


@then('the right now JSON tree should have root "{root_id}" with child "{child_id}"')
def then_right_now_json_tree_has_child(
    context: object, root_id: str, child_id: str
) -> None:
    """Verify nested children in right-now tree JSON output.

    :param context: Behave context object.
    :type context: object
    :param root_id: Root issue identifier.
    :type root_id: str
    :param child_id: Expected child issue identifier.
    :type child_id: str
    """
    payload = json.loads(_strip_ansi(context.result.stdout))
    assert isinstance(payload, list)
    root = next(item for item in payload if item.get("id") == root_id)
    child_ids = [child.get("id") for child in root.get("children", [])]
    assert child_id in child_ids


def _find_flat_json_item(payload: object, identifier: str) -> dict:
    assert isinstance(payload, list)
    for item in payload:
        if isinstance(item, dict) and item.get("id") == identifier:
            return item
    raise AssertionError(f"JSON item for {identifier} not found")


def _find_flat_yaml_item(payload: object, identifier: str) -> dict:
    assert isinstance(payload, list)
    for item in payload:
        if isinstance(item, dict) and item.get("id") == identifier:
            return item
    raise AssertionError(f"YAML item for {identifier} not found")


def _find_tree_yaml_item(payload: object, identifier: str) -> dict:
    found = _search_tree_yaml_item(payload, identifier)
    if found is None:
        raise AssertionError(f"YAML tree item for {identifier} not found")
    return found


def _search_tree_yaml_item(payload: object, identifier: str) -> dict | None:
    if isinstance(payload, list):
        for item in payload:
            found = _search_tree_yaml_item(item, identifier)
            if found is not None:
                return found
    elif isinstance(payload, dict):
        if payload.get("id") == identifier:
            return payload
        for child in payload.get("children", []):
            found = _search_tree_yaml_item(child, identifier)
            if found is not None:
                return found
    return None


def _find_tree_json_item(payload: object, identifier: str) -> dict:
    found = _search_tree_json_item(payload, identifier)
    if found is None:
        raise AssertionError(f"JSON tree item for {identifier} not found")
    return found


def _search_tree_json_item(payload: object, identifier: str) -> dict | None:
    if isinstance(payload, list):
        for item in payload:
            found = _search_tree_json_item(item, identifier)
            if found is not None:
                return found
    elif isinstance(payload, dict):
        if payload.get("id") == identifier:
            return payload
        for child in payload.get("children", []):
            found = _search_tree_json_item(child, identifier)
            if found is not None:
                return found
    return None


def _write_prefixed_issues(
    context: object,
    count: int,
    prefix: str,
    status: str,
) -> None:
    project_dir = load_project_directory(context)
    newest = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    for index in range(1, count + 1):
        identifier = f"{prefix}-{index}"
        issue = build_issue(
            identifier,
            f"Many issue {index}",
            "task",
            status,
            None,
            [],
        )
        updated_at = newest - timedelta(minutes=index)
        issue = issue.model_copy(
            update={"updated_at": updated_at, "created_at": updated_at}
        )
        write_issue_file(project_dir, issue)
