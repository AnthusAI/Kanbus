"""Snyk vulnerability synchronization support.

Pulls vulnerabilities from the Snyk REST API and creates/updates Kanbus issues
under a configured parent epic.  The secret is read from the environment
variable SNYK_TOKEN (OAuth bearer token or legacy API key).

Hierarchy created:
  epic  "Snyk Vulnerabilities"
    task  "<repo>:<manifest-file>"  (one per affected file)
      sub-task  "[Snyk] KEY in pkg@version"  (one per vulnerability)
"""

from __future__ import annotations

import os
import subprocess
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import requests

from kanbus.ids import IssueIdentifierRequest, generate_issue_identifier
from kanbus.issue_files import (
    list_issue_identifiers,
    read_issue_from_file,
    write_issue_to_file,
)
from kanbus.models import IssueData, SnykConfiguration

SNYK_API_BASE = "https://api.snyk.io"
SNYK_API_VERSION = "2025-11-05"
SNYK_INITIATIVE_TITLE = "Snyk Vulnerability Remediation"
SNYK_DEP_EPIC_TITLE = "Snyk Dependency Vulnerabilities"
SNYK_CODE_EPIC_TITLE = "Snyk Code Vulnerabilities"


class SnykSyncError(RuntimeError):
    """Raised when a Snyk sync operation fails."""


@dataclass
class SnykPullResult:
    """Result of a Snyk pull operation."""

    pulled: int = 0
    updated: int = 0
    skipped: int = 0


