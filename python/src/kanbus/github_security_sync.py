"""GitHub security synchronization support.

Pulls Dependabot alerts from the GitHub REST API and creates/updates Kanbus
issues under a managed hierarchy.
"""

from __future__ import annotations

import os
import logging
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import requests

from kanbus.ids import IssueIdentifierRequest, generate_issue_identifier
from kanbus.issue_files import (
    list_issue_identifiers,
    read_issue_from_file,
    write_issue_to_file,
)
from kanbus.beads_write import create_beads_issue, update_beads_issue
from kanbus.migration import load_beads_issues
from kanbus.models import (
    DependabotConfiguration,
    GithubSecurityConfiguration,
    IssueData,
)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_SECURITY_INITIATIVE_TITLE = "GitHub Security Remediation"
GITHUB_DEPENDABOT_EPIC_TITLE = "GitHub Dependabot Alerts"
LOGGER = logging.getLogger(__name__)


class GithubSecuritySyncError(RuntimeError):
    """Raised when a GitHub security sync operation fails."""


@dataclass
class DependabotPullResult:
    """Result of a Dependabot pull operation."""

    pulled: int = 0
    updated: int = 0
    skipped: int = 0


def pull_dependabot_from_github(
    root: Path,
    github_security_config: GithubSecurityConfiguration,
    project_key: str,
    dry_run: bool = False,
) -> DependabotPullResult:
    """Pull Dependabot alerts from GitHub and create/update Kanbus issues."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise GithubSecuritySyncError(
            "GITHUB_TOKEN or GH_TOKEN environment variable is not set"
        )

    dependabot_config = github_security_config.dependabot or DependabotConfiguration()
    _validate_state(dependabot_config.state)
    min_priority = _severity_to_priority(dependabot_config.min_severity)

    repo = github_security_config.repo or _detect_repo_from_git(root)
    if not repo:
        raise GithubSecuritySyncError(
            "could not determine GitHub repository slug "
            "(use --repo or github_security.repo)"
        )

    from kanbus.project import load_project_directory

    project_dir = load_project_directory(root)
    issues_dir = project_dir / "issues"
    if not issues_dir.exists():
        raise GithubSecuritySyncError("issues directory does not exist")

    alerts = _fetch_dependabot_alerts(repo, token, dependabot_config.state)
    alerts = [
        alert
        for alert in alerts
        if _severity_to_priority(_alert_severity(alert)) <= min_priority
    ]

    all_existing: Set[str] = set(list_issue_identifiers(issues_dir))
    alert_index = _build_alert_index(all_existing, issues_dir)
    task_index = _build_task_index(all_existing, issues_dir)

    parent_epic = _resolve_dependabot_epic(
        issues_dir,
        project_key,
        dependabot_config.parent_epic,
        dry_run,
        all_existing,
    )

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for alert in alerts:
        grouped[_task_target_key(alert)].append(alert)

    result = DependabotPullResult()

    for target_key, alerts_for_target in sorted(grouped.items()):
        task_id = _resolve_manifest_task(
            issues_dir,
            project_key,
            repo,
            target_key,
            parent_epic,
            _min_priority(alerts_for_target),
            dry_run,
            task_index,
            all_existing,
        )

        for alert in alerts_for_target:
            alert_number = _alert_number(alert)
            if alert_number <= 0:
                continue

            index_key = f"{repo}#{alert_number}"
            existing_kanbus_id = alert_index.get(index_key)
            if existing_kanbus_id:
                kanbus_id = existing_kanbus_id
                action = "updated"
            else:
                request = IssueIdentifierRequest(
                    title=_dependabot_alert_title(alert),
                    existing_ids=frozenset(all_existing),
                    prefix=project_key,
                )
                identifier = generate_issue_identifier(request).identifier
                all_existing.add(identifier)
                kanbus_id = identifier
                action = "pulled "

            issue = _map_dependabot_to_kanbus(alert, repo, task_id)
            issue = issue.model_copy(update={"identifier": kanbus_id})

            issue_path = _issue_path(issues_dir, kanbus_id)
            if action == "updated" and issue_path.exists():
                try:
                    existing = read_issue_from_file(issue_path)
                    issue = issue.model_copy(update={"created_at": existing.created_at})
                except Exception:
                    # Keep pull flow best-effort; continue while surfacing failure details.
                    LOGGER.exception(
                        "Failed to preserve created_at from existing issue at %s",
                        issue_path,
                    )

            severity = _alert_severity(alert)
            print(
                f'{action}  [{severity:<8}]  {"alert#" + str(alert_number):<14}  "{issue.title}"'
            )

            if not dry_run:
                write_issue_to_file(issue, issue_path)

            if action == "updated":
                result.updated += 1
            else:
                result.pulled += 1

    return result


def pull_dependabot_from_github_beads(
    root: Path,
    github_security_config: GithubSecurityConfiguration,
    dry_run: bool = False,
) -> DependabotPullResult:
    """Pull Dependabot alerts from GitHub and create/update Beads issues."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise GithubSecuritySyncError(
            "GITHUB_TOKEN or GH_TOKEN environment variable is not set"
        )

    dependabot_config = github_security_config.dependabot or DependabotConfiguration()
    _validate_state(dependabot_config.state)
    min_priority = _severity_to_priority(dependabot_config.min_severity)

    repo = github_security_config.repo or _detect_repo_from_git(root)
    if not repo:
        raise GithubSecuritySyncError(
            "could not determine GitHub repository slug "
            "(use --repo or github_security.repo)"
        )

    alerts = _fetch_dependabot_alerts(repo, token, dependabot_config.state)
    alerts = [
        alert
        for alert in alerts
        if _severity_to_priority(_alert_severity(alert)) <= min_priority
    ]

    existing_issues = load_beads_issues(root)
    alert_index = _build_beads_alert_index(existing_issues)
    task_index = _build_beads_task_index(existing_issues)

    initiative_id = _resolve_beads_initiative(root, existing_issues, dry_run)
    parent_epic = _resolve_beads_epic(
        root,
        existing_issues,
        dependabot_config.parent_epic,
        initiative_id,
        dry_run,
    )

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for alert in alerts:
        grouped[_task_target_key(alert)].append(alert)

    result = DependabotPullResult()
    runtime_alert_index = dict(alert_index)
    runtime_task_index = dict(task_index)

    for target_key, alerts_for_target in sorted(grouped.items()):
        task_id = _resolve_beads_task(
            root=root,
            repository=repo,
            target_key=target_key,
            parent_epic=parent_epic,
            priority=_min_priority(alerts_for_target),
            dry_run=dry_run,
            task_index=runtime_task_index,
        )

        for alert in alerts_for_target:
            alert_number = _alert_number(alert)
            if alert_number <= 0:
                continue

            index_key = f"{repo}#{alert_number}"
            existing_id = runtime_alert_index.get(index_key)
            title = _dependabot_alert_title(alert)
            description = _map_dependabot_to_beads_description(alert, repo)
            severity = _alert_severity(alert)

            if existing_id:
                if not dry_run:
                    update_beads_issue(
                        root=root,
                        identifier=existing_id,
                        status="open",
                        title=title,
                        description=description,
                        priority=_severity_to_priority(severity),
                        set_labels=["security", "github", "dependabot"],
                    )
                action = "updated"
            else:
                action = "pulled "
                if dry_run:
                    pass
                else:
                    created = create_beads_issue(
                        root=root,
                        title=title,
                        issue_type="sub-task",
                        priority=_severity_to_priority(severity),
                        assignee=None,
                        parent=task_id,
                        description=description,
                    )
                    update_beads_issue(
                        root=root,
                        identifier=created.identifier,
                        status="open",
                        title=title,
                        description=description,
                        priority=_severity_to_priority(severity),
                        set_labels=["security", "github", "dependabot"],
                    )
                    runtime_alert_index[index_key] = created.identifier

            print(
                f'{action}  [{severity:<8}]  {"alert#" + str(alert_number):<14}  "{title}"'
            )
            if action == "updated":
                result.updated += 1
            else:
                result.pulled += 1

    return result


