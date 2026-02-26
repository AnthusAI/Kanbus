"""
Issue identifier generation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable, Optional, Set

from pydantic import BaseModel, Field


class IssueIdentifierRequest(BaseModel):
    """
    Request to generate a unique issue identifier.

    :param title: The issue title for uniqueness checks.
    :type title: str
    :param existing_ids: Set of existing IDs to avoid collisions.
    :type existing_ids: Set[str]
    :param prefix: ID prefix from configuration.
    :type prefix: str
    """

    title: str = Field(min_length=1)
    existing_ids: Set[str] = Field(default_factory=set)
    prefix: str = Field(default="kanbus", min_length=1)


@dataclass(frozen=True)
class IssueIdentifierResult:
    """Result of issue identifier generation."""

    identifier: str


_TEST_UUID_SEQUENCE: Optional[list[str]] = None


def set_test_uuid_sequence(sequence: Optional[Iterable[str]]) -> None:
    """
    Override UUID generation for deterministic tests.

    :param sequence: Sequence of UUID strings to use, or None to clear.
    :type sequence: Optional[Iterable[str]]
    """
    global _TEST_UUID_SEQUENCE
    _TEST_UUID_SEQUENCE = list(sequence) if sequence is not None else None


def _next_uuid_value() -> str:
    if _TEST_UUID_SEQUENCE:
        return _TEST_UUID_SEQUENCE.pop(0)
    return str(uuid.uuid4())


def format_issue_key(identifier: str, project_context: bool) -> str:
    """
    Produce a display-friendly issue key.

    :param identifier: Full issue identifier (may include project key and UUID).
    :type identifier: str
    :param project_context: Whether the display is within a project context.
    :type project_context: bool
    :return: Formatted key with optional project key and abbreviated hash.
    :rtype: str
    """
    if identifier.isdigit():
        return identifier

    key_part = ""
    remainder = identifier
    if "-" in identifier:
        parts = identifier.split("-", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            key_part, remainder = parts

    base = remainder
    suffix = ""
    if "." in remainder:
        base, suffix = remainder.split(".", 1)
        suffix = f".{suffix}"

    normalized = base.replace("-", "")
    truncated = normalized[:6] if normalized else normalized

    if project_context:
        return f"{truncated}{suffix}"

    if key_part:
        return f"{key_part}-{truncated}{suffix}"

    return f"{truncated}{suffix}"


def matches_issue_identifier(candidate: str, full_id: str) -> bool:
    """
    Check if a candidate identifier matches a full issue identifier.

    Accepts full identifiers, project-context short ids, and abbreviated prefixes.

    :param candidate: User-provided identifier value.
    :type candidate: str
    :param full_id: Full issue identifier from storage.
    :type full_id: str
    :return: True if the candidate matches the full identifier.
    :rtype: bool
    """
    if candidate == full_id:
        return True

    if candidate == format_issue_key(full_id, project_context=False):
        return True

    if candidate == format_issue_key(full_id, project_context=True):
        return True

    if len(candidate) >= len(full_id):
        return False

    return full_id.startswith(candidate)


def generate_issue_identifier(request: IssueIdentifierRequest) -> IssueIdentifierResult:
    """Generate a unique issue ID using a UUID.

    :param request: Validated request containing title and existing IDs.
    :type request: IssueIdentifierRequest
    :return: A unique ID string with format '{prefix}-{uuid}'.
    :rtype: IssueIdentifierResult
    :raises RuntimeError: If unable to generate unique ID after 10 attempts.
    """
    for _ in range(10):
        identifier = f"{request.prefix}-{_next_uuid_value()}"
        if identifier not in request.existing_ids:
            return IssueIdentifierResult(identifier=identifier)

    raise RuntimeError("unable to generate unique id after 10 attempts")


def generate_many_identifiers(title: str, prefix: str, count: int) -> Set[str]:
    """Generate multiple identifiers for uniqueness checks.

    :param title: Base title for hashing.
    :type title: str
    :param prefix: ID prefix.
    :type prefix: str
    :param count: Number of IDs to generate.
    :type count: int
    :return: Set of generated identifiers.
    :rtype: Set[str]
    """
    existing: Set[str] = set()
    for _ in range(count):
        request = IssueIdentifierRequest(
            title=title, prefix=prefix, existing_ids=existing
        )
        result = generate_issue_identifier(request)
        existing.add(result.identifier)
    return existing
