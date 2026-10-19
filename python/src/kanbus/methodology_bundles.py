"""Methodology bundles assembled into the generated CONTRIBUTING_AGENT.md.

A methodology is a Markdown document with YAML frontmatter that carries one
set of process opinions (for example Behavior-Driven Design or Git Flow).
Kanbus core stays neutral; the configured methodologies supply the opinions.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path, PurePath

import yaml
from jinja2 import Environment

from kanbus.models import ProjectConfiguration, ProjectMethodologyBundleReference

BUILT_IN_METHODOLOGY_NAMES = ("bdd", "git-flow")
DEFAULT_METHODOLOGY_NAMES = ("bdd", "git-flow")
METHODOLOGY_DOCUMENT_FILENAME = "METHODOLOGY.md"
FRONTMATTER_DELIMITER = "---\n"
ALLOWED_FRONTMATTER_KEYS = {"name", "title", "description", "tools"}
TOOL_DECLARATION_KEYS = {"name", "command", "purpose"}
METHODOLOGY_TOOL_INVOCATION_PREFIX = "kbs methodology run"
METHODOLOGY_DIRECTORY_ENVIRONMENT_VARIABLE = "KANBUS_METHODOLOGY_DIRECTORY"


class MethodologyError(ValueError):
    """Raised when a methodology cannot be resolved, parsed, or rendered."""


@dataclass(frozen=True)
class MethodologyToolDeclaration:
    """A tool a methodology bundle ships, declared in its frontmatter."""

    name: str
    command: str
    purpose: str


@dataclass(frozen=True)
class MethodologyDocument:
    """A methodology document split into its frontmatter and template body."""

    name: str
    title: str
    description: str
    template_body: str
    tools: list[MethodologyToolDeclaration] = field(default_factory=list)
    bundle_directory: Path | None = None


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
    tools = _parse_methodology_tool_declarations(
        frontmatter.get("tools") or [], source_description
    )
    return MethodologyDocument(
        name=str(frontmatter["name"]),
        title=str(frontmatter["title"]),
        description=str(frontmatter.get("description") or ""),
        template_body=template_body,
        tools=tools,
    )


def _parse_methodology_tool_declarations(
    raw_tool_declarations: object, source_description: str
) -> list[MethodologyToolDeclaration]:
    if not isinstance(raw_tool_declarations, list):
        raise MethodologyError(
            f"methodology {source_description} has invalid frontmatter: "
            "tools must be a list"
        )
    tools: list[MethodologyToolDeclaration] = []
    for raw_tool_declaration in raw_tool_declarations:
        if (
            not isinstance(raw_tool_declaration, dict)
            or set(raw_tool_declaration) != TOOL_DECLARATION_KEYS
        ):
            raise MethodologyError(
                f"methodology {source_description} has invalid frontmatter: "
                "each tool needs exactly name, command and purpose"
            )
        tool = MethodologyToolDeclaration(
            name=str(raw_tool_declaration["name"]),
            command=str(raw_tool_declaration["command"]),
            purpose=str(raw_tool_declaration["purpose"]),
        )
        if any(earlier_tool.name == tool.name for earlier_tool in tools):
            raise MethodologyError(
                f"methodology {source_description} declares tool {tool.name} "
                "more than once"
            )
        command_parts = PurePath(tool.command).parts
        command_stays_inside_bundle = (
            bool(tool.command)
            and not PurePath(tool.command).is_absolute()
            and ".." not in command_parts
        )
        if not command_stays_inside_bundle:
            raise MethodologyError(
                f"methodology {source_description} tool {tool.name} command must be "
                f"a path inside the bundle: {tool.command}"
            )
        tools.append(tool)
    return tools


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
    methodology = parse_methodology_document(
        source_text, f"bundle {bundle_relative_path}"
    )
    return MethodologyDocument(
        name=methodology.name,
        title=methodology.title,
        description=methodology.description,
        template_body=methodology.template_body,
        tools=methodology.tools,
        bundle_directory=bundle_directory,
    )


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
) -> list[dict[str, object]]:
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
    :rtype: list[dict[str, object]]
    :raises MethodologyError: If loading or rendering a methodology fails.
    """
    return [
        render_methodology_document(methodology, template_environment, template_context)
        for methodology in load_selected_methodologies(repository_root, configuration)
    ]


def render_methodology_document(
    methodology: MethodologyDocument,
    template_environment: Environment,
    template_context: dict[str, object],
) -> dict[str, object]:
    """Render one methodology body and append its tool listing.

    :param methodology: Parsed methodology document.
    :type methodology: MethodologyDocument
    :param template_environment: Jinja environment used for the agents file.
    :type template_environment: Environment
    :param template_context: Agents-file template context.
    :type template_context: dict[str, object]
    :return: Rendered methodology as a template-ready dictionary.
    :rtype: dict[str, object]
    :raises MethodologyError: If the body fails to render.
    """
    try:
        content = template_environment.from_string(methodology.template_body).render(
            template_context
        )
    except Exception as error:
        raise MethodologyError(
            f"methodology {methodology.name} failed to render: {error}"
        ) from error
    rendered_tools = [
        {
            "name": tool.name,
            "purpose": tool.purpose,
            "invocation": (
                f"{METHODOLOGY_TOOL_INVOCATION_PREFIX} "
                f"{methodology.name} {tool.name}"
            ),
        }
        for tool in methodology.tools
    ]
    if rendered_tools:
        content = (
            content.rstrip()
            + "\n\n"
            + _methodology_tool_listing_text(methodology.title, rendered_tools)
        )
    rendered_methodology: dict[str, object] = asdict(
        RenderedMethodology(
            name=methodology.name,
            title=methodology.title,
            description=methodology.description,
            content=content,
        )
    )
    rendered_methodology["tools"] = rendered_tools
    return rendered_methodology