def _validate_state(state: str) -> None:
    allowed = {"open", "fixed", "dismissed", "auto_dismissed"}
    if state not in allowed:
        raise GithubSecuritySyncError(
            f"invalid dependabot state '{state}' "
            f"(expected one of: {', '.join(sorted(allowed))})"
        )


def _resolve_dependabot_epic(
    issues_dir: Path,
    project_key: str,
    configured_id: Optional[str],
    dry_run: bool,
    all_existing: Set[str],
) -> str:
    if configured_id and _issue_path(issues_dir, configured_id).exists():
        return configured_id

    initiative_id = _resolve_security_initiative(
        issues_dir, project_key, dry_run, all_existing
    )
    existing = _find_existing_dependabot_epic(issues_dir, all_existing, initiative_id)
    if existing:
        return existing

    request = IssueIdentifierRequest(
        title=GITHUB_DEPENDABOT_EPIC_TITLE,
        existing_ids=frozenset(all_existing),
        prefix=project_key,
    )
    epic_id = generate_issue_identifier(request).identifier
    all_existing.add(epic_id)

    now = datetime.now(timezone.utc)
    epic = IssueData.model_validate(
        {
            "id": epic_id,
            "title": GITHUB_DEPENDABOT_EPIC_TITLE,
            "description": "Dependabot alerts imported from GitHub Security.",
            "type": "epic",
            "status": "open",
            "priority": 1,
            "assignee": None,
            "creator": None,
            "parent": initiative_id,
            "labels": ["security", "github", "dependabot"],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": {},
        }
    )
    print(f'created  [epic    ]  "{GITHUB_DEPENDABOT_EPIC_TITLE}"')
    if not dry_run:
        write_issue_to_file(epic, _issue_path(issues_dir, epic_id))
    return epic_id


