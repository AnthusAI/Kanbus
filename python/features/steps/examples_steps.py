"""Steps for example project integration setup."""

from __future__ import annotations

import shutil
from pathlib import Path

from behave import given, then, when

from features.steps.shared import ensure_git_repository, run_cli
from taskulus.agents_management import (
    build_project_management_text,
    TASKULUS_SECTION_TEXT,
)

README_STUB = "This is a sample project that uses Taskulus."


def _examples_root() -> Path:
    return Path(__file__).resolve().parents[3] / "examples"


def _example_dir(name: str) -> Path:
    slug = name.strip().lower().replace(" ", "-")
    return _examples_root() / slug


@given('the "{name}" example project does not exist')
def given_example_missing(context: object, name: str) -> None:
    path = _example_dir(name)
    if path.exists():
        shutil.rmtree(path)


@when('I create the "{name}" example project')
def when_create_example_project(context: object, name: str) -> None:
    path = _example_dir(name)
    path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(path)


@when('I run "tsk setup agents" in the "{name}" example project')
def when_run_setup_agents_in_example(context: object, name: str) -> None:
    path = _example_dir(name)
    context.working_directory = path
    run_cli(context, "tsk setup agents")


@when('I run "tsk init" in the "{name}" example project')
def when_run_init_in_example(context: object, name: str) -> None:
    path = _example_dir(name)
    context.working_directory = path
    run_cli(context, "tsk init")


@when('I add a README stub to the "{name}" example project')
def when_add_readme_stub(context: object, name: str) -> None:
    path = _example_dir(name)
    readme = path / "README.md"
    readme.write_text(README_STUB + "\n", encoding="utf-8")


@then('the "{name}" example project should contain a README stub')
def then_example_contains_readme(context: object, name: str) -> None:
    path = _example_dir(name)
    readme = path / "README.md"
    assert readme.exists()
    content = readme.read_text(encoding="utf-8").strip()
    assert content == README_STUB


@then('the "{name}" example project should contain .taskulus.yml')
def then_example_contains_config(context: object, name: str) -> None:
    path = _example_dir(name)
    assert (path / ".taskulus.yml").exists()


@then('the "{name}" example project should contain the project directory')
def then_example_contains_project_dir(context: object, name: str) -> None:
    path = _example_dir(name)
    assert (path / "project").exists()


@then(
    'the "{name}" example project should contain AGENTS.md with Taskulus instructions'
)
def then_example_contains_agents(context: object, name: str) -> None:
    path = _example_dir(name)
    agents = path / "AGENTS.md"
    assert agents.exists()
    content = agents.read_text(encoding="utf-8")
    assert TASKULUS_SECTION_TEXT.strip() in content


@then('the "{name}" example project should contain CONTRIBUTING_AGENT.md')
def then_example_contains_instructions(context: object, name: str) -> None:
    path = _example_dir(name)
    instructions = path / "CONTRIBUTING_AGENT.md"
    assert instructions.exists()
    content = instructions.read_text(encoding="utf-8")
    expected = build_project_management_text(path)
    assert content.strip() == expected.strip()
