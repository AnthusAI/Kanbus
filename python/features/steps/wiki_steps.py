"""Behave steps for wiki rendering and wiki-issue cross-linking."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from behave import given, use_step_matcher, when, then

from kanbus.models import IssueComment

from features.steps.shared import (
    build_issue,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)


@given("3 open tasks exist")
def given_three_open_tasks(context: object) -> None:
    project_dir = load_project_directory(context)
    issues = [
        build_issue("kanbus-open01", "Open 1", "task", "open", None, []),
        build_issue("kanbus-open02", "Open 2", "task", "open", None, []),
        build_issue("kanbus-open03", "Open 3", "task", "open", None, []),
    ]
    for issue in issues:
        write_issue_file(project_dir, issue)


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


@given('a wiki page "{filename}" with content "{content}"')
def given_wiki_page_with_content_string(
    context: object, filename: str, content: str
) -> None:
    project_dir = load_project_directory(context)
    wiki_subdir = getattr(context, "wiki_directory", "wiki")
    if wiki_subdir.startswith("../"):
        repo_root = Path(context.working_directory)
        wiki_dir = repo_root / wiki_subdir.lstrip("../").lstrip("..\\")
    else:
        wiki_dir = project_dir / wiki_subdir
    wiki_dir.mkdir(parents=True, exist_ok=True)
    target = wiki_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@given('a wiki page "{filename}" with content')
@given('a wiki page "{filename}" with content:')
def given_wiki_page_with_content(context: object, filename: str) -> None:
    project_dir = load_project_directory(context)
    wiki_subdir = getattr(context, "wiki_directory", "wiki")
    if wiki_subdir.startswith("../"):
        repo_root = Path(context.working_directory)
        wiki_dir = repo_root / wiki_subdir.lstrip("../").lstrip("..\\")
    else:
        wiki_dir = project_dir / wiki_subdir
    wiki_dir.mkdir(parents=True, exist_ok=True)
    content = context.text or ""
    target = wiki_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@given('a raw wiki page "{filename}" with content')
@given('a raw wiki page "{filename}" with content:')
def given_raw_wiki_page_with_content(context: object, filename: str) -> None:
    working_directory = Path(context.working_directory)
    content = context.text or ""
    (working_directory / filename).write_text(content, encoding="utf-8")


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


use_step_matcher("re")


@given(r'issue "(?P<identifier>[^"]+)" has description containing(?:\s*:)?')
def given_issue_has_description_containing(context: object, identifier: str) -> None:
    project_dir = load_project_directory(context)
    content = context.text or ""
    try:
        issue = read_issue_file(project_dir, identifier)
    except Exception:
        issue = build_issue(identifier, "Title", "task", "open", None, [])
    issue = issue.model_copy(update={"description": content})
    write_issue_file(project_dir, issue)


use_step_matcher("parse")


@given('a comment on issue "{identifier}" contains "{text}"')
def given_comment_contains(context: object, identifier: str, text: str) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, identifier)
    author = getattr(context, "current_user", "dev@example.com")
    comment = IssueComment(
        author=author,
        text=text,
        created_at=datetime.now(timezone.utc),
    )
    comments = list(issue.comments) + [comment]
    issue = issue.model_copy(update={"comments": comments})
    write_issue_file(project_dir, issue)


use_step_matcher("re")


@given(r'a comment on issue "(?P<identifier>[^"]+)" contains(?:\s*:)?')
def given_comment_contains_multiline(context: object, identifier: str) -> None:
    text = context.text or ""
    given_comment_contains(context, identifier, text)


use_step_matcher("parse")


@then('the rendered description should contain a link to wiki path "{path}"')
def then_rendered_description_has_wiki_link(context: object, path: str) -> None:
    stdout = context.result.stdout
    assert path in stdout, f"expected wiki path {path!r} in output, got: {stdout[:500]}"


@then('the rendered comments should contain a link to wiki path "{path}"')
def then_rendered_comments_has_wiki_link(context: object, path: str) -> None:
    stdout = context.result.stdout
    assert path in stdout, f"expected wiki path {path!r} in output, got: {stdout[:500]}"


@then('the rendered description should contain "{text}"')
def then_rendered_description_contains(context: object, text: str) -> None:
    stdout = context.result.stdout
    assert text in stdout, f"expected {text!r} in output, got: {stdout[:500]}"


@then('the rendered comments should contain "{text}"')
def then_rendered_comments_contains(context: object, text: str) -> None:
    stdout = context.result.stdout
    assert text in stdout, f"expected {text!r} in output, got: {stdout[:500]}"


@then('the rendered wiki should contain a link to issue "{identifier}"')
def then_rendered_wiki_has_issue_link(context: object, identifier: str) -> None:
    stdout = context.result.stdout
    assert (
        identifier in stdout
    ), f"expected issue {identifier!r} in output, got: {stdout[:500]}"


@given("a Kanbus project with AI configured")
def given_project_with_ai_configured(context: object) -> None:
    """Create a Kanbus project with AI config and test mock enabled."""
    import copy
    import os
    import yaml

    from features.steps.shared import initialize_default_project
    from kanbus.config import DEFAULT_CONFIGURATION

    initialize_default_project(context)
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["ai"] = {"provider": "openai", "model": "gpt-4o"}
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    context._ai_mock_env = os.environ.get("KANBUS_TEST_AI_MOCK")
    os.environ["KANBUS_TEST_AI_MOCK"] = "1"


def _ai_calls_log_path(context: object) -> Path:
    """Return path to ai_calls.log in project cache."""
    project_dir = load_project_directory(context)
    return project_dir / ".cache" / "ai_calls.log"


def _ai_call_count(context: object) -> int:
    path = _ai_calls_log_path(context)
    if not path.exists():
        return 0
    return len(path.read_text(encoding="utf-8").strip().splitlines())


@then("the AI provider API should be called")
def then_ai_provider_api_called(context: object) -> None:
    count = _ai_call_count(context)
    assert count >= 1, f"expected at least 1 API call, got {count}"
    context._ai_call_count_after_first_render = count


@then("the AI provider API should not be called")
def then_ai_provider_api_not_called(context: object) -> None:
    count_before = getattr(context, "_ai_call_count_after_first_render", 0)
    count_after = _ai_call_count(context)
    assert (
        count_after == count_before
    ), f"expected no new API calls (count was {count_before}), got {count_after}"


@then('the rendered wiki should contain a generated summary for "{identifier}"')
def then_rendered_wiki_has_generated_summary(context: object, identifier: str) -> None:
    """Verify rendered wiki output contains the mock generated summary."""
    stdout = context.result.stdout
    expected = f"Generated summary for {identifier}"
    assert expected in stdout, f"expected {expected!r} in output, got: {stdout[:500]}"


@given('a Kanbus project with wiki_directory set to "{value}"')
def given_project_with_wiki_directory(context: object, value: str) -> None:
    import copy
    import yaml

    from features.steps.shared import initialize_default_project
    from kanbus.config import DEFAULT_CONFIGURATION

    initialize_default_project(context)
    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["wiki_directory"] = value
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    context.wiki_directory = value


def _wiki_render_cache_dir(context: object) -> Path:
    project_dir = load_project_directory(context)
    return project_dir / ".cache" / "wiki_render"


@then("a cached rendered file should exist")
def then_cached_rendered_file_exists(context: object) -> None:
    cache_dir = _wiki_render_cache_dir(context)
    assert cache_dir.exists(), f"expected cache dir {cache_dir} to exist"
    md_files = list(cache_dir.glob("*.md"))
    assert md_files, f"expected at least one cached .md file in {cache_dir}"


@then("the command should use the cache")
def then_command_uses_cache(context: object) -> None:
    project_dir = load_project_directory(context)
    log_path = project_dir / ".cache" / "wiki_cache_hits.log"
    assert log_path.exists(), f"expected cache hit log {log_path} to exist"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1, f"expected at least 1 cache hit, got {len(lines)}"


@then('the wiki root should be "{expected}"')
def then_wiki_root_is(context: object, expected: str) -> None:
    repo = Path(context.working_directory)
    wiki_path = (repo / expected).resolve()
    assert wiki_path.exists(), f"expected wiki root {expected} to exist at {wiki_path}"


@given('the Kanbus configuration has wiki_directory set to "{value}"')
def given_config_wiki_directory(context: object, value: str) -> None:
    import yaml

    repository = Path(context.working_directory)
    config_path = repository / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    payload["wiki_directory"] = value
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
