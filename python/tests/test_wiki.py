from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import wiki
from kanbus import config_loader, project
from kanbus.console_snapshot import ConsoleSnapshotError
from kanbus.config_loader import ConfigurationError
from kanbus.models import DependencyLink
from kanbus.project import ProjectMarkerError

from test_helpers import build_issue, build_project_configuration


def _write_default_kanbus_config(root: Path) -> None:
    import copy
    import yaml

    from kanbus.config import DEFAULT_CONFIGURATION

    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["project_directory"] = "project"
    (root / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def test_get_string_and_serialize_issue() -> None:
    assert wiki._get_string(None) is None
    assert wiki._get_string("x") == "x"
    with pytest.raises(wiki.WikiError, match="invalid query parameter"):
        wiki._get_string(123)

    issue = build_issue("kanbus-1")
    payload = wiki._serialize_issue(issue)
    assert payload["id"] == "kanbus-1"
    assert payload["key"] == "1"
    assert payload["short_id"] == "1"
    assert payload["type"] == issue.issue_type


def test_wiki_context_query_count_issue_and_invalid_sort() -> None:
    a = build_issue("kanbus-a", title="B title", priority=3, status="open")
    b = build_issue("kanbus-b", title="A title", priority=1, status="open")
    c = build_issue("kanbus-c", title="C title", priority=2, status="closed")
    context = wiki.WikiContext([a, b, c], root=Path.cwd())

    base = context.query(status="open")
    assert {row["id"] for row in base} == {"kanbus-a", "kanbus-b"}

    by_title = context.query(status="open", sort="title")
    assert [row["id"] for row in by_title] == ["kanbus-b", "kanbus-a"]

    by_priority = context.query(status="open", sort="priority")
    assert [row["id"] for row in by_priority] == ["kanbus-b", "kanbus-a"]

    assert context.count(status="closed") == 1
    assert context.issue("kanbus-a")["id"] == "kanbus-a"  # type: ignore[index]
    assert context.issue("missing") is None

    with pytest.raises(wiki.WikiError, match="invalid sort key"):
        context.query(sort="bad")


def test_wiki_context_children_blocked_by_and_blocks() -> None:
    parent = build_issue("kanbus-epic01", title="Epic", issue_type="epic")
    child = build_issue("kanbus-child", title="Child", parent="kanbus-epic01")
    blocker = build_issue("kanbus-blocker", title="Blocker")
    blocked = build_issue("kanbus-blocked01", title="Blocked", status="blocked")
    blocked = blocked.model_copy(
        update={
            "dependencies": [
                DependencyLink(target="kanbus-blocker", type="blocked-by"),
                DependencyLink(target="kanbus-epic01", type="relates-to"),
            ]
        }
    )
    context = wiki.WikiContext([parent, child, blocker, blocked], root=Path.cwd())

    assert [row["id"] for row in context.children("kanbus-epic01")] == ["kanbus-child"]
    assert context.children("missing") == []

    blockers = context.blocked_by("kanbus-blocked01")
    assert [row["id"] for row in blockers] == ["kanbus-blocker"]
    assert context.blocked_by("kanbus-blocker") == []
    assert context.blocked_by("missing") == []

    blocked_rows = context.blocks("kanbus-blocker")
    assert [row["id"] for row in blocked_rows] == ["kanbus-blocked01"]
    assert context.blocks("kanbus-blocked01") == []


def test_render_template_string_blocked_by_helper() -> None:
    blocker = build_issue("kanbus-blocker", title="Blocker")
    blocked = build_issue("kanbus-blocked01", title="Blocked", status="blocked")
    blocked = blocked.model_copy(
        update={
            "dependencies": [DependencyLink(target="kanbus-blocker", type="blocked-by")]
        }
    )
    rendered = wiki.render_template_string(
        "{% for blocker in blocked_by('kanbus-blocked01') %}{{ blocker.id }}{% endfor %}",
        [blocker, blocked],
    )
    assert rendered == "kanbus-blocker"

    combined = wiki.render_template_string(
        (
            "{% for issue in query(status='blocked') %}"
            "{{ issue.id }}:"
            "{% for blocker in blocked_by(issue.id) %}{{ blocker.id }}{% endfor %}"
            "{% endfor %}"
        ),
        [blocker, blocked],
    )
    assert combined == "kanbus-blocked01:kanbus-blocker"


def test_wiki_render_cache_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = tmp_path / "page.md"
    page.write_text("hello", encoding="utf-8")
    issues = [build_issue("kanbus-1")]

    key = wiki._wiki_render_cache_key(page, issues, tmp_path, "hello")
    assert len(key) == 64

    cache_dir = tmp_path / "cache"
    assert wiki._wiki_render_read_cache(cache_dir, "missing") is None

    wiki._wiki_render_write_cache(cache_dir, "k1", "content")
    assert wiki._wiki_render_read_cache(cache_dir, "k1") == "content"

    # Read errors should return None.
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("boom")),
    )
    assert wiki._wiki_render_read_cache(cache_dir, "k1") is None


