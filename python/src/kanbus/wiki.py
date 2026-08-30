"""Wiki rendering utilities."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kanbus.ai_summarize import make_ai_summarize
from kanbus.console_snapshot import ConsoleSnapshotError, get_issues_for_root
from kanbus.ids import format_issue_key
from kanbus.models import IssueData
from kanbus.queries import filter_issues

WIKI_STUB_INDEX = "# Wiki\n\nEdit pages under project/wiki/.\n"
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


@dataclass(frozen=True)
class WikiLinkProblem:
    """Broken wiki-internal markdown link reported by lint or render warnings.

    :param source_page: Repository-relative wiki page path.
    :type source_page: str
    :param link_target: Link target as written in markdown.
    :type link_target: str
    :param resolved_path: Wiki-relative resolved target path.
    :type resolved_path: str
    """

    source_page: str
    link_target: str
    resolved_path: str


class WikiError(RuntimeError):
    """Raised when wiki rendering fails."""


@dataclass(frozen=True)
class WikiLocation:
    """Resolved wiki directory location for a repository.

    :param wiki_root: Absolute path to the wiki directory.
    :type wiki_root: Path
    :param list_prefix: Path prefix used in list/search output (e.g. project/wiki).
    :type list_prefix: str
    :param project_directory: Configured project directory name.
    :type project_directory: str
    """

    wiki_root: Path
    list_prefix: str
    project_directory: str


@dataclass(frozen=True)
class WikiContext:
    """Wiki context for rendering.

    :param issues: Issues loaded for rendering.
    :type issues: List[IssueData]
    :param root: Repository root path.
    :type root: Path
    :param reference_warnings: Warnings collected while loading story references.
    :type reference_warnings: List[str]
    """

    issues: List[IssueData]
    root: Path
    reference_warnings: List[str] = field(default_factory=list)

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
        for issue in self.issues:
            if issue.identifier == identifier:
                return _serialize_issue(issue)
        return None

    def references(self, **filters: object) -> List[Dict[str, object]]:
        """List Papyrus story references for wiki templates.

        :return: Matching story references.
        :rtype: List[Dict[str, object]]
        :raises WikiError: If the filter parameters are invalid.
        """
        status = _get_string(filters.get("status"))
        return load_story_references(
            self.root, status=status, warnings_out=self.reference_warnings
        )


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


def load_wiki_location(root: Path) -> WikiLocation:
    """Load wiki directory location from project configuration.

    :param root: Repository root path.
    :type root: Path
    :return: Wiki location metadata.
    :rtype: WikiLocation
    :raises WikiError: If configuration cannot be loaded.
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
        list_prefix = normalized
    else:
        wiki_root = root / project_dir / wiki_subdir
        list_prefix = f"{project_dir}/{wiki_subdir}"
    return WikiLocation(
        wiki_root=wiki_root,
        list_prefix=list_prefix,
        project_directory=project_dir,
    )


def wiki_directory_missing_message(location: WikiLocation) -> str:
    """Build an operator-facing message when the wiki directory is absent.

    :param location: Wiki location metadata.
    :type location: WikiLocation
    :return: Error message with setup instructions.
    :rtype: str
    """
    return (
        f"wiki directory not found at {location.list_prefix}. "
        f"Create it with: mkdir -p {location.list_prefix} "
        f"&& echo '# Wiki' > {location.list_prefix}/index.md\n"
        "Or run: kbs wiki init"
    )


