"""Environment diagnostics for Kanbus."""

from __future__ import annotations

import subprocess
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
from kanbus.gossip import MISSING_PROJECT_ID_MESSAGE
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
    events_gitignore_warning: str | None = None
    realtime_project_id_warning: str | None = None


def describe_gitignore_rule_hiding_events(root: Path, project_dir: Path) -> str | None:
    """Describe the gitignore rule that hides the project events directory.

    :param root: Repository root path.
    :type root: Path
    :param project_dir: Primary project directory.
    :type project_dir: Path
    :return: Warning text naming the rule to remove, or None when events are tracked.
    :rtype: str | None
    """
    events_relative_path = (
        (project_dir / "events").resolve().relative_to(root.resolve()).as_posix()
    )
    check_result = subprocess.run(
        ["git", "check-ignore", "-v", "--", f"{events_relative_path}/probe.json"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if check_result.returncode != 0:
        return None
    rule_source = check_result.stdout.split("\t", 1)[0].strip()
    source_file, line_number, pattern = rule_source.split(":", 2)
    return (
        f"events are enabled but {events_relative_path} is gitignored by the rule "
        f"{pattern} ({source_file}:{line_number}); remove the rule so kbs commit "
        "includes events"
    )


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

    events_gitignore_warning = (
        describe_gitignore_rule_hiding_events(root, project_dir)
        if configuration.events
        else None
    )

    realtime_project_id_warning = (
        MISSING_PROJECT_ID_MESSAGE
        if not configuration.project_id and configuration.realtime.broker != "off"
        else None
    )

    return DoctorResult(
        project_dir=project_dir,
        ai_credential_source=ai_credential_source,
        methodology_names=methodology_names,
        project_management_file_is_current=project_management_file_is_current,
        events_gitignore_warning=events_gitignore_warning,
        realtime_project_id_warning=realtime_project_id_warning,
    )
