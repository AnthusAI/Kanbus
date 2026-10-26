from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional

from kanbus.issue_mutation import (
    PersistIssueMutationRequest,
    PersistIssueMutationResult,
)
from kanbus.models import IssueData, ProjectConfiguration
from kanbus.project_context import ProjectContext

if TYPE_CHECKING:
    import pytest

    from kanbus.issue_update import IssueUpdateResult


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


def build_update_result(
    identifier: str,
    *,
    changed: bool = True,
    **issue_kwargs: object,
) -> IssueUpdateResult:
    from kanbus.issue_update import IssueUpdateResult

    return IssueUpdateResult(
        issue=build_issue(identifier, **issue_kwargs),
        changed=changed,
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
            "statuses": [
                {
                    "key": "open",
                    "name": "Open",
                    "category": "To do",
                    "semantic_category": "todo",
                },
                {
                    "key": "in_progress",
                    "name": "In Progress",
                    "category": "In progress",
                    "semantic_category": "in_progress",
                },
                {
                    "key": "blocked",
                    "name": "Blocked",
                    "category": "In progress",
                    "semantic_category": "in_progress",
                },
                {
                    "key": "closed",
                    "name": "Closed",
                    "category": "Done",
                    "semantic_category": "done",
                },
            ],
            "beads_compatibility": beads_compatibility,
            "sort_order": {},
            "type_colors": {},
        }
    )


def stub_persist_issue_mutation(
    calls: Optional[List[PersistIssueMutationRequest]] = None,
) -> Callable[[PersistIssueMutationRequest], PersistIssueMutationResult]:
    """Return a persist_issue_mutation stand-in that records requests.

    :param calls: Optional list that receives each persist request.
    :type calls: Optional[List[PersistIssueMutationRequest]]
    :return: Stand-in persist function.
    :rtype: Callable[[PersistIssueMutationRequest], PersistIssueMutationResult]
    """

    def persist(
        request: PersistIssueMutationRequest,
        events_enabled: Optional[bool] = None,
    ) -> PersistIssueMutationResult:
        if calls is not None:
            calls.append(request)
        return PersistIssueMutationResult(issue=request.issue, events=request.events)

    return persist


def build_project_context(
    root: Path, configuration: Optional[ProjectConfiguration] = None
) -> ProjectContext:
    """Build a project context without reading any configuration file.

    :param root: Working root and repository root of the context.
    :type root: Path
    :param configuration: Configuration to carry; a default one when omitted.
    :type configuration: Optional[ProjectConfiguration]
    :return: Project context.
    :rtype: ProjectContext
    """
    resolved = configuration or build_project_configuration()
    return ProjectContext(
        root=root,
        config_path=root / ".kanbus.yml",
        repository_root=root,
        configuration=resolved,
        project_dir=root / resolved.project_directory,
        overlay=resolved.overlay,
    )


def stub_cli_project_context(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    configuration: Optional[ProjectConfiguration] = None,
) -> ProjectContext:
    """Make the CLI entry point build a fixed project context.

    :param monkeypatch: Pytest monkeypatch fixture.
    :type monkeypatch: pytest.MonkeyPatch
    :param root: Working root of the context.
    :type root: Path
    :param configuration: Configuration to carry; a default one when omitted.
    :type configuration: Optional[ProjectConfiguration]
    :return: The context the CLI will use.
    :rtype: ProjectContext
    """
    from kanbus import cli

    context = build_project_context(root, configuration)
    monkeypatch.setattr(cli, "_build_project_context", lambda _root: context)
    return context