def _resolve_security_initiative(
    issues_dir: Path,
    project_key: str,
    dry_run: bool,
    all_existing: Set[str],
) -> str:
    existing = _find_existing_security_initiative(issues_dir, all_existing)
    if existing:
        return existing

    request = IssueIdentifierRequest(
        title=GITHUB_SECURITY_INITIATIVE_TITLE,
        existing_ids=frozenset(all_existing),
        prefix=project_key,
    )
    initiative_id = generate_issue_identifier(request).identifier
    all_existing.add(initiative_id)

    now = datetime.now(timezone.utc)
    initiative = IssueData.model_validate(
        {
            "id": initiative_id,
            "title": GITHUB_SECURITY_INITIATIVE_TITLE,
            "description": "Track remediation of GitHub security findings.",
            "type": "initiative",
            "status": "open",
            "priority": 1,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": ["security", "github"],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": {},
        }
    )
    print(f'created  [initiative]  "{GITHUB_SECURITY_INITIATIVE_TITLE}"')
    if not dry_run:
        write_issue_to_file(initiative, _issue_path(issues_dir, initiative_id))
    return initiative_id


def _find_existing_security_initiative(
    issues_dir: Path, all_existing: Set[str]
) -> Optional[str]:
    best: Optional[IssueData] = None
    for identifier in all_existing:
        try:
            issue = read_issue_from_file(_issue_path(issues_dir, identifier))
        except Exception:
            continue
        if issue.issue_type != "initiative":
            continue
        if issue.title != GITHUB_SECURITY_INITIATIVE_TITLE:
            continue
        if "github" not in issue.labels:
            continue
        if best is None or issue.updated_at > best.updated_at:
            best = issue
    return best.identifier if best else None


def _find_existing_dependabot_epic(
    issues_dir: Path, all_existing: Set[str], parent_initiative: str
) -> Optional[str]:
    best: Optional[IssueData] = None
    for identifier in all_existing:
        try:
            issue = read_issue_from_file(_issue_path(issues_dir, identifier))
        except Exception:
            continue
        if issue.issue_type != "epic":
            continue
        if issue.title != GITHUB_DEPENDABOT_EPIC_TITLE:
            continue
        if "dependabot" not in issue.labels:
            continue
        if issue.parent != parent_initiative:
            continue
        if best is None or issue.updated_at > best.updated_at:
            best = issue
    return best.identifier if best else None


