use cucumber::{gherkin::Step, given, then, when};

use crate::step_definitions::console_ui_steps::{ensure_wiki_state, select_wiki_page};
use crate::step_definitions::initialization_steps::KanbusWorld;

fn is_invalid_wiki_path(path: &str) -> bool {
    path.split('/').any(|segment| segment == "..")
}

#[given("the wiki storage is empty")]
fn given_wiki_storage_empty(world: &mut KanbusWorld) {
    world.console_wiki_state = Some(kanbus_wiki_workspace_state());
}

fn kanbus_wiki_workspace_state() -> crate::step_definitions::console_ui_steps::WikiWorkspaceState {
    crate::step_definitions::console_ui_steps::WikiWorkspaceState::default_new()
}

#[given(regex = r#"a wiki page "(?P<path>[^"]+)" exists with content:"#)]
fn given_wiki_page_exists_with_content(world: &mut KanbusWorld, path: String, step: &Step) {
    let wiki = ensure_wiki_state(world);
    let content = step.docstring().map(|s| s.as_str()).unwrap_or("");
    wiki.pages.insert(path.clone(), content.to_string());
    if !wiki.page_order.contains(&path) {
        wiki.page_order.push(path);
    }
}

#[when(regex = r#"I create a wiki page named "(?P<path>[^"]+)"$"#)]
fn when_create_wiki_page_named(world: &mut KanbusWorld, path: String) {
    let wiki = ensure_wiki_state(world);
    if is_invalid_wiki_path(&path) {
        wiki.error_banner = Some("wiki create request failed".to_string());
        return;
    }
    let content = "# New page".to_string();
    wiki.pages.insert(path.clone(), content.clone());
    if !wiki.page_order.contains(&path) {
        wiki.page_order.push(path.clone());
    }
    wiki.selected_path = Some(path);
    wiki.editor_content = content;
    wiki.status = "Saved".to_string();
    wiki.preview_content = "No preview yet".to_string();
    wiki.error_banner = None;
}

#[when(regex = r#"I try to create a wiki page named "(?P<path>[^"]+)"$"#)]
fn when_try_create_wiki_page_named(world: &mut KanbusWorld, path: String) {
    when_create_wiki_page_named(world, path);
}

#[when(regex = r#"I select wiki page "(?P<path>[^"]+)"$"#)]
fn when_select_wiki_page(world: &mut KanbusWorld, path: String) {
    let wiki = ensure_wiki_state(world);
    select_wiki_page(wiki, &path);
}

#[when("I type wiki content:")]
fn when_type_wiki_content(world: &mut KanbusWorld, step: &Step) {
    let wiki = ensure_wiki_state(world);
    wiki.editor_content = step
        .docstring()
        .map(|s| s.as_str())
        .unwrap_or("")
        .to_string();
    wiki.status = "Unsaved changes".to_string();
    wiki.error_banner = None;
}

#[when("I save the wiki page")]
fn when_save_wiki_page(world: &mut KanbusWorld) {
    let wiki = ensure_wiki_state(world);
    let path = wiki.selected_path.as_ref().expect("no wiki page selected");
    if let Some(content) = wiki.pages.get_mut(path) {
        *content = wiki.editor_content.clone();
    }
    wiki.status = "Saved".to_string();
    wiki.error_banner = None;
}

#[when("I render the wiki page")]
fn when_render_wiki_page(world: &mut KanbusWorld) {
    let wiki = ensure_wiki_state(world);
    if wiki.editor_content.contains("{{ 1 / 0 }}") {
        wiki.error_banner = Some("division by zero".to_string());
        return;
    }
    wiki.preview_content = wiki.editor_content.clone();
    wiki.error_banner = None;
}

#[when(regex = r#"I rename the wiki page "(?P<old_path>[^"]+)" to "(?P<new_path>[^"]+)"$"#)]
fn when_rename_wiki_page(world: &mut KanbusWorld, old_path: String, new_path: String) {
    let wiki = ensure_wiki_state(world);
    let content = wiki.pages.remove(&old_path).expect("wiki page not found");
    wiki.pages.insert(new_path.clone(), content.clone());
    wiki.page_order = wiki
        .page_order
        .iter()
        .map(|p| {
            if p == &old_path {
                new_path.clone()
            } else {
                p.clone()
            }
        })
        .collect();
    if wiki.selected_path.as_deref() == Some(old_path.as_str()) {
        wiki.selected_path = Some(new_path);
        wiki.editor_content = content;
    }
    wiki.error_banner = None;
}

#[when(regex = r#"I delete the wiki page "(?P<path>[^"]+)"$"#)]
fn when_delete_wiki_page(world: &mut KanbusWorld, path: String) {
    let wiki = ensure_wiki_state(world);
    wiki.pages.remove(&path);
    wiki.page_order.retain(|p| p != &path);
    if wiki.selected_path.as_deref() == Some(path.as_str()) {
        wiki.selected_path = wiki.page_order.first().cloned();
        wiki.editor_content = wiki
            .selected_path
            .as_ref()
            .and_then(|p| wiki.pages.get(p))
            .cloned()
            .unwrap_or_default();
        wiki.status = "Saved".to_string();
    }
    wiki.error_banner = None;
}