def test_wiki_render_log_cache_hit(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".cache" / "wiki_render"
    wiki._wiki_render_log_cache_hit(cache_dir)
    log = cache_dir.parent / "wiki_cache_hits.log"
    assert log.read_text(encoding="utf-8") == "1\n"


def test_load_ai_config_and_project_dir_success_and_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = build_project_configuration().model_copy(
        update={"project_directory": "project"}
    )
    cfg_path = tmp_path / ".kanbus.yml"

    monkeypatch.setattr(project, "get_configuration_path", lambda _root: cfg_path)
    monkeypatch.setattr(config_loader, "load_project_configuration", lambda _path: cfg)

    ai_config, project_dir = wiki._load_ai_config_and_project_dir(tmp_path)
    assert ai_config is None
    assert project_dir == "project"

    monkeypatch.setattr(
        project,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("missing")),
    )
    assert wiki._load_ai_config_and_project_dir(tmp_path) == (None, None)

    monkeypatch.setattr(project, "get_configuration_path", lambda _root: cfg_path)
    monkeypatch.setattr(
        config_loader,
        "load_project_configuration",
        lambda _path: (_ for _ in ()).throw(ConfigurationError("bad")),
    )
    assert wiki._load_ai_config_and_project_dir(tmp_path) == (None, None)


def test_render_template_string_success_and_errors() -> None:
    issues = [build_issue("kanbus-1", title="Hello")]

    rendered = wiki.render_template_string("{{ issue('kanbus-1').title }}", issues)
    assert rendered == "Hello"

    with pytest.raises(wiki.WikiError, match="invalid query parameter"):
        wiki.render_template_string("{{ count(status=1) }}", issues)

    with pytest.raises(wiki.WikiError):
        wiki.render_template_string("{% for x in %}", issues)


def test_render_wiki_page_raises_for_missing_page(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    request = wiki.WikiRenderRequest(
        root=tmp_path, page_path=Path("project/wiki/missing.md")
    )
    with pytest.raises(
        wiki.WikiError, match="wiki page not found: project/wiki/missing.md"
    ):
        wiki.render_wiki_page(request)


def test_render_wiki_page_wraps_console_snapshot_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_default_kanbus_config(tmp_path)
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        wiki,
        "get_issues_for_root",
        lambda _root: (_ for _ in ()).throw(ConsoleSnapshotError("snapshot failed")),
    )

    with pytest.raises(wiki.WikiError, match="snapshot failed"):
        wiki.render_wiki_page(
            wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/p.md"))
        )


def test_render_wiki_page_cache_hit_returns_cached_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_default_kanbus_config(tmp_path)
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("{{ 1 }}", encoding="utf-8")

    monkeypatch.setattr(
        wiki, "get_issues_for_root", lambda _root: [build_issue("kanbus-1")]
    )
    monkeypatch.setattr(
        wiki, "_load_ai_config_and_project_dir", lambda _root: (None, "project")
    )
    monkeypatch.setattr(
        wiki, "_wiki_render_cache_key", lambda _p, _issues, _root, _tpl: "k"
    )
    monkeypatch.setattr(wiki, "_wiki_render_read_cache", lambda _dir, _key: "cached")

    logged: list[str] = []
    monkeypatch.setattr(
        wiki, "_wiki_render_log_cache_hit", lambda _dir: logged.append("hit")
    )

    rendered = wiki.render_wiki_page(
        wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/p.md"))
    )
    assert rendered == "cached"
    assert logged == ["hit"]