def _resolve_manifest_task(
    issues_dir: Path,
    project_key: str,
    repo: str,
    target_key: str,
    parent_epic: str,
    priority: int,
    dry_run: bool,
    task_index: Dict[str, str],
    all_existing: Set[str],
) -> str:
    existing = task_index.get(target_key)
    if existing:
        if not dry_run:
            path = _issue_path(issues_dir, existing)
            task = read_issue_from_file(path)
            changed = False
            if task.parent != parent_epic:
                task.parent = parent_epic
                changed = True
            if task.priority != priority:
                task.priority = priority
                changed = True
            for label in ("security", "github", "dependabot"):
                if label not in task.labels:
                    task.labels.append(label)
                    changed = True
            if changed:
                task.updated_at = datetime.now(timezone.utc)
                write_issue_to_file(task, path)
                print(f'updated  [task    ]  "{task.title}"')
        return existing

    title = f"{repo}:{target_key}"
    request = IssueIdentifierRequest(
        title=title,
        existing_ids=frozenset(all_existing),
        prefix=project_key,
    )
    task_id = generate_issue_identifier(request).identifier
    all_existing.add(task_id)

    now = datetime.now(timezone.utc)
    task = IssueData.model_validate(
        {
            "id": task_id,
            "title": title,
            "description": f"Dependabot alerts for `{target_key}`.",
            "type": "task",
            "status": "open",
            "priority": priority,
            "assignee": None,
            "creator": None,
            "parent": parent_epic,
            "labels": ["security", "github", "dependabot"],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": {
                "github_provider": "dependabot",
                "github_repository": repo,
                "github_manifest_path": target_key,
            },
        }
    )
    print(f'created  [task    ]  "{title}"')
    if not dry_run:
        write_issue_to_file(task, _issue_path(issues_dir, task_id))
    return task_id


def _map_dependabot_to_kanbus(
    alert: Dict[str, Any], repo: str, task_id: str
) -> IssueData:
    number = _alert_number(alert)
    package = _alert_package(alert)
    severity = _alert_severity(alert)
    state = _alert_state(alert)
    manifest_path = _alert_manifest(alert)
    ecosystem = _alert_ecosystem(alert)
    advisory = alert.get("security_advisory") or {}
    summary = advisory.get("summary") or "Dependabot alert"
    description = advisory.get("description") or ""
    ghsa_id = advisory.get("ghsa_id") or "dependabot-alert"
    html_url = alert.get("html_url") or ""

    title = (
        f"[Dependabot] {ghsa_id} in {package}"
        if package
        else f"[Dependabot] Alert #{number}: {summary}"
    )

    body = (
        f"## {summary}\n\n"
        f"**Provider:** GitHub Dependabot\n"
        f"**Repository:** `{repo}`\n"
        f"**Alert Number:** {number}\n"
        f"**Severity:** {severity}\n"
        f"**State:** {state}\n"
        f"**Package:** `{package}`\n"
        f"**Ecosystem:** `{ecosystem}`\n"
        f"**Manifest:** `{manifest_path}`\n\n"
        f"### Advisory\n{description}\n\n"
        f"### Reference\n- {html_url}"
    )

    now = datetime.now(timezone.utc)
    return IssueData.model_validate(
        {
            "id": "__placeholder__",
            "title": title,
            "description": body,
            "type": "sub-task",
            "status": "open",
            "priority": _severity_to_priority(severity),
            "assignee": None,
            "creator": None,
            "parent": task_id,
            "labels": ["security", "github", "dependabot"],
            "dependencies": [],
            "comments": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "closed_at": None,
            "custom": {
                "github_provider": "dependabot",
                "github_alert_number": number,
                "github_repository": repo,
                "github_manifest_path": manifest_path,
                "github_ecosystem": ecosystem,
                "github_package": package,
                "github_severity": severity,
                "github_alert_state": state,
                "github_html_url": html_url,
            },
        }
    )


