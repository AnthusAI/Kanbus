from __future__ import annotations

from datetime import datetime, timezone

from kanbus.models import IssueData, ProjectConfiguration


def build_issue(
    identifier: str,
    *,
    title: str = "Test issue",
    issue_type: str = "task",
    status: str = "open",
    priority: int = 2,
    parent: str | None = None,
    labels: list[str] | None = None,
    custom: dict[str, object] | None = None,
) -> IssueData:
    now = datetime(2026, 3, 6, tzinfo=timezone.utc)
    return IssueData.model_validate(
        {
            "id": identifier,
            "title": title,
            "description": "",
            "type": issue_type,
            "status": status,
            "priority": priority,
            "assignee": None,
            "creator": None,
            "parent": parent,
            "labels": labels or [],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": custom or {},
        }
    )


def build_project_configuration(
    *,
    project_directory: str = "project",
    project_key: str = "kanbus",
    virtual_projects: dict[str, dict[str, str]] | None = None,
    beads_compatibility: bool = False,
) -> ProjectConfiguration:
    return ProjectConfiguration.model_validate(
        {
            "project_directory": project_directory,
            "virtual_projects": virtual_projects or {},
            "project_key": project_key,
            "hierarchy": ["initiative", "epic", "task", "sub-task"],
            "types": ["bug", "story", "chore"],
            "workflows": {
                "default": {
                    "open": ["in_progress", "closed"],
                    "in_progress": ["open", "closed"],
                    "closed": ["open"],
                }
            },
            "initial_status": "open",
            "priorities": {
                0: {"name": "critical", "color": "red"},
                1: {"name": "high", "color": "bright_red"},
                2: {"name": "medium", "color": "yellow"},
                3: {"name": "low", "color": "blue"},
                4: {"name": "trivial", "color": "white"},
            },
            "default_priority": 2,
            "beads_compatibility": beads_compatibility,
            "sort_order": {},
            "type_colors": {},
        }
    )
