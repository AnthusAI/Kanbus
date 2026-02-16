"""Beads compatibility write helpers."""

from __future__ import annotations

import json
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from kanbus.models import DependencyLink, IssueData
from kanbus.users import get_current_user


class BeadsWriteError(RuntimeError):
    """Raised when writing Beads JSONL issues fails."""


class BeadsDeleteError(RuntimeError):
    """Raised when deleting Beads issues fails."""


_TEST_BEADS_SLUG_SEQUENCE: Optional[list[str]] = None


def set_test_beads_slug_sequence(sequence: Optional[Iterable[str]]) -> None:
    """
    Override Beads slug generation for deterministic tests.

    :param sequence: Sequence of slug strings to use, or None to clear.
    :type sequence: Optional[Iterable[str]]
    """
    global _TEST_BEADS_SLUG_SEQUENCE
    _TEST_BEADS_SLUG_SEQUENCE = list(sequence) if sequence is not None else None


def _next_beads_slug() -> Optional[str]:
    if _TEST_BEADS_SLUG_SEQUENCE:
        return _TEST_BEADS_SLUG_SEQUENCE.pop(0)
    return None


def create_beads_issue(
    root: Path,
    title: str,
    issue_type: Optional[str],
    priority: Optional[int],
    assignee: Optional[str],
    parent: Optional[str],
    description: Optional[str],
) -> IssueData:
    """Create a Beads-compatible issue in .beads/issues.jsonl.

    :param root: Repository root path.
    :type root: Path
    :param title: Issue title.
    :type title: str
    :param issue_type: Issue type override.
    :type issue_type: Optional[str]
    :param priority: Priority override.
    :type priority: Optional[int]
    :param assignee: Assignee identifier.
    :type assignee: Optional[str]
    :param parent: Parent issue identifier.
    :type parent: Optional[str]
    :param description: Issue description.
    :type description: Optional[str]
    :return: Created issue data.
    :rtype: IssueData
    :raises BeadsWriteError: If Beads data cannot be read or written.
    """
    beads_dir = root / ".beads"
    if not beads_dir.exists():
        raise BeadsWriteError("no .beads directory")
    issues_path = beads_dir / "issues.jsonl"
    if not issues_path.exists():
        raise BeadsWriteError("no issues.jsonl")

    records = _load_beads_records(issues_path)
    if not records:
        raise BeadsWriteError("no beads issues available")

    existing_ids = {record["id"] for record in records if "id" in record}
    prefix = _derive_prefix(existing_ids)
    identifier = _generate_identifier(existing_ids, prefix, parent)

    if parent is not None and parent not in existing_ids:
        raise BeadsWriteError("not found")

    created_at = datetime.now(timezone.utc)
    created_at_text = created_at.isoformat()
    created_by = get_current_user()
    resolved_type = issue_type or "task"
    resolved_priority = priority if priority is not None else 2
    resolved_description = description or ""
    dependencies: List[Dict[str, object]] = []
    dependency_links: List[DependencyLink] = []
    if parent is not None:
        dependency = {
            "issue_id": identifier,
            "depends_on_id": parent,
            "type": "parent-child",
            "created_at": created_at_text,
            "created_by": created_by,
        }
        dependencies.append(dependency)
        dependency_links.append(
            DependencyLink(target=parent, **{"type": "parent-child"})
        )

    record: Dict[str, object] = {
        "id": identifier,
        "title": title,
        "description": resolved_description,
        "status": "open",
        "priority": resolved_priority,
        "issue_type": resolved_type,
        "owner": created_by,
        "created_at": created_at_text,
        "created_by": created_by,
        "updated_at": created_at_text,
    }
    if assignee is not None:
        record["assignee"] = assignee
    if dependencies:
        record["dependencies"] = dependencies
    record["comments"] = []

    _append_beads_record(issues_path, record)

    return IssueData(
        id=identifier,
        title=title,
        description=resolved_description,
        type=resolved_type,
        status="open",
        priority=resolved_priority,
        assignee=assignee,
        creator=created_by,
        parent=parent,
        labels=[],
        dependencies=dependency_links,
        comments=[],
        created_at=created_at,
        updated_at=created_at,
        closed_at=None,
        custom={},
    )