def resolve_wiki_page_path(root: Path, page_argument: str) -> Path:
    """Resolve a wiki page argument to a repository-relative path.

    Canonical form: ``project/wiki/<relative-path>.md``. Also accepts wiki-relative
    paths such as ``index``, ``index.md``, and ``concepts/foo.md``.

    :param root: Repository root path.
    :type root: Path
    :param page_argument: User-provided page path.
    :type page_argument: str
    :return: Repository-relative path to the wiki page.
    :rtype: Path
    :raises WikiError: If the wiki directory or page does not exist.
    """
    location = load_wiki_location(root)
    if not location.wiki_root.exists():
        raise WikiError(wiki_directory_missing_message(location))

    normalized_argument = page_argument.replace("\\", "/").strip()
    if not normalized_argument:
        raise WikiError("wiki page not found")

    candidate = Path(normalized_argument)
    if candidate.is_absolute():
        try:
            relative = candidate.resolve().relative_to(root.resolve())
        except ValueError as error:
            raise WikiError(f"wiki page not found: {normalized_argument}") from error
        absolute_page = root / relative
        if not absolute_page.exists():
            raise WikiError(f"wiki page not found: {relative.as_posix()}")
        return relative

    prefixed = normalized_argument
    if prefixed.startswith("./"):
        prefixed = prefixed[2:]
    list_prefix = location.list_prefix.replace("\\", "/")
    if prefixed == list_prefix or prefixed.startswith(f"{list_prefix}/"):
        relative = Path(prefixed)
    else:
        wiki_relative = prefixed
        if not wiki_relative.endswith(".md"):
            wiki_relative = f"{wiki_relative}.md"
        relative = Path(list_prefix) / wiki_relative

    absolute_page = root / relative
    if not absolute_page.exists():
        raise WikiError(f"wiki page not found: {relative.as_posix()}")
    return relative


def show_wiki_page(root: Path, page_argument: str) -> str:
    """Return raw wiki page source without template rendering.

    :param root: Repository root path.
    :type root: Path
    :param page_argument: User-provided page path.
    :type page_argument: str
    :return: Raw markdown source.
    :rtype: str
    :raises WikiError: If the page cannot be resolved or read.
    """
    resolved_page = resolve_wiki_page_path(root, page_argument)
    full_page = root / resolved_page
    return full_page.read_text(encoding="utf-8")


def lint_wiki(root: Path) -> List[WikiLinkProblem]:
    """Validate wiki-internal markdown links across the wiki tree.

    :param root: Repository root path.
    :type root: Path
    :return: Broken link problems, empty when the wiki is valid.
    :rtype: List[WikiLinkProblem]
    :raises WikiError: If configuration cannot be loaded.
    """
    location = load_wiki_location(root)
    if not location.wiki_root.exists():
        raise WikiError(wiki_directory_missing_message(location))

    problems: List[WikiLinkProblem] = []
    for page_path in sorted(location.wiki_root.rglob("*.md")):
        if not page_path.is_file():
            continue
        wiki_relative = page_path.relative_to(location.wiki_root).as_posix()
        listed_path = f"{location.list_prefix}/{wiki_relative}"
        content = page_path.read_text(encoding="utf-8")
        problems.extend(
            _find_broken_wiki_links(location, wiki_relative, listed_path, content)
        )
    problems.sort(key=lambda problem: (problem.source_page, problem.resolved_path))
    return problems


def check_wiki_page_links(root: Path, page_argument: str) -> List[WikiLinkProblem]:
    """Validate wiki-internal markdown links in a single page.

    :param root: Repository root path.
    :type root: Path
    :param page_argument: User-provided page path.
    :type page_argument: str
    :return: Broken link problems for the page.
    :rtype: List[WikiLinkProblem]
    :raises WikiError: If the page cannot be resolved or read.
    """
    resolved_page = resolve_wiki_page_path(root, page_argument)
    location = load_wiki_location(root)
    wiki_relative = (root / resolved_page).relative_to(location.wiki_root).as_posix()
    listed_path = resolved_page.as_posix()
    content = (root / resolved_page).read_text(encoding="utf-8")
    return _find_broken_wiki_links(location, wiki_relative, listed_path, content)


def format_wiki_link_problem(problem: WikiLinkProblem, *, warning: bool) -> str:
    """Format a broken wiki link for operator output.

    :param problem: Broken link details.
    :type problem: WikiLinkProblem
    :param warning: Whether to prefix the line as a warning.
    :type warning: bool
    :return: Formatted message.
    :rtype: str
    """
    message = (
        f"{problem.source_page}: broken wiki link "
        f'"{problem.link_target}" ({problem.resolved_path} not found)'
    )
    if warning:
        return f"warning: {message}"
    return message


