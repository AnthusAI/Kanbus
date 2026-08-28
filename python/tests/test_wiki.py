from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from kanbus import wiki
from kanbus import config_loader, project
from kanbus.console_snapshot import ConsoleSnapshotError
from kanbus.config_loader import ConfigurationError
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


def test_load_story_references_skips_invalid_json_with_warnings(
    tmp_path: Path,
) -> None:
    references_dir = tmp_path / "stories" / "STORY-1" / "references"
    references_dir.mkdir(parents=True)
    (references_dir / "bad.json").write_text("", encoding="utf-8")
    (references_dir / "good.json").write_text(
        '{"id": "good", "title": "Valid", "status": "accepted"}',
        encoding="utf-8",
    )

    warnings: list[str] = []
    records = wiki.load_story_references(
        tmp_path, status="accepted", warnings_out=warnings
    )

    assert len(records) == 1
    assert records[0]["id"] == "good"
    assert any("skipping" in message and "bad.json" in message for message in warnings)


def test_wiki_render_cache_key_includes_reference_mtimes(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text("{% for ref in references() %}{% endfor %}", encoding="utf-8")
    issues = [build_issue("kanbus-1")]
    template = page.read_text(encoding="utf-8")

    references_dir = tmp_path / "stories" / "STORY-1" / "references"
    references_dir.mkdir(parents=True)
    (references_dir / "ref-a.json").write_text('{"id": "ref-a"}', encoding="utf-8")

    key_before = wiki._wiki_render_cache_key(page, issues, tmp_path, template)
    (references_dir / "ref-b.json").write_text('{"id": "ref-b"}', encoding="utf-8")
    key_after = wiki._wiki_render_cache_key(page, issues, tmp_path, template)

    assert key_before != key_after


def test_resolve_wiki_page_path_dot_prefix_and_extensionless(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "dot.md").write_text("dot", encoding="utf-8")
    (wiki_root / "bare.md").write_text("bare", encoding="utf-8")

    resolved_dot = wiki.resolve_wiki_page_path(tmp_path, "./dot.md")
    assert resolved_dot.as_posix() == "project/wiki/dot.md"

    resolved_bare = wiki.resolve_wiki_page_path(tmp_path, "bare")
    assert resolved_bare.as_posix() == "project/wiki/bare.md"


def test_resolve_wiki_page_path_missing_wiki_directory(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    missing_wiki = tmp_path / "project" / "wiki-missing"
    missing_wiki.parent.mkdir(parents=True)
    import copy
    import yaml

    from kanbus.config import DEFAULT_CONFIGURATION

    payload = copy.deepcopy(DEFAULT_CONFIGURATION)
    payload["project_directory"] = "project"
    payload["wiki_directory"] = "wiki-missing"
    (tmp_path / ".kanbus.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(wiki.WikiError, match="wiki directory not found"):
        wiki.resolve_wiki_page_path(tmp_path, "index.md")


def test_format_wiki_link_problem_warning_prefix() -> None:
    problem = wiki.WikiLinkProblem(
        source_page="project/wiki/index.md",
        link_target="missing.md",
        resolved_path="missing.md",
    )
    assert wiki.format_wiki_link_problem(problem, warning=False).startswith(
        "project/wiki/index.md"
    )
    assert wiki.format_wiki_link_problem(problem, warning=True).startswith("warning:")


def test_extract_wiki_title_returns_none_without_heading() -> None:
    assert wiki._extract_wiki_title("plain text without a markdown heading") is None


def test_find_broken_wiki_links_escape_outside_wiki_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location = wiki.WikiLocation(
        wiki_root=Path("/tmp/wiki"),
        list_prefix="project/wiki",
    )

    def _raise_value_error(_self: Path, _other: Path) -> Path:
        raise ValueError("outside wiki root")

    monkeypatch.setattr(Path, "relative_to", _raise_value_error)
    problems = wiki._find_broken_wiki_links(
        location,
        "concepts/a.md",
        "project/wiki/concepts/a.md",
        "[escape](../../../outside.md)",
    )
    assert len(problems) == 1
    assert problems[0].link_target == "../../../outside.md"


def test_find_broken_wiki_links_ignores_external_targets() -> None:
    location = wiki.WikiLocation(
        wiki_root=Path("/tmp/wiki"),
        list_prefix="project/wiki",
    )
    problems = wiki._find_broken_wiki_links(
        location,
        "index.md",
        "project/wiki/index.md",
        "[external](https://example.com/page.md)",
    )
    assert problems == []


def test_resolve_wiki_internal_link_strips_dot_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_path = wiki.Path

    class DotPath:
        parts = ("dir", ".", "target.md")

    def path_factory(value: object) -> object:
        if value == "dir/./target.md":
            return DotPath()
        return original_path(value)  # type: ignore[call-arg]

    monkeypatch.setattr(wiki, "Path", path_factory)
    assert (
        wiki._resolve_wiki_internal_link("dir/page.md", "./target.md")
        == "dir/target.md"
    )


def test_story_references_cache_part_skips_missing_references_dir(
    tmp_path: Path,
) -> None:
    stories_root = tmp_path / "stories"
    (stories_root / "STORY-1").mkdir(parents=True)
    (stories_root / "STORY-2" / "references").mkdir(parents=True)
    (stories_root / "STORY-2" / "references" / "ref.json").write_text(
        '{"id": "ref"}', encoding="utf-8"
    )
    (stories_root / "not-a-story-dir").write_text("skip", encoding="utf-8")

    part = wiki._story_references_cache_part(tmp_path)
    assert "STORY-2/references/ref.json" in part
    assert "not-a-story-dir" not in part


def test_story_references_cache_part_handles_stat_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    references_dir = tmp_path / "stories" / "STORY-1" / "references"
    references_dir.mkdir(parents=True)
    reference_path = references_dir / "ref.json"
    reference_path.write_text('{"id": "ref"}', encoding="utf-8")

    original_stat = Path.stat

    def _failing_stat(self: Path, *args: object, **kwargs: object) -> object:
        if self == reference_path:
            raise OSError("stat failed")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _failing_stat)
    part = wiki._story_references_cache_part(tmp_path)
    assert part.endswith(":")


def test_lint_wiki_skips_non_file_markdown_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "valid.md").write_text("# Valid", encoding="utf-8")

    original_is_file = Path.is_file

    def _selective_is_file(self: Path) -> bool:
        if self.name == "valid.md":
            return False
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", _selective_is_file)
    assert wiki.lint_wiki(tmp_path) == []


def test_search_wiki_pages_skips_non_file_markdown_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "valid.md").write_text("# Beta title", encoding="utf-8")

    original_is_file = Path.is_file

    def _selective_is_file(self: Path) -> bool:
        if self.name == "valid.md":
            return False
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", _selective_is_file)
    assert wiki.search_wiki_pages(tmp_path, "beta") == []