def test_render_wiki_page_renders_and_writes_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_default_kanbus_config(tmp_path)
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("Count={{ count(status='open') }}", encoding="utf-8")

    issues = [
        build_issue("kanbus-1", status="open"),
        build_issue("kanbus-2", status="closed"),
    ]
    monkeypatch.setattr(wiki, "get_issues_for_root", lambda _root: issues)
    monkeypatch.setattr(
        wiki, "_load_ai_config_and_project_dir", lambda _root: (None, "project")
    )
    monkeypatch.setattr(
        wiki, "_wiki_render_cache_key", lambda _p, _issues, _root, _tpl: "k"
    )
    monkeypatch.setattr(wiki, "_wiki_render_read_cache", lambda _dir, _key: None)
    monkeypatch.setattr(
        wiki,
        "make_ai_summarize",
        lambda *_args, **_kwargs: (lambda *_a, **_k: "summary"),
    )
    monkeypatch.chdir(tmp_path)

    writes: list[str] = []

    def _write(_cache_dir: Path, _key: str, content: str) -> None:
        writes.append(content)

    monkeypatch.setattr(wiki, "_wiki_render_write_cache", _write)

    rendered = wiki.render_wiki_page(
        wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/p.md"))
    )
    assert rendered == "Count=1"
    assert writes == ["Count=1"]