def init_wiki(root: Path) -> str:
    """Create the wiki directory and a stub index page.

    :param root: Repository root path.
    :type root: Path
    :return: Repository-relative path to the created index page.
    :rtype: str
    :raises WikiError: If configuration cannot be loaded.
    """
    from kanbus.file_io import refresh_project_wiki_agents_file

    location = load_wiki_location(root)
    location.wiki_root.mkdir(parents=True, exist_ok=True)
    index_path = location.wiki_root / "index.md"
    if not index_path.exists():
        index_path.write_text(WIKI_STUB_INDEX, encoding="utf-8")
    refresh_project_wiki_agents_file(root / location.project_directory)
    return f"{location.list_prefix}/index.md"


def search_wiki_pages(root: Path, query: str) -> List[str]:
    """Search wiki pages by path, title, and body content.

    :param root: Repository root path.
    :type root: Path
    :param query: Case-insensitive search string.
    :type query: str
    :return: Matching wiki page paths relative to repository root.
    :rtype: List[str]
    :raises WikiError: If configuration cannot be loaded.
    """
    location = load_wiki_location(root)
    if not location.wiki_root.exists():
        return []

    needle = query.casefold()
    if not needle:
        return list_wiki_pages(root)

    matches: List[str] = []
    for path in location.wiki_root.rglob("*.md"):
        if not path.is_file():
            continue
        relative = path.relative_to(location.wiki_root)
        listed_path = f"{location.list_prefix}/{relative.as_posix()}"
        body = path.read_text(encoding="utf-8")
        title = _extract_wiki_title(body) or path.stem
        haystack = f"{listed_path}\n{title}\n{body}".casefold()
        if needle in haystack:
            matches.append(listed_path)
    matches.sort()
    return matches


def load_story_references(
    root: Path,
    status: str | None = None,
    warnings_out: List[str] | None = None,
) -> List[Dict[str, object]]:
    """Load Papyrus story references from stories/*/references/*.json.

    :param root: Repository root path.
    :type root: Path
    :param status: Optional status filter (for example accepted or pending).
    :type status: str | None
    :param warnings_out: Optional list to append skip warnings to.
    :type warnings_out: List[str] | None
    :return: Story reference records.
    :rtype: List[Dict[str, object]]
    """
    stories_root = root / "stories"
    if not stories_root.exists():
        return []

    references: List[Dict[str, object]] = []
    for story_dir in sorted(stories_root.iterdir()):
        if not story_dir.is_dir():
            continue
        references_dir = story_dir / "references"
        if not references_dir.exists():
            continue
        story_id = story_dir.name
        for reference_path in sorted(references_dir.glob("*.json")):
            try:
                raw = reference_path.read_text(encoding="utf-8")
            except OSError as error:
                _append_story_reference_warning(
                    warnings_out,
                    f"warning: skipping unreadable story reference {reference_path}: {error}",
                )
                continue
            if not raw.strip():
                _append_story_reference_warning(
                    warnings_out,
                    f"warning: skipping empty story reference {reference_path}",
                )
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as error:
                _append_story_reference_warning(
                    warnings_out,
                    "warning: skipping invalid story reference JSON in "
                    f"{reference_path}: {error}",
                )
                continue
            if not isinstance(payload, dict):
                _append_story_reference_warning(
                    warnings_out,
                    f"warning: skipping non-object story reference in {reference_path}",
                )
                continue
            record = dict(payload)
            record.setdefault("story_id", story_id)
            if status is not None and record.get("status") != status:
                continue
            references.append(record)
    references.sort(
        key=lambda item: (str(item.get("story_id", "")), str(item.get("id", "")))
    )
    return references


