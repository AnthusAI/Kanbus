"""Behave steps for wiki rendering."""

from __future__ import annotations

from pathlib import Path

from behave import given, when, then

from features.steps.shared import (
    build_issue,
    load_project_directory,
    run_cli,
    write_issue_file,
)


@given("3 open tasks and 2 closed tasks exist")
def given_open_and_closed_tasks(context: object) -> None:
    project_dir = load_project_directory(context)
    issues = [
        build_issue("kanbus-open01", "Open 1", "task", "open", None, []),
        build_issue("kanbus-open02", "Open 2", "task", "open", None, []),
        build_issue("kanbus-open03", "Open 3", "task", "open", None, []),
        build_issue("kanbus-closed01", "Closed 1", "task", "closed", None, []),
        build_issue("kanbus-closed02", "Closed 2", "task", "closed", None, []),
    ]
    for issue in issues:
        write_issue_file(project_dir, issue)


@given('open tasks "{first}" and "{second}" exist')
def given_open_tasks_alpha_beta(context: object, first: str, second: str) -> None:
    project_dir = load_project_directory(context)
    issues = [
        build_issue("kanbus-alpha", first, "task", "open", None, []),
        build_issue("kanbus-beta", second, "task", "open", None, []),
    ]
    for issue in issues:
        write_issue_file(project_dir, issue)


@given('open tasks "Urgent" and "Later" exist with priorities 1 and 3')
def given_open_tasks_with_priorities(context: object) -> None:
    project_dir = load_project_directory(context)
    urgent = build_issue("kanbus-urgent", "Urgent", "task", "open", None, [])
    later = build_issue("kanbus-later", "Later", "task", "open", None, [])
    urgent = urgent.model_copy(update={"priority": 1})
    later = later.model_copy(update={"priority": 3})
    for issue in [urgent, later]:
        write_issue_file(project_dir, issue)


@given('a wiki page "{filename}" with content:')
def given_wiki_page_with_content(context: object, filename: str) -> None:
    project_dir = load_project_directory(context)
    wiki_dir = project_dir / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    content = context.text or ""
    (wiki_dir / filename).write_text(content, encoding="utf-8")


@given('a raw wiki page "{filename}" with content:')
def given_raw_wiki_page_with_content(context: object, filename: str) -> None:
    working_directory = Path(context.working_directory)
    content = context.text or ""
    (working_directory / filename).write_text(content, encoding="utf-8")


@when('I run "kanbus wiki render {page}"')
def when_render_page(context: object, page: str) -> None:
    run_cli(context, f"kanbus wiki render {page}")


@when('I render the wiki page "{filename}" by absolute path')
def when_render_page_absolute(context: object, filename: str) -> None:
    project_dir = load_project_directory(context)
    page_path = (project_dir / "wiki" / filename).resolve()
    run_cli(context, f"kanbus wiki render {page_path}")


@then('"{first}" should appear before "{second}" in the output')
def then_first_before_second(context: object, first: str, second: str) -> None:
    stdout = context.result.stdout
    first_index = stdout.find(first)
    second_index = stdout.find(second)
    assert first_index != -1
    assert second_index != -1
    assert first_index < second_index
