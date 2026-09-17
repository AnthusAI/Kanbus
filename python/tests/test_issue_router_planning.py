"""Admission-cap regressions for recoverable Issue Router packages."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.issue_router import (
    RouterContext,
    RouterControlState,
    build_router_plan,
)
from kanbus.models import IssueData, ProjectConfiguration


def _planning_context(
    root: Path,
    *,
    project_wip: int,
    review_wip: int,
    blocker_status: str,
    route_label: str = "agent-provider:codex",
    class_wip: dict[str, int] | None = None,
    provider_wip: dict[str, int] | None = None,
) -> RouterContext:
    configuration_data = copy.deepcopy(DEFAULT_CONFIGURATION)
    configuration_data["statuses"].append(
        {
            "key": "review",
            "name": "Review",
            "category": "In progress",
            "semantic_category": "in_progress",
        }
    )
    configuration_data["workflows"]["default"]["open"].append("review")
    configuration_data["workflows"]["default"]["in_progress"].append("review")
    configuration_data["workflows"]["default"]["review"] = ["in_progress", "closed"]
    labels = configuration_data.setdefault("transition_labels", {}).setdefault(
        "default", {}
    )
    labels["open"] = {**labels.get("open", {}), "review": "Ready for review"}
    labels["in_progress"] = {
        **labels.get("in_progress", {}),
        "review": "Ready for review",
    }
    labels["review"] = {"in_progress": "Request changes", "closed": "Merge"}
    configuration_data["router"] = {
        "workflow": {
            "pending": "open",
            "active": "in_progress",
            "review": "review",
            "blocked": "blocked",
            "terminal": ["closed"],
        },
        "limits": {
            "project_wip": project_wip,
            "review_wip": review_wip,
            "class_wip": class_wip or {},
            "provider_wip": provider_wip or {},
        },
        "providers": {"codex": {"adapter": "codex"}},
        "classes": {"backend": {"providers": ["codex"]}} if class_wip else {},
    }
    configuration = ProjectConfiguration.model_validate(configuration_data)
    now = datetime.now(UTC)
    issues = [
        IssueData(
            id="kbs-recoverable",
            title="Recover active package",
            type="task",
            status="in_progress",
            priority=2,
            labels=[route_label],
            created_at=now,
            updated_at=now,
        ),
        IssueData(
            id="kbs-capacity-holder",
            title="Existing WIP",
            type="task",
            status=blocker_status,
            priority=2,
            created_at=now,
            updated_at=now,
        ),
    ]
    project_dir = root / configuration.project_directory
    (project_dir / "events").mkdir(parents=True, exist_ok=True)
    return RouterContext(
        root=root,
        project_dir=project_dir,
        configuration=configuration,
        router=configuration.router,
        issues=issues,
        control=RouterControlState(),
    )


@pytest.mark.parametrize(
    ("project_wip", "review_wip", "blocker_status"),
    [
        (2, 2, "in_progress"),
        (3, 1, "review"),
    ],
    ids=["project-cap", "review-cap"],
)
def test_recoverable_active_package_is_not_deferred_by_new_start_caps(
    tmp_path: Path,
    project_wip: int,
    review_wip: int,
    blocker_status: str,
) -> None:
    context = _planning_context(
        tmp_path,
        project_wip=project_wip,
        review_wip=review_wip,
        blocker_status=blocker_status,
    )

    plan = build_router_plan(context)

    assert [item.issue_id for item in plan.eligible] == ["kbs-recoverable"]


@pytest.mark.parametrize(
    ("route_label", "class_wip", "provider_wip"),
    [
        ("agent-class:backend", {"backend": 1}, {}),
        ("agent-provider:codex", {}, {"codex": 1}),
    ],
    ids=["class-cap", "provider-cap"],
)
def test_recoverable_active_package_is_not_deferred_by_route_caps(
    tmp_path: Path,
    route_label: str,
    class_wip: dict[str, int],
    provider_wip: dict[str, int],
) -> None:
    context = _planning_context(
        tmp_path,
        project_wip=3,
        review_wip=2,
        blocker_status="open",
        route_label=route_label,
        class_wip=class_wip,
        provider_wip=provider_wip,
    )

    plan = build_router_plan(context)

    assert [item.issue_id for item in plan.eligible] == ["kbs-recoverable"]