def render_wiki_page(
    request: WikiRenderRequest,
    reference_warnings: List[str] | None = None,
) -> str:
    """Render a wiki page using the live issue index.

    :param request: Render request with root and page path.
    :type request: WikiRenderRequest
    :param reference_warnings: Optional list to append story-reference skip warnings to.
    :type reference_warnings: List[str] | None
    :return: Rendered wiki content.
    :rtype: str
    :raises WikiError: If rendering fails.
    """
    resolved_page = resolve_wiki_page_path(request.root, str(request.page_path))
    full_page = request.root / resolved_page
    page_template = full_page.read_text(encoding="utf-8")

    try:
        issues = get_issues_for_root(request.root)
    except ConsoleSnapshotError as error:
        raise WikiError(str(error)) from error

    ai_config, project_dir = _load_ai_config_and_project_dir(request.root)
    wiki_render_cache_dir = (
        request.root / project_dir / ".cache" / "wiki_render" if project_dir else None
    )
    cache_key: str | None = None
    if wiki_render_cache_dir is not None:
        cache_key = _wiki_render_cache_key(
            full_page, list(issues), request.root, page_template
        )
        cached = _wiki_render_read_cache(wiki_render_cache_dir, cache_key)
        if cached is not None:
            _wiki_render_log_cache_hit(wiki_render_cache_dir)
            return cached
    issues_by_id = {issue.identifier: _serialize_issue(issue) for issue in issues}
    ai_cache_dir = request.root / project_dir / ".cache" if project_dir else None
    ai_summarize_fn = make_ai_summarize(issues_by_id, ai_config, ai_cache_dir)

    context = WikiContext(issues=list(issues), root=request.root)
    environment = Environment(
        loader=FileSystemLoader(str(full_page.parent)),
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
            "references": context.references,
            "ai_summarize": ai_summarize_fn,
        }
    )
    try:
        rendered = environment.get_template(full_page.name).render()
    except WikiError:
        raise
    except Exception as error:
        raise WikiError(str(error)) from error

    if reference_warnings is not None:
        reference_warnings.extend(context.reference_warnings)

    if wiki_render_cache_dir is not None and cache_key is not None:
        _wiki_render_write_cache(wiki_render_cache_dir, cache_key, rendered)
    return rendered


def _find_broken_wiki_links(
    location: WikiLocation,
    wiki_relative: str,
    listed_path: str,
    content: str,
) -> List[WikiLinkProblem]:
    problems: List[WikiLinkProblem] = []
    code_excluded_ranges = _markdown_code_excluded_ranges(content)
    for match in MARKDOWN_LINK_PATTERN.finditer(content):
        if _position_in_excluded_ranges(match.start(), code_excluded_ranges):
            continue
        link_target = match.group(1).strip()
        if not _is_wiki_internal_md_link(link_target):
            continue
        resolved_path = _resolve_wiki_internal_link(wiki_relative, link_target)
        resolved_absolute = location.wiki_root / resolved_path
        try:
            resolved_absolute.resolve().relative_to(location.wiki_root.resolve())
        except ValueError:
            problems.append(
                WikiLinkProblem(
                    source_page=listed_path,
                    link_target=link_target,
                    resolved_path=resolved_path,
                )
            )
            continue
        if not resolved_absolute.exists():
            problems.append(
                WikiLinkProblem(
                    source_page=listed_path,
                    link_target=link_target,
                    resolved_path=resolved_path,
                )
            )
    return problems


def _markdown_code_excluded_ranges(content: str) -> List[tuple[int, int]]:
    excluded_ranges: List[tuple[int, int]] = []
    index = 0
    content_length = len(content)
    while index < content_length:
        if content.startswith("```", index):
            range_start = index
            index += 3
            while index < content_length and content[index] != "\n":
                index += 1
            if index < content_length:
                index += 1
            while index < content_length:
                if content.startswith("```", index):
                    index += 3
                    if index < content_length and content[index] == "\n":
                        index += 1
                    excluded_ranges.append((range_start, index))
                    break
                index += 1
            else:
                excluded_ranges.append((range_start, content_length))
            continue
        if content.startswith("``", index) and not content.startswith("```", index):
            range_start = index
            index += 2
            while index < content_length:
                if content.startswith("``", index):
                    index += 2
                    excluded_ranges.append((range_start, index))
                    break
                index += 1
            else:
                excluded_ranges.append((range_start, content_length))
            continue
        if content[index] == "`":
            range_start = index
            index += 1
            while index < content_length and content[index] not in {"`", "\n"}:
                index += 1
            if index < content_length and content[index] == "`":
                index += 1
                excluded_ranges.append((range_start, index))
            continue
        index += 1
    return excluded_ranges


