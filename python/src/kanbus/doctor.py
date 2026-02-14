"""Environment diagnostics for Kanbus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.file_io import InitializationError, ensure_git_repository
from kanbus.project import (
    ProjectMarkerError,
    get_configuration_path,
    load_project_directory,
)


class DoctorError(RuntimeError):
    """Raised when doctor checks fail."""


@dataclass(frozen=True)
class DoctorResult:
    """Result of running doctor checks."""

    project_dir: Path


def run_doctor(root: Path) -> DoctorResult:
    """Run diagnostic checks for Kanbus.

    :param root: Repository root path.
    :type root: Path
    :return: Doctor result with project directory.
    :rtype: DoctorResult
    :raises DoctorError: If any check fails.
    """
    try:
        ensure_git_repository(root)
    except InitializationError as error:
        raise DoctorError(str(error)) from error

    try:
        project_dir = load_project_directory(root)
    except ProjectMarkerError as error:
        raise DoctorError(str(error)) from error

    try:
        load_project_configuration(get_configuration_path(project_dir))
    except ConfigurationError as error:
        raise DoctorError(str(error)) from error

    return DoctorResult(project_dir=project_dir)
