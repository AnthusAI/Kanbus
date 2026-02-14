"""Generate deterministic fixture corpora for discovery benchmarks."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = ROOT / "python" / "src"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from kanbus.models import IssueData


@dataclass(frozen=True)
class FixturePlan:
    """Fixture parameters for benchmark corpora."""

    projects: int
    issues_per_project: int


def _issue_identifier(project_index: int, issue_index: int) -> str:
    """Build a deterministic issue identifier.

    :param project_index: Project index for the fixture.
    :type project_index: int
    :param issue_index: Issue index within the project.
    :type issue_index: int
    :return: Issue identifier string.
    :rtype: str
    """
    return f"kanbus-{project_index:02d}{issue_index:04d}"


def _issue_title(project_index: int, issue_index: int) -> str:
    """Build a deterministic issue title.

    :param project_index: Project index for the fixture.
    :type project_index: int
    :param issue_index: Issue index within the project.
    :type issue_index: int
    :return: Issue title string.
    :rtype: str
    """
    return f"Project {project_index} issue {issue_index}"


def _build_issue(identifier: str, title: str, timestamp: datetime) -> IssueData:
    """Create an IssueData instance for fixture output.

    :param identifier: Issue identifier.
    :type identifier: str
    :param title: Issue title.
    :type title: str
    :param timestamp: Timestamp to assign to created/updated fields.
    :type timestamp: datetime
    :return: Issue data instance.
    :rtype: IssueData
    """
    return IssueData(
        id=identifier,
        title=title,
        description="",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=timestamp,
        updated_at=timestamp,
        closed_at=None,
        custom={},
    )


def _write_issue(issue: IssueData, issues_dir: Path) -> None:
    """Write an issue JSON file to disk.

    :param issue: Issue data to serialize.
    :type issue: IssueData
    :param issues_dir: Directory to write the file into.
    :type issues_dir: Path
    :return: None.
    :rtype: None
    """
    issues_dir.mkdir(parents=True, exist_ok=True)
    issue_path = issues_dir / f"{issue.identifier}.json"
    payload = issue.model_dump(by_alias=True, mode="json")
    issue_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )


def _generate_project_issues(
    project_dir: Path, project_index: int, plan: FixturePlan, timestamp: datetime
) -> None:
    """Generate issues for a single project directory.

    :param project_dir: Project directory to populate.
    :type project_dir: Path
    :param project_index: Project index used in identifiers and titles.
    :type project_index: int
    :param plan: Fixture sizing parameters.
    :type plan: FixturePlan
    :param timestamp: Timestamp to assign to created/updated fields.
    :type timestamp: datetime
    :return: None.
    :rtype: None
    """
    issues_dir = project_dir / "issues"
    for issue_index in range(1, plan.issues_per_project + 1):
        identifier = _issue_identifier(project_index, issue_index)
        title = _issue_title(project_index, issue_index)
        issue = _build_issue(identifier, title, timestamp)
        _write_issue(issue, issues_dir)


def generate_single_project(root: Path, plan: FixturePlan) -> Path:
    """Generate a single-project fixture layout.

    :param root: Root directory for fixture output.
    :type root: Path
    :param plan: Fixture sizing parameters.
    :type plan: FixturePlan
    :return: Path to the created project directory.
    :rtype: Path
    """
    timestamp = datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc)
    project_root = root / "single" / "project"
    _generate_project_issues(project_root, 1, plan, timestamp)
    return project_root


def generate_multi_project(root: Path, plan: FixturePlan) -> Path:
    """Generate a multi-project fixture layout under a monorepo tree.

    :param root: Root directory for fixture output.
    :type root: Path
    :param plan: Fixture sizing parameters.
    :type plan: FixturePlan
    :return: Path to the created repository root.
    :rtype: Path
    """
    timestamp = datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc)
    repo_root = root / "multi"
    for project_index in range(1, plan.projects + 1):
        project_root = (
            repo_root
            / "services"
            / f"service-{project_index:02d}"
            / "project"
        )
        _generate_project_issues(project_root, project_index, plan, timestamp)
    return repo_root


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic fixture corpora for discovery benchmarks."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT / "tools" / "tmp" / "benchmark-discovery-fixtures",
        help="Output root directory for fixtures.",
    )
    parser.add_argument(
        "--projects",
        type=int,
        default=10,
        help="Number of projects for multi-project fixtures.",
    )
    parser.add_argument(
        "--issues-per-project",
        type=int,
        default=200,
        help="Number of issues per project.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    """Generate deterministic fixtures for discovery benchmarks.

    :param argv: Command-line arguments.
    :type argv: Iterable[str]
    :return: Exit code.
    :rtype: int
    """
    args = _parse_args(argv)
    plan = FixturePlan(projects=args.projects, issues_per_project=args.issues_per_project)
    root = args.root
    single_path = generate_single_project(root, plan)
    multi_path = generate_multi_project(root, plan)
    print(
        json.dumps(
            {
                "root": str(root),
                "single_project": str(single_path),
                "multi_project": str(multi_path),
                "projects": plan.projects,
                "issues_per_project": plan.issues_per_project,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