def _position_in_excluded_ranges(
    position: int, excluded_ranges: List[tuple[int, int]]
) -> bool:
    return any(
        range_start <= position < range_end
        for range_start, range_end in excluded_ranges
    )


def _is_wiki_internal_md_link(link_target: str) -> bool:
    path_part = link_target.split("#", 1)[0].strip()
    if not path_part or path_part.startswith("#"):
        return False
    lowered = path_part.lower()
    if lowered.startswith(("http://", "https://", "mailto:", "//")):
        return False
    if "{{" in path_part or "}}" in path_part:
        return False
    return path_part.endswith(".md")


def _resolve_wiki_internal_link(source_wiki_relative: str, link_target: str) -> str:
    path_part = link_target.split("#", 1)[0].strip()
    source_path = Path(source_wiki_relative)
    resolved = (source_path.parent / path_part).as_posix()
    normalized_parts: List[str] = []
    for part in Path(resolved).parts:
        if part == "..":
            if normalized_parts:
                normalized_parts.pop()
            continue
        if part == ".":
            continue
        normalized_parts.append(part)
    return "/".join(normalized_parts)


def _wiki_render_cache_key(
    page_path: Path,
    issues: List[IssueData],
    root: Path,
    page_template: str,
) -> str:
    page_mtime = str(page_path.stat().st_mtime) if page_path.exists() else ""
    issue_part = "|".join(
        f"{issue.identifier}:{issue.updated_at.isoformat()}"
        for issue in sorted(issues, key=lambda item: item.identifier)
    )
    reference_part = ""
    if _page_uses_references(page_template):
        reference_part = _story_references_cache_part(root)
    raw = f"{page_path}|{page_mtime}|{issue_part}|{reference_part}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _page_uses_references(page_template: str) -> bool:
    return "references(" in page_template


def _story_references_cache_part(root: Path) -> str:
    stories_root = root / "stories"
    if not stories_root.exists():
        return ""

    parts: List[str] = []
    for story_dir in sorted(stories_root.iterdir()):
        if not story_dir.is_dir():
            continue
        references_dir = story_dir / "references"
        if not references_dir.exists():
            continue
        for reference_path in sorted(references_dir.glob("*.json")):
            try:
                mtime = str(reference_path.stat().st_mtime)
            except OSError:
                mtime = ""
            relative = reference_path.relative_to(root).as_posix()
            parts.append(f"{relative}:{mtime}")
    return "|".join(parts)


def _append_story_reference_warning(
    warnings_out: List[str] | None, message: str
) -> None:
    if warnings_out is not None:
        warnings_out.append(message)


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
    payload = issue.model_dump(by_alias=True, mode="json")
    short_key = format_issue_key(issue.identifier, project_context=True)
    payload["key"] = short_key
    payload["short_id"] = short_key
    return payload


def _extract_wiki_title(content: str) -> str | None:
    for line in content.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1)
    return None


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
    context = WikiContext(issues=issues, root=Path.cwd())
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
            "references": context.references,
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
    location = load_wiki_location(root)
    if not location.wiki_root.exists():
        return []

    paths: List[str] = []
    for path in location.wiki_root.rglob("*.md"):
        if path.is_file():
            rel = path.relative_to(location.wiki_root)
            paths.append(f"{location.list_prefix}/{rel.as_posix()}")
    paths.sort()
    return paths