def pull_from_snyk(
    root: Path,
    snyk_config: SnykConfiguration,
    project_key: str,
    dry_run: bool = False,
) -> SnykPullResult:
    """Pull vulnerabilities from Snyk and create/update Kanbus issues.

    Creates the hierarchy: epic → task-per-file → sub-task-per-vulnerability.

    :param root: Repository root path.
    :param snyk_config: Snyk configuration from .kanbus.yml.
    :param project_key: Kanbus project key (issue ID prefix).
    :param dry_run: If True, print what would be done without writing files.
    :raises SnykSyncError: If authentication or API calls fail.
    """
    token = os.environ.get("SNYK_TOKEN")
    if not token:
        raise SnykSyncError("SNYK_TOKEN environment variable is not set")

    from kanbus.project import load_project_directory

    project_dir = load_project_directory(root)
    issues_dir = project_dir / "issues"

    if not issues_dir.exists():
        raise SnykSyncError("issues directory does not exist")

    min_priority = _severity_to_priority(snyk_config.min_severity)

    # Resolve repo filter: use config value or auto-detect from git remote
    repo_filter = snyk_config.repo or _detect_repo_from_git(root)

    # Fetch projects map: project_id → target_file (filtered to this repo)
    project_map = _fetch_snyk_projects(snyk_config.org_id, token, repo_filter)

    # Fetch all vulnerabilities
    vulns = _fetch_all_snyk_issues(
        snyk_config.org_id, token, min_priority, ["package_vulnerability", "code"]
    )

    # Fetch enrichment data (fixedIn, description, cvssScore, etc.) from v1 API
    enrichment = _fetch_v1_enrichment(
        snyk_config.org_id, token, list(project_map.keys())
    )

    # Resolve or auto-create the parent epic(s) after we know which categories exist.
    all_existing: Set[str] = set(list_issue_identifiers(issues_dir))

    # Build indexes for idempotency
    snyk_key_index = _build_snyk_key_index(all_existing, issues_dir)
    file_task_index = _build_file_task_index(all_existing, issues_dir)

    # Group vulnerabilities by category + target_file, deduplicating by (project_id, key).
    file_to_vulns: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    has_code = False
    has_dependency = False
    category_priority: Dict[str, int] = {}
    seen_proj_key: set[str] = set()
    for vuln in vulns:
        proj_id = (
            vuln.get("relationships", {})
            .get("scan_item", {})
            .get("data", {})
            .get("id", "")
        )
        target_file = project_map.get(proj_id)
        if target_file is None:
            continue  # skip issues not in filtered project set
        issue_type = vuln.get("attributes", {}).get("type", "package_vulnerability")
        if issue_type == "code":
            category = "code"
            has_code = True
        else:
            category = "dependency"
            has_dependency = True
        priority = _severity_to_priority(
            vuln.get("attributes", {}).get("effective_severity_level", "low")
        )
        if category not in category_priority or priority < category_priority[category]:
            category_priority[category] = priority
        key = vuln.get("attributes", {}).get("key", "")
        dedup_key = f"{proj_id}:{key}"
        if dedup_key in seen_proj_key:
            continue
        seen_proj_key.add(dedup_key)
        file_to_vulns[(category, target_file)].append(vuln)

    epic_ids = _resolve_snyk_epics(
        issues_dir,
        project_key,
        snyk_config.parent_epic,
        dry_run,
        all_existing,
        include_dependency=has_dependency,
        include_code=has_code,
        dependency_priority=category_priority.get("dependency"),
        code_priority=category_priority.get("code"),
    )

    counts = SnykPullResult()

    for (category, target_file), file_vulns in sorted(file_to_vulns.items()):
        epic_id = epic_ids.get(category) or epic_ids.get("dependency")
        if not epic_id:
            continue
        # Highest priority (lowest number) among this file's vulnerabilities
        file_priority = min(
            (
                _severity_to_priority(
                    v.get("attributes", {}).get("effective_severity_level", "low")
                )
                for v in file_vulns
            ),
            default=3,
        )

        # Resolve or create a task for this file
        task_id = _resolve_file_task(
            issues_dir,
            project_key,
            target_file,
            category,
            FileTaskContext(epic_id=epic_id, priority=file_priority, dry_run=dry_run),
            file_task_index,
            all_existing,
        )

        # Create/update sub-tasks for each vulnerability in this file
        for vuln in file_vulns:
            snyk_key = _vuln_key(vuln)

            existing_kanbus_id = snyk_key_index.get(snyk_key)
            if existing_kanbus_id:
                kanbus_id = existing_kanbus_id
                action = "updated"
            else:
                request = IssueIdentifierRequest(
                    title=_vuln_title(vuln),
                    existing_ids=frozenset(all_existing),
                    prefix=project_key,
                )
                result = generate_issue_identifier(request)
                kanbus_id = result.identifier
                all_existing.add(kanbus_id)
                action = "pulled "

            v1_data = enrichment.get(snyk_key)
            issue = _map_snyk_to_kanbus(vuln, task_id, v1_data, target_file, root)
            issue = issue.model_copy(update={"identifier": kanbus_id})

            # Preserve created_at for updates
            issue_path = _issue_path(issues_dir, kanbus_id)
            if action == "updated" and issue_path.exists():
                try:
                    existing = read_issue_from_file(issue_path)
                    issue = issue.model_copy(update={"created_at": existing.created_at})
                except Exception as exc:
                    print(
                        f"Warning: failed to read existing issue file '{issue_path}' "
                        f"to preserve created_at: {exc}"
                    )

            short_key = (
                kanbus_id[: kanbus_id.find("-") + 7]
                if "-" in kanbus_id
                else kanbus_id[:6]
            )
            severity = vuln.get("attributes", {}).get("effective_severity_level", "?")
            print(f'{action}  [{severity:<8}]  {short_key:<14}  "{issue.title}"')

            if not dry_run:
                write_issue_to_file(issue, issue_path)

            if action == "updated":
                counts.updated += 1
            else:
                counts.pulled += 1

    return counts


