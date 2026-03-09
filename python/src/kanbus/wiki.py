"""Wiki rendering utilities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kanbus.ai_summarize import make_ai_summarize
from kanbus.console_snapshot import ConsoleSnapshotError, get_issues_for_root
from kanbus.models import IssueData
from kanbus.queries import filter_issues


class WikiError(RuntimeError):
    """Raised when wiki rendering fails."""


@dataclass(frozen=True)
class WikiContext:
    """Wiki context for rendering.

    :param issues: Issues loaded for rendering.
    :type issues: List[IssueData]
    """

    issues: List[IssueData]

    def query(self, **filters: object) -> List[Dict[str, object]]:
        """Query issues for wiki templates.

        :return: Matching issues.
        :rtype: List[Dict[str, object]]
        :raises WikiError: If the query parameters are invalid.
        """
        status = _get_string(filters.get("status"))
        issue_type = _get_string(filters.get("issue_type") or filters.get("type"))
        sort_key = _get_string(filters.get("sort"))

        filtered = filter_issues(
            self.issues,
            status,
            issue_type,
            None,
            None,
        )
        if sort_key is None:
            return [_serialize_issue(issue) for issue in filtered]
        if sort_key == "title":
            return [
                _serialize_issue(issue)
                for issue in sorted(filtered, key=lambda issue: issue.title)
            ]
        if sort_key == "priority":
            return [
                _serialize_issue(issue)
                for issue in sorted(filtered, key=lambda issue: issue.priority)
            ]
        raise WikiError("invalid sort key")

    def count(self, **filters: object) -> int:
        """Count issues for wiki templates.

        :return: Count of matching issues.
        :rtype: int
        :raises WikiError: If the query parameters are invalid.
        """
        return len(self.query(**filters))

    def issue(self, identifier: str) -> Dict[str, object] | None:
        """Look up an issue by identifier for wiki templates.

        :param identifier: Issue identifier.
        :type identifier: str
        :return: Serialized issue or None if not found.
        :rtype: Dict[str, object] | None
        """
        for i in self.issues:
            if i.identifier == identifier:
                return _serialize_issue(i)
        return None


@dataclass(frozen=True)
class WikiRenderRequest:
    """Request for rendering a wiki page.

    :param root: Repository root path.
    :type root: Path
    :param page_path: Path to the wiki page.
    :type page_path: Path
    """

    root: Path
    page_path: Path


def render_wiki_page(request: WikiRenderRequest) -> str:
    """Render a wiki page using the live issue index.

    :param request: Render request with root and page path.
    :type request: WikiRenderRequest
    :return: Rendered wiki content.
    :rtype: str
    :raises WikiError: If rendering fails.
    """
    full_page = request.root / request.page_path
    if not full_page.exists():
        raise WikiError("wiki page not found")

    try:
        issues = get_issues_for_root(request.root)
    except ConsoleSnapshotError as error:
        raise WikiError(str(error)) from error

    ai_config, project_dir = _load_ai_config_and_project_dir(request.root)
    wiki_render_cache_dir = (
        request.root / project_dir / ".cache" / "wiki_render" if project_dir else None
    )
    if wiki_render_cache_dir is not None:
        cache_key = _wiki_render_cache_key(full_page, list(issues))
        cached = _wiki_render_read_cache(wiki_render_cache_dir, cache_key)
        if cached is not None:
            _wiki_render_log_cache_hit(wiki_render_cache_dir)
            return cached
    issues_by_id = {i.identifier: _serialize_issue(i) for i in issues}
    ai_cache_dir = request.root / project_dir / ".cache" if project_dir else None
    ai_summarize_fn = make_ai_summarize(issues_by_id, ai_config, ai_cache_dir)

    context = WikiContext(issues=list(issues))
    environment = Environment(
        loader=FileSystemLoader(str(request.page_path.parent)),
        autoescape=select_autoescape(
            enabled_extensions=("html", "htm", "xml"),
            default_for_string=False,
            default=False,
        ),
    )
    environment.globals.update(
        {
            "query": context.query,
            "count": context.count,
            "issue": context.issue,
            "ai_summarize": ai_summarize_fn,
        }
    )
    try:
        rendered = environment.get_template(request.page_path.name).render()
    except WikiError:
        raise
    except Exception as error:
        raise WikiError(str(error)) from error

    if wiki_render_cache_dir is not None:
        _wiki_render_write_cache(wiki_render_cache_dir, cache_key, rendered)
    return rendered


def _wiki_render_cache_key(page_path: Path, issues: List[IssueData]) -> str:
    page_mtime = str(page_path.stat().st_mtime) if page_path.exists() else ""
    issue_part = "|".join(
        f"{i.identifier}:{i.updated_at.isoformat()}"
        for i in sorted(issues, key=lambda x: x.identifier)
    )
    raw = f"{page_path}|{page_mtime}|{issue_part}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _wiki_render_read_cache(cache_dir: Path, key: str) -> str | None:
    path = cache_dir / f"{key}.md"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _wiki_render_write_cache(cache_dir: Path, key: str, content: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.md").write_text(content, encoding="utf-8")


def _wiki_render_log_cache_hit(cache_dir: Path) -> None:
    log_path = cache_dir.parent / "wiki_cache_hits.log"
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    log_path.open("a", encoding="utf-8").write("1\n")


def _load_ai_config_and_project_dir(root: Path) -> tuple[object | None, str | None]:
    """Load AI configuration and project directory. Returns (ai_config, project_dir)."""
    from kanbus.config_loader import ConfigurationError, load_project_configuration
    from kanbus.project import ProjectMarkerError, get_configuration_path

    try:
        config_path = get_configuration_path(root)
        configuration = load_project_configuration(config_path)
        return (configuration.ai, configuration.project_directory)
    except (ProjectMarkerError, ConfigurationError):
        return (None, None)


def _get_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise WikiError("invalid query parameter")


def _serialize_issue(issue: IssueData) -> Dict[str, object]:
    return issue.model_dump(by_alias=True, mode="json")


def render_template_string(text: str, issues: List[IssueData]) -> str:
    """Render a template string with wiki context (query, count, issue).

    :param text: Template string (may contain Jinja2).
    :type text: str
    :param issues: Issues for query/count/issue context.
    :type issues: List[IssueData]
    :return: Rendered text.
    :rtype: str
    :raises WikiError: If template rendering fails.
    """
    context = WikiContext(issues=issues)
    environment = Environment(
        autoescape=select_autoescape(
            enabled_extensions=("html", "htm", "xml"),
            default_for_string=False,
            default=False,
        ),
    )
    environment.globals.update(
        {
            "query": context.query,
            "count": context.count,
            "issue": context.issue,
        }
    )
    try:
        template = environment.from_string(text)
        return template.render()
    except WikiError:
        raise
    except Exception as error:
        raise WikiError(str(error)) from error


def list_wiki_pages(root: Path) -> List[str]:
    """List wiki page paths relative to repository root.

    :param root: Repository root path.
    :type root: Path
    :return: Sorted list of paths like project/docs/page.md.
    :rtype: List[str]
    :raises WikiError: If configuration or project structure is invalid.
    """
    from kanbus.config_loader import ConfigurationError, load_project_configuration
    from kanbus.project import ProjectMarkerError, get_configuration_path

    try:
        config_path = get_configuration_path(root)
        configuration = load_project_configuration(config_path)
    except (ProjectMarkerError, ConfigurationError) as error:
        raise WikiError(str(error)) from error

    project_dir = configuration.project_directory
    wiki_subdir = configuration.wiki_directory or "wiki"
    if wiki_subdir.startswith("../"):
        normalized = wiki_subdir.replace("\\", "/").lstrip("../").lstrip("..\\")
        wiki_root = root / normalized
        prefix = Path(normalized)
    else:
        wiki_root = root / project_dir / wiki_subdir
        prefix = Path(project_dir) / wiki_subdir

    if not wiki_root.exists():
        return []

    paths: List[str] = []
    for path in wiki_root.rglob("*.md"):
        if path.is_file():
            rel = path.relative_to(wiki_root)
            paths.append(str(prefix / rel).replace("\\", "/"))
    paths.sort()
    return paths