def test_resolve_wiki_page_path_absolute_and_empty(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    page = wiki_root / "abs.md"
    page.write_text("absolute", encoding="utf-8")

    resolved = wiki.resolve_wiki_page_path(tmp_path, str(page.resolve()))
    assert resolved.as_posix() == "project/wiki/abs.md"

    outside = tmp_path.parent / "outside-wiki.md"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(wiki.WikiError, match="wiki page not found"):
        wiki.resolve_wiki_page_path(tmp_path, str(outside.resolve()))

    missing_absolute = wiki_root / "missing-abs.md"
    with pytest.raises(wiki.WikiError, match="wiki page not found"):
        wiki.resolve_wiki_page_path(tmp_path, str(missing_absolute.resolve()))

    with pytest.raises(wiki.WikiError, match="wiki page not found"):
        wiki.resolve_wiki_page_path(tmp_path, "")


def test_show_wiki_page_returns_raw_source(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    page = tmp_path / "project" / "wiki" / "raw.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Raw\n{{ count() }}", encoding="utf-8")

    assert wiki.show_wiki_page(tmp_path, "raw.md") == "# Raw\n{{ count() }}"


def test_lint_wiki_reports_broken_links(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "index.md").write_text("[x](missing.md)", encoding="utf-8")

    problems = wiki.lint_wiki(tmp_path)
    assert len(problems) == 1
    assert problems[0].resolved_path == "missing.md"


def test_lint_wiki_missing_directory_raises(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    with pytest.raises(wiki.WikiError, match="wiki directory not found"):
        wiki.lint_wiki(tmp_path)


def test_load_story_references_skips_more_invalid_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    references_dir = tmp_path / "stories" / "STORY-1" / "references"
    references_dir.mkdir(parents=True)
    (references_dir / "array.json").write_text("[]", encoding="utf-8")
    (references_dir / "pending.json").write_text(
        '{"id": "pending", "status": "pending"}', encoding="utf-8"
    )
    (references_dir / "accepted.json").write_text(
        '{"id": "accepted", "status": "accepted"}', encoding="utf-8"
    )

    warnings: list[str] = []
    records = wiki.load_story_references(
        tmp_path, status="accepted", warnings_out=warnings
    )
    assert [record["id"] for record in records] == ["accepted"]
    assert any("non-object" in message for message in warnings)

    unreadable = references_dir / "unreadable.json"
    unreadable.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def _selective_read_error(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "unreadable.json":
            raise OSError("read failed")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _selective_read_error)
    warnings.clear()
    wiki.load_story_references(tmp_path, warnings_out=warnings)
    assert any("unreadable" in message for message in warnings)

    invalid = references_dir / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    warnings.clear()
    wiki.load_story_references(tmp_path, warnings_out=warnings)
    assert any("invalid story reference JSON" in message for message in warnings)


def test_load_story_references_without_stories_directory(tmp_path: Path) -> None:
    assert wiki.load_story_references(tmp_path) == []


def test_search_wiki_pages_empty_query_lists_all(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "a.md").write_text("# A", encoding="utf-8")

    assert wiki.search_wiki_pages(tmp_path, "") == ["project/wiki/a.md"]
    assert wiki.search_wiki_pages(tmp_path, "alpha") == []

    shutil.rmtree(wiki_root)
    assert wiki.search_wiki_pages(tmp_path, "alpha") == []


def test_check_wiki_page_links_for_single_page(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "page.md").write_text("[x](missing.md)", encoding="utf-8")

    problems = wiki.check_wiki_page_links(tmp_path, "page.md")
    assert len(problems) == 1


def test_init_wiki_creates_stub_index(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    index_path = wiki.init_wiki(tmp_path)
    assert index_path == "project/wiki/index.md"
    assert (tmp_path / "project" / "wiki" / "index.md").exists()


def test_story_references_cache_part_collects_mtimes(tmp_path: Path) -> None:
    references_dir = tmp_path / "stories" / "STORY-1" / "references"
    references_dir.mkdir(parents=True)
    (references_dir / "ref.json").write_text('{"id": "ref"}', encoding="utf-8")
    (tmp_path / "stories" / "skip-file").write_text("not a dir", encoding="utf-8")

    part = wiki._story_references_cache_part(tmp_path)
    assert "stories/STORY-1/references/ref.json:" in part


def test_wiki_context_references_filters_status(tmp_path: Path) -> None:
    references_dir = tmp_path / "stories" / "STORY-1" / "references"
    references_dir.mkdir(parents=True)
    (references_dir / "accepted.json").write_text(
        '{"id": "accepted", "status": "accepted"}', encoding="utf-8"
    )
    context = wiki.WikiContext(issues=[], root=tmp_path)
    records = context.references(status="accepted")
    assert records[0]["id"] == "accepted"


def test_wiki_internal_link_helpers() -> None:
    assert wiki._is_wiki_internal_md_link("https://example.com/x.md") is False
    assert wiki._is_wiki_internal_md_link("mailto:team@example.com") is False
    assert wiki._is_wiki_internal_md_link("#section-only") is False
    assert wiki._is_wiki_internal_md_link("{{ dynamic }}.md") is False
    assert wiki._is_wiki_internal_md_link("notes.md#section") is True
    assert (
        wiki._resolve_wiki_internal_link("concepts/a.md", "../notes.md") == "notes.md"
    )
    assert wiki._resolve_wiki_internal_link("index.md", "./same.md") == "same.md"

    location = wiki.WikiLocation(
        wiki_root=Path("/tmp/wiki"),
        list_prefix="project/wiki",
    )
    problems = wiki._find_broken_wiki_links(
        location,
        "concepts/a.md",
        "project/wiki/concepts/a.md",
        "[escape](../../outside.md)",
    )
    assert len(problems) == 1


def test_load_story_references_skips_non_directory_entries(tmp_path: Path) -> None:
    stories_root = tmp_path / "stories"
    stories_root.mkdir(parents=True)
    (stories_root / "not-a-directory").write_text("skip", encoding="utf-8")
    (stories_root / "STORY-1" / "references").mkdir(parents=True)
    (stories_root / "STORY-1" / "references" / "ok.json").write_text(
        '{"id": "ok"}', encoding="utf-8"
    )

    records = wiki.load_story_references(tmp_path)
    assert len(records) == 1
    assert records[0]["id"] == "ok"


def test_load_story_references_skips_story_without_references_dir(
    tmp_path: Path,
) -> None:
    stories_root = tmp_path / "stories"
    (stories_root / "STORY-1").mkdir(parents=True)
    (stories_root / "STORY-1" / "references").mkdir()
    (stories_root / "STORY-1" / "references" / "ok.json").write_text(
        '{"id": "ok"}', encoding="utf-8"
    )
    (stories_root / "STORY-2").mkdir()

    records = wiki.load_story_references(tmp_path)
    assert len(records) == 1
    assert records[0]["id"] == "ok"


def test_search_wiki_pages_finds_title_and_body(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "notes.md").write_text("# Beta title\nbody mention", encoding="utf-8")

    matches = wiki.search_wiki_pages(tmp_path, "beta")
    assert matches == ["project/wiki/notes.md"]


def test_render_template_string_with_references(tmp_path: Path) -> None:
    references_dir = tmp_path / "stories" / "STORY-1" / "references"
    references_dir.mkdir(parents=True)
    (references_dir / "accepted.json").write_text(
        '{"id": "ref-a", "title": "Paper", "status": "accepted"}',
        encoding="utf-8",
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    try:
        rendered = wiki.render_template_string(
            '{% for ref in references(status="accepted") %}{{ ref.id }}{% endfor %}',
            [],
        )
    finally:
        monkeypatch.undo()
    assert "ref-a" in rendered


def test_lint_wiki_success_on_valid_links(tmp_path: Path) -> None:
    _write_default_kanbus_config(tmp_path)
    wiki_root = tmp_path / "project" / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "target.md").write_text("# Target", encoding="utf-8")
    (wiki_root / "index.md").write_text("[ok](target.md)", encoding="utf-8")

    assert wiki.lint_wiki(tmp_path) == []


def test_wiki_cache_key_ignores_references_without_template_call(
    tmp_path: Path,
) -> None:
    page = tmp_path / "page.md"
    page.write_text("plain page", encoding="utf-8")
    issues = [build_issue("kanbus-1")]
    wiki._wiki_render_cache_key(
        page, issues, tmp_path, page.read_text(encoding="utf-8")
    )
    assert wiki._story_references_cache_part(tmp_path) == ""


def test_render_wiki_page_collects_reference_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_default_kanbus_config(tmp_path)
    page = tmp_path / "project" / "wiki" / "refs.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        '{% for ref in references(status="accepted") %}{{ ref.id }}{% endfor %}',
        encoding="utf-8",
    )
    references_dir = tmp_path / "stories" / "STORY-1" / "references"
    references_dir.mkdir(parents=True)
    (references_dir / "bad.json").write_text("", encoding="utf-8")
    (references_dir / "good.json").write_text(
        '{"id": "good", "status": "accepted"}', encoding="utf-8"
    )

    monkeypatch.setattr(wiki, "get_issues_for_root", lambda _root: [])
    monkeypatch.setattr(
        wiki, "_load_ai_config_and_project_dir", lambda _root: (None, "project")
    )
    monkeypatch.setattr(
        wiki,
        "make_ai_summarize",
        lambda *_args, **_kwargs: (lambda *_a, **_k: "summary"),
    )
    monkeypatch.chdir(tmp_path)

    reference_warnings: list[str] = []
    rendered = wiki.render_wiki_page(
        wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/refs.md")),
        reference_warnings=reference_warnings,
    )
    assert "good" in rendered
    assert any("bad.json" in message for message in reference_warnings)


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

    # Missing directory returns empty list.
    cfg_missing = build_project_configuration().model_copy(
        update={"project_directory": "project", "wiki_directory": "wiki-missing"}
    )
    monkeypatch.setattr(
        config_loader, "load_project_configuration", lambda _path: cfg_missing
    )
    assert wiki.list_wiki_pages(tmp_path) == []

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