def _resolve_parent_epic(
    issues_dir: Path,
    project_key: str,
    configured_id: Optional[str],
    dry_run: bool,
    all_existing: Set[str],
) -> str:
    """Resolve the parent epic ID, creating one if it doesn't exist."""
    if configured_id:
        path = _issue_path(issues_dir, configured_id)
        if path.exists():
            return configured_id

    existing_id = _find_existing_snyk_epic(issues_dir, all_existing)
    if existing_id:
        return existing_id

    request = IssueIdentifierRequest(
        title="Snyk Vulnerabilities",
        existing_ids=frozenset(all_existing),
        prefix=project_key,
    )
    result = generate_issue_identifier(request)
    epic_id = result.identifier
    all_existing.add(epic_id)

    now = datetime.now(timezone.utc)
    epic = IssueData.model_validate(
        {
            "id": epic_id,
            "title": "Snyk Vulnerabilities",
            "description": "Security vulnerabilities imported from Snyk.",
            "type": "epic",
            "status": "open",
            "priority": 1,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": ["security", "snyk"],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": {},
        }
    )

    print(f'created  [epic    ]  {epic_id:<14}  "Snyk Vulnerabilities"')

    if not dry_run:
        write_issue_to_file(epic, _issue_path(issues_dir, epic_id))

    return epic_id


def _resolve_snyk_epics(
    issues_dir: Path,
    project_key: str,
    configured_id: Optional[str],
    dry_run: bool,
    all_existing: Set[str],
    include_dependency: bool,
    include_code: bool,
    dependency_priority: Optional[int],
    code_priority: Optional[int],
) -> Dict[str, str]:
    if configured_id:
        epic_id = _resolve_parent_epic(
            issues_dir, project_key, configured_id, dry_run, all_existing
        )
        epics: Dict[str, str] = {}
        if include_dependency:
            epics["dependency"] = epic_id
        if include_code:
            epics["code"] = epic_id
        return epics

    if not include_dependency and not include_code:
        return {}

    initiative_id = _resolve_snyk_initiative(
        issues_dir, project_key, dry_run, all_existing
    )
    epics: Dict[str, str] = {}
    if include_dependency:
        dep_epic = _resolve_snyk_epic(
            issues_dir,
            project_key,
            initiative_id,
            SNYK_DEP_EPIC_TITLE,
            "dependency",
            dependency_priority if dependency_priority is not None else 2,
            dry_run,
            all_existing,
        )
        epics["dependency"] = dep_epic
    if include_code:
        code_epic = _resolve_snyk_epic(
            issues_dir,
            project_key,
            initiative_id,
            SNYK_CODE_EPIC_TITLE,
            "code",
            code_priority if code_priority is not None else 2,
            dry_run,
            all_existing,
        )
        epics["code"] = code_epic
    return epics


def _resolve_snyk_initiative(
    issues_dir: Path,
    project_key: str,
    dry_run: bool,
    all_existing: Set[str],
) -> str:
    existing = _find_existing_snyk_initiative(issues_dir, all_existing)
    if existing:
        return existing

    request = IssueIdentifierRequest(
        title=SNYK_INITIATIVE_TITLE,
        existing_ids=frozenset(all_existing),
        prefix=project_key,
    )
    result = generate_issue_identifier(request)
    initiative_id = result.identifier
    all_existing.add(initiative_id)

    now = datetime.now(timezone.utc)
    initiative = IssueData.model_validate(
        {
            "id": initiative_id,
            "title": SNYK_INITIATIVE_TITLE,
            "description": "Track remediation of Snyk vulnerabilities.",
            "type": "initiative",
            "status": "open",
            "priority": 1,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": ["security", "snyk"],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": {},
        }
    )

    print(f'created  [initiative]  {initiative_id:<14}  "{SNYK_INITIATIVE_TITLE}"')

    if not dry_run:
        write_issue_to_file(initiative, _issue_path(issues_dir, initiative_id))

    return initiative_id


def _resolve_snyk_epic(
    issues_dir: Path,
    project_key: str,
    parent_initiative: str,
    title: str,
    category: str,
    priority: int,
    dry_run: bool,
    all_existing: Set[str],
) -> str:
    existing = _find_existing_snyk_epic(
        issues_dir, all_existing, title, parent_initiative
    )
    if existing:
        path = _issue_path(issues_dir, existing)
        issue = read_issue_from_file(path)
        if issue.priority != priority:
            issue.priority = priority
            issue.updated_at = datetime.now(timezone.utc)
            if not dry_run:
                write_issue_to_file(issue, path)
        return existing

    request = IssueIdentifierRequest(
        title=title,
        existing_ids=frozenset(all_existing),
        prefix=project_key,
    )
    result = generate_issue_identifier(request)
    epic_id = result.identifier
    all_existing.add(epic_id)

    now = datetime.now(timezone.utc)
    epic = IssueData.model_validate(
        {
            "id": epic_id,
            "title": title,
            "description": "Security vulnerabilities imported from Snyk.",
            "type": "epic",
            "status": "open",
            "priority": priority,
            "assignee": None,
            "creator": None,
            "parent": parent_initiative,
            "labels": ["security", "snyk", category],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": {"snyk_category": category},
        }
    )

    print(f'created  [epic    ]  {epic_id:<14}  "{title}"')

    if not dry_run:
        write_issue_to_file(epic, _issue_path(issues_dir, epic_id))

    return epic_id


