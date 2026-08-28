use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use kanbus::wiki::{
    check_wiki_page_links, format_wiki_link_problem, init_wiki, lint_wiki, load_story_references,
    search_wiki_pages, show_wiki_page, WikiRenderRequest,
};
use kanbus::wiki::render_wiki_page;

fn write_default_config(dir: &Path) {
    let contents = r#"
project_directory: project
project_key: kanbus
hierarchy: [initiative, epic, task, sub-task]
types: [bug, story, chore]
workflows:
  default:
    open: [in_progress, closed]
    in_progress: [open, closed]
    closed: [open]
transition_labels:
  default:
    open:
      in_progress: "Start"
      closed: "Close"
    in_progress:
      open: "Reopen"
      closed: "Close"
    closed:
      open: "Reopen"
initial_status: open
priorities:
  0: { name: critical }
  1: { name: high }
  2: { name: medium }
  3: { name: low }
  4: { name: trivial }
default_priority: 2
statuses:
  - { key: open, name: Open, category: todo }
  - { key: in_progress, name: In Progress, category: doing }
  - { key: closed, name: Closed, category: done }
categories:
  - { name: todo }
  - { name: doing }
  - { name: done }
type_colors: {}
beads_compatibility: false
"#;
    fs::write(dir.join(".kanbus.yml"), contents).expect("write config");
    env::set_var("KANBUS_NO_DAEMON", "1");
    fs::create_dir_all(dir.join("project/issues")).expect("create issues dir");
}

fn wiki_root(dir: &Path) -> PathBuf {
    dir.join("project/wiki")
}

#[test]
fn load_story_references_skips_invalid_and_filters_status() {
    let dir = tempfile::tempdir().expect("tempdir");
    let references_dir = dir
        .path()
        .join("stories/STORY-1/references");
    fs::create_dir_all(&references_dir).expect("create references");
    fs::write(references_dir.join("bad.json"), "").expect("write bad");
    fs::write(
        references_dir.join("array.json"),
        "[]",
    )
    .expect("write array");
    fs::write(
        references_dir.join("accepted.json"),
        r#"{"id":"accepted","status":"accepted"}"#,
    )
    .expect("write accepted");
    fs::write(
        references_dir.join("pending.json"),
        r#"{"id":"pending","status":"pending"}"#,
    )
    .expect("write pending");

    let references = load_story_references(dir.path(), Some("accepted")).expect("load references");
    assert_eq!(references.len(), 1);
    assert_eq!(
        references[0].get("id").and_then(|value| value.as_str()),
        Some("accepted")
    );
}

#[test]
fn init_show_search_and_lint_wiki_helpers() {
    let dir = tempfile::tempdir().expect("tempdir");
    write_default_config(dir.path());

    let index_path = init_wiki(dir.path()).expect("init wiki");
    assert_eq!(index_path, "project/wiki/index.md");

    let wiki_dir = wiki_root(dir.path());
    fs::write(wiki_dir.join("alpha.md"), "# Alpha\nalpha body").expect("write alpha");
    fs::write(
        wiki_dir.join("broken.md"),
        "[missing](concepts/missing.md)",
    )
    .expect("write broken");

    let raw = show_wiki_page(dir.path(), "alpha.md").expect("show page");
    assert!(raw.contains("alpha body"));

    let matches = search_wiki_pages(dir.path(), "alpha").expect("search wiki");
    assert!(matches.iter().any(|path| path.contains("alpha.md")));

    let problems = lint_wiki(dir.path()).expect("lint wiki");
    assert!(problems.iter().any(|problem| problem.resolved_path == "concepts/missing.md"));

    let page_problems =
        check_wiki_page_links(dir.path(), "broken.md").expect("check page links");
    assert_eq!(page_problems.len(), 1);
    let formatted = format_wiki_link_problem(&page_problems[0], true);
    assert!(formatted.contains("warning:"));
    assert!(formatted.contains("broken wiki link"));
}

#[test]
fn render_wiki_page_picks_up_new_story_reference_after_cache_warm() {
    let dir = tempfile::tempdir().expect("tempdir");
    write_default_config(dir.path());
    let wiki_dir = wiki_root(dir.path());
    fs::create_dir_all(&wiki_dir).expect("create wiki");
    fs::write(
        wiki_dir.join("live-refs.md"),
        r#"{% for ref in references(status="accepted") %}
- {{ ref.id }}: {{ ref.title }}
{% endfor %}
"#,
    )
    .expect("write template");

    let references_dir = dir
        .path()
        .join("stories/WIKI-650fd9/references");
    fs::create_dir_all(&references_dir).expect("create references");
    fs::write(
        references_dir.join("ref-a.json"),
        r#"{"id":"ref-a","title":"First accepted paper","status":"accepted"}"#,
    )
    .expect("write ref-a");

    let request = WikiRenderRequest {
        root: dir.path().to_path_buf(),
        page_path: PathBuf::from("live-refs.md"),
    };
    let first = render_wiki_page(&request).expect("first render");
    assert!(first.contains("ref-a: First accepted paper"));

    fs::write(
        references_dir.join("ref-c.json"),
        r#"{"id":"ref-c","title":"Newly accepted paper","status":"accepted"}"#,
    )
    .expect("write ref-c");

    let second = render_wiki_page(&request).expect("second render");
    assert!(second.contains("ref-c: Newly accepted paper"));
}
