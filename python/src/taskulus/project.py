"""Project discovery utilities."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional


class ProjectMarkerError(RuntimeError):
    """Raised when project discovery fails."""


def discover_project_directories(root: Path) -> List[Path]:
    """Discover project directories beneath the current root.

    :param root: Root directory to search from.
    :type root: Path
    :return: List of discovered project directories.
    :rtype: List[Path]
    :raises ProjectMarkerError: If a .taskulus file references a missing path.
    """
    project_dirs: List[Path] = []
    for current, dirs, _files in os.walk(root):
        if "project" in dirs:
            project_dirs.append(Path(current) / "project")
        if "project" in dirs:
            dirs.remove("project")
        if "project-local" in dirs:
            dirs.remove("project-local")
    project_dirs.extend(_discover_taskulus_projects(root))
    return sorted({path.resolve() for path in project_dirs})


def _discover_taskulus_projects(root: Path) -> List[Path]:
    dotfile = _find_taskulus_dotfile(root)
    if dotfile is None:
        return []
    paths: List[Path] = []
    for line in dotfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        candidate = Path(stripped)
        if not candidate.is_absolute():
            candidate = (dotfile.parent / candidate).resolve()
        if not candidate.is_dir():
            raise ProjectMarkerError(f"taskulus path not found: {candidate}")
        paths.append(candidate)
    return paths


def _find_taskulus_dotfile(root: Path) -> Optional[Path]:
    git_root = _find_git_root(root)
    current = root.resolve()
    while True:
        candidate = current / ".taskulus"
        if candidate.is_file():
            return candidate
        if git_root is not None and current == git_root:
            break
        if current.parent == current:
            break
        current = current.parent
    return None


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
        raise ProjectMarkerError("multiple projects found")

    return project_dirs[0]


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
    issues_dir.mkdir(parents=True, exist_ok=True)
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