@dataclass(frozen=True)
class MethodologyListing:
    """A methodology as shown by ``kbs methodology list``."""

    name: str
    title: str
    source: str
    active: bool


def list_methodologies(
    repository_root: Path, configuration: ProjectConfiguration
) -> list[MethodologyListing]:
    """List the configured methodologies in order, then inactive built-ins.

    :param repository_root: Repository root path.
    :type repository_root: Path
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :return: Methodology listings.
    :rtype: list[MethodologyListing]
    :raises MethodologyError: If a configured methodology cannot be loaded.
    """
    listings: list[MethodologyListing] = []
    for methodology in load_selected_methodologies(repository_root, configuration):
        source = "built-in"
        if methodology.bundle_directory is not None:
            source = (
                f"bundle {methodology.bundle_directory.relative_to(repository_root)}"
            )
        listings.append(
            MethodologyListing(
                name=methodology.name,
                title=methodology.title,
                source=source,
                active=True,
            )
        )
    for built_in_name in BUILT_IN_METHODOLOGY_NAMES:
        if any(listing.name == built_in_name for listing in listings):
            continue
        built_in_methodology = load_built_in_methodology(built_in_name)
        listings.append(
            MethodologyListing(
                name=built_in_methodology.name,
                title=built_in_methodology.title,
                source="built-in",
                active=False,
            )
        )
    return listings


def _methodology_tool_listing_text(
    methodology_title: str, rendered_tools: list[dict[str, str]]
) -> str:
    tool_lines = "\n".join(
        f"- `{tool['invocation']}`: {tool['purpose']}" for tool in rendered_tools
    )
    return (
        f"### {methodology_title} tools\n\n"
        f"Run these from the repository root:\n\n{tool_lines}\n"
    )


def run_methodology_tool(
    repository_root: Path,
    configuration: ProjectConfiguration,
    methodology_name: str,
    tool_name: str,
    tool_arguments: list[str],
) -> str:
    """Run a tool declared by one of the configured methodologies.

    The tool runs from the repository root with the bundle directory exported in
    ``KANBUS_METHODOLOGY_DIRECTORY``. Its standard output is returned; its
    standard error is passed through.

    :param repository_root: Repository root path.
    :type repository_root: Path
    :param configuration: Project configuration.
    :type configuration: ProjectConfiguration
    :param methodology_name: Configured methodology name.
    :type methodology_name: str
    :param tool_name: Tool name declared in the methodology frontmatter.
    :type tool_name: str
    :param tool_arguments: Arguments passed to the tool unchanged.
    :type tool_arguments: list[str]
    :return: The tool's standard output.
    :rtype: str
    :raises MethodologyError: If the methodology or tool is unknown, the tool
        cannot start, or it exits unsuccessfully.
    """
    configured_methodologies = load_selected_methodologies(
        repository_root, configuration
    )
    methodology = next(
        (
            configured_methodology
            for configured_methodology in configured_methodologies
            if configured_methodology.name == methodology_name
        ),
        None,
    )
    if methodology is None:
        configured_names = ", ".join(
            configured_methodology.name
            for configured_methodology in configured_methodologies
        )
        raise MethodologyError(
            f"methodology not configured: {methodology_name} "
            f"(configured methodologies: {configured_names})"
        )
    tool = next(
        (
            declared_tool
            for declared_tool in methodology.tools
            if declared_tool.name == tool_name
        ),
        None,
    )
    if tool is None:
        declared_tool_names = [
            declared_tool.name for declared_tool in methodology.tools
        ]
        declared_tool_summary = (
            f"declared tools: {', '.join(declared_tool_names)}"
            if declared_tool_names
            else "it declares no tools"
        )
        raise MethodologyError(
            f"methodology {methodology_name} has no tool named {tool_name} "
            f"({declared_tool_summary})"
        )
    if methodology.bundle_directory is None:
        raise MethodologyError(
            f"methodology {methodology_name} is built in and has no bundle directory"
        )
    tool_environment = dict(os.environ)
    tool_environment[METHODOLOGY_DIRECTORY_ENVIRONMENT_VARIABLE] = str(
        methodology.bundle_directory
    )
    try:
        completed_tool = subprocess.run(
            [str(methodology.bundle_directory / tool.command), *tool_arguments],
            cwd=repository_root,
            env=tool_environment,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise MethodologyError(
            f"methodology tool {methodology_name} {tool_name} could not start "
            f"{tool.command}: {error}"
        ) from error
    if completed_tool.returncode == 0:
        sys.stderr.write(completed_tool.stderr)
        return completed_tool.stdout
    exit_status_description = (
        str(completed_tool.returncode) if completed_tool.returncode >= 0 else "a signal"
    )
    raise MethodologyError(
        f"{completed_tool.stdout}{completed_tool.stderr}methodology tool "
        f"{methodology_name} {tool_name} exited with status {exit_status_description}"
    )
