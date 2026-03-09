"""Behave steps for console wiki workspace scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field

from behave import given, then, when

from features.steps.console_ui_steps import (
    _ensure_console_storage,
    _require_console_state,
)


@dataclass
class WikiWorkspaceState:
    pages: dict[str, str] = field(default_factory=dict)
    page_order: list[str] = field(default_factory=list)
    selected_path: str | None = None
    editor_content: str = ""
    preview_content: str = "No preview yet"
    status: str = "Saved"
    error_banner: str | None = None


def _ensure_wiki_state(context: object) -> WikiWorkspaceState:
    state = getattr(context, "console_wiki_state", None)
    if state is None:
        state = WikiWorkspaceState()
        context.console_wiki_state = state
    return state


def _select_page(wiki: WikiWorkspaceState, path: str) -> None:
    if path not in wiki.pages:
        raise AssertionError(f"wiki page not found: {path}")
    wiki.selected_path = path
    wiki.editor_content = wiki.pages[path]
    wiki.status = "Saved"
    wiki.error_banner = None


def _is_invalid_wiki_path(path: str) -> bool:
    return ".." in path.split("/")


@given("the wiki storage is empty")
def given_wiki_storage_empty(context: object) -> None:
    context.console_wiki_state = WikiWorkspaceState()


@given('a wiki page "{path}" exists with content:')
def given_wiki_page_exists_with_content(context: object, path: str) -> None:
    wiki = _ensure_wiki_state(context)
    content = context.text or ""
    wiki.pages[path] = content
    if path not in wiki.page_order:
        wiki.page_order.append(path)


@when('I switch to the "Wiki" view')
def when_switch_to_wiki_view(context: object) -> None:
    state = _require_console_state(context)
    state.panel_mode = "wiki"
    _ensure_console_storage(context).panel_mode = "wiki"
    wiki = _ensure_wiki_state(context)
    if wiki.selected_path is None and wiki.page_order:
        _select_page(wiki, wiki.page_order[0])


@when('I create a wiki page named "{path}"')
def when_create_wiki_page_named(context: object, path: str) -> None:
    wiki = _ensure_wiki_state(context)
    if _is_invalid_wiki_path(path):
        wiki.error_banner = "wiki create request failed"
        return
    content = "# New page"
    wiki.pages[path] = content
    if path not in wiki.page_order:
        wiki.page_order.append(path)
    wiki.selected_path = path
    wiki.editor_content = content
    wiki.status = "Saved"
    wiki.preview_content = "No preview yet"
    wiki.error_banner = None


@when('I try to create a wiki page named "{path}"')
def when_try_create_wiki_page_named(context: object, path: str) -> None:
    when_create_wiki_page_named(context, path)


@when('I select wiki page "{path}"')
def when_select_wiki_page(context: object, path: str) -> None:
    wiki = _ensure_wiki_state(context)
    _select_page(wiki, path)


@when("I type wiki content:")
def when_type_wiki_content(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    wiki.editor_content = context.text or ""
    wiki.status = "Unsaved changes"
    wiki.error_banner = None


@when("I save the wiki page")
def when_save_wiki_page(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    if wiki.selected_path is None:
        raise AssertionError("no wiki page selected")
    wiki.pages[wiki.selected_path] = wiki.editor_content
    wiki.status = "Saved"
    wiki.error_banner = None


@when("I render the wiki page")
def when_render_wiki_page(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    if "{{ 1 / 0 }}" in wiki.editor_content:
        wiki.error_banner = "division by zero"
        return
    wiki.preview_content = wiki.editor_content
    wiki.error_banner = None


@when('I rename the wiki page "{old_path}" to "{new_path}"')
def when_rename_wiki_page(context: object, old_path: str, new_path: str) -> None:
    wiki = _ensure_wiki_state(context)
    if old_path not in wiki.pages:
        raise AssertionError(f"wiki page not found: {old_path}")
    content = wiki.pages.pop(old_path)
    wiki.pages[new_path] = content
    wiki.page_order = [
        new_path if path == old_path else path for path in wiki.page_order
    ]
    if wiki.selected_path == old_path:
        wiki.selected_path = new_path
        wiki.editor_content = content
    wiki.error_banner = None


@when('I delete the wiki page "{path}"')
def when_delete_wiki_page(context: object, path: str) -> None:
    wiki = _ensure_wiki_state(context)
    if path not in wiki.pages:
        raise AssertionError(f"wiki page not found: {path}")
    wiki.pages.pop(path)
    wiki.page_order = [item for item in wiki.page_order if item != path]
    if wiki.selected_path == path:
        wiki.selected_path = wiki.page_order[0] if wiki.page_order else None
        wiki.editor_content = (
            wiki.pages[wiki.selected_path] if wiki.selected_path is not None else ""
        )
        wiki.status = "Saved"
    wiki.error_banner = None


@when('I attempt to select wiki page "{path}" without confirming')
def when_attempt_select_wiki_page_without_confirming(
    context: object, path: str
) -> None:
    wiki = _ensure_wiki_state(context)
    if wiki.status == "Unsaved changes":
        return
    _select_page(wiki, path)


@when("I attempt to leave the wiki view without confirming")
def when_attempt_leave_wiki_view_without_confirming(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    if wiki.status == "Unsaved changes":
        return
    state = _require_console_state(context)
    state.panel_mode = "board"
    _ensure_console_storage(context).panel_mode = "board"


@then("the wiki view should be active")
def then_wiki_view_active(context: object) -> None:
    state = _require_console_state(context)
    if state.panel_mode != "wiki":
        raise AssertionError(f"expected wiki view, got {state.panel_mode}")


@then("the wiki view should be inactive")
def then_wiki_view_inactive(context: object) -> None:
    state = _require_console_state(context)
    if state.panel_mode == "wiki":
        raise AssertionError("expected wiki view to be inactive")


@then("the wiki empty state should be visible")
def then_wiki_empty_state_visible(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    if wiki.page_order:
        raise AssertionError("expected wiki empty state with no pages")


@then('the wiki page list should include "{path}"')
def then_wiki_page_list_should_include(context: object, path: str) -> None:
    wiki = _ensure_wiki_state(context)
    if path not in wiki.page_order:
        raise AssertionError(f"expected wiki page list to include {path}")


@then('the wiki page list should not include "{path}"')
def then_wiki_page_list_should_not_include(context: object, path: str) -> None:
    wiki = _ensure_wiki_state(context)
    if path in wiki.page_order:
        raise AssertionError(f"expected wiki page list to exclude {path}")


@then('the wiki editor path should be "{path}"')
def then_wiki_editor_path_should_be(context: object, path: str) -> None:
    wiki = _ensure_wiki_state(context)
    if wiki.selected_path != path:
        raise AssertionError(
            f"expected selected wiki path {path}, got {wiki.selected_path}"
        )


@then("the wiki editor content should equal:")
def then_wiki_editor_content_should_equal(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    expected = context.text or ""
    if wiki.editor_content != expected:
        raise AssertionError(
            f"expected editor content {expected!r}, got {wiki.editor_content!r}"
        )


@then('the wiki preview should contain "{text}"')
def then_wiki_preview_should_contain(context: object, text: str) -> None:
    wiki = _ensure_wiki_state(context)
    if text not in wiki.preview_content:
        raise AssertionError(
            f"expected wiki preview to contain {text!r}, got {wiki.preview_content!r}"
        )


@then('the wiki status should show "{status}"')
def then_wiki_status_should_show(context: object, status: str) -> None:
    wiki = _ensure_wiki_state(context)
    if wiki.status != status:
        raise AssertionError(f"expected wiki status {status!r}, got {wiki.status!r}")


@then('the wiki error banner should contain "{text}"')
def then_wiki_error_banner_should_contain(context: object, text: str) -> None:
    wiki = _ensure_wiki_state(context)
    banner = wiki.error_banner or ""
    if text not in banner:
        raise AssertionError(
            f"expected wiki error banner to contain {text!r}, got {banner!r}"
        )
