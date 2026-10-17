"""Methodology bundles assembled into the generated CONTRIBUTING_AGENT.md.

A methodology is a Markdown document with YAML frontmatter that carries one
set of process opinions (for example Behavior-Driven Design or Git Flow).
Kanbus core stays neutral; the configured methodologies supply the opinions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path

import yaml
from jinja2 import Environment

from kanbus.models import ProjectConfiguration, ProjectMethodologyBundleReference

BUILT_IN_METHODOLOGY_NAMES = ("bdd", "git-flow")
DEFAULT_METHODOLOGY_NAMES = ("bdd", "git-flow")
METHODOLOGY_DOCUMENT_FILENAME = "METHODOLOGY.md"
FRONTMATTER_DELIMITER = "---\n"
ALLOWED_FRONTMATTER_KEYS = {"name", "title", "description"}


class MethodologyError(ValueError):
    """Raised when a methodology cannot be resolved, parsed, or rendered."""


@dataclass(frozen=True)
class MethodologyDocument:
    """A methodology document split into its frontmatter and template body."""

    name: str
    title: str
    description: str
    template_body: str


@dataclass(frozen=True)
class RenderedMethodology:
    """A methodology whose body has been rendered with the agents-file context."""

    name: str
    title: str
    description: str
    content: str


def selected_methodologies(
    configuration: ProjectConfiguration,
) -> list[str | ProjectMethodologyBundleReference]:
    """Return the methodologies selected by the configuration.

    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Configured selections, or the default built-in names when unset.
    :rtype: list[str | ProjectMethodologyBundleReference]
    """
    if configuration.methodologies is None:
        return list(DEFAULT_METHODOLOGY_NAMES)
    return list(configuration.methodologies)


def parse_methodology_document(
    source_text: str, source_description: str
) -> MethodologyDocument:
    """Parse a methodology document with ``---`` delimited YAML frontmatter.

    :param source_text: Full METHODOLOGY.md text.
    :type source_text: str
    :param source_description: Where the text came from, for error messages.
    :type source_description: str
    :return: Parsed methodology document.
    :rtype: MethodologyDocument
    :raises MethodologyError: If the frontmatter is missing or malformed.
    """
    malformed_frontmatter_message = (
        f"methodology {source_description} must begin with YAML frontmatter "
        "between --- lines"
    )
    normalized_text = source_text.replace("\r\n", "\n")
    if not normalized_text.startswith(FRONTMATTER_DELIMITER):
        raise MethodologyError(malformed_frontmatter_message)
    after_opening_delimiter = normalized_text[len(FRONTMATTER_DELIMITER) :]
    closing_delimiter = "\n" + FRONTMATTER_DELIMITER
    closing_delimiter_index = after_opening_delimiter.find(closing_delimiter)
    if closing_delimiter_index < 0:
        raise MethodologyError(malformed_frontmatter_message)
    frontmatter_text = after_opening_delimiter[:closing_delimiter_index]
    template_body = after_opening_delimiter[
        closing_delimiter_index + len(closing_delimiter) :
    ]
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as error:
        raise MethodologyError(
            f"methodology {source_description} has invalid frontmatter: {error}"
        ) from error
    if not isinstance(frontmatter, dict):
        raise MethodologyError(malformed_frontmatter_message)
    unknown_keys = sorted(set(frontmatter) - ALLOWED_FRONTMATTER_KEYS)
    missing_keys = sorted({"name", "title"} - set(frontmatter))
    if unknown_keys or missing_keys:
        raise MethodologyError(
            f"methodology {source_description} has invalid frontmatter: "
            f"unknown keys {unknown_keys}, missing keys {missing_keys}"
        )
    return MethodologyDocument(
        name=str(frontmatter["name"]),
        title=str(frontmatter["title"]),
        description=str(frontmatter.get("description") or ""),
        template_body=template_body,
    )


def load_built_in_methodology(name: str) -> MethodologyDocument:
    """Load a built-in methodology by name.

    :param name: Built-in methodology name.
    :type name: str
    :return: Parsed methodology document.
    :rtype: MethodologyDocument
    :raises MethodologyError: If no built-in methodology has that name.
    """
    if name not in BUILT_IN_METHODOLOGY_NAMES:
        raise MethodologyError(
            f"unknown methodology: {name} "
            f"(built-in methodologies: {', '.join(BUILT_IN_METHODOLOGY_NAMES)})"
        )
    source_text = (
        resources.files("kanbus")
        .joinpath("methodologies", name, "METHODOLOGY.md")
        .read_text(encoding="utf-8")
    )
    return parse_methodology_document(source_text, f"built-in {name}")


def load_project_methodology_bundle(
    repository_root: Path, bundle_relative_path: str
) -> MethodologyDocument:
    """Load a methodology bundle directory from the repository.

    :param repository_root: Repository root path.
    :type repository_root: Path
    :param bundle_relative_path: Bundle directory relative to the repository root.
    :type bundle_relative_path: str
    :return: Parsed methodology document.
    :rtype: MethodologyDocument
    :raises MethodologyError: If the bundle or its document is missing or malformed.
    """
    bundle_directory = repository_root / bundle_relative_path
    if not bundle_directory.is_dir():
        raise MethodologyError(f"methodology bundle not found: {bundle_relative_path}")
    document_path = bundle_directory / METHODOLOGY_DOCUMENT_FILENAME
    try:
        source_text = document_path.read_text(encoding="utf-8")
    except OSError as error:
        raise MethodologyError(
            f"methodology bundle {bundle_relative_path} has no "
            f"{METHODOLOGY_DOCUMENT_FILENAME}"
        ) from error
    return parse_methodology_document(source_text, f"bundle {bundle_relative_path}")


def load_selected_methodologies(
    repository_root: Path, configuration: ProjectConfiguration
) -> list[MethodologyDocument]:
    """Load every methodology selected by the configuration, in configured order.

    :param repository_root: Repository root path.
    :type repository_root: Path
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Parsed methodology documents.
    :rtype: list[MethodologyDocument]
    :raises MethodologyError: For unknown, missing, malformed or duplicated methodologies.
    """
    loaded_methodologies: list[MethodologyDocument] = []
    for selection in selected_methodologies(configuration):
        if isinstance(selection, ProjectMethodologyBundleReference):
            methodology = load_project_methodology_bundle(
                repository_root, selection.path
            )
        else:
            methodology = load_built_in_methodology(selection)
        if any(
            loaded_methodology.name == methodology.name
            for loaded_methodology in loaded_methodologies
        ):
            raise MethodologyError(
                f"methodology listed more than once: {methodology.name}"
            )
        loaded_methodologies.append(methodology)
    return loaded_methodologies


def render_selected_methodologies(
    repository_root: Path,
    configuration: ProjectConfiguration,
    template_environment: Environment,
    template_context: dict[str, object],
) -> list[dict[str, str]]:
    """Render each selected methodology body with the agents-file context.

    :param repository_root: Repository root path.
    :type repository_root: Path
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :param template_environment: Jinja environment used for the agents file.
    :type template_environment: Environment
    :param template_context: Agents-file template context.
    :type template_context: dict[str, object]
    :return: Rendered methodologies as template-ready dictionaries.
    :rtype: list[dict[str, str]]
    :raises MethodologyError: If loading or rendering a methodology fails.
    """
    rendered_methodologies: list[dict[str, str]] = []
    for methodology in load_selected_methodologies(repository_root, configuration):
        try:
            content = template_environment.from_string(
                methodology.template_body
            ).render(template_context)
        except Exception as error:
            raise MethodologyError(
                f"methodology {methodology.name} failed to render: {error}"
            ) from error
        rendered_methodologies.append(
            asdict(
                RenderedMethodology(
                    name=methodology.name,
                    title=methodology.title,
                    description=methodology.description,
                    content=content,
                )
            )
        )
    return rendered_methodologies
