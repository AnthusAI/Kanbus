"""One resolved project context per command.

A :class:`ProjectContext` is built once at command entry. It carries the root
the command runs from, the configuration file that governs it, the loaded
configuration, the primary project directory and the overlay settings, so no
code path below the entry point rediscovers the root or reloads the
configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from kanbus.config_loader import load_project_configuration
from kanbus.models import OverlayConfig, ProjectConfiguration
from kanbus.project import (
    ProjectMarkerError,
    ResolvedProject,
    _apply_ignore_paths_for_config,
    _resolve_labeled_project_directories,
    get_configuration_path,
    resolve_project_path,
)

PROJECT_NOT_INITIALIZED_MESSAGE = "project not initialized"


def locate_configuration_path(root: Path) -> Optional[Path]:
    """Locate the configuration file that governs a root.

    :param root: Working root used for the upward search.
    :type root: Path
    :return: Configuration path, or None when no ``.kanbus.yml`` exists above root.
    :rtype: Optional[Path]
    :raises ConfigurationError: If the configuration path lookup fails.
    """
    try:
        return get_configuration_path(root)
    except ProjectMarkerError as error:
        if str(error) == PROJECT_NOT_INITIALIZED_MESSAGE:
            return None
        raise


@dataclass(frozen=True)
class ProjectContext:
    """Everything a command needs to know about the project it runs against.

    :param root: Working root the command was started from.
    :param config_path: The ``.kanbus.yml`` that governs ``root``.
    :param repository_root: Directory containing ``config_path``.
    :param configuration: The configuration loaded once from ``config_path``.
    :param project_dir: Primary project directory declared by the configuration.
    :param overlay: Overlay settings from the configuration.
    """

    root: Path
    config_path: Path
    repository_root: Path
    configuration: ProjectConfiguration
    project_dir: Path
    overlay: OverlayConfig

    @classmethod
    def discover(cls, root: Path) -> Optional["ProjectContext"]:
        """Build a context for a root, returning None when no configuration exists.

        :param root: Working root used for the upward search.
        :type root: Path
        :return: The context, or None when no configuration file exists.
        :rtype: Optional[ProjectContext]
        :raises ConfigurationError: If the configuration file is invalid.
        """
        config_path = locate_configuration_path(root)
        if config_path is None:
            return None
        return cls.from_configuration_path(root, config_path)

    @classmethod
    def from_configuration_path(cls, root: Path, config_path: Path) -> "ProjectContext":
        """Build a context from an already located configuration path.

        :param root: Working root the command runs from.
        :type root: Path
        :param config_path: Path returned by :func:`locate_configuration_path`.
        :type config_path: Path
        :return: The context.
        :rtype: ProjectContext
        :raises ConfigurationError: If the configuration file is invalid.
        """
        configuration = load_project_configuration(config_path)
        repository_root = config_path.parent
        project_dir = resolve_project_path(
            repository_root / configuration.project_directory
        )
        return cls(
            root=root,
            config_path=config_path,
            repository_root=repository_root,
            configuration=configuration,
            project_dir=project_dir,
            overlay=configuration.overlay,
        )

    def configuration_at_root(self) -> Optional[ProjectConfiguration]:
        """Return the configuration when it lives directly in the working root.

        Commands scan for nested workspaces only when the root itself does not
        hold the configuration; this tells them which case applies.

        :return: The configuration, or None when the root holds no configuration.
        :rtype: Optional[ProjectConfiguration]
        """
        if resolve_project_path(self.repository_root) == resolve_project_path(
            self.root
        ):
            return self.configuration
        return None

    def primary_project_directory(self) -> Path:
        """Return the primary project directory for write operations.

        :return: The primary project directory.
        :rtype: Path
        :raises ProjectMarkerError: If the primary directory is ignored.
        """
        filtered = _apply_ignore_paths_for_config(
            self.repository_root,
            self.configuration,
            [self.repository_root / self.configuration.project_directory],
        )
        if not filtered:
            raise ProjectMarkerError(PROJECT_NOT_INITIALIZED_MESSAGE)
        return self.project_dir

    def labeled_projects(self) -> List[ResolvedProject]:
        """Resolve every labeled project directory declared by the configuration.

        :return: Labeled project directories.
        :rtype: List[ResolvedProject]
        :raises ProjectMarkerError: If a virtual project path is missing.
        """
        return _resolve_labeled_project_directories(
            self.repository_root, self.configuration
        )

    def configuration_for_project_directory(
        self, project_dir: Path
    ) -> ProjectConfiguration:
        """Return the configuration that governs a project directory.

        The context configuration is reused when the directory belongs to the
        same configuration file. A project owned by a different configuration
        file, such as a virtual project, is loaded from that file.

        :param project_dir: Project directory whose configuration is needed.
        :type project_dir: Path
        :return: The governing configuration.
        :rtype: ProjectConfiguration
        :raises ProjectMarkerError: If no configuration governs the directory.
        :raises ConfigurationError: If the owning configuration is invalid.
        """
        owning_path = get_configuration_path(project_dir)
        if resolve_project_path(owning_path) == resolve_project_path(self.config_path):
            return self.configuration
        return load_project_configuration(owning_path)


def require_project_context(root: Path) -> ProjectContext:
    """Build a context for a root, failing when no configuration exists.

    :param root: Working root used for the upward search.
    :type root: Path
    :return: The context.
    :rtype: ProjectContext
    :raises ProjectMarkerError: If no configuration exists.
    :raises ConfigurationError: If the configuration file is invalid.
    """
    context = ProjectContext.discover(root)
    if context is None:
        raise ProjectMarkerError(PROJECT_NOT_INITIALIZED_MESSAGE)
    return context
