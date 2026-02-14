#!/usr/bin/env python3
"""
Bidirectional sync between Kanbus issue files and GitHub Issues.

Ensures every Kanbus issue has a GitHub issue with a clickable link to its
JSON file, and every GitHub issue without such a link gets a new Kanbus
issue and an updated body. Uses the `gh` CLI only.

Run from repository root (where .kanbus.yaml and the project directory live).
Requires: gh installed and authenticated, PYTHONPATH including python/src or
pip install -e python.

:usage: python tools/sync_github_issues.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "python" / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python" / "src"))

from kanbus.config_loader import load_project_configuration  # noqa: E402
from kanbus.ids import IssueIdentifierRequest, generate_issue_identifier  # noqa: E402
from kanbus.issue_files import (  # noqa: E402
    list_issue_identifiers,
    read_issue_from_file,
    write_issue_to_file,
)
from kanbus.models import IssueData  # noqa: E402
from kanbus.project import ProjectMarkerError, load_project_directory  # noqa: E402

KANBUS_SOURCE_PATTERN = re.compile(
    r"<!--\s*kanbus-source:\s*([^\s]+)\s*-->", re.IGNORECASE
)


def _run(
    cmd: list[str], cwd: Path | None = None, capture: bool = True
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        capture_output=capture,
        text=True,
        check=False,
    )


def get_repo_root() -> Path:
    """Resolve the git repository root.

    :return: Repository root path.
    :rtype: Path
    """
    result = _run(["git", "rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return REPO_ROOT
    root = Path(result.stdout.strip())
    return root if root.is_dir() else REPO_ROOT


def get_default_branch() -> str:
    """Return the default branch name.

    :return: Default branch name.
    :rtype: str
    """
    result = _run(
        [
            "gh",
            "repo",
            "view",
            "--json",
            "defaultBranchRef",
            "-q",
            ".defaultBranchRef.name",
        ]
    )
    if result.returncode != 0 or not result.stdout.strip():
        return "main"
    return result.stdout.strip()


def get_github_repository() -> str | None:
    """Return the GitHub repository identifier from the environment.

    :return: GitHub repository identifier or None.
    :rtype: str | None
    """
    return os.environ.get("GITHUB_REPOSITORY")


def build_blob_url(repository: str, branch: str, relative_path: str) -> str:
    """Build a GitHub blob URL for a repository path.

    :param repository: Repository identifier (owner/name).
    :type repository: str
    :param branch: Branch name.
    :type branch: str
    :param relative_path: Path relative to repository root.
    :type relative_path: str
    :return: Blob URL string.
    :rtype: str
    """
    return f"https://github.com/{repository}/blob/{branch}/{relative_path}"


def make_link_block(relative_path: str, blob_url: str) -> str:
    """Build the Kanbus source link block.

    :param relative_path: Relative path to the issue file.
    :type relative_path: str
    :param blob_url: Blob URL for the issue file.
    :type blob_url: str
    :return: Markdown link block with source marker.
    :rtype: str
    """
    return (
        "\n\n---\n**Kanbus source:** "
        f"[{relative_path}]({blob_url})\n"
        f"<!-- kanbus-source: {relative_path} -->"
    )


def parse_kanbus_source_from_body(body: str | None) -> str | None:
    """Parse the Kanbus source marker from an issue body.

    :param body: Issue body text.
    :type body: str | None
    :return: Source path if present.
    :rtype: str | None
    """
    if not body:
        return None
    match = KANBUS_SOURCE_PATTERN.search(body)
    return match.group(1).strip() if match else None


def gh_issue_list(state: str = "open", limit: int = 500) -> list[dict]:
    """List GitHub issues via gh.

    :param state: Issue state filter.
    :type state: str
    :param limit: Maximum number of issues.
    :type limit: int
    :return: Issue summaries.
    :rtype: list[dict]
    """
    result = _run(
        [
            "gh",
            "issue",
            "list",
            "--state",
            state,
            "--limit",
            str(limit),
            "--json",
            "number,title",
        ]
    )
    if result.returncode != 0:
        return []
    return json.loads(result.stdout) if result.stdout.strip() else []


def gh_issue_view(number: int) -> dict | None:
    """Fetch a GitHub issue by number via gh.

    :param number: Issue number.
    :type number: int
    :return: Issue data or None on failure.
    :rtype: dict | None
    """
    result = _run(["gh", "issue", "view", str(number), "--json", "number,title,body"])
    if result.returncode != 0:
        return None
    return json.loads(result.stdout) if result.stdout.strip() else None


def gh_issue_create(title: str, body: str) -> int | None:
    """Create a GitHub issue via gh.

    :param title: Issue title.
    :type title: str
    :param body: Issue body.
    :type body: str
    :return: Issue number on success.
    :rtype: int | None
    """
    result = _run(["gh", "issue", "create", "--title", title, "--body", body])
    if result.returncode != 0:
        return None
    out = (result.stdout or result.stderr or "").strip()
    if not out:
        return None
    try:
        return int(out.rstrip("/").split("/")[-1])
    except (ValueError, IndexError):
        return None


def gh_issue_edit_body(number: int, body: str) -> bool:
    """Update a GitHub issue body via gh.

    :param number: Issue number.
    :type number: int
    :param body: New body text.
    :type body: str
    :return: True if update succeeded.
    :rtype: bool
    """
    result = _run(["gh", "issue", "edit", str(number), "--body", body])
    return result.returncode == 0


def main() -> int:
    """Sync Kanbus issues with GitHub issues.

    :return: Exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(
        description="Sync Kanbus issues with GitHub Issues."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be done without creating or updating issues.",
    )
    args = parser.parse_args()
    dry_run = args.dry_run

    repo_root = get_repo_root()
    repository = get_github_repository()
    if not repository:
        print(
            "GITHUB_REPOSITORY is not set; sync requires a GitHub repo context.",
            file=sys.stderr,
        )
        return 1

    try:
        project_dir = load_project_directory(repo_root)
    except ProjectMarkerError:
        print("No Kanbus project found; skipping sync.", file=sys.stderr)
        return 0

    branch = get_default_branch()
    issues_dir = project_dir / "issues"
    if not issues_dir.is_dir():
        print("No project/issues directory.", file=sys.stderr)
        return 1

    project_dir_name = project_dir.name
    if project_dir != project_dir.resolve():
        project_dir_name = project_dir.resolve().name
    try:
        project_dir_relative = project_dir.relative_to(repo_root)
    except ValueError:
        project_dir_relative = Path(project_dir_name)

    configuration = load_project_configuration(project_dir / "kanbus.yml")
    local_identifiers = list_issue_identifiers(issues_dir)
    existing_gh_issues: list[dict] = []
    source_to_gh_number: dict[str, int] = {}
    gh_numbers_without_source: list[int] = []

    for issue in gh_issue_list():
        num = issue.get("number")
        if num is None:
            continue
        view = gh_issue_view(num)
        if not view:
            continue
        existing_gh_issues.append(view)
        body = view.get("body") or ""
        source = parse_kanbus_source_from_body(body)
        if source:
            source_to_gh_number[source] = num
        else:
            gh_numbers_without_source.append(num)

    def relative_path_for(identifier: str) -> str:
        return str(project_dir_relative / "issues" / f"{identifier}.json").replace(
            "\\", "/"
        )

    created = 0
    updated = 0

    for identifier in sorted(local_identifiers):
        issue_path = issues_dir / f"{identifier}.json"
        if not issue_path.is_file():
            continue
        rel_path = relative_path_for(identifier)
        blob_url = build_blob_url(repository, branch, rel_path)
        link_block = make_link_block(rel_path, blob_url)

        try:
            issue_data = read_issue_from_file(issue_path)
        except Exception as e:
            print(f"Skip {identifier}: failed to read: {e}", file=sys.stderr)
            continue

        gh_num = source_to_gh_number.get(rel_path)
        if gh_num is not None:
            view = gh_issue_view(gh_num)
            if view and link_block.strip() not in (view.get("body") or ""):
                if not dry_run:
                    existing_body = view.get("body") or ""
                    if "<!-- kanbus-source:" in existing_body:
                        new_body = KANBUS_SOURCE_PATTERN.sub(
                            f"<!-- kanbus-source: {rel_path} -->",
                            existing_body,
                            count=1,
                        )
                        if f"]({blob_url})" not in new_body:
                            new_body = new_body.rstrip() + link_block
                    else:
                        new_body = existing_body.rstrip() + link_block
                    if gh_issue_edit_body(gh_num, new_body):
                        updated += 1
                else:
                    updated += 1
            continue

        body = (issue_data.description or "").strip()
        if body:
            body = body + link_block
        else:
            body = link_block.strip()
        if dry_run:
            print(f"[dry-run] Would create GitHub issue: {issue_data.title}")
            created += 1
            continue
        new_num = gh_issue_create(issue_data.title, body)
        if new_num is not None:
            created += 1
            source_to_gh_number[rel_path] = new_num

    for gh_num in gh_numbers_without_source:
        view = gh_issue_view(gh_num)
        if not view:
            continue
        title = (view.get("title") or "Untitled").strip()
        body_text = (view.get("body") or "").strip()

        if dry_run:
            print(
                f"[dry-run] Would create Kanbus issue from GitHub #{gh_num}: {title}"
            )
            created += 1
            continue

        existing_ids = list_issue_identifiers(issues_dir)
        created_at = datetime.now(timezone.utc)
        request = IssueIdentifierRequest(
            title=title,
            existing_ids=existing_ids,
            prefix=configuration.prefix,
            created_at=created_at,
        )
        try:
            result = generate_issue_identifier(request)
        except RuntimeError as e:
            print(f"Skip GH #{gh_num}: {e}", file=sys.stderr)
            continue
        identifier = result.identifier
        rel_path = relative_path_for(identifier)
        blob_url = build_blob_url(repository, branch, rel_path)
        link_block = make_link_block(rel_path, blob_url)

        issue = IssueData(
            id=identifier,
            title=title,
            description=body_text,
            type="task",
            status=configuration.initial_status,
            priority=configuration.default_priority,
            assignee=None,
            creator=None,
            parent=None,
            labels=[],
            dependencies=[],
            comments=[],
            created_at=created_at,
            updated_at=created_at,
            closed_at=None,
            custom={},
        )
        issue_path = issues_dir / f"{identifier}.json"
        write_issue_to_file(issue, issue_path)
        new_body = (body_text or "").rstrip() + link_block
        if gh_issue_edit_body(gh_num, new_body):
            updated += 1
        created += 1

    if dry_run:
        print(
            f"[dry-run] Would create {created} and update {updated} GitHub/Kanbus issues."
        )
    else:
        print(f"Created {created} and updated {updated} issues.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