def _find_existing_snyk_initiative(
    issues_dir: Path, all_existing: Set[str]
) -> Optional[str]:
    best_id: Optional[str] = None
    best_updated: Optional[datetime] = None

    for identifier in all_existing:
        issue = read_issue_from_file(_issue_path(issues_dir, identifier))
        if issue.issue_type != "initiative":
            continue
        if issue.title != SNYK_INITIATIVE_TITLE:
            continue
        if "snyk" not in issue.labels:
            continue
        if best_updated is None or issue.updated_at > best_updated:
            best_updated = issue.updated_at
            best_id = issue.identifier

    return best_id


def _find_existing_snyk_epic(
    issues_dir: Path, all_existing: Set[str], title: str, parent_initiative: str
) -> Optional[str]:
    best_id: Optional[str] = None
    best_updated: Optional[datetime] = None

    for identifier in all_existing:
        issue = read_issue_from_file(_issue_path(issues_dir, identifier))
        if issue.issue_type != "epic":
            continue
        if issue.title != title:
            continue
        if "snyk" not in issue.labels:
            continue
        if issue.parent != parent_initiative:
            continue
        if best_updated is None or issue.updated_at > best_updated:
            best_updated = issue.updated_at
            best_id = issue.identifier

    return best_id


@dataclass
class FileTaskContext:
    epic_id: str
    priority: int
    dry_run: bool


def _resolve_file_task(
    issues_dir: Path,
    project_key: str,
    target_file: str,
    category: str,
    ctx: FileTaskContext,
    file_task_index: Dict[tuple[str, str], str],
    all_existing: Set[str],
) -> str:
    """Resolve or create a task for a manifest file under the epic."""
    key = (category, target_file)
    if key in file_task_index:
        task_id = file_task_index[key]
        if not ctx.dry_run:
            task_path = _issue_path(issues_dir, task_id)
            task = read_issue_from_file(task_path)
            if task.issue_type == "task":
                changed = False
                if task.parent != ctx.epic_id:
                    task.parent = ctx.epic_id
                    changed = True
                if task.priority != ctx.priority:
                    task.priority = ctx.priority
                    changed = True
                task.custom["snyk_target_file"] = target_file
                task.custom["snyk_category"] = category
                if "snyk" not in task.labels:
                    task.labels.append("snyk")
                    changed = True
                if "security" not in task.labels:
                    task.labels.append("security")
                    changed = True
                if changed:
                    task.updated_at = datetime.now(timezone.utc)
                    write_issue_to_file(task, task_path)
                    short_key = (
                        task_id[: task_id.find("-") + 7]
                        if "-" in task_id
                        else task_id[:6]
                    )
                    print(f'updated  [task    ]  {short_key:<14}  "{target_file}"')
        return task_id

    request = IssueIdentifierRequest(
        title=target_file,
        existing_ids=frozenset(all_existing),
        prefix=project_key,
    )
    result = generate_issue_identifier(request)
    task_id = result.identifier
    all_existing.add(task_id)

    now = datetime.now(timezone.utc)
    task = IssueData.model_validate(
        {
            "id": task_id,
            "title": target_file,
            "description": f"Snyk vulnerabilities found in `{target_file}`.",
            "type": "task",
            "status": "open",
            "priority": ctx.priority,
            "assignee": None,
            "creator": None,
            "parent": ctx.epic_id,
            "labels": ["security", "snyk"],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": {"snyk_target_file": target_file, "snyk_category": category},
        }
    )

    short_key = task_id[: task_id.find("-") + 7] if "-" in task_id else task_id[:6]
    print(f'created  [task    ]  {short_key:<14}  "{target_file}"')

    if not ctx.dry_run:
        write_issue_to_file(task, _issue_path(issues_dir, task_id))

    return task_id


