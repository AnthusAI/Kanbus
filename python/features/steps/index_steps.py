"""Behave steps for index and cache scenarios."""

from __future__ import annotations

import time

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    initialize_default_project,
    load_project_directory,
    read_issue_file,
    run_cli,
    write_issue_file,
)
from kanbus.cache import load_cache_if_valid
from kanbus.daemon_paths import get_index_cache_path
from kanbus.index import build_index_from_directory
from kanbus.models import DependencyLink


@given("a Kanbus project with 5 issues of varying types and statuses")
def given_project_with_varied_issues(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    issues = [
        build_issue("kanbus-parent", "Parent", "epic", "open", None, []),
        build_issue("kanbus-child", "Child", "task", "open", "kanbus-parent", []),
        build_issue("kanbus-closed", "Closed", "bug", "closed", None, []),
        build_issue("kanbus-deferred", "Deferred", "task", "deferred", None, []),
        build_issue("kanbus-other", "Other", "story", "open", None, []),
    ]
    for issue in issues:
        write_issue_file(project_dir, issue)


@when("the index is built")
def when_index_built(context: object) -> None:
    project_dir = load_project_directory(context)
    issues_dir = project_dir / "issues"
    context.index = build_index_from_directory(issues_dir)


@then("the index should contain 5 issues")
def then_index_contains_five(context: object) -> None:
    index = getattr(context, "index", None)
    assert index is not None
    assert len(index.by_id) == 5


@then('querying by status "open" should return the correct issues')
def then_index_status_open(context: object) -> None:
    index = getattr(context, "index", None)
    assert index is not None
    identifiers = sorted(issue.identifier for issue in index.by_status.get("open", []))
    assert identifiers == ["kanbus-child", "kanbus-other", "kanbus-parent"]


@then('querying by type "task" should return the correct issues')
def then_index_type_task(context: object) -> None:
    index = getattr(context, "index", None)
    assert index is not None
    identifiers = sorted(issue.identifier for issue in index.by_type.get("task", []))
    assert identifiers == ["kanbus-child", "kanbus-deferred"]


@then("querying by parent should return the correct children")
def then_index_parent_children(context: object) -> None:
    index = getattr(context, "index", None)
    assert index is not None
    children = index.by_parent.get("kanbus-parent", [])
    identifiers = sorted(issue.identifier for issue in children)
    assert identifiers == ["kanbus-child"]


@given('issue "kanbus-aaa" exists with a blocked-by dependency on "kanbus-bbb"')
def given_issue_with_blocked_dependency(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("kanbus-aaa", "Title", "task", "open", None, [])
    issue = issue.model_copy(
        update={
            "dependencies": [DependencyLink(target="kanbus-bbb", type="blocked-by")]
        }
    )
    write_issue_file(project_dir, issue)
    write_issue_file(
        project_dir, build_issue("kanbus-bbb", "Target", "task", "open", None, [])
    )


@then('the reverse dependency index should show "kanbus-bbb" blocks "kanbus-aaa"')
def then_reverse_dependency_index(context: object) -> None:
    index = getattr(context, "index", None)
    assert index is not None
    dependents = index.reverse_dependencies.get("kanbus-bbb", [])
    identifiers = [issue.identifier for issue in dependents]
    assert identifiers == ["kanbus-aaa"]


@given("a Kanbus project with issues but no cache file")
def given_project_with_issues_no_cache(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    issue = build_issue("kanbus-cache", "Cache", "task", "open", None, [])
    write_issue_file(project_dir, issue)
    cache_path = get_index_cache_path(project_dir.parent)
    if cache_path.exists():
        cache_path.unlink()
    context.cache_path = cache_path


@given("the cache file is unreadable")
def given_cache_file_unreadable(context: object) -> None:
    project_dir = load_project_directory(context)
    cache_path = get_index_cache_path(project_dir.parent)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        cache_path.unlink()
    cache_path.mkdir()
    context.cache_path = cache_path


@given("a non-issue file exists in the issues directory")
def given_non_issue_file(context: object) -> None:
    project_dir = load_project_directory(context)
    notes_path = project_dir / "issues" / "notes.txt"
    notes_path.write_text("ignore", encoding="utf-8")


@given("a non-issue file exists in the local issues directory")
def given_non_issue_file_local(context: object) -> None:
    project_dir = load_project_directory(context)
    local_dir = project_dir.parent / "project-local" / "issues"
    local_dir.mkdir(parents=True, exist_ok=True)
    notes_path = local_dir / "notes.txt"
    notes_path.write_text("ignore", encoding="utf-8")


@when("any kanbus command is run")
def when_any_tsk_command(context: object) -> None:
    run_cli(context, "kanbus list")


@then("a cache file should be created in project/.cache/index.json")
def then_cache_file_created(context: object) -> None:
    cache_path = getattr(context, "cache_path", None)
    if cache_path is None:
        project_dir = load_project_directory(context)
        cache_path = get_index_cache_path(project_dir.parent)
    assert cache_path.exists()


@given("a Kanbus project with a valid cache")
def given_project_with_valid_cache(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    issue = build_issue("kanbus-cache", "Cache", "task", "open", None, [])
    write_issue_file(project_dir, issue)
    cache_path = get_index_cache_path(project_dir.parent)
    if cache_path.exists():
        cache_path.unlink()
    run_cli(context, "kanbus list")
    context.cache_path = cache_path
    context.cache_mtime = cache_path.stat().st_mtime


@then("the cache should be loaded without re-scanning issue files")
def then_cache_loaded_without_rebuild(context: object) -> None:
    cache_path = context.cache_path
    current_mtime = cache_path.stat().st_mtime
    assert current_mtime == context.cache_mtime
    project_dir = load_project_directory(context)
    issues_dir = project_dir / "issues"
    cached = load_cache_if_valid(cache_path, issues_dir)
    assert cached is not None


@when("an issue file is modified (mtime changes)")
def when_issue_file_modified(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = read_issue_file(project_dir, "kanbus-cache")
    issue = issue.model_copy(update={"title": "Cache updated"})
    write_issue_file(project_dir, issue)
    time.sleep(0.01)


@then("the cache should be rebuilt from the issue files")
def then_cache_rebuilt(context: object) -> None:
    cache_path = context.cache_path
    assert cache_path.stat().st_mtime > context.cache_mtime


@when("a new issue file appears in the issues directory")
def when_new_issue_file_appears(context: object) -> None:
    project_dir = load_project_directory(context)
    issue = build_issue("kanbus-cache-new", "New", "task", "open", None, [])
    write_issue_file(project_dir, issue)
    time.sleep(0.01)


@then("the cache should be rebuilt")
def then_cache_rebuilt_after_change(context: object) -> None:
    cache_path = context.cache_path
    assert cache_path.stat().st_mtime > context.cache_mtime


@when("an issue file is removed from the issues directory")
def when_issue_file_removed(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "kanbus-cache.json"
    if issue_path.exists():
        issue_path.unlink()
    time.sleep(0.01)


@given("a Kanbus project with cacheable issue metadata")
def given_project_cacheable_metadata(context: object) -> None:
    initialize_default_project(context)
    project_dir = load_project_directory(context)
    parent = build_issue("kanbus-parent", "Parent", "epic", "open", None, ["core"])
    child = build_issue("kanbus-child", "Child", "task", "open", "kanbus-parent", [])
    blocked = build_issue("kanbus-blocked", "Blocked", "task", "open", None, [])
    blocked = blocked.model_copy(
        update={
            "dependencies": [DependencyLink(target="kanbus-parent", type="blocked-by")]
        }
    )
    for issue in (parent, child, blocked):
        write_issue_file(project_dir, issue)
    run_cli(context, "kanbus list")
    context.cache_path = get_index_cache_path(project_dir.parent)


@when("the cache is loaded")
def when_cache_loaded(context: object) -> None:
    project_dir = load_project_directory(context)
    issues_dir = project_dir / "issues"
    cache_path = getattr(context, "cache_path", None)
    if cache_path is None:
        cache_path = get_index_cache_path(project_dir.parent)
    context.cached_index = load_cache_if_valid(cache_path, issues_dir)


@then("the cached index should include parent relationships")
def then_cached_index_parents(context: object) -> None:
    index = getattr(context, "cached_index", None)
    assert index is not None
    identifiers = [
        issue.identifier for issue in index.by_parent.get("kanbus-parent", [])
    ]
    assert identifiers == ["kanbus-child"]


@then("the cached index should include label indexes")
def then_cached_index_labels(context: object) -> None:
    index = getattr(context, "cached_index", None)
    assert index is not None
    identifiers = [issue.identifier for issue in index.by_label.get("core", [])]
    assert identifiers == ["kanbus-parent"]


@then("the cached index should include reverse dependencies")
def then_cached_index_reverse_dependencies(context: object) -> None:
    index = getattr(context, "cached_index", None)
    assert index is not None
    identifiers = [
        issue.identifier
        for issue in index.reverse_dependencies.get("kanbus-parent", [])
    ]
    assert identifiers == ["kanbus-blocked"]
