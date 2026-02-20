"""Jira synchronization support.

Pulls issues from a remote Jira project into the local Kanbus project.
Secrets are read from environment variables JIRA_API_TOKEN and JIRA_USER_EMAIL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests

from kanbus.ids import IssueIdentifierRequest, generate_issue_identifier
from kanbus.issue_files import (
    list_issue_identifiers,
    read_issue_from_file,
    write_issue_to_file,
)
from kanbus.models import IssueComment, IssueData, JiraConfiguration


class JiraSyncError(RuntimeError):
    """Raised when a Jira sync operation fails."""


@dataclass
class JiraPullResult:
    """Result of a Jira pull operation."""

    pulled: int = 0
    updated: int = 0


def pull_from_jira(
    root: Path,
    jira_config: JiraConfiguration,
    project_key: str,
    dry_run: bool = False,
) -> JiraPullResult:
    """Pull issues from a Jira project into the local Kanbus project.

    :param root: Repository root path.
    :param jira_config: Jira configuration from .kanbus.yml.
    :param project_key: Kanbus project key (issue ID prefix).
    :param dry_run: If True, print what would be done without writing files.
    :raises JiraSyncError: If authentication or API calls fail.
    """
    api_token = os.environ.get("JIRA_API_TOKEN")
    user_email = os.environ.get("JIRA_USER_EMAIL")

    if not api_token:
        raise JiraSyncError("JIRA_API_TOKEN environment variable is not set")
    if not user_email:
        raise JiraSyncError("JIRA_USER_EMAIL environment variable is not set")

    from kanbus.project import load_project_directory

    project_dir = load_project_directory(root)
    issues_dir = project_dir / "issues"

    if not issues_dir.exists():
        raise JiraSyncError("issues directory does not exist")

    jira_issues = _fetch_all_jira_issues(jira_config, user_email, api_token)

    existing_ids = list_issue_identifiers(issues_dir)
    jira_key_index = _build_jira_key_index(existing_ids, issues_dir)

    # Pre-assign Kanbus IDs to new issues so parent links can be resolved
    jira_key_to_kanbus_id: Dict[str, str] = dict(jira_key_index)
    new_issue_ids: Dict[str, str] = {}
    all_existing: Set[str] = set(existing_ids)

    for jira_issue in jira_issues:
        jira_key = _jira_issue_key(jira_issue)
        if jira_key not in jira_key_to_kanbus_id:
            request = IssueIdentifierRequest(
                title=_jira_issue_summary(jira_issue),
                existing_ids=frozenset(all_existing),
                prefix=project_key,
            )
            result = generate_issue_identifier(request)
            all_existing.add(result.identifier)
            new_issue_ids[jira_key] = result.identifier
            jira_key_to_kanbus_id[jira_key] = result.identifier

    result_counts = JiraPullResult()

    for jira_issue in jira_issues:
        jira_key = _jira_issue_key(jira_issue)
        kanbus_issue = _map_jira_to_kanbus(
            jira_issue, jira_config, jira_key_to_kanbus_id
        )

        existing_kanbus_id = jira_key_index.get(jira_key)
        if existing_kanbus_id:
            kanbus_id = existing_kanbus_id
            action = "updated"
        else:
            kanbus_id = new_issue_ids[jira_key]
            action = "pulled "

        kanbus_issue = kanbus_issue.model_copy(update={"identifier": kanbus_id})

        # For updates, preserve fields not managed by Jira
        issue_path = issue_path_for_identifier(issues_dir, kanbus_id)
        if action == "updated" and issue_path.exists():
            try:
                existing = read_issue_from_file(issue_path)
                kanbus_issue = kanbus_issue.model_copy(
                    update={"created_at": existing.created_at}
                )
            except Exception:
                pass

        short_key = (
            kanbus_id[: kanbus_id.find("-") + 7] if "-" in kanbus_id else kanbus_id[:6]
        )
        print(f'{action}  {jira_key:<12}  {short_key:<14}  "{kanbus_issue.title}"')

        if not dry_run:
            write_issue_to_file(kanbus_issue, issue_path)

        if action == "updated":
            result_counts.updated += 1
        else:
            result_counts.pulled += 1

    return result_counts


def _fetch_all_jira_issues(
    jira_config: JiraConfiguration,
    user_email: str,
    api_token: str,
) -> List[Dict[str, Any]]:
    """Fetch all issues from Jira with pagination."""
    base_url = jira_config.url.rstrip("/")
    project_key = jira_config.project_key
    fields = (
        "summary,description,issuetype,status,priority,assignee,"
        "reporter,parent,labels,comment,created,updated,resolutiondate"
    )

    auth = (user_email, api_token)
    headers = {"Accept": "application/json"}
    all_issues: List[Dict[str, Any]] = []
    start_at = 0
    max_results = 100

    while True:
        url = (
            f"{base_url}/rest/api/3/search/jql"
            f"?jql=project={project_key}+ORDER+BY+created+ASC"
            f"&fields={fields}&maxResults={max_results}&startAt={start_at}"
        )
        response = requests.get(url, auth=auth, headers=headers, timeout=30)

        if not response.ok:
            raise JiraSyncError(
                f"Jira API returned {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)

        total = data.get("total", 0)
        start_at += len(issues)
        if start_at >= total or not issues:
            break

    return all_issues


def _build_jira_key_index(existing_ids: Set[str], issues_dir: Path) -> Dict[str, str]:
    """Build a map from jira_key → kanbus identifier."""
    index: Dict[str, str] = {}
    for identifier in existing_ids:
        path = issue_path_for_identifier(issues_dir, identifier)
        try:
            issue = read_issue_from_file(path)
            jira_key = issue.custom.get("jira_key")
            if isinstance(jira_key, str):
                index[jira_key] = identifier
        except Exception:
            pass
    return index


def _jira_issue_key(issue: Dict[str, Any]) -> str:
    return issue.get("key", "")


def _jira_issue_summary(issue: Dict[str, Any]) -> str:
    return issue.get("fields", {}).get("summary", "Untitled")


def _map_jira_to_kanbus(
    jira_issue: Dict[str, Any],
    jira_config: JiraConfiguration,
    jira_key_to_kanbus_id: Dict[str, str],
) -> IssueData:
    """Map a Jira issue dict to a Kanbus IssueData."""
    fields = jira_issue.get("fields", {})
    jira_key = _jira_issue_key(jira_issue)

    title = fields.get("summary", "Untitled")
    description = _extract_adf_text(fields.get("description"))

    jira_type = (fields.get("issuetype") or {}).get("name", "Task")
    issue_type = jira_config.type_mappings.get(jira_type, jira_type.lower())

    jira_status = (fields.get("status") or {}).get("name", "open")
    status = _map_jira_status(jira_status)

    jira_priority = (fields.get("priority") or {}).get("name", "Medium")
    priority = _map_jira_priority(jira_priority)

    assignee_field = fields.get("assignee") or {}
    assignee: Optional[str] = assignee_field.get("displayName")

    reporter_field = fields.get("reporter") or {}
    creator: Optional[str] = reporter_field.get("displayName")

    parent_jira_key = (fields.get("parent") or {}).get("key")
    parent: Optional[str] = (
        jira_key_to_kanbus_id.get(parent_jira_key) if parent_jira_key else None
    )

    labels: List[str] = fields.get("labels") or []

    comments = _extract_comments(fields.get("comment") or {})

    created_at = _parse_jira_datetime(fields.get("created", "")) or datetime.now(
        timezone.utc
    )
    updated_at = _parse_jira_datetime(fields.get("updated", "")) or datetime.now(
        timezone.utc
    )
    closed_at = _parse_jira_datetime(fields.get("resolutiondate") or "")

    custom: Dict[str, object] = {"jira_key": jira_key}

    return IssueData.model_validate(
        {
            "id": "__placeholder__",  # filled in by caller
            "title": title,
            "description": description,
            "type": issue_type,
            "status": status,
            "priority": priority,
            "assignee": assignee,
            "creator": creator,
            "parent": parent,
            "labels": labels,
            "dependencies": [],
            "comments": [
                {
                    "id": c.id,
                    "author": c.author,
                    "text": c.text,
                    "created_at": c.created_at.isoformat(),
                }
                for c in comments
            ],
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
            "closed_at": closed_at.isoformat() if closed_at else None,
            "custom": custom,
        }
    )


def _extract_adf_text(value: Any) -> str:
    """Extract plain text from Atlassian Document Format or plain string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _extract_adf_content(value)
    return ""