def test_render_wiki_page_wraps_template_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_default_kanbus_config(tmp_path)
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("{% for x in %}", encoding="utf-8")

    monkeypatch.setattr(
        wiki, "get_issues_for_root", lambda _root: [build_issue("kanbus-1")]
    )
    monkeypatch.setattr(
        wiki, "_load_ai_config_and_project_dir", lambda _root: (None, "project")
    )
    monkeypatch.setattr(
        wiki, "_wiki_render_cache_key", lambda _p, _issues, _root, _tpl: "k"
    )
    monkeypatch.setattr(wiki, "_wiki_render_read_cache", lambda _dir, _key: None)
    monkeypatch.setattr(
        wiki,
        "make_ai_summarize",
        lambda *_args, **_kwargs: (lambda *_a, **_k: "summary"),
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(wiki.WikiError):
        wiki.render_wiki_page(
            wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/p.md"))
        )


def test_render_wiki_page_re_raises_wiki_error_from_template_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_default_kanbus_config(tmp_path)
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("{{ count(status=1) }}", encoding="utf-8")

    monkeypatch.setattr(
        wiki, "get_issues_for_root", lambda _root: [build_issue("kanbus-1")]
    )
    monkeypatch.setattr(
        wiki, "_load_ai_config_and_project_dir", lambda _root: (None, "project")
    )
    monkeypatch.setattr(
        wiki, "_wiki_render_cache_key", lambda _p, _issues, _root, _tpl: "k"
    )
    monkeypatch.setattr(wiki, "_wiki_render_read_cache", lambda _dir, _key: None)
    monkeypatch.setattr(
        wiki,
        "make_ai_summarize",
        lambda *_args, **_kwargs: (lambda *_a, **_k: "summary"),
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(wiki.WikiError, match="invalid query parameter"):
        wiki.render_wiki_page(
            wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/p.md"))
        )


def test_list_wiki_pages_success_absolute_relative_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = tmp_path / ".kanbus.yml"

    monkeypatch.setattr(project, "get_configuration_path", lambda _root: cfg_path)

    cfg = build_project_configuration().model_copy(
        update={"project_directory": "project", "wiki_directory": "wiki"}
    )
    monkeypatch.setattr(config_loader, "load_project_configuration", lambda _path: cfg)

    root_wiki = tmp_path / "project" / "wiki"
    (root_wiki / "sub").mkdir(parents=True)
    (root_wiki / "a.md").write_text("a", encoding="utf-8")
    (root_wiki / "sub" / "b.md").write_text("b", encoding="utf-8")
    (root_wiki / "skip.txt").write_text("x", encoding="utf-8")

    paths = wiki.list_wiki_pages(tmp_path)
    assert paths == ["project/wiki/a.md", "project/wiki/sub/b.md"]

    cfg_outside = build_project_configuration().model_copy(
        update={"project_directory": "project", "wiki_directory": "../docs/wiki"}
    )
    monkeypatch.setattr(
        config_loader, "load_project_configuration", lambda _path: cfg_outside
    )

    outside_wiki = tmp_path / "docs" / "wiki"
    outside_wiki.mkdir(parents=True)
    (outside_wiki / "c.md").write_text("c", encoding="utf-8")

    paths2 = wiki.list_wiki_pages(tmp_path)
    assert paths2 == ["docs/wiki/c.md"]

    cfg_missing = build_project_configuration().model_copy(
        update={"project_directory": "project", "wiki_directory": "wiki-missing"}
    )
    monkeypatch.setattr(
        config_loader, "load_project_configuration", lambda _path: cfg_missing
    )
    with pytest.raises(wiki.WikiError, match="wiki directory not found"):
        wiki.list_wiki_pages(tmp_path)

    monkeypatch.setattr(
        project,
        "get_configuration_path",
        lambda _root: (_ for _ in ()).throw(ProjectMarkerError("missing")),
    )
    with pytest.raises(wiki.WikiError, match="missing"):
        wiki.list_wiki_pages(tmp_path)

    monkeypatch.setattr(project, "get_configuration_path", lambda _root: cfg_path)
    monkeypatch.setattr(
        config_loader,
        "load_project_configuration",
        lambda _path: (_ for _ in ()).throw(ConfigurationError("bad config")),
    )
    with pytest.raises(wiki.WikiError, match="bad config"):
        wiki.list_wiki_pages(tmp_path)


def test_extract_wiki_title_reads_h1() -> None:
    assert wiki.extract_wiki_title("# Blocked issues\nOpen items.") == "Blocked issues"


def test_extract_wiki_title_prefers_frontmatter_over_h1() -> None:
    content = "---\ntitle: Epic progress\n---\n# Ignored heading\nStatus body\n"
    assert wiki.extract_wiki_title(content) == "Epic progress"


def test_extract_wiki_title_ignores_leading_blank_lines_before_frontmatter() -> None:
    content = "\n---\ntitle: Epic progress\n---\n# Ignored heading\n"
    assert wiki.extract_wiki_title(content) == "Epic progress"


def test_extract_wiki_title_unquotes_frontmatter_title() -> None:
    content = '---\ntitle: "Quoted title"\n---\n# Heading\n'
    assert wiki.extract_wiki_title(content) == "Quoted title"


def test_extract_wiki_title_uses_h1_when_frontmatter_has_no_title() -> None:
    content = "---\nstatus: draft\n---\n# Heading title\n"
    assert wiki.extract_wiki_title(content) == "Heading title"


def test_wiki_page_display_title_falls_back_to_stem() -> None:
    assert (
        wiki.wiki_page_display_title("Just a paragraph.", "untitled_notes.md")
        == "untitled_notes"
    )


def test_convert_wiki_markdown_to_html_wraps_gfm_in_markus_document() -> None:
    html = wiki.convert_wiki_markdown_to_html("Plain paragraph with **bold** text.")
    assert "markus-document" in html
    assert "Plain paragraph with" in html


def test_convert_wiki_markdown_to_html_renders_pull_quote() -> None:
    source = ":::pull-quote\n> Measure what matters.\n:::\n"
    html = wiki.convert_wiki_markdown_to_html(source)
    assert "markus-pull-quote" in html
    assert "Measure what matters." in html


def test_convert_wiki_markdown_to_html_rejects_unknown_directive() -> None:
    source = ":::unknown-directive\nInvalid block.\n:::\n"
    with pytest.raises(wiki.WikiError, match="Unknown directive"):
        wiki.convert_wiki_markdown_to_html(source)


def test_convert_wiki_markdown_to_html_wraps_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_runtime_error(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("markus exploded")

    monkeypatch.setattr(wiki, "convert_markus_source", raise_runtime_error)
    with pytest.raises(wiki.WikiError, match="markus exploded"):
        wiki.convert_wiki_markdown_to_html("plain")


def test_wiki_internal_link_normalizes_dot_segments() -> None:
    assert (
        wiki._resolve_wiki_internal_link("guides/intro.md", "./sibling.md")
        == "guides/sibling.md"
    )


def test_extract_wiki_title_alias_and_unclosed_frontmatter() -> None:
    assert wiki._extract_wiki_title("# Heading title") == "Heading title"
    frontmatter, body = wiki._split_wiki_frontmatter("---\ntitle: Dangling\n# Body\n")
    assert frontmatter is None
    assert "Dangling" in body


def test_format_wiki_render_json_includes_rendered_html() -> None:
    payload = wiki.format_wiki_render_json(
        "project/wiki/status.md",
        "Open: 3",
        '<article class="markus-document"><p>Open: 3</p></article>',
    )
    assert '"path": "project/wiki/status.md"' in payload
    assert '"rendered": "Open: 3"' in payload
    assert "rendered_html" in payload
    assert "markus-document" in payload
