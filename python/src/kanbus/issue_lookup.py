"""Issue lookup helpers for project directories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kanbus.ids import matches_issue_identifier
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.issue_files import list_issue_identifiers, read_issue_from_file
from kanbus.models import IssueData, OverlayConfig, ProjectConfiguration
from kanbus.overlay import load_overlay_issue, load_tombstone, resolve_issue_with_overlay
from kanbus.project import (
    ProjectMarkerError,
    discover_project_directories,
    find_project_local_directory,
    get_configuration_path,
    resolve_labeled_projects,
)


class IssueLookupError(RuntimeError):
    """Raised when an issue lookup fails."""


@dataclass(frozen=True)
class IssueLookupResult:
    """Result of issue lookup."""

    issue: IssueData
    issue_path: Path
    project_dir: Path


def load_issue_from_project(root: Path, identifier: str) -> IssueLookupResult:
    """Load an issue by identifier from a project directory.

    Searches all project directories (including virtual projects and local
    directories) for the given identifier.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :return: Issue lookup result.
    :rtype: IssueLookupResult
    :raises IssueLookupError: If the issue cannot be found.
    """
    try:
        project_dirs = discover_project_directories(root)
    except ProjectMarkerError as error:
        raise IssueLookupError(str(error)) from error

    if not project_dirs:
        raise IssueLookupError("project not initialized")

    all_matches: list[tuple[str, Path, Path]] = []
    root_configuration: ProjectConfiguration | None = None
    project_labels: dict[Path, str] = {}
    try:
        root_configuration = load_project_configuration(get_configuration_path(root))
        project_labels = {
            project.project_dir: project.label
            for project in resolve_labeled_projects(root)
        }
    except (ProjectMarkerError, ConfigurationError):
        root_configuration = None

    overlay_configs = {
        project_dir: _overlay_config_for_project(project_dir, root_configuration)
        for project_dir in project_dirs
    }

    for project_dir in project_dirs:
        overlay_config = overlay_configs.get(project_dir, OverlayConfig(enabled=False))
        for issues_dir in _search_directories(project_dir):
            issue_path = issues_dir / f"{identifier}.json"
            if issue_path.exists():
                issue = read_issue_from_file(issue_path)
                if issues_dir == project_dir / "issues":
                    overlay_issue = load_overlay_issue(project_dir, issue.identifier)
                    tombstone = load_tombstone(project_dir, issue.identifier)
                    issue = resolve_issue_with_overlay(
                        project_dir,
                        issue,
                        overlay_issue,
                        tombstone,
                        overlay_config,
                        project_label=project_labels.get(project_dir),
                    )
                    if issue is None:
                        continue
                return IssueLookupResult(
                    issue=issue, issue_path=issue_path, project_dir=project_dir
                )

            matches = _find_matching_issues(issues_dir, identifier)
            for full_id, path in matches:
                all_matches.append((full_id, path, project_dir))

        overlay_issue = load_overlay_issue(project_dir, identifier)
        if overlay_issue is not None:
            tombstone = load_tombstone(project_dir, identifier)
            resolved = resolve_issue_with_overlay(
                project_dir,
                None,
                overlay_issue,
                tombstone,
                overlay_config,
                project_label=project_labels.get(project_dir),
            )
            if resolved is not None:
                overlay_path = (
                    project_dir / ".overlay" / "issues" / f"{identifier}.json"
                )
                return IssueLookupResult(
                    issue=resolved,
                    issue_path=overlay_path,
                    project_dir=project_dir,
                )

    if not all_matches:
        raise IssueLookupError("not found")
    if len(all_matches) == 1:
        _, issue_path, project_dir = all_matches[0]
        issue = read_issue_from_file(issue_path)
        return IssueLookupResult(
            issue=issue, issue_path=issue_path, project_dir=project_dir
        )

    ids = ", ".join(full_id for full_id, _, _ in all_matches)
    raise IssueLookupError(f"ambiguous identifier, matches: {ids}")


def _search_directories(project_dir: Path) -> list[Path]:
    """Return issue directories to search for a given project directory."""
    dirs = [project_dir / "issues"]
    local_dir = find_project_local_directory(project_dir)
    if local_dir is not None:
        dirs.append(local_dir / "issues")
    return dirs


def resolve_issue_identifier(
    issues_dir: Path, _project_key: str, candidate: str
) -> str:
    """Resolve a full issue identifier from a user-provided value.

    Accepts a full identifier, a unique short identifier using the project key,
    or a project-context short identifier without the project key.

    :param issues_dir: Issues directory.
    :type issues_dir: Path
    :param project_key: Project key prefix.
    :type project_key: str
    :param candidate: Candidate identifier (full or short).
    :type candidate: str
    :return: Full issue identifier.
    :rtype: str
    :raises IssueLookupError: If no match or ambiguous short id.
    """
    issue_path = issues_dir / f"{candidate}.json"
    if issue_path.exists():
        return candidate

    matches = [
        identifier
        for identifier in list_issue_identifiers(issues_dir)
        if matches_issue_identifier(candidate, identifier)
    ]

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise IssueLookupError("not found")
    raise IssueLookupError("ambiguous short id")


def _find_matching_issues(issues_dir: Path, identifier: str) -> list[tuple[str, Path]]:
    matches: list[tuple[str, Path]] = []
    for full_id in list_issue_identifiers(issues_dir):
        if matches_issue_identifier(identifier, full_id):
            matches.append((full_id, issues_dir / f"{full_id}.json"))
    return matches


def _overlay_config_for_project(
    project_dir: Path, root_configuration: ProjectConfiguration | None
) -> OverlayConfig:
    if root_configuration is not None:
        return root_configuration.overlay
    config_path = project_dir.parent / ".kanbus.yml"
    if not config_path.is_file():
        return OverlayConfig(enabled=False)
    try:
        return load_project_configuration(config_path).overlay
    except (ConfigurationError, ProjectMarkerError, RuntimeError):
        return OverlayConfig(enabled=False)