def _extract_adf_content(node: Dict[str, Any]) -> str:
    parts: List[str] = []
    for child in node.get("content", []):
        node_type = child.get("type", "")
        if node_type == "text":
            parts.append(child.get("text", ""))
        elif node_type == "hardBreak":
            parts.append("\n")
        else:
            text = _extract_adf_content(child)
            if text:
                parts.append(text)
    return " ".join(p for p in parts if p)


def _extract_comments(comment_field: Dict[str, Any]) -> List[IssueComment]:
    result = []
    for c in comment_field.get("comments", []):
        author = (c.get("author") or {}).get("displayName", "Unknown")
        text = _extract_adf_text(c.get("body"))
        created_at = _parse_jira_datetime(c.get("created", "")) or datetime.now(
            timezone.utc
        )
        result.append(
            IssueComment(
                id=str(c["id"]) if "id" in c else None,
                author=author,
                text=text or "(empty)",
                created_at=created_at,
            )
        )
    return result


def _map_jira_status(jira_status: str) -> str:
    mapping = {
        "to do": "open",
        "open": "open",
        "new": "open",
        "backlog": "open",
        "in progress": "in_progress",
        "in review": "in_progress",
        "in development": "in_progress",
        "done": "closed",
        "closed": "closed",
        "resolved": "closed",
        "complete": "closed",
        "completed": "closed",
        "blocked": "blocked",
        "impediment": "blocked",
    }
    return mapping.get(jira_status.lower(), "open")


def _map_jira_priority(jira_priority: str) -> int:
    mapping = {
        "highest": 0,
        "critical": 0,
        "blocker": 0,
        "high": 1,
        "medium": 2,
        "normal": 2,
        "low": 3,
        "lowest": 4,
        "trivial": 4,
        "minor": 4,
    }
    return mapping.get(jira_priority.lower(), 2)


def _parse_jira_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def issue_path_for_identifier(issues_dir: Path, identifier: str) -> Path:
    """Resolve an issue file path by identifier."""
    return issues_dir / f"{identifier}.json"
