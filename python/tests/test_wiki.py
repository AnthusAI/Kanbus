from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import wiki
from kanbus import config_loader, project
from kanbus.console_snapshot import ConsoleSnapshotError
from kanbus.config_loader import ConfigurationError
from kanbus.project import ProjectMarkerError

from test_helpers import build_issue, build_project_configuration


def test_get_string_and_serialize_issue() -> None:
    assert wiki._get_string(None) is None
    assert wiki._get_string("x") == "x"
    with pytest.raises(wiki.WikiError, match="invalid query parameter"):
        wiki._get_string(123)

    issue = build_issue("kanbus-1")
    payload = wiki._serialize_issue(issue)
    assert payload["id"] == "kanbus-1"
    assert payload["type"] == issue.issue_type


def test_wiki_context_query_count_issue_and_invalid_sort() -> None:
    a = build_issue("kanbus-a", title="B title", priority=3, status="open")
    b = build_issue("kanbus-b", title="A title", priority=1, status="open")
    c = build_issue("kanbus-c", title="C title", priority=2, status="closed")
    context = wiki.WikiContext([a, b, c])

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


def test_wiki_render_cache_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = tmp_path / "page.md"
    page.write_text("hello", encoding="utf-8")
    issues = [build_issue("kanbus-1")]

    key = wiki._wiki_render_cache_key(page, issues)
    assert len(key) == 64

    cache_dir = tmp_path / "cache"
    assert wiki._wiki_render_read_cache(cache_dir, "missing") is None

    wiki._wiki_render_write_cache(cache_dir, "k1", "content")
    assert wiki._wiki_render_read_cache(cache_dir, "k1") == "content"

    # Read errors should return None.
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("boom")))
    assert wiki._wiki_render_read_cache(cache_dir, "k1") is None


def test_wiki_render_log_cache_hit(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".cache" / "wiki_render"
    wiki._wiki_render_log_cache_hit(cache_dir)
    log = cache_dir.parent / "wiki_cache_hits.log"
    assert log.read_text(encoding="utf-8") == "1\n"


def test_load_ai_config_and_project_dir_success_and_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = build_project_configuration().model_copy(update={"project_directory": "project"})
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
    request = wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/missing.md"))
    with pytest.raises(wiki.WikiError, match="wiki page not found"):
        wiki.render_wiki_page(request)


def test_render_wiki_page_wraps_console_snapshot_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        wiki,
        "get_issues_for_root",
        lambda _root: (_ for _ in ()).throw(ConsoleSnapshotError("snapshot failed")),
    )

    with pytest.raises(wiki.WikiError, match="snapshot failed"):
        wiki.render_wiki_page(wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/p.md")))


def test_render_wiki_page_cache_hit_returns_cached_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("{{ 1 }}", encoding="utf-8")

    monkeypatch.setattr(wiki, "get_issues_for_root", lambda _root: [build_issue("kanbus-1")])
    monkeypatch.setattr(wiki, "_load_ai_config_and_project_dir", lambda _root: (None, "project"))
    monkeypatch.setattr(wiki, "_wiki_render_cache_key", lambda _p, _issues: "k")
    monkeypatch.setattr(wiki, "_wiki_render_read_cache", lambda _dir, _key: "cached")

    logged: list[str] = []
    monkeypatch.setattr(wiki, "_wiki_render_log_cache_hit", lambda _dir: logged.append("hit"))

    rendered = wiki.render_wiki_page(
        wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/p.md"))
    )
    assert rendered == "cached"
    assert logged == ["hit"]


def test_render_wiki_page_renders_and_writes_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("Count={{ count(status='open') }}", encoding="utf-8")

    issues = [build_issue("kanbus-1", status="open"), build_issue("kanbus-2", status="closed")]
    monkeypatch.setattr(wiki, "get_issues_for_root", lambda _root: issues)
    monkeypatch.setattr(wiki, "_load_ai_config_and_project_dir", lambda _root: (None, "project"))
    monkeypatch.setattr(wiki, "_wiki_render_cache_key", lambda _p, _issues: "k")
    monkeypatch.setattr(wiki, "_wiki_render_read_cache", lambda _dir, _key: None)
    monkeypatch.setattr(wiki, "make_ai_summarize", lambda *_args, **_kwargs: (lambda *_a, **_k: "summary"))
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
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("{% for x in %}", encoding="utf-8")

    monkeypatch.setattr(wiki, "get_issues_for_root", lambda _root: [build_issue("kanbus-1")])
    monkeypatch.setattr(wiki, "_load_ai_config_and_project_dir", lambda _root: (None, "project"))
    monkeypatch.setattr(wiki, "_wiki_render_cache_key", lambda _p, _issues: "k")
    monkeypatch.setattr(wiki, "_wiki_render_read_cache", lambda _dir, _key: None)
    monkeypatch.setattr(wiki, "make_ai_summarize", lambda *_args, **_kwargs: (lambda *_a, **_k: "summary"))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(wiki.WikiError):
        wiki.render_wiki_page(
            wiki.WikiRenderRequest(root=tmp_path, page_path=Path("project/wiki/p.md"))
        )


def test_render_wiki_page_re_raises_wiki_error_from_template_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = tmp_path / "project" / "wiki" / "p.md"
    page.parent.mkdir(parents=True)
    page.write_text("{{ count(status=1) }}", encoding="utf-8")

    monkeypatch.setattr(wiki, "get_issues_for_root", lambda _root: [build_issue("kanbus-1")])
    monkeypatch.setattr(wiki, "_load_ai_config_and_project_dir", lambda _root: (None, "project"))
    monkeypatch.setattr(wiki, "_wiki_render_cache_key", lambda _p, _issues: "k")
    monkeypatch.setattr(wiki, "_wiki_render_read_cache", lambda _dir, _key: None)
    monkeypatch.setattr(wiki, "make_ai_summarize", lambda *_args, **_kwargs: (lambda *_a, **_k: "summary"))
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
    monkeypatch.setattr(config_loader, "load_project_configuration", lambda _path: cfg_outside)

    outside_wiki = tmp_path / "docs" / "wiki"
    outside_wiki.mkdir(parents=True)
    (outside_wiki / "c.md").write_text("c", encoding="utf-8")

    paths2 = wiki.list_wiki_pages(tmp_path)
    assert paths2 == ["docs/wiki/c.md"]

    # Missing directory returns empty list.
    cfg_missing = build_project_configuration().model_copy(
        update={"project_directory": "project", "wiki_directory": "wiki-missing"}
    )
    monkeypatch.setattr(config_loader, "load_project_configuration", lambda _path: cfg_missing)
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
