"""Wiki rendering utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

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
    if not request.page_path.exists():
        raise WikiError("wiki page not found")

    try:
        issues = get_issues_for_root(request.root)
    except ConsoleSnapshotError as error:
        raise WikiError(str(error)) from error

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
        }
    )
    try:
        return environment.get_template(request.page_path.name).render()
    except WikiError:
        raise
    except Exception as error:
        raise WikiError(str(error)) from error


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