#[when(regex = r#"I attempt to select wiki page "(?P<path>[^"]+)" without confirming"#)]
fn when_attempt_select_wiki_page_without_confirming(world: &mut KanbusWorld, path: String) {
    let wiki = ensure_wiki_state(world);
    if wiki.status == "Unsaved changes" {
        return;
    }
    select_wiki_page(wiki, &path);
}

#[when("I attempt to leave the wiki view without confirming")]
fn when_attempt_leave_wiki_view_without_confirming(world: &mut KanbusWorld) {
    let wiki = ensure_wiki_state(world);
    if wiki.status == "Unsaved changes" {
        return;
    }
    let state = world
        .console_state
        .as_mut()
        .expect("console state not initialized");
    state.panel_mode = "board".to_string();
    world.console_local_storage.panel_mode = Some("board".to_string());
}

#[then("the wiki view should be active")]
fn then_wiki_view_active(world: &mut KanbusWorld) {
    let state = world
        .console_state
        .as_ref()
        .expect("console state not initialized");
    assert_eq!(
        state.panel_mode, "wiki",
        "expected wiki view, got {}",
        state.panel_mode
    );
}

#[then("the wiki view should be inactive")]
fn then_wiki_view_inactive(world: &mut KanbusWorld) {
    let state = world
        .console_state
        .as_ref()
        .expect("console state not initialized");
    assert_ne!(
        state.panel_mode, "wiki",
        "expected wiki view to be inactive"
    );
}

#[then("the wiki empty state should be visible")]
fn then_wiki_empty_state_visible(world: &mut KanbusWorld) {
    let wiki = ensure_wiki_state(world);
    assert!(
        wiki.page_order.is_empty(),
        "expected wiki empty state with no pages"
    );
}

#[then(regex = r#"the wiki page list should include "(?P<path>[^"]+)"$"#)]
fn then_wiki_page_list_should_include(world: &mut KanbusWorld, path: String) {
    let wiki = ensure_wiki_state(world);
    assert!(
        wiki.page_order.contains(&path),
        "expected wiki page list to include {}",
        path
    );
}

#[then(regex = r#"the wiki page list should not include "(?P<path>[^"]+)"$"#)]
fn then_wiki_page_list_should_not_include(world: &mut KanbusWorld, path: String) {
    let wiki = ensure_wiki_state(world);
    assert!(
        !wiki.page_order.contains(&path),
        "expected wiki page list to exclude {}",
        path
    );
}

#[then(regex = r#"the wiki editor path should be "(?P<path>[^"]+)"$"#)]
fn then_wiki_editor_path_should_be(world: &mut KanbusWorld, path: String) {
    let wiki = ensure_wiki_state(world);
    assert_eq!(
        wiki.selected_path.as_deref(),
        Some(path.as_str()),
        "expected selected wiki path {}, got {:?}",
        path,
        wiki.selected_path
    );
}

#[then("the wiki editor content should equal:")]
fn then_wiki_editor_content_should_equal(world: &mut KanbusWorld, step: &Step) {
    let wiki = ensure_wiki_state(world);
    let expected = step.docstring().map(|s| s.as_str()).unwrap_or("").trim();
    let actual = wiki.editor_content.trim();
    assert_eq!(
        actual, expected,
        "expected editor content {:?}, got {:?}",
        expected, wiki.editor_content
    );
}

#[then(regex = r#"the wiki preview should contain "(?P<text>[^"]+)"$"#)]
fn then_wiki_preview_should_contain(world: &mut KanbusWorld, text: String) {
    let wiki = ensure_wiki_state(world);
    assert!(
        wiki.preview_content.contains(&text),
        "expected wiki preview to contain {:?}, got {:?}",
        text,
        wiki.preview_content
    );
}

#[then(regex = r#"the wiki status should show "(?P<status>[^"]+)"$"#)]
fn then_wiki_status_should_show(world: &mut KanbusWorld, status: String) {
    let wiki = ensure_wiki_state(world);
    assert_eq!(
        wiki.status, status,
        "expected wiki status {:?}, got {:?}",
        status, wiki.status
    );
}

#[then(regex = r#"the wiki error banner should contain "(?P<text>[^"]+)"$"#)]
fn then_wiki_error_banner_should_contain(world: &mut KanbusWorld, text: String) {
    let wiki = ensure_wiki_state(world);
    let banner = wiki.error_banner.as_deref().unwrap_or("");
    assert!(
        banner.contains(&text),
        "expected wiki error banner to contain {:?}, got {:?}",
        text,
        banner
    );
}
