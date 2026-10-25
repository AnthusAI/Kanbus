"""Steps for managing AGENTS.md Kanbus instructions."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from behave import given, then, when

from features.steps.shared import ensure_git_repository, run_cli, run_cli_with_input
from kanbus.agents_management import (
    build_project_management_text,
    KANBUS_SECTION_TEXT,
)


def _fixture_path(name: str) -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "specs" / "fixtures" / "agents_project" / name


def _config_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / ".kanbus.yml"


def _copy_configuration(repo_path: Path) -> None:
    config = _config_path()
    if config.exists():
        (repo_path / ".kanbus.yml").write_text(
            config.read_text(encoding="utf-8"), encoding="utf-8"
        )


def _write_agents_fixture(context: object, fixture_name: str) -> None:
    temp_dir = Path(context.temp_dir)
    repo_path = temp_dir / "repo"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repo_path)
    _copy_configuration(repo_path)
    fixture = _fixture_path(fixture_name)
    content = fixture.read_text(encoding="utf-8")
    (repo_path / "AGENTS.md").write_text(content, encoding="utf-8")
    context.working_directory = repo_path
    context.original_agents_text = content


def _read_agents(context: object) -> str:
    repo_path = Path(context.working_directory)
    return (repo_path / "AGENTS.md").read_text(encoding="utf-8")


def _extract_kanbus_section(content: str) -> str:
    lines = content.splitlines()
    start = None
    end = len(lines)
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#") and "kanbus" in stripped.lower():
            start = index
            level = len(stripped) - len(stripped.lstrip("#"))
            for next_index in range(index + 1, len(lines)):
                next_line = lines[next_index].lstrip()
                if not next_line.startswith("#"):
                    continue
                next_level = len(next_line) - len(next_line.lstrip("#"))
                if next_level <= level:
                    end = next_index
                    break
            break
    if start is None:
        return ""
    return "\n".join(lines[start:end]).strip()


@given("a Kanbus repository without AGENTS.md")
def given_repo_without_agents(context: object) -> None:
    temp_dir = Path(context.temp_dir)
    repo_path = temp_dir / "repo"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repo_path)
    _copy_configuration(repo_path)
    context.working_directory = repo_path


@given("a Kanbus repository with AGENTS.md without a Kanbus section")
def given_repo_agents_without_kanbus(context: object) -> None:
    _write_agents_fixture(context, "agents_no_kanbus.md")


@given("a Kanbus repository with AGENTS.md containing a Kanbus section")
def given_repo_agents_with_kanbus(context: object) -> None:
    _write_agents_fixture(context, "agents_with_kanbus.md")


@when('I run "kanbus setup agents" non-interactively')
def when_run_setup_agents_non_interactive(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_NON_INTERACTIVE"] = "1"
    context.environment_overrides = overrides
    run_cli(context, "kanbus setup agents")


@when('I run "{command}" with stdin "{stdin_text}" in non-interactive mode')
def when_run_command_with_stdin_non_interactive(
    context: object, command: str, stdin_text: str
) -> None:
    """Run a command with piped stdin while KANBUS_NON_INTERACTIVE is set.

    :param context: Behave context object.
    :type context: object
    :param command: Full command string.
    :type command: str
    :param stdin_text: Stdin content, with escaped newlines.
    :type stdin_text: str
    """
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_NON_INTERACTIVE"] = "1"
    context.environment_overrides = overrides
    run_cli_with_input(context, command, stdin_text.replace("\\n", "\n"))


@when('I run "{command}" with stdin "{stdin_text}" without forced interactivity')
def when_run_command_with_stdin_unforced(
    context: object, command: str, stdin_text: str
) -> None:
    """Run a command with piped stdin and KANBUS_FORCE_INTERACTIVE disabled.

    :param context: Behave context object.
    :type context: object
    :param command: Full command string.
    :type command: str
    :param stdin_text: Stdin content, with escaped newlines.
    :type stdin_text: str
    """
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_FORCE_INTERACTIVE"] = "0"
    context.environment_overrides = overrides
    run_cli_with_input(context, command, stdin_text.replace("\\n", "\n"))


@when('I run "{command}" with stdin "{stdin_text}" with forced interactivity')
def when_run_command_with_stdin_forced(
    context: object, command: str, stdin_text: str
) -> None:
    """Run a command with piped stdin and KANBUS_FORCE_INTERACTIVE enabled.

    :param context: Behave context object.
    :type context: object
    :param command: Full command string.
    :type command: str
    :param stdin_text: Stdin content, with escaped newlines.
    :type stdin_text: str
    """
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["KANBUS_FORCE_INTERACTIVE"] = "1"
    context.environment_overrides = overrides
    run_cli_with_input(context, command, stdin_text.replace("\\n", "\n"))


@then("AGENTS.md should exist")
def then_agents_exists(context: object) -> None:
    repo_path = Path(context.working_directory)
    assert (repo_path / "AGENTS.md").exists()


@then("AGENTS.md should contain the Kanbus section")
def then_agents_contains_kanbus(context: object) -> None:
    content = _read_agents(context)
    section = _extract_kanbus_section(content)
    assert section == KANBUS_SECTION_TEXT.strip()


@then("the Kanbus section should appear after the H1 heading")
def then_kanbus_after_h1(context: object) -> None:
    content = _read_agents(context)
    lines = content.splitlines()
    h1_index = next(
        index for index, line in enumerate(lines) if line.strip().startswith("# ")
    )
    kanbus_index = next(
        index for index, line in enumerate(lines) if "kanbus" in line.lower()
    )
    assert kanbus_index > h1_index
    for index in range(h1_index + 1, kanbus_index):
        if lines[index].strip().startswith("## "):
            raise AssertionError("Kanbus section is not the first H2")


@then("AGENTS.md should be unchanged")
def then_agents_unchanged(context: object) -> None:
    content = _read_agents(context)
    assert content == context.original_agents_text


@then("CONTRIBUTING_AGENT.md should exist")
def then_agent_instructions_exists(context: object) -> None:
    repo_path = Path(context.working_directory)
    instructions = repo_path / "CONTRIBUTING_AGENT.md"
    assert instructions.exists()
    content = instructions.read_text(encoding="utf-8")
    expected = build_project_management_text(repo_path)
    assert content.strip() == expected.strip()


@then('CONTRIBUTING_AGENT.md should contain "{text}"')
def then_project_management_contains_text(context: object, text: str) -> None:
    normalized = text.replace('\\"', '"')
    repo_path = Path(context.working_directory)
    content = (repo_path / "CONTRIBUTING_AGENT.md").read_text(encoding="utf-8")
    assert normalized in content


PROJECT_BUNDLE_STEP_PREFIX = "path:"


def _methodology_selection_from_step_text(selection_text: str) -> object:
    if selection_text.startswith(PROJECT_BUNDLE_STEP_PREFIX):
        return {"path": selection_text[len(PROJECT_BUNDLE_STEP_PREFIX) :]}
    return selection_text


def _write_methodology_bundle_document(
    context: object, bundle_relative_path: str, document_text: str
) -> None:
    bundle_directory = Path(context.working_directory) / bundle_relative_path
    bundle_directory.mkdir(parents=True, exist_ok=True)
    (bundle_directory / "METHODOLOGY.md").write_text(document_text, encoding="utf-8")


@given(
    'the repository has a methodology bundle at "{bundle_relative_path}" named "{methodology_name}" with heading "{heading}"'
)
def given_repository_has_methodology_bundle(
    context: object, bundle_relative_path: str, methodology_name: str, heading: str
) -> None:
    _write_methodology_bundle_document(
        context,
        bundle_relative_path,
        f"---\nname: {methodology_name}\ntitle: {heading}\n---\n"
        f"## {heading}\n\nProject key: {{{{ project_key }}}}.\n",
    )


@given(
    'the repository has a methodology bundle at "{bundle_relative_path}" without frontmatter'
)
def given_repository_has_methodology_bundle_without_frontmatter(
    context: object, bundle_relative_path: str
) -> None:
    _write_methodology_bundle_document(
        context, bundle_relative_path, "## Plain Guidance\n"
    )


def _methodology_tool_frontmatter(
    methodology_name: str, tool_declarations: list[dict[str, str]]
) -> str:
    frontmatter = {
        "name": methodology_name,
        "title": f"{methodology_name} methodology",
        "tools": tool_declarations,
    }
    return f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n## Tool Guidance\n"


def _write_methodology_tool_script(
    context: object, bundle_relative_path: str, script_text: str
) -> None:
    tool_script = (
        Path(context.working_directory) / bundle_relative_path / "tools" / "run-tool"
    )
    tool_script.parent.mkdir(parents=True, exist_ok=True)
    tool_script.write_text(f"#!/bin/sh\n{script_text}\n", encoding="utf-8")
    tool_script.chmod(0o755)


@given(
    'the repository has a methodology bundle at "{bundle_relative_path}" named "{methodology_name}" with a tool "{tool_name}" that prints "{printed_text}"'
)
def given_repository_has_methodology_bundle_with_tool(
    context: object,
    bundle_relative_path: str,
    methodology_name: str,
    tool_name: str,
    printed_text: str,
) -> None:
    _write_methodology_bundle_document(
        context,
        bundle_relative_path,
        _methodology_tool_frontmatter(
            methodology_name,
            [
                {
                    "name": tool_name,
                    "command": "tools/run-tool",
                    "purpose": "Report the demo output",
                }
            ],
        ),
    )
    _write_methodology_tool_script(
        context, bundle_relative_path, f'echo "{printed_text} $*"'
    )


@given(
    'the repository has a methodology bundle at "{bundle_relative_path}" named "{methodology_name}" with a failing tool "{tool_name}"'
)
def given_repository_has_methodology_bundle_with_failing_tool(
    context: object,
    bundle_relative_path: str,
    methodology_name: str,
    tool_name: str,
) -> None:
    _write_methodology_bundle_document(
        context,
        bundle_relative_path,
        _methodology_tool_frontmatter(
            methodology_name,
            [
                {
                    "name": tool_name,
                    "command": "tools/run-tool",
                    "purpose": "Always fails",
                }
            ],
        ),
    )
    _write_methodology_tool_script(
        context, bundle_relative_path, 'echo "tool failed loudly"\nexit 3'
    )


@given(
    'the repository has a methodology bundle at "{bundle_relative_path}" declaring a tool "{tool_name}" with command "{command}"'
)
def given_repository_has_methodology_bundle_declaring_tool_command(
    context: object, bundle_relative_path: str, tool_name: str, command: str
) -> None:
    _write_methodology_bundle_document(
        context,
        bundle_relative_path,
        _methodology_tool_frontmatter(
            Path(bundle_relative_path).name,
            [{"name": tool_name, "command": command, "purpose": "Declared only"}],
        ),
    )


@given(
    'the repository has a methodology bundle at "{bundle_relative_path}" declaring the tool "{tool_name}" twice'
)
def given_repository_has_methodology_bundle_declaring_tool_twice(
    context: object, bundle_relative_path: str, tool_name: str
) -> None:
    declaration = {
        "name": tool_name,
        "command": "tools/run-tool",
        "purpose": "Declared twice",
    }
    _write_methodology_bundle_document(
        context,
        bundle_relative_path,
        _methodology_tool_frontmatter(
            Path(bundle_relative_path).name, [declaration, declaration]
        ),
    )


@given('the Kanbus configuration selects methodologies "{methodology_list}"')
@when('the Kanbus configuration selects methodologies "{methodology_list}"')
def given_configuration_selects_methodologies(
    context: object, methodology_list: str
) -> None:
    selected_methodology_names = [
        _methodology_selection_from_step_text(name.strip())
        for name in methodology_list.split(",")
        if name.strip()
    ]
    configuration_path = Path(context.working_directory) / ".kanbus.yml"
    configuration_document = yaml.safe_load(
        configuration_path.read_text(encoding="utf-8")
    )
    configuration_document["methodologies"] = selected_methodology_names
    configuration_path.write_text(
        yaml.safe_dump(configuration_document, sort_keys=False), encoding="utf-8"
    )


@given("the Kanbus configuration selects no methodologies")
def given_configuration_selects_no_methodologies(context: object) -> None:
    given_configuration_selects_methodologies(context, "")


@then('CONTRIBUTING_AGENT.md should not contain "{text}"')
def then_project_management_does_not_contain_text(context: object, text: str) -> None:
    repo_path = Path(context.working_directory)
    content = (repo_path / "CONTRIBUTING_AGENT.md").read_text(encoding="utf-8")
    assert text not in content


@then('CONTRIBUTING_AGENT.md should show "{earlier_text}" before "{later_text}"')
def then_project_management_orders_text(
    context: object, earlier_text: str, later_text: str
) -> None:
    repo_path = Path(context.working_directory)
    content = (repo_path / "CONTRIBUTING_AGENT.md").read_text(encoding="utf-8")
    assert earlier_text in content and later_text in content
    assert content.index(earlier_text) < content.index(later_text)