def _detect_repo_from_git(root: Path) -> Optional[str]:
    """Detect the GitHub repo slug from git remote origin URL.

    Returns e.g. "AnthusAI/Plexus" from https or SSH remote URLs.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        url = result.stdout.strip()
        if url.startswith("https://github.com/"):
            return url[len("https://github.com/") :].removesuffix(".git")
        if url.startswith("git@github.com:"):
            return url[len("git@github.com:") :].removesuffix(".git")
    except Exception as exc:
        # Best-effort detection; if git is unavailable or misconfigured, just return None.
        logging.getLogger(__name__).debug(
            "Failed to detect GitHub repo from git remote for %s: %s", root, exc
        )
    return None


def _fetch_snyk_projects(
    org_id: str, token: str, repo_filter: Optional[str] = None
) -> Dict[str, str]:
    """Fetch all projects, returning a map of project_id → target_file.

    If ``repo_filter`` is set (e.g. "AnthusAI/Plexus"), only projects whose
    Snyk name starts with ``"{repo_filter}:"`` are included.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.api+json",
    }
    project_map: Dict[str, str] = {}
    prefix = f"{repo_filter}:" if repo_filter else None

    url: Optional[str] = (
        f"{SNYK_API_BASE}/rest/orgs/{org_id}/projects"
        f"?version={SNYK_API_VERSION}&limit=100"
    )

    while url:
        response = requests.get(url, headers=headers, timeout=30)
        if not response.ok:
            raise SnykSyncError(
                f"Snyk projects API returned {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        for project in data.get("data", []):
            proj_id = project.get("id", "")
            attrs = project.get("attributes", {})
            name = attrs.get("name", "")
            if prefix:
                repo = prefix.rstrip(":")
                if name != repo and not name.startswith(prefix):
                    continue
            target_file = attrs.get("target_file") or name
            if proj_id and target_file:
                project_map[proj_id] = target_file

        next_link = data.get("links", {}).get("next")
        url = f"{SNYK_API_BASE}{next_link}" if next_link else None

    return project_map


def _fetch_all_snyk_issues(
    org_id: str,
    token: str,
    min_priority: int,
    issue_types: Iterable[str],
) -> List[Dict[str, Any]]:
    """Fetch all issues from the Snyk REST API, filtering by min_priority.

    Returns all occurrences (one per project) without deduplication by key,
    so the same vulnerability may appear for multiple files.
    """
    all_issues: List[Dict[str, Any]] = []
    for issue_type in issue_types:
        try:
            all_issues.extend(
                _fetch_snyk_issues_for_type(org_id, token, min_priority, issue_type)
            )
        except SnykSyncError as exc:
            if issue_type == "package_vulnerability":
                raise
            logging.getLogger(__name__).warning(
                "Failed to fetch Snyk issues type '%s': %s", issue_type, exc
            )

    return all_issues


def _fetch_snyk_issues_for_type(
    org_id: str,
    token: str,
    min_priority: int,
    issue_type: str,
) -> List[Dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.api+json",
    }
    all_issues: List[Dict[str, Any]] = []

    url: Optional[str] = (
        f"{SNYK_API_BASE}/rest/orgs/{org_id}/issues"
        f"?version={SNYK_API_VERSION}&limit=100&type={issue_type}"
    )

    while url:
        response = requests.get(url, headers=headers, timeout=30)
        if not response.ok:
            raise SnykSyncError(
                f"Snyk API returned {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        for issue in data.get("data", []):
            key = issue.get("attributes", {}).get("key", "")
            if not key:
                continue
            sev = issue.get("attributes", {}).get("effective_severity_level", "low")
            if _severity_to_priority(sev) <= min_priority:
                all_issues.append(issue)

        next_link = data.get("links", {}).get("next")
        url = f"{SNYK_API_BASE}{next_link}" if next_link else None

    return all_issues


def _fetch_v1_enrichment(
    org_id: str, token: str, project_ids: List[str]
) -> Dict[str, Any]:
    """Fetch enrichment data from the Snyk v1 aggregated-issues API.

    Returns a map of snyk_key → issue dict with fixedIn, description, cvssScore, etc.
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    enrichment: Dict[str, Any] = {}

    for proj_id in project_ids:
        url = f"{SNYK_API_BASE}/api/v1/org/{org_id}/project/{proj_id}/aggregated-issues"
        try:
            r = requests.post(
                url,
                headers=headers,
                json={"filters": {}, "includeDescription": True},
                timeout=30,
            )
            if not r.ok:
                continue
            for issue in r.json().get("issues", []):
                key = issue.get("issueData", {}).get("id", "")
                if key:
                    enrichment[key] = issue
        except Exception:
            continue

    return enrichment


def _build_snyk_key_index(existing_ids: Set[str], issues_dir: Path) -> Dict[str, str]:
    """Build a map from snyk_key → kanbus identifier."""
    index: Dict[str, str] = {}
    for identifier in existing_ids:
        path = _issue_path(issues_dir, identifier)
        try:
            issue = read_issue_from_file(path)
            snyk_key = issue.custom.get("snyk_key")
            if isinstance(snyk_key, str):
                index[snyk_key] = identifier
        except Exception as exc:
            logging.warning("Failed to read issue file %s: %s", path, exc)
    return index


def _build_file_task_index(
    existing_ids: Set[str], issues_dir: Path
) -> Dict[tuple[str, str], str]:
    """Build a map from (category, target_file) → kanbus task identifier."""
    index: Dict[tuple[str, str], str] = {}
    for identifier in existing_ids:
        path = _issue_path(issues_dir, identifier)
        try:
            issue = read_issue_from_file(path)
            if issue.issue_type == "task":
                target_file = issue.custom.get("snyk_target_file")
                if isinstance(target_file, str):
                    category = issue.custom.get("snyk_category")
                    if not isinstance(category, str):
                        category = "dependency"
                    index[(category, target_file)] = identifier
        except Exception as exc:
            logging.warning("Failed to read issue file %s: %s", path, exc)
    return index


def _vuln_key(issue: Dict[str, Any]) -> str:
    return issue.get("attributes", {}).get("key", "")


def _vuln_title(issue: Dict[str, Any]) -> str:
    attrs = issue.get("attributes", {})
    issue_type = attrs.get("type", "package_vulnerability")
    if issue_type == "code":
        title = attrs.get("title") or "Snyk Code issue"
        return f"[Snyk Code] {title}"
    key = attrs.get("key", "unknown")
    coords = attrs.get("coordinates", [{}])
    reps = coords[0].get("representations", [{}]) if coords else [{}]
    pkg = reps[0].get("dependency", {}).get("package_name", "") if reps else ""
    return f"[Snyk] {key} in {pkg}" if pkg else f"[Snyk] {key}"


def _extract_source_location(issue: Dict[str, Any]) -> Optional[Dict[str, object]]:
    coords = issue.get("attributes", {}).get("coordinates", [])
    for coord in coords:
        for rep in coord.get("representations", []):
            loc = rep.get("source_location") or rep.get("sourceLocation")
            if not loc:
                continue
            file_path = loc.get("file")
            if not file_path:
                continue
            region = loc.get("region")
            if region:
                start = region.get("start") or region
                end = region.get("end") or region
                return {
                    "file": file_path,
                    "line": start.get("line"),
                    "column": start.get("column"),
                    "end_line": end.get("line"),
                    "end_column": end.get("column"),
                }
            return {
                "file": file_path,
                "line": loc.get("line"),
                "column": loc.get("column") or loc.get("col"),
            }
    return None


def _extract_classes(issue: Dict[str, Any]) -> List[str]:
    classes = issue.get("attributes", {}).get("classes", [])
    parsed: List[str] = []
    for entry in classes:
        if isinstance(entry, str):
            parsed.append(entry)
            continue
        if isinstance(entry, dict):
            source = entry.get("source")
            ident = entry.get("id")
            if source and ident:
                parsed.append(f"{source}-{ident}")
    return parsed


SNIPPET_CONTEXT = 2
MAX_SNIPPET_LINES = 25


def _build_snippet(
    repo_root: Path,
    file_path: str,
    start_line: Optional[int],
    end_line: Optional[int],
) -> str:
    if not start_line or start_line <= 0:
        return ""
    if not end_line or end_line <= 0:
        end_line = start_line

    path = repo_root / file_path
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return ""

    lines = content.splitlines()
    if not lines:
        return ""

    total = len(lines)
    snippet_start = max(1, start_line - SNIPPET_CONTEXT)
    snippet_end = min(total, end_line + SNIPPET_CONTEXT)
    if snippet_end - snippet_start + 1 > MAX_SNIPPET_LINES:
        snippet_start = max(1, start_line - SNIPPET_CONTEXT)
        snippet_end = min(total, snippet_start + MAX_SNIPPET_LINES - 1)

    body_lines = []
    for line_no in range(snippet_start, snippet_end + 1):
        body_lines.append(f"{line_no:>4} | {lines[line_no - 1]}")

    body = "\n".join(body_lines)
    return (
        f"### Snippet ({file_path}:{snippet_start}-{snippet_end})\n```\n{body}\n```\n\n"
    )


def _map_snyk_to_kanbus(
    issue: Dict[str, Any],
    parent_task_id: Optional[str],
    v1: Optional[Dict[str, Any]] = None,
    target_file: str = "",
    repo_root: Optional[Path] = None,
) -> IssueData:
    """Map a Snyk issue dict to a Kanbus IssueData sub-task."""
    attrs = issue.get("attributes", {})
    issue_type = attrs.get("type", "package_vulnerability")
    snyk_key = attrs.get("key", "")
    severity = attrs.get("effective_severity_level", "low")
    priority = _severity_to_priority(severity)

    now = datetime.now(timezone.utc)
    custom: Dict[str, object] = {
        "snyk_key": snyk_key,
        "snyk_severity": severity,
        "snyk_type": issue_type,
    }

    if issue_type == "code":
        issue_title = attrs.get("title") or snyk_key
        description_text = attrs.get("description") or ""
        classes = _extract_classes(issue)
        class_line = f"**Classes:** {', '.join(classes)}\n" if classes else ""
        location = _extract_source_location(issue)
        file_line = loc_line = ""
        snippet_block = ""
        if location:
            file_line = f"**File:** `{location['file']}`\n"
            if location.get("line") is not None:
                if location.get("column") is not None:
                    if (
                        location.get("end_line") is not None
                        and location.get("end_column") is not None
                    ):
                        loc_line = (
                            f"**Location:** line {location['line']}, "
                            f"column {location['column']} to line "
                            f"{location['end_line']}, column {location['end_column']}\n"
                        )
                    else:
                        loc_line = (
                            f"**Location:** line {location['line']}, "
                            f"column {location['column']}\n"
                        )
                else:
                    loc_line = f"**Location:** line {location['line']}\n"
            custom["snyk_file"] = location["file"]
            if location.get("line") is not None:
                custom["snyk_line"] = int(location["line"])
            if location.get("column") is not None:
                custom["snyk_column"] = int(location["column"])
            if location.get("end_line") is not None:
                custom["snyk_end_line"] = int(location["end_line"])
            if location.get("end_column") is not None:
                custom["snyk_end_column"] = int(location["end_column"])
            if repo_root is not None:
                snippet_block = _build_snippet(
                    repo_root,
                    location["file"],
                    location.get("line"),
                    location.get("end_line"),
                )

        title = f"[Snyk Code] {issue_title}"
        details_block = (
            f"### Details\n{description_text}\n\n" if description_text else ""
        )
        description = (
            f"## {issue_title}\n\n"
            f"**Severity:** {severity}\n"
            f"**Project:** `{target_file}`\n"
            f"{file_line}"
            f"{loc_line}"
            f"{class_line}"
            f"{snippet_block}"
            f"**Issue Key:** {snyk_key}\n\n"
            f"{details_block}"
            f"**Fix:** Review and remediate in code."
        )
    else:
        coords = attrs.get("coordinates", [{}])
        reps = coords[0].get("representations", [{}]) if coords else [{}]
        dep = reps[0].get("dependency", {}) if reps else {}
        pkg_name = dep.get("package_name", "")
        pkg_version = dep.get("package_version", "")

        title = (
            f"[Snyk] {snyk_key} in {pkg_name}@{pkg_version}"
            if pkg_name
            else f"[Snyk] {snyk_key}"
        )

        # Prefer v1 human-readable title
        issue_data = (v1 or {}).get("issueData", {})
        vuln_title = issue_data.get("title") or snyk_key

        cves = [p["id"] for p in attrs.get("problems", []) if p.get("source") == "NVD"]
        cve_lines = (
            "\n".join(
                f"- [{cve}](https://nvd.nist.gov/vuln/detail/{cve})" for cve in cves
            )
            if cves
            else "No CVE assigned."
        )

        coord0 = coords[0] if coords else {}
        fixed_in = (v1 or {}).get("fixInfo", {}).get("fixedIn", [])
        if fixed_in:
            versions = ", ".join(fixed_in)
            if coord0.get("is_upgradeable"):
                fix_advice = (
                    f"**Fix:** Upgrade `{pkg_name}` to version {versions} or later."
                )
            else:
                fix_advice = (
                    f"**Fix:** Pin `{pkg_name}` to version {versions} or later."
                )
        elif coord0.get("is_upgradeable"):
            fix_advice = f"**Fix:** Upgrade `{pkg_name}` to a patched version."
        elif coord0.get("is_pinnable"):
            fix_advice = f"**Fix:** Pin `{pkg_name}` to a patched version."
        elif coord0.get("is_fixable_snyk"):
            fix_advice = "**Fix:** Snyk fix available — run `snyk fix`."
        else:
            fix_advice = "**Fix:** No automatic fix available. Review manually."

        # Extra metadata from v1
        cvss_score = issue_data.get("cvssScore")
        exploit_maturity = issue_data.get("exploitMaturity", "")
        priority_score = (v1 or {}).get("priorityScore")
        v1_description = issue_data.get("description", "")

        meta_lines = []
        if cvss_score is not None:
            meta_lines.append(f"**CVSS Score:** {cvss_score:.1f}")
        if exploit_maturity and exploit_maturity != "no-known-exploit":
            meta_lines.append(f"**Exploit Maturity:** {exploit_maturity}")
        if priority_score is not None:
            meta_lines.append(f"**Snyk Priority Score:** {priority_score}/1000")
        meta_block = ("  \n".join(meta_lines) + "\n\n") if meta_lines else ""

        detail_block = f"### Details\n{v1_description}\n\n" if v1_description else ""

        snyk_url = f"https://security.snyk.io/vuln/{snyk_key}"
        description = (
            f"## {vuln_title}\n\n"
            f"**Severity:** {severity}\n"
            f"**Package:** {pkg_name}@{pkg_version}\n"
            f"**File:** `{target_file}`\n\n"
            f"{meta_block}"
            f"### CVEs\n{cve_lines}\n\n"
            f"{fix_advice}\n\n"
            f"{detail_block}"
            f"### Reference\n- [Snyk advisory]({snyk_url})"
        )

    return IssueData.model_validate(
        {
            "id": "__placeholder__",
            "title": title,
            "description": description,
            "type": "sub-task",
            "status": "open",
            "priority": priority,
            "assignee": None,
            "creator": None,
            "parent": parent_task_id,
            "labels": ["security", "snyk"],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": custom,
        }
    )


def _severity_to_priority(severity: str) -> int:
    """Map Snyk severity to Kanbus priority. critical=0, high=1, medium=2, low=3."""
    return {"critical": 0, "high": 1, "medium": 2}.get(severity.lower(), 3)


def _issue_path(issues_dir: Path, identifier: str) -> Path:
    return issues_dir / f"{identifier}.json"
