"""Environment diagnostics for Kanbus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click

from kanbus.agents_management import build_project_management_text
from kanbus.ai_credentials import (
    CredentialSource,
    describe_api_key_source,
    resolve_api_key_source,
)
from kanbus.config_loader import ConfigurationError, load_project_configuration
from kanbus.file_io import InitializationError, ensure_git_repository
from kanbus.maintenance import ProjectValidationError, validate_project
from kanbus.methodology_bundles import MethodologyError, load_selected_methodologies
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
    ai_credential_source: str = CredentialSource.NONE.value
    methodology_names: tuple[str, ...] = ()
    project_management_file_is_current: bool | None = None


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
        configuration_path = get_configuration_path(root)
        configuration = load_project_configuration(configuration_path)
    except (ConfigurationError, ProjectMarkerError) as error:
        raise DoctorError(str(error)) from error

    try:
        validate_project(root)
    except ProjectValidationError as error:
        raise DoctorError(str(error)) from error

    try:
        methodology_names = tuple(
            methodology.name
            for methodology in load_selected_methodologies(root, configuration)
        )
        expected_project_management_text = build_project_management_text(root)
    except (MethodologyError, click.ClickException) as error:
        raise DoctorError(str(error)) from error
    project_management_path = root / "CONTRIBUTING_AGENT.md"
    project_management_file_is_current = None
    if project_management_path.exists():
        project_management_file_is_current = (
            project_management_path.read_text(encoding="utf-8")
            == expected_project_management_text
        )

    ai_credential_source = CredentialSource.NONE.value
    try:
        ai_credential_source = describe_api_key_source(resolve_api_key_source(root))
    except Exception:
        ai_credential_source = CredentialSource.NONE.value

    return DoctorResult(
        project_dir=project_dir,
        ai_credential_source=ai_credential_source,
        methodology_names=methodology_names,
        project_management_file_is_current=project_management_file_is_current,
    )