def _build_alert_index(existing_ids: Set[str], issues_dir: Path) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for identifier in existing_ids:
        try:
            issue = read_issue_from_file(_issue_path(issues_dir, identifier))
        except Exception:
            continue
        custom = issue.custom
        provider = custom.get("github_provider")
        number = custom.get("github_alert_number")
        repo = custom.get("github_repository")
        if (
            provider == "dependabot"
            and isinstance(number, int)
            and isinstance(repo, str)
        ):
            index[f"{repo}#{number}"] = identifier
    return index


def _build_task_index(existing_ids: Set[str], issues_dir: Path) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for identifier in existing_ids:
        try:
            issue = read_issue_from_file(_issue_path(issues_dir, identifier))
        except Exception:
            continue
        if issue.issue_type != "task":
            continue
        custom = issue.custom
        if (
            custom.get("github_provider") == "dependabot"
            and isinstance(custom.get("github_manifest_path"), str)
            and custom.get("github_manifest_path")
        ):
            index[str(custom["github_manifest_path"])] = identifier
    return index


def _fetch_dependabot_alerts(repo: str, token: str, state: str) -> List[Dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "kanbus-cli",
    }
    alerts: List[Dict[str, Any]] = []
    url: Optional[str] = (
        f"{GITHUB_API_BASE}/repos/{repo}/dependabot/alerts"
        f"?state={state}&per_page=100"
    )
    while url:
        response = requests.get(url, headers=headers, timeout=30)
        if not response.ok:
            raise GithubSecuritySyncError(
                f"GitHub Dependabot API returned {response.status_code}: "
                f"{response.text[:400]}"
            )
        page = response.json()
        if not isinstance(page, list):
            raise GithubSecuritySyncError("unexpected Dependabot API response shape")
        alerts.extend(page)
        url = _parse_next_link(response.headers.get("Link"))
    return alerts


def _parse_next_link(link_header: Optional[str]) -> Optional[str]:
    if not link_header:
        return None
    for part in link_header.split(","):
        chunk = part.strip()
        if 'rel="next"' not in chunk:
            continue
        if "<" not in chunk or ">" not in chunk:
            return None
        return chunk[chunk.find("<") + 1 : chunk.find(">")]
    return None


def _task_target_key(alert: Dict[str, Any]) -> str:
    manifest = _alert_manifest(alert)
    if manifest and manifest != "unknown":
        return manifest
    ecosystem = _alert_ecosystem(alert)
    return ecosystem or "unknown"


def _min_priority(alerts: List[Dict[str, Any]]) -> int:
    return min(
        (_severity_to_priority(_alert_severity(item)) for item in alerts), default=3
    )


def _alert_number(alert: Dict[str, Any]) -> int:
    value = alert.get("number")
    return int(value) if isinstance(value, int) else 0


def _alert_state(alert: Dict[str, Any]) -> str:
    value = alert.get("state")
    return value if isinstance(value, str) else "open"


def _alert_severity(alert: Dict[str, Any]) -> str:
    advisory = alert.get("security_advisory") or {}
    sev = advisory.get("severity")
    if isinstance(sev, str):
        return sev
    vulnerability = alert.get("security_vulnerability") or {}
    sev = vulnerability.get("severity")
    return sev if isinstance(sev, str) else "low"


def _alert_manifest(alert: Dict[str, Any]) -> str:
    dependency = alert.get("dependency") or {}
    value = dependency.get("manifest_path")
    return value if isinstance(value, str) else "unknown"


def _alert_ecosystem(alert: Dict[str, Any]) -> str:
    dependency = alert.get("dependency") or {}
    package = dependency.get("package") or {}
    value = package.get("ecosystem")
    if isinstance(value, str):
        return value
    vuln = alert.get("security_vulnerability") or {}
    package = vuln.get("package") or {}
    value = package.get("ecosystem")
    return value if isinstance(value, str) else "unknown"


def _alert_package(alert: Dict[str, Any]) -> str:
    dependency = alert.get("dependency") or {}
    package = dependency.get("package") or {}
    value = package.get("name")
    if isinstance(value, str):
        return value
    vuln = alert.get("security_vulnerability") or {}
    package = vuln.get("package") or {}
    value = package.get("name")
    return value if isinstance(value, str) else "unknown"


