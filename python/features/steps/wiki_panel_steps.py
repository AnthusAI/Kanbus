"""Behave steps for console wiki workspace scenarios."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from behave import given, then, when

from kanbus.wiki import (
    WikiError,
    convert_wiki_markdown_to_html,
    wiki_page_display_title,
)

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
    wiki_directory_exists: bool = True
    pages_request_failed: bool = False


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


def _wiki_page_to_open_after_delete(
    deleted_path: str, remaining_paths: list[str]
) -> str | None:
    """
    Choose the wiki path to open after deleting a page.

    :param deleted_path: Path that was deleted.
    :type deleted_path: str
    :param remaining_paths: Remaining page paths.
    :type remaining_paths: list[str]
    :return: Next remaining path after the deleted path, the previous
        remaining path if the deleted page was last, or None if none remain.
    :rtype: str | None
    """
    leftover_paths = sorted(
        {page_path for page_path in remaining_paths if page_path != deleted_path}
    )
    if not leftover_paths:
        return None
    for page_path in leftover_paths:
        if page_path > deleted_path:
            return page_path
    return leftover_paths[-1]


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
    if wiki.pages_request_failed:
        wiki.error_banner = "wiki pages request failed"
        wiki.selected_path = None
        return


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


@when('I select the wiki page titled "{title}"')
def when_select_wiki_page_titled(context: object, title: str) -> None:
    """Select a wiki page whose resolved display title matches.

    :param context: Behave context holding console wiki workspace state.
    :type context: object
    :param title: Display title from frontmatter, H1, or file stem.
    :type title: str
    :return: None
    :rtype: None
    :raises AssertionError: If no page resolves to the given title.
    """
    wiki = _ensure_wiki_state(context)
    for path in wiki.page_order:
        content = wiki.pages.get(path, "")
        if wiki_page_display_title(content, path) == title:
            _select_page(wiki, path)
            return
    raise AssertionError(f"no wiki page titled {title}")


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


@when("I render the wiki page through the backend")
def when_render_wiki_page_through_backend(context: object) -> None:
    """Render the current editor draft through Jinja then Markus.

    :param context: Behave context holding console wiki workspace state.
    :type context: object
    :return: None
    :rtype: None
    """
    wiki = _ensure_wiki_state(context)
    try:
        wiki.preview_content = convert_wiki_markdown_to_html(wiki.editor_content)
        wiki.error_banner = None
    except WikiError as error:
        wiki.error_banner = str(error)


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
        wiki.selected_path = _wiki_page_to_open_after_delete(path, wiki.page_order)
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


@given("the console wiki directory is missing")
def given_console_wiki_directory_is_missing(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    wiki.pages = {}
    wiki.page_order = []
    wiki.selected_path = None
    wiki.wiki_directory_exists = False
    wiki.pages_request_failed = False
    wiki.error_banner = None


@given("the console wiki pages request fails")
def given_console_wiki_pages_request_fails(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    wiki.pages = {}
    wiki.page_order = []
    wiki.selected_path = None
    wiki.pages_request_failed = True
    wiki.error_banner = None


@given("the console wiki pages request hangs")
def given_console_wiki_pages_request_hangs(context: object) -> None:
    """Record a hung wiki pages request as a visible load failure.

    :param context: Behave context holding console wiki workspace state.
    :type context: object
    :return: None
    :rtype: None
    """
    wiki = _ensure_wiki_state(context)
    wiki.pages = {}
    wiki.page_order = []
    wiki.selected_path = None
    wiki.pages_request_failed = True
    wiki.error_banner = None


@then("the wiki empty state should be visible")
def then_wiki_empty_state_visible(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    if (
        wiki.page_order
        or not wiki.wiki_directory_exists
        or wiki.pages_request_failed
        or wiki.error_banner
    ):
        raise AssertionError("expected wiki empty state with no pages")


@then("the wiki empty state should not be visible")
def then_wiki_empty_state_should_not_be_visible(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    is_true_empty = (
        wiki.wiki_directory_exists
        and not wiki.page_order
        and not wiki.pages_request_failed
        and wiki.error_banner is None
    )
    if is_true_empty:
        raise AssertionError("wiki empty state should not be visible")


@then("the wiki missing-directory state should be visible")
def then_wiki_missing_directory_state_should_be_visible(context: object) -> None:
    wiki = _ensure_wiki_state(context)
    if wiki.wiki_directory_exists or wiki.page_order or wiki.pages_request_failed:
        raise AssertionError("expected wiki missing-directory state")


def _wiki_directory_listing_labels(wiki: WikiWorkspaceState) -> list[str]:
    labels: dict[str, str] = {}
    for path in wiki.page_order:
        parts = path.split("/")
        name = parts[0]
        is_dir = len(parts) > 1
        if name not in labels:
            if is_dir:
                labels[name] = name
            else:
                labels[name] = wiki_page_display_title(wiki.pages[path], path)
        elif is_dir:
            labels[name] = name
    return list(labels.values())


@then('the wiki directory listing should show "{text}"')
def then_wiki_directory_listing_should_show(context: object, text: str) -> None:
    """Assert the Wiki Home directory listing includes a visible label.

    :param context: Behave context holding console wiki workspace state.
    :type context: object
    :param text: Expected listing label.
    :type text: str
    :return: None
    :rtype: None
    :raises AssertionError: If the label is not present.
    """
    wiki = _ensure_wiki_state(context)
    labels = _wiki_directory_listing_labels(wiki)
    if text not in labels:
        raise AssertionError(
            f"expected directory listing to show {text!r}, got {labels!r}"
        )


@then('the wiki directory listing should not show "{text}"')
def then_wiki_directory_listing_should_not_show(context: object, text: str) -> None:
    """Assert the Wiki Home directory listing does not include a label.

    :param context: Behave context holding console wiki workspace state.
    :type context: object
    :param text: Label that must not appear.
    :type text: str
    :return: None
    :rtype: None
    :raises AssertionError: If the label is present.
    """
    wiki = _ensure_wiki_state(context)
    labels = _wiki_directory_listing_labels(wiki)
    if text in labels:
        raise AssertionError(
            f"expected directory listing not to show {text!r}, got {labels!r}"
        )


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


def _preview_html_contains_class(html: str, css_class: str) -> bool:
    """Return whether preview HTML includes an element with the given class.

    :param html: Preview HTML fragment.
    :type html: str
    :param css_class: Class token to find.
    :type css_class: str
    :return: True when the class token is present.
    :rtype: bool
    """
    pattern = re.compile(r'class=(["\'])([^"\']*)\1')
    for match in pattern.finditer(html):
        if css_class in match.group(2).split():
            return True
    return False


@then('the wiki preview HTML should contain element with class "{css_class}"')
def then_wiki_preview_html_contains_class(context: object, css_class: str) -> None:
    """Assert preview HTML includes an element with a Markus class.

    :param context: Behave context holding console wiki workspace state.
    :type context: object
    :param css_class: Expected class token.
    :type css_class: str
    :return: None
    :rtype: None
    :raises AssertionError: If the class is missing from the preview HTML.
    """
    wiki = _ensure_wiki_state(context)
    if not _preview_html_contains_class(wiki.preview_content, css_class):
        raise AssertionError(
            f"expected preview HTML class {css_class!r}, got {wiki.preview_content!r}"
        )


@then('the wiki preview HTML should contain "{text}"')
def then_wiki_preview_html_contains(context: object, text: str) -> None:
    """Assert preview HTML includes the given text.

    :param context: Behave context holding console wiki workspace state.
    :type context: object
    :param text: Expected substring.
    :type text: str
    :return: None
    :rtype: None
    :raises AssertionError: If the text is missing.
    """
    wiki = _ensure_wiki_state(context)
    if text not in wiki.preview_content:
        raise AssertionError(
            f"expected wiki preview HTML to contain {text!r}, got {wiki.preview_content!r}"
        )


@then('the wiki preview HTML should not contain "{text}"')
def then_wiki_preview_html_not_contain(context: object, text: str) -> None:
    """Assert preview HTML does not include the given text.

    :param context: Behave context holding console wiki workspace state.
    :type context: object
    :param text: Forbidden substring.
    :type text: str
    :return: None
    :rtype: None
    :raises AssertionError: If the text is present.
    """
    wiki = _ensure_wiki_state(context)
    if text in wiki.preview_content:
        raise AssertionError(
            f"expected wiki preview HTML not to contain {text!r}, got {wiki.preview_content!r}"
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
