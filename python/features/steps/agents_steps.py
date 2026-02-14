"""Steps for managing AGENTS.md Taskulus instructions."""

from __future__ import annotations

import shutil
from pathlib import Path

from behave import given, then, when

from features.steps.shared import ensure_git_repository, run_cli, run_cli_with_input
from taskulus.agents_management import (
    build_project_management_text,
    TASKULUS_SECTION_TEXT,
)


def _fixture_path(name: str) -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "specs" / "fixtures" / "agents_project" / name


def _config_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / ".taskulus.yml"


def _copy_configuration(repo_path: Path) -> None:
    config = _config_path()
    if config.exists():
        (repo_path / ".taskulus.yml").write_text(
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


def _extract_taskulus_section(content: str) -> str:
    lines = content.splitlines()
    start = None
    end = len(lines)
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#") and "taskulus" in stripped.lower():
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


@given("a Taskulus repository without AGENTS.md")
def given_repo_without_agents(context: object) -> None:
    temp_dir = Path(context.temp_dir)
    repo_path = temp_dir / "repo"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repo_path)
    _copy_configuration(repo_path)
    context.working_directory = repo_path


@given("a Taskulus repository with AGENTS.md without a Taskulus section")
def given_repo_agents_without_taskulus(context: object) -> None:
    _write_agents_fixture(context, "agents_no_taskulus.md")


@given("a Taskulus repository with AGENTS.md containing a Taskulus section")
def given_repo_agents_with_taskulus(context: object) -> None:
    _write_agents_fixture(context, "agents_with_taskulus.md")


@when('I run "tsk setup agents"')
def when_run_setup_agents(context: object) -> None:
    run_cli(context, "tsk setup agents")


@when('I run "tsk setup agents --force"')
def when_run_setup_agents_force(context: object) -> None:
    run_cli(context, "tsk setup agents --force")


@when('I run "tsk setup agents" and respond "{response}"')
def when_run_setup_agents_with_response(context: object, response: str) -> None:
    run_cli_with_input(context, "tsk setup agents", f"{response}\n")


@when('I run "tsk setup agents" non-interactively')
def when_run_setup_agents_non_interactive(context: object) -> None:
    overrides = dict(getattr(context, "environment_overrides", {}) or {})
    overrides["TASKULUS_NON_INTERACTIVE"] = "1"
    context.environment_overrides = overrides
    run_cli(context, "tsk setup agents")


@then("AGENTS.md should exist")
def then_agents_exists(context: object) -> None:
    repo_path = Path(context.working_directory)
    assert (repo_path / "AGENTS.md").exists()


@then("AGENTS.md should contain the Taskulus section")
def then_agents_contains_taskulus(context: object) -> None:
    content = _read_agents(context)
    section = _extract_taskulus_section(content)
    assert section == TASKULUS_SECTION_TEXT.strip()


@then("the Taskulus section should appear after the H1 heading")
def then_taskulus_after_h1(context: object) -> None:
    content = _read_agents(context)
    lines = content.splitlines()
    h1_index = next(
        index for index, line in enumerate(lines) if line.strip().startswith("# ")
    )
    taskulus_index = next(
        index for index, line in enumerate(lines) if "taskulus" in line.lower()
    )
    assert taskulus_index > h1_index
    for index in range(h1_index + 1, taskulus_index):
        if lines[index].strip().startswith("## "):
            raise AssertionError("Taskulus section is not the first H2")


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