def update_beads_issue(
    root: Path,
    identifier: str,
    status: Optional[str] = None,
) -> IssueData:
    """Update a Beads-compatible issue in .beads/issues.jsonl.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier to update.
    :type identifier: str
    :param status: New status value.
    :type status: Optional[str]
    :return: Updated issue.
    :rtype: IssueData
    :raises BeadsWriteError: If the issue cannot be found or written.
    """
    beads_dir = root / ".beads"
    if not beads_dir.exists():
        raise BeadsWriteError("no .beads directory")
    issues_path = beads_dir / "issues.jsonl"
    if not issues_path.exists():
        raise BeadsWriteError("no issues.jsonl")
    records = _load_beads_records(issues_path)
    updated = False
    for record in records:
        if record.get("id") != identifier:
            continue
        if status is not None:
            record["status"] = status
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = True
        break
    if not updated:
        raise BeadsWriteError("not found")

    with issues_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")

    # Return a minimal IssueData for display
    return IssueData(
        id=identifier,
        title=next(
            rec.get("title", "") for rec in records if rec.get("id") == identifier
        ),
        description=next(
            rec.get("description", "") for rec in records if rec.get("id") == identifier
        ),
        type=next(
            rec.get("issue_type", "") for rec in records if rec.get("id") == identifier
        ),
        status=next(
            rec.get("status", "") for rec in records if rec.get("id") == identifier
        ),
        priority=next(
            rec.get("priority", 0) for rec in records if rec.get("id") == identifier
        ),
        assignee=next(
            rec.get("assignee") for rec in records if rec.get("id") == identifier
        ),
        creator=next(
            rec.get("created_by") for rec in records if rec.get("id") == identifier
        ),
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        closed_at=None,
        custom={},
    )


def add_beads_comment(root: Path, identifier: str, author: str, text: str) -> None:
    """Add a comment to a Beads issue in .beads/issues.jsonl.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :param author: Comment author.
    :type author: str
    :param text: Comment text.
    :type text: str
    :raises BeadsWriteError: If the issue cannot be found or written.
    """
    beads_dir = root / ".beads"
    if not beads_dir.exists():
        raise BeadsWriteError("no .beads directory")
    issues_path = beads_dir / "issues.jsonl"
    if not issues_path.exists():
        raise BeadsWriteError("no issues.jsonl")

    records = _load_beads_records(issues_path)
    found = False
    for record in records:
        if record.get("id") == identifier:
            found = True
            # Add comment to comments array
            if "comments" not in record:
                record["comments"] = []
            comment_id = len(record["comments"]) + 1
            comment = {
                "id": comment_id,
                "issue_id": identifier,
                "author": author,
                "text": text,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            record["comments"].append(comment)
            # Update updated_at timestamp
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            break

    if not found:
        raise BeadsWriteError("not found")

    # Write back all records
    with issues_path.open("w", encoding="utf-8") as handle:
        for record in records:
            json.dump(record, handle, separators=(",", ":"))
            handle.write("\n")


def delete_beads_issue(root: Path, identifier: str) -> None:
    """Delete a Beads-compatible issue from .beads/issues.jsonl.

    :param root: Repository root path.
    :type root: Path
    :param identifier: Issue identifier to delete.
    :type identifier: str
    :raises BeadsDeleteError: If the issue cannot be found or written.
    """
    beads_dir = root / ".beads"
    if not beads_dir.exists():
        raise BeadsDeleteError("no .beads directory")
    issues_path = beads_dir / "issues.jsonl"
    if not issues_path.exists():
        raise BeadsDeleteError("no issues.jsonl")

    records = _load_beads_records(issues_path)
    remaining = [record for record in records if record.get("id") != identifier]
    if len(remaining) == len(records):
        raise BeadsDeleteError("not found")

    with issues_path.open("w", encoding="utf-8") as handle:
        for record in remaining:
            handle.write(json.dumps(record) + "\n")


def _load_beads_records(issues_path: Path) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for line in issues_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def _append_beads_record(issues_path: Path, record: Dict[str, object]) -> None:
    with issues_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _derive_prefix(existing_ids: Set[str]) -> str:
    for identifier in existing_ids:
        if "-" in identifier:
            return identifier.split("-", 1)[0]
    raise BeadsWriteError("invalid beads id")


def _generate_identifier(
    existing_ids: Set[str], prefix: str, parent: Optional[str]
) -> str:
    if parent is not None:
        suffix = _next_child_suffix(existing_ids, parent)
        return f"{parent}.{suffix}"
    for _ in range(10):
        slug = _generate_slug()
        identifier = f"{prefix}-{slug}"
        if identifier not in existing_ids:
            return identifier
    raise BeadsWriteError("unable to generate unique id after 10 attempts")


def _next_child_suffix(existing_ids: Set[str], parent: str) -> int:
    max_suffix = 0
    prefix = f"{parent}."
    for identifier in existing_ids:
        if not identifier.startswith(prefix):
            continue
        suffix_text = identifier[len(prefix) :]
        if suffix_text.isdigit():
            max_suffix = max(max_suffix, int(suffix_text))
    return max_suffix + 1


def _generate_slug() -> str:
    overridden = _next_beads_slug()
    if overridden is not None:
        return overridden
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(3))
