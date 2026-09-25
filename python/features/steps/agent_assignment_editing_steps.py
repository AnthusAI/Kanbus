"""Behave steps for editing an issue's routing assignment through the console API.

Like the other issue write API steps these exercise a real kbsc over HTTP.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from behave import given, then, when

from features.steps.issue_write_controls_steps import (
    _ensure_real_console_server,
    _issue_write_request,
)
from kanbus.project import load_project_directory as resolve_project_directory


def _with_review_status(config: dict) -> None:
    config["statuses"].append(
        {
            "key": "review",
            "name": "Review",
            "category": "In progress",
            "semantic_category": "in_progress",
        }
    )
    workflow = config["workflows"]["default"]
    workflow["in_progress"].append("review")
    workflow["review"] = ["in_progress", "blocked", "closed"]
    labels = config["transition_labels"]["default"]
    labels["in_progress"]["review"] = "Ready for review"
    labels["review"] = {
        "in_progress": "Request changes",
        "blocked": "Close without merge",
        "closed": "Merge",
    }


@given(
    'the Kanbus configuration has a router with class "{class_name}" using provider "{provider}"'
)
def given_router_with_class_and_provider(
    context: object, class_name: str, provider: str
) -> None:
    _ensure_real_console_server(context)
    config_path = Path(context.working_directory) / ".kanbus.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    _with_review_status(config)
    config["router"] = {
        "workflow": {
            "pending": "open",
            "active": "in_progress",
            "review": "review",
            "blocked": "blocked",
            "terminal": ["closed"],
        },
        "limits": {"project_wip": 3, "review_wip": 2},
        "providers": {provider: {"adapter": "codex"}},
        "classes": {class_name: {"providers": [provider]}},
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


@given('the issue "{issue_id}" has labels "{labels}"')
def given_issue_has_labels(context: object, issue_id: str, labels: str) -> None:
    _ensure_real_console_server(context)
    project_dir = resolve_project_directory(Path(context.working_directory))
    issue_path = project_dir / "issues" / f"{issue_id}.json"
    issue = json.loads(issue_path.read_text(encoding="utf-8"))
    issue["labels"] = [label.strip() for label in labels.split(",") if label.strip()]
    issue_path.write_text(json.dumps(issue, indent=2), encoding="utf-8")


@when(
    'I set the routing assignment through the issue write API for "{issue_id}" to {kind} "{name}"'
)
def when_set_routing_assignment(
    context: object, issue_id: str, kind: str, name: str
) -> None:
    _issue_write_request(context, issue_id, "assignment", {"kind": kind, "name": name})


@when('I clear the routing assignment through the issue write API for "{issue_id}"')
def when_clear_routing_assignment(context: object, issue_id: str) -> None:
    _issue_write_request(context, issue_id, "assignment", {"clear": True})


@then('the issue write API response should be successful with labels "{labels}"')
def then_write_api_labels(context: object, labels: str) -> None:
    assert context.issue_write_status == 200, context.issue_write_payload
    assert sorted(context.issue_write_payload["issue"]["labels"]) == sorted(
        labels.split(",")
    )


@then('the issue write API response should show agent assignment "{kind}" "{name}"')
def then_write_api_shows_assignment(context: object, kind: str, name: str) -> None:
    assignment = context.issue_write_payload["issue"]["custom"].get("agent_assignment")
    assert assignment is not None, context.issue_write_payload
    assert (assignment["kind"], assignment["name"]) == (kind, name)


@then("the issue write API response should show no agent assignment")
def then_write_api_shows_no_assignment(context: object) -> None:
    custom = context.issue_write_payload["issue"]["custom"]
    assert "agent_assignment" not in custom, custom
