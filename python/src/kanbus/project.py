"""Project discovery utilities."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.models import ProjectConfiguration


@dataclass
class ResolvedProject:
    """A resolved project directory with its label."""

    label: str
    project_dir: Path


class ProjectMarkerError(RuntimeError):
    """Raised when project discovery fails."""


def discover_project_directories(root: Path) -> List[Path]:
    """Discover project directories beneath the current root.

    :param root: Root directory to search from.
    :type root: Path
    :return: List of discovered project directories.
    :rtype: List[Path]
    :raises ProjectMarkerError: If a configured project path is missing.
    """
    project_dirs: List[Path] = []
    _collect_project_directories(root, project_dirs)
    project_dirs.extend(discover_kanbus_projects(root))
    return _normalize_project_directories(project_dirs)


def discover_kanbus_projects(root: Path) -> List[Path]:
    """Discover project directories from Kanbus configuration only.

    :param root: Root directory to search from.
    :type root: Path
    :return: List of configured project directories.
    :rtype: List[Path]
    :raises ProjectMarkerError: If a referenced path is missing.
    """
    marker = _find_configuration_file(root)
    if marker is None:
        return []
    try:
        configuration = _load_configuration(marker)
    except RuntimeError as error:
        raise ProjectMarkerError(str(error)) from error
    project_dirs = _resolve_project_directories(marker.parent, configuration)
    return _normalize_project_directories(project_dirs)


def resolve_labeled_projects(root: Path) -> List[ResolvedProject]:
    """Resolve all labeled project directories from configuration.

    :param root: Repository root.
    :type root: Path
    :return: List of resolved projects with labels.
    :rtype: List[ResolvedProject]
    :raises ProjectMarkerError: If configuration or paths are invalid.
    """
    config_path = get_configuration_path(root)
    try:
        configuration = load_project_configuration(config_path)
    except RuntimeError as error:
        raise ProjectMarkerError(str(error)) from error
    return _resolve_labeled_project_directories(config_path.parent, configuration)


def _resolve_labeled_project_directories(
    base: Path, configuration: ProjectConfiguration
) -> List[ResolvedProject]:
    projects: List[ResolvedProject] = []
    primary = base / configuration.project_directory
    projects.append(ResolvedProject(label=configuration.project_key, project_dir=primary))
    for label, vp in configuration.virtual_projects.items():
        candidate = Path(vp.path)
        if not candidate.is_absolute():
            candidate = base / candidate
        candidate = resolve_project_path(candidate)
        if not candidate.is_dir():
            raise ProjectMarkerError(f"virtual project path not found: {candidate}")
        projects.append(ResolvedProject(label=label, project_dir=candidate))
    return projects


def _resolve_project_directories(
    base: Path, configuration: ProjectConfiguration
) -> List[Path]:
    paths: List[Path] = []
    primary = base / configuration.project_directory
    paths.append(primary)
    for vp in configuration.virtual_projects.values():
        candidate = Path(vp.path)
        if not candidate.is_absolute():
            candidate = base / candidate
        candidate = resolve_project_path(candidate)
        if not candidate.is_dir():
            raise ProjectMarkerError(f"virtual project path not found: {candidate}")
        paths.append(candidate)
    return paths


def _collect_project_directories(root: Path, projects: List[Path]) -> None:
    """Collect project directories without deep recursion.

    Scan the root and one level of children for a "project" directory. This
    avoids pulling in deep fixture projects while still supporting repos that
    organize multiple projects under immediate subdirectories.
    """
    try:
        entries = list(root.iterdir())
    except OSError as error:
        raise ProjectMarkerError(str(error)) from error
    for entry in entries:
        if not entry.is_dir():
            continue
        name = entry.name
        if name == "project":
            projects.append(entry)
            continue
        nested_project = entry / "project"
        if nested_project.is_dir():
            projects.append(nested_project)
        # Do not recurse into subdirectories; explicit configuration controls
        # additional project discovery.


def _normalize_project_directories(paths: Iterable[Path]) -> List[Path]:
    normalized: List[Path] = []
    seen: set[Path] = set()
    for path in paths:
        candidate = resolve_project_path(path)
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return sorted(normalized, key=lambda item: str(item))


def resolve_project_path(path: Path) -> Path:
    """Resolve a project path while tolerating filesystem errors.

    :param path: Path to resolve.
    :type path: Path
    :return: Resolved path or original path on failure.
    :rtype: Path
    """
    try:
        return _resolve_path(path)
    except OSError:
        return path


def _resolve_path(path: Path) -> Path:
    if os.getenv("KANBUS_TEST_CANONICALIZE_FAILURE"):
        raise OSError("forced canonicalize failure")
    return path.resolve()


def _find_configuration_file(root: Path) -> Optional[Path]:
    git_root = _find_git_root(root)
    current = root.resolve()
    while True:
        candidate = current / ".kanbus.yml"
        if candidate.is_file():
            return candidate
        if git_root is not None and current == git_root:
            break
        if current.parent == current:
            break
        current = current.parent
    return None


def _load_configuration(marker: Path) -> ProjectConfiguration:
    return load_project_configuration(marker)


def _find_git_root(root: Path) -> Optional[Path]:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    if path.is_dir():
        return path
    return None


def load_project_directory(root: Path) -> Path:
    """Load a single project directory from the current root.

    :param root: Repository root path.
    :type root: Path
    :return: Path to the project directory.
    :rtype: Path
    :raises ProjectMarkerError: If no project or multiple projects are found.
    """
    project_dirs = discover_project_directories(root)
    if not project_dirs:
        raise ProjectMarkerError("project not initialized")
    if len(project_dirs) > 1:
        discovered = ", ".join(str(path) for path in project_dirs)
        raise ProjectMarkerError(
            f"multiple projects found: {discovered}. "
            "Run this command from a directory with a single project/, "
            "or remove extra entries from virtual_projects in .kanbus.yml."
        )

    return project_dirs[0]


def get_configuration_path(root: Path) -> Path:
    """Return the configuration file path.

    :param root: Repository root path.
    :type root: Path
    :return: Path to .kanbus.yml.
    :rtype: Path
    :raises ProjectMarkerError: If the configuration file is missing.
    :raises ConfigurationError: If configuration path lookup fails.
    """
    if os.getenv("KANBUS_TEST_CONFIGURATION_PATH_FAILURE"):
        raise ConfigurationError("configuration path lookup failed")
    marker = _find_configuration_file(root)
    if marker is None:
        raise ProjectMarkerError("project not initialized")
    return marker


def find_project_local_directory(project_dir: Path) -> Optional[Path]:
    """Find a sibling project-local directory for a project.

    :param project_dir: Shared project directory.
    :type project_dir: Path
    :return: Project-local directory if present.
    :rtype: Optional[Path]
    """
    local_dir = project_dir.parent / "project-local"
    if local_dir.is_dir():
        return local_dir
    return None


def ensure_project_local_directory(project_dir: Path) -> Path:
    """Ensure the project-local directory exists and is gitignored.

    :param project_dir: Shared project directory.
    :type project_dir: Path
    :return: Path to the project-local directory.
    :rtype: Path
    """
    local_dir = project_dir.parent / "project-local"
    issues_dir = local_dir / "issues"
    events_dir = local_dir / "events"
    issues_dir.mkdir(parents=True, exist_ok=True)
    events_dir.mkdir(parents=True, exist_ok=True)
    _ensure_gitignore_entry(project_dir.parent, "project-local/")
    return local_dir


def _ensure_gitignore_entry(root: Path, entry: str) -> None:
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        contents = gitignore_path.read_text(encoding="utf-8")
        lines = [line.strip() for line in contents.splitlines()]
    else:
        contents = ""
        lines = []
    if entry in lines:
        return
    suffix = "" if contents.endswith("\n") or contents == "" else "\n"
    gitignore_path.write_text(f"{contents}{suffix}{entry}\n", encoding="utf-8")
