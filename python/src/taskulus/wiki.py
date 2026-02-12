"""Wiki rendering utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment

from taskulus.issue_listing import IssueListingError, list_issues
from taskulus.models import IssueData
from taskulus.queries import filter_issues


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
        issues = list_issues(request.root)
    except IssueListingError as error:
        raise WikiError(str(error)) from error

    context = WikiContext(issues=list(issues))
    template = request.page_path.read_text(encoding="utf-8")
    environment = Environment(autoescape=False)
    environment.globals.update(
        {
            "query": context.query,
            "count": context.count,
        }
    )
    try:
        return environment.from_string(template).render()
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
