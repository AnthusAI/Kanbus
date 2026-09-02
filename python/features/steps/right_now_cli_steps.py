"""Behave steps for the right-now CLI command."""

from __future__ import annotations

import json

from behave import then

from features.steps.output_steps import _strip_ansi


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
