"""Project discovery utilities."""

from __future__ import annotations

import os
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


WORKSPACE_IGNORE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "project",
    "project-local",
    "target",
}

LEGACY_DISCOVERY_IGNORE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "project-local",
    "target",
}


def discover_project_directories(root: Path) -> List[Path]:
    """Discover project directories beneath the current root.

    :param root: Root directory to search from.
    :type root: Path
    :return: List of discovered project directories.
    :rtype: List[Path]
    :raises ProjectMarkerError: If a configured project path is missing.
    """
    config_path = root / ".kanbus.yml"
    try:
        has_config = config_path.is_file()
    except OSError as error:
        raise ProjectMarkerError(str(error)) from error
    if has_config:
        project_dirs = _resolve_project_directories_from_config(config_path)
        for project_dir in project_dirs:
            if not project_dir.is_dir():
                raise ProjectMarkerError(f"kanbus path not found: {project_dir}")
        return _normalize_project_directories(project_dirs)

    project_dirs: List[Path] = []
    for workspace_config in _discover_workspace_config_paths(root):
        try:
            resolved = _resolve_project_directories_from_config(workspace_config)
        except ProjectMarkerError:
            continue
        for project_dir in resolved:
            if project_dir.is_dir():
                project_dirs.append(project_dir)
    if not project_dirs:
        project_dirs.extend(_discover_legacy_project_directories(root))
    return _normalize_project_directories(project_dirs)


def discover_kanbus_projects(root: Path) -> List[Path]:
    """Discover project directories from Kanbus configuration only.

    :param root: Root directory to search from.
    :type root: Path
    :return: List of configured project directories.
    :rtype: List[Path]
    :raises ProjectMarkerError: If a referenced path is missing.
    """
    config_path = root / ".kanbus.yml"
    if not config_path.is_file():
        return []
    return _normalize_project_directories(
        _resolve_project_directories_from_config(config_path)
    )


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
    projects.append(
        ResolvedProject(label=configuration.project_key, project_dir=primary)
    )
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


def _resolve_project_directories_from_config(config_path: Path) -> List[Path]:
    try:
        configuration = _load_configuration(config_path)
    except RuntimeError as error:
        raise ProjectMarkerError(str(error)) from error
    project_dirs = _resolve_project_directories(config_path.parent, configuration)
    return _apply_ignore_paths_for_config(
        config_path.parent, configuration, project_dirs
    )


def _apply_ignore_paths_for_config(
    base: Path, configuration: ProjectConfiguration, project_dirs: List[Path]
) -> List[Path]:
    if not configuration.ignore_paths:
        return project_dirs
    ignored = set()
    for pattern in configuration.ignore_paths:
        ignore_path = base / pattern
        try:
            ignored.add(ignore_path.resolve())
        except OSError:
            pass
    return [path for path in project_dirs if path.resolve() not in ignored]


def _discover_workspace_config_paths(root: Path) -> List[Path]:
    configs: List[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError as error:
            if current == root:
                raise ProjectMarkerError(str(error)) from error
            continue
        config_path = current / ".kanbus.yml"
        if config_path.is_file():
            configs.append(config_path)
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.is_symlink():
                continue
            if entry.name in WORKSPACE_IGNORE_DIRS:
                continue
            stack.append(entry)
    return sorted(configs, key=str)


def _discover_legacy_project_directories(root: Path) -> List[Path]:
    projects: List[Path] = []
    if root.is_dir() and root.name == "project":
        projects.append(root)
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError as error:
            if current == root:
                raise ProjectMarkerError(str(error)) from error
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.is_symlink():
                continue
            if entry.name == "project":
                projects.append(entry)
                continue
            if entry.name in LEGACY_DISCOVERY_IGNORE_DIRS:
                continue
            stack.append(entry)
    return projects


def _normalize_project_directories(paths: Iterable[Path]) -> List[Path]:
    normalized: List[Path] = []
    seen: set[Path] = set()
    for path in paths:
        candidate = resolve_project_path(path)
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return sorted(normalized, key=str)


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
    current: Optional[Path] = root
    while current is not None:
        candidate = current / ".kanbus.yml"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _load_configuration(marker: Path) -> ProjectConfiguration:
    return load_project_configuration(marker)


def load_project_directory(root: Path) -> Path:
    """Load the primary project directory for write operations.

    When a configuration file is found, derives the project directory directly
    from ``project_directory`` in the config. Virtual project directories are
    for reading and lookup only and are not returned here.

    :param root: Repository root path.
    :type root: Path
    :return: Path to the primary project directory.
    :rtype: Path
    :raises ProjectMarkerError: If no project is found or the configuration
        is invalid.
    """
    marker = _find_configuration_file(root)
    if marker is not None:
        try:
            configuration = _load_configuration(marker)
        except RuntimeError as error:
            raise ProjectMarkerError(str(error)) from error
        primary = marker.parent / configuration.project_directory
        filtered = _apply_ignore_paths_for_config(
            marker.parent, configuration, [primary]
        )
        if not filtered:
            raise ProjectMarkerError("project not initialized")
        return _normalize_project_directories(filtered)[0]

    project_dirs = discover_project_directories(root)
    if not project_dirs:
        raise ProjectMarkerError("project not initialized")
    if len(project_dirs) > 1:
        discovered = ", ".join(str(path) for path in project_dirs)
        raise ProjectMarkerError(
            f"multiple projects found: {discovered}. "
            "Run this command from a directory with a single project/"
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