def _dependabot_alert_title(alert: Dict[str, Any]) -> str:
    advisory = (alert.get("security_advisory") or {}).get(
        "ghsa_id"
    ) or "dependabot-alert"
    return f"[Dependabot] {advisory} in {_alert_package(alert)} #{_alert_number(alert)}"


def _severity_to_priority(severity: str) -> int:
    normalized = severity.lower()
    if normalized == "critical":
        return 0
    if normalized == "high":
        return 1
    if normalized == "medium":
        return 2
    return 3


def _detect_repo_from_git(root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    return _extract_repo_slug(result.stdout.strip())


def _extract_repo_slug(remote: str) -> Optional[str]:
    if remote.startswith("https://github.com/"):
        return remote[len("https://github.com/") :].removesuffix(".git")
    if remote.startswith("git@github.com:"):
        return remote[len("git@github.com:") :].removesuffix(".git")
    return None


def _issue_path(issues_dir: Path, identifier: str) -> Path:
    return issues_dir / f"{identifier}.json"


def _metadata_marker_alert(repository: str, alert_number: int) -> str:
    return f"kanbus-gh-alert:dependabot|{repository}|{alert_number}"


def _metadata_marker_target(repository: str, target_key: str) -> str:
    return f"kanbus-gh-target:dependabot|{repository}|{target_key}"


def _append_marker(description: str, marker: str) -> str:
    return f"{description}\n\n<!-- {marker} -->"


def _extract_marker(description: str, prefix: str) -> Optional[str]:
    for line in description.splitlines():
        stripped = line.strip()
        if stripped.startswith("<!-- ") and stripped.endswith(" -->"):
            inner = stripped.removeprefix("<!-- ").removesuffix(" -->").strip()
            if inner.startswith(prefix):
                return inner[len(prefix) :]
    return None


def _build_beads_alert_index(issues: List[IssueData]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for issue in issues:
        marker = _extract_marker(issue.description or "", "kanbus-gh-alert:dependabot|")
        if not marker:
            continue
        parts = marker.split("|", 1)
        if len(parts) != 2:
            continue
        index[f"{parts[0]}#{parts[1]}"] = issue.identifier
    return index


def _build_beads_task_index(issues: List[IssueData]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for issue in issues:
        if issue.issue_type != "task":
            continue
        marker = _extract_marker(
            issue.description or "", "kanbus-gh-target:dependabot|"
        )
        if not marker:
            continue
        parts = marker.split("|", 1)
        if len(parts) != 2:
            continue
        index[parts[1]] = issue.identifier
    return index


def _resolve_beads_initiative(
    root: Path, issues: List[IssueData], dry_run: bool
) -> str:
    existing = _latest_beads_match(
        issues,
        lambda issue: (
            issue.issue_type == "initiative"
            and issue.title == GITHUB_SECURITY_INITIATIVE_TITLE
            and "github" in issue.labels
        ),
    ) or _latest_beads_match(
        issues,
        lambda issue: (
            issue.issue_type == "initiative"
            and issue.title == GITHUB_SECURITY_INITIATIVE_TITLE
        ),
    )
    if existing:
        return existing
    print(f'created  [initiative]  "{GITHUB_SECURITY_INITIATIVE_TITLE}"')
    if dry_run:
        return "would-create-initiative"
    created = create_beads_issue(
        root=root,
        title=GITHUB_SECURITY_INITIATIVE_TITLE,
        issue_type="initiative",
        priority=1,
        assignee=None,
        parent=None,
        description="Track remediation of GitHub security findings.",
    )
    update_beads_issue(
        root=root,
        identifier=created.identifier,
        status="open",
        title=GITHUB_SECURITY_INITIATIVE_TITLE,
        description="Track remediation of GitHub security findings.",
        priority=1,
        set_labels=["security", "github"],
    )
    return created.identifier


def _resolve_beads_epic(
    root: Path,
    issues: List[IssueData],
    configured_id: Optional[str],
    initiative_id: str,
    dry_run: bool,
) -> str:
    if configured_id and any(issue.identifier == configured_id for issue in issues):
        return configured_id
    existing = _latest_beads_match(
        issues,
        lambda issue: (
            issue.issue_type == "epic"
            and issue.title == GITHUB_DEPENDABOT_EPIC_TITLE
            and "dependabot" in issue.labels
        ),
    ) or _latest_beads_match(
        issues,
        lambda issue: (
            issue.issue_type == "epic" and issue.title == GITHUB_DEPENDABOT_EPIC_TITLE
        ),
    )
    if existing:
        return existing
    print(f'created  [epic    ]  "{GITHUB_DEPENDABOT_EPIC_TITLE}"')
    if dry_run:
        return "would-create-epic"
    created = create_beads_issue(
        root=root,
        title=GITHUB_DEPENDABOT_EPIC_TITLE,
        issue_type="epic",
        priority=1,
        assignee=None,
        parent=initiative_id,
        description="Dependabot alerts imported from GitHub Security.",
    )
    update_beads_issue(
        root=root,
        identifier=created.identifier,
        status="open",
        title=GITHUB_DEPENDABOT_EPIC_TITLE,
        description="Dependabot alerts imported from GitHub Security.",
        priority=1,
        set_labels=["security", "github", "dependabot"],
    )
    return created.identifier


def _latest_beads_match(
    issues: List[IssueData], predicate: Callable[[IssueData], bool]
) -> Optional[str]:
    matches = [issue for issue in issues if predicate(issue)]
    if not matches:
        return None
    matches.sort(key=lambda issue: issue.updated_at)
    return matches[-1].identifier


def _resolve_beads_task(
    root: Path,
    repository: str,
    target_key: str,
    parent_epic: str,
    priority: int,
    dry_run: bool,
    task_index: Dict[str, str],
) -> str:
    title = f"{repository}:{target_key}"
    description = _append_marker(
        f"Dependabot alerts for `{target_key}`.",
        _metadata_marker_target(repository, target_key),
    )

    existing = task_index.get(target_key)
    if existing:
        if not dry_run:
            update_beads_issue(
                root=root,
                identifier=existing,
                status="open",
                title=title,
                description=description,
                priority=priority,
                set_labels=["security", "github", "dependabot"],
            )
        return existing

    print(f'created  [task    ]  "{title}"')
    if dry_run:
        synthetic = f"would-create-task-{target_key}"
        task_index[target_key] = synthetic
        return synthetic

    created = create_beads_issue(
        root=root,
        title=title,
        issue_type="task",
        priority=priority,
        assignee=None,
        parent=parent_epic,
        description=description,
    )
    update_beads_issue(
        root=root,
        identifier=created.identifier,
        status="open",
        title=title,
        description=description,
        priority=priority,
        set_labels=["security", "github", "dependabot"],
    )
    task_index[target_key] = created.identifier
    return created.identifier


def _map_dependabot_to_beads_description(alert: Dict[str, Any], repo: str) -> str:
    number = _alert_number(alert)
    package = _alert_package(alert)
    severity = _alert_severity(alert)
    state = _alert_state(alert)
    manifest_path = _alert_manifest(alert)
    ecosystem = _alert_ecosystem(alert)
    advisory = alert.get("security_advisory") or {}
    summary = advisory.get("summary") or "Dependabot alert"
    description = advisory.get("description") or ""
    html_url = alert.get("html_url") or ""
    body = (
        f"## {summary}\n\n"
        f"**Provider:** GitHub Dependabot\n"
        f"**Repository:** `{repo}`\n"
        f"**Alert Number:** {number}\n"
        f"**Severity:** {severity}\n"
        f"**State:** {state}\n"
        f"**Package:** `{package}`\n"
        f"**Ecosystem:** `{ecosystem}`\n"
        f"**Manifest:** `{manifest_path}`\n\n"
        f"### Advisory\n{description}\n\n"
        f"### Reference\n- {html_url}"
    )
    return _append_marker(body, _metadata_marker_alert(repo, number))
